"""워크포워드 백테스트와 보정(폭 배율) 조정.

- 2019-01-01부터 3일 간격으로 '그날까지의 데이터만' 써서 예측을 만들고,
  7/14/30일 뒤 실제 종가가 예측 분포의 어디에 떨어졌는지(PIT)를 기록한다.
- 50/80/95% 구간 안에 실제로 들어간 비율 = 커버리지(보정도). 잘 맞으면 각각 50/80/95%에 가깝다.
- 커버리지가 목표에서 3%p 넘게 벗어나면 '대칭 분위수 재보정'을 한다:
  목표 c% 구간을 그릴 때, 과거에 실제로 c% 가 들어갔던 원래 모델의 구간을 대신 쓴다.
  (단순 폭 배율은 50% 구간과 95% 구간 오차 방향이 반대일 때 둘을 동시에 못 고쳐서 이 방식을 택함.)
  앞쪽 절반 기간으로 맞추고 뒤쪽 절반으로 검증해 표본 외에서도 나아질 때만 적용하며,
  실서비스에는 전체 기간으로 다시 맞춘 지도를 쓴다. 중앙값은 건드리지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .models import analog, ensemble, montecarlo
from .models.common import HORIZONS, QUANTILES

LEVELS = (0.5, 0.8, 0.95)
RECAL_KNOTS = np.r_[np.arange(0, 0.951, 0.05), 0.975, 0.99, 1.0]
TOL = 0.03
MODELS = ("montecarlo", "analog", "ensemble")


def run(daily: pd.DataFrame, start: str = "2019-01-01", step: int = 3, n_paths: int = 1500, seed: int = 7) -> dict:
    """daily: 완성된 일봉 전체. 반환: 모델·기간별 표본(정렬된 예측 샘플, 실제값)."""
    rng = np.random.default_rng(seed)
    F = analog.features(daily)
    Fm, sig = F[analog.FEATURES].to_numpy(), F["sig"].to_numpy()
    fwd = analog.forward_paths(daily)
    lc = np.log(daily["close"].to_numpy())
    last = len(daily) - 1
    t0 = int(np.searchsorted(daily.index, pd.Timestamp(start, tz="UTC")))
    rec = {m: {h: {"S": [], "y": [], "t": []} for h in HORIZONS} for m in MODELS}
    for t in range(max(t0, 400), last - min(HORIZONS) + 1, step):
        pm = montecarlo.simulate(montecarlo.prepare(daily.iloc[: t + 1]), n_paths, seed=int(rng.integers(1 << 31)))
        try:
            pa, _, _ = analog.search(Fm, sig, t, fwd, rng, n_paths)
        except ValueError:
            continue
        pe = ensemble.mix(pm, pa, n=n_paths, seed=int(rng.integers(1 << 31)))
        for name, p in (("montecarlo", pm), ("analog", pa), ("ensemble", pe)):
            for h in HORIZONS:
                if t + h > last:
                    continue
                r = rec[name][h]
                r["S"].append(np.sort(p.close[:, h - 1]).astype(np.float32))
                r["y"].append(lc[t + h] - lc[t])
                r["t"].append(t)
    out = {}
    for name in MODELS:
        out[name] = {}
        for h in HORIZONS:
            r = rec[name][h]
            out[name][h] = {"S": np.array(r["S"]), "y": np.array(r["y"]), "t": np.array(r["t"])}
    out["_dates"] = daily.index
    return out


def pit(S: np.ndarray, y: np.ndarray) -> np.ndarray:
    """실제값 y 가 예측 분포의 어디(0~1)에 떨어졌는지."""
    return (S <= y[:, None]).mean(1)


def fold(p: np.ndarray) -> np.ndarray:
    """중앙 기준 거리: 0 = 중앙값, 1 = 분포의 맨 끝. '몇 % 구간의 경계에 걸렸나'와 같다."""
    return np.abs(2 * p - 1)


def coverage_from_level(a: np.ndarray) -> dict:
    """a: 실제값이 걸린 중앙구간 수준(0~1). a <= 0.8 이면 80% 구간 안."""
    return {f"cov{int(lv * 100)}": round(float((a <= lv).mean()), 3) for lv in LEVELS}


def cov_loss(a: np.ndarray) -> float:
    c = coverage_from_level(a)
    return sum((c[f"cov{int(lv * 100)}"] - lv) ** 2 for lv in LEVELS)


def fit_recal(a: np.ndarray) -> dict:
    """대칭 분위수 재보정 지도. c(목표 구간) → c_raw(원래 모델에서 써야 할 구간).

    c_raw = 과거에 실제값이 걸린 구간 수준 a 의 c-분위수. 즉 '실제로 c 비율이 들어간 원래 구간'.
    중앙값은 움직이지 않는다(과거 추세를 미래에 주입하지 않음).
    """
    c = RECAL_KNOTS
    c_raw = np.quantile(a, c)
    c_raw[0], c_raw[-1] = 0.0, 1.0
    c_raw = np.maximum.accumulate(c_raw)
    return {"c": [round(float(x), 3) for x in c], "c_raw": [round(float(x), 4) for x in c_raw]}


def apply_recal_level(a: np.ndarray, recal: dict | None) -> np.ndarray:
    """원래 수준 a → 재보정 후 수준. (fit_recal 의 역함수)"""
    if not recal:
        return a
    return np.interp(a, recal["c_raw"], recal["c"])


def pinball(S: np.ndarray, y: np.ndarray, recal: dict | None = None) -> float:
    """분위수 손실 평균(로그수익률 단위, 작을수록 좋음)."""
    qs = np.array(list(QUANTILES.values()))
    if recal:
        c = np.abs(2 * qs - 1)
        c_raw = np.interp(c, recal["c"], recal["c_raw"])
        lv = 0.5 + np.sign(qs - 0.5) * c_raw / 2
    else:
        lv = qs
    Q = np.quantile(S, lv, axis=1).T
    e = y[:, None] - Q
    return float(np.mean(np.maximum(qs * e, (qs - 1) * e)))


def interval_map(recal: dict | None) -> dict:
    """사람이 읽는 요약: 목표 50/80/95% 구간을 원래 모델의 몇 % 구간으로 그리는지."""
    if not recal:
        return {str(int(lv * 100)): lv for lv in LEVELS}
    return {str(int(lv * 100)): round(float(np.interp(lv, recal["c"], recal["c_raw"])), 3) for lv in LEVELS}


def calibrate(bt: dict) -> dict:
    dates = bt["_dates"]
    result = {}
    for name in MODELS:
        result[name] = {}
        for h in HORIZONS:
            S, y, t = bt[name][h]["S"], bt[name][h]["y"], bt[name][h]["t"]
            n = len(y)
            half = n // 2
            p = pit(S, y)
            a = fold(p)
            rc_train = fit_recal(a[:half])
            rc_full = fit_recal(a)
            raw = coverage_from_level(a)
            test_raw = coverage_from_level(a[half:])
            a_test_adj = apply_recal_level(a[half:], rc_train)
            test_adj = coverage_from_level(a_test_adj)
            worst = max(abs(raw[f"cov{int(lv * 100)}"] - lv) for lv in LEVELS)
            improves = cov_loss(a_test_adj) < cov_loss(a[half:])
            adjusted = bool(worst > TOL and improves)
            rc_use = rc_full if adjusted else None
            if not adjusted:
                reason = "보정 양호(목표와 차이 3%p 이하)" if worst <= TOL else "조정해도 표본 외 성능이 나아지지 않아 원래대로 사용"
            else:
                reason = f"목표와 최대 {worst * 100:.1f}%p 차이 → 구간 재보정 적용"
            result[name][str(h)] = {
                "n": int(n),
                "period": [dates[t[0]].strftime("%Y-%m-%d"), dates[t[-1]].strftime("%Y-%m-%d")],
                "raw": raw,
                "adjusted": adjusted,
                "reason_ko": reason,
                "after": coverage_from_level(apply_recal_level(a, rc_use)),
                "interval_map": interval_map(rc_use),
                "recal": rc_use,
                "test_half": {"from": dates[t[half]].strftime("%Y-%m-%d"), "raw": test_raw, "adjusted": test_adj},
                "pinball_raw": round(pinball(S, y), 5),
                "pinball_after": round(pinball(S, y, rc_use), 5),
                "pit_hist": [round(float(x), 3) for x in np.histogram(p, bins=10, range=(0, 1))[0] / n],
                "share_below_median": round(float((p < 0.5).mean()), 3),
            }
    return result
