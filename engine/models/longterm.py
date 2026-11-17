"""장기(최대 5년) 전망: 국면 보존 블록 부트스트랩 + 경로 모양별 시나리오 묶음.

방법
1) 일간 로그수익률(평균 0으로 맞춤)을 90일 블록째로 복원추출해 5년(1826일) 경로를 만든다.
   긴 블록이라 과거의 강세장·약세장·고변동 국면 같은 '덩어리'가 그대로 들어간다.
2) 전체 이력의 변동성 수준을 최근 2년 수준으로 맞춘다(초기 2017~18년의 극단적 변동성이 과대 반영되지 않게).
3) 추세(드리프트)는 세 가지 가정으로 각각 계산한다(경로의 '흔들림'은 같고 방향성만 다름):
   - shrunk(기본): 최근일수록 크게 반영한 과거 평균(반감기 3년)의 절반
   - zero: 추세 0 (중앙값 ≈ 현재가)
   - historical: 전체 이력의 평균 추세 그대로(2017~ 초기 급성장기 포함 → 낙관적)
4) 시나리오: 5년 경로를 3개월 간격 20개 지점의 모양으로 k-means(5개 묶음) → 가장 큰 묶음 2개.
   각 묶음의 비율 = 시나리오 확률, 묶음 중심에 가장 가까운 실제 시뮬레이션 경로 1개를 가상 캔들로 그린다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..sources.base import bar_start
from .common import QUANTILES

DAYS = 1826
BLOCK = 90
RECENT = 730
LONG_HORIZONS = (91, 182, 365, 1095, 1826)
FACTOR = {91: 1.2, 182: 1.3, 365: 1.5, 1095: 2.0, 1826: 2.0}   # 시나리오 경계: ×f 이상 / ÷f 이하
HORIZON_KO = {91: "3개월", 182: "6개월", 365: "1년", 1095: "3년", 1826: "5년"}
K_CLUSTERS = 5
CHECKPOINTS = np.arange(91, DAYS + 1, 91)


VARIANTS = ("shrunk", "zero", "historical")
VARIANT_KO = {"shrunk": "줄인 추세", "zero": "추세 0", "historical": "과거 추세 그대로"}
DRIFT_HALFLIFE = 1095
SHRINK = 0.5


def drift(daily: pd.DataFrame, kind: str) -> float:
    """일간 로그 추세. daily 끝까지의 데이터만 사용."""
    lr = np.diff(np.log(daily["close"].to_numpy()))
    if kind == "zero":
        return 0.0
    if kind == "historical":
        return float(lr.mean())
    w = 0.5 ** (np.arange(len(lr))[::-1] / DRIFT_HALFLIFE)
    return float(SHRINK * (w * lr).sum() / w.sum())


def returns_pool(daily: pd.DataFrame) -> dict:
    lc = np.log(daily["close"].to_numpy())
    r = np.diff(lc)
    u = np.log(daily["high"].to_numpy()[1:]) - lc[1:]
    d = np.log(daily["low"].to_numpy()[1:]) - lc[1:]
    scale = np.std(r[-RECENT:]) / np.std(r)
    return {"r": (r - r.mean()) * scale, "u": u * scale, "d": d * scale, "scale": float(scale),
            "sig_recent": float(np.std(r[-RECENT:]))}


def simulate(pool: dict, n_paths: int, days: int, seed: int) -> dict:
    """반환: cum(종가 누적 로그수익률), hi/lo(그날 고가/저가). shape (n, days), float32."""
    rng = np.random.default_rng(seed)
    r, u, d = pool["r"], pool["u"], pool["d"]
    nb = -(-days // BLOCK)
    starts = rng.integers(0, len(r) - BLOCK, size=(n_paths, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)).reshape(n_paths, -1)[:, :days]
    cum = np.cumsum(r[idx], axis=1).astype(np.float32)
    return {"cum": cum, "hi": (cum + u[idx]).astype(np.float32), "lo": (cum + d[idx]).astype(np.float32)}


def kmeans(X: np.ndarray, k: int, seed: int = 0, iters: int = 40) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    C = [X[rng.integers(len(X))]]
    for _ in range(1, k):  # k-means++ 초기화
        d2 = np.min(((X[:, None, :] - np.array(C)[None]) ** 2).sum(-1), axis=1)
        C.append(X[rng.choice(len(X), p=d2 / d2.sum())])
    C = np.array(C)
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        newC = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return lab, C


def describe(shape: np.ndarray) -> str:
    """중심 경로(로그수익률, 3개월 간격)를 보고 한국어 이름을 붙인다."""
    end, mx, mn = shape[-1], shape.max(), shape.min()
    first_half_min = shape[: len(shape) // 2].min()
    big, mid = np.log(2.0), np.log(1.3)
    if end >= np.log(4.0):
        return "폭등"
    if end <= -np.log(4.0):
        return "폭락"
    if end >= big:
        return "하락 후 큰 상승" if first_half_min <= -mid else "큰 상승"
    if end >= mid:
        return "조정 후 상승" if mn <= -mid else "완만한 상승"
    if end <= -big:
        return "상승 후 큰 하락" if mx >= mid else "큰 하락"
    if end <= -mid:
        return "반등 후 하락" if mx >= mid else "완만한 하락"
    # 여기부터는 끝 가격이 현재가 ±30% 안 → '제자리 근처'. 묶음 안 경로들은 중간에 크게 오르내린다.
    if mx >= mid and mn <= -mid:
        return "큰 등락 후 제자리 근처"
    if mx >= mid:
        return "상승 후 되돌림"
    if mn <= -mid:
        return "하락 후 회복"
    return "등락 끝에 제자리 근처"


def _ohlc_from_daily(price: float, cum: np.ndarray, hi: np.ndarray, lo: np.ndarray, dates: pd.DatetimeIndex,
                     iv: str, after: pd.Timestamp) -> dict:
    """하루 단위 가상 경로 → 달력 기준 주봉/월봉 캔들. 현재 진행 중인 봉 이후부터."""
    df = pd.DataFrame({"close": price * np.exp(cum), "high": price * np.exp(np.maximum(hi, cum)),
                       "low": price * np.exp(np.minimum(lo, cum))}, index=dates)
    df["open"] = df["close"].shift(1).fillna(price)
    g = df.groupby(bar_start(df.index, iv))
    o = g.agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    o = o[o.index > after]
    o["open"] = o["close"].shift(1).fillna(o["open"])  # 봉끼리 이어지게
    o["high"] = o[["high", "open", "close"]].max(axis=1)
    o["low"] = o[["low", "open", "close"]].min(axis=1)
    r = lambda s: [round(float(x), 2) for x in s]  # noqa: E731
    return {"t": [int(t.timestamp()) for t in o.index], "o": r(o["open"]), "h": r(o["high"]), "l": r(o["low"]),
            "c": r(o["close"])}


def forecast(daily: pd.DataFrame, price: float, now: pd.Timestamp, bar_starts: dict[str, pd.Timestamp],
             levels: list[dict], n_paths: int = 4000, seed: int = 11) -> dict:
    """daily: 완성된 일봉. now: 예측 출발 시각. bar_starts: {"1w": 이번 주봉 시작, "1M": 이번 달 시작}.

    반환: 기본 가정(shrunk)의 결과를 최상위에 두고(1.1 호환), variants 에 세 가정 모두.
    """
    pool = returns_pool(daily)
    sim = simulate(pool, n_paths, DAYS, seed)
    days = np.arange(1, DAYS + 1, dtype=np.float32)
    variants = {}
    for kind in VARIANTS:
        mu = drift(daily, kind)
        shift = (mu * days)[None, :]
        res = _summarize(sim["cum"] + shift, sim["hi"] + shift, sim["lo"] + shift, price, now, bar_starts, levels, seed)
        variants[kind] = {"label_ko": VARIANT_KO[kind], "drift_annual": round(float(np.exp(mu * 365) - 1), 4), **res}
    out = {
        "method_ko": "90일 블록 부트스트랩(최근 2년 변동성 기준) · 경로 모양 5개 묶음 · 추세 가정 3가지",
        "n_paths": n_paths,
        "sigma_daily_recent": round(pool["sig_recent"], 5),
        "default_variant": "shrunk",
        "drift_note_ko": (f"기본값은 최근일수록 크게 반영한 과거 평균(반감기 3년)의 절반입니다. "
                          f"과거 평균을 그대로 쓰면 2017년 이후 초기 급성장기 수익률을 미래에도 가정하게 되고, "
                          f"0으로 두면 과거 내내 있었던 상승 경향을 무시하게 됩니다."),
        **variants["shrunk"],
        "variants": variants,
    }
    return out


def _summarize(cum, hi, lo, price, now, bar_starts, levels, seed) -> dict:
    n_paths = cum.shape[0]
    day0 = now.floor("1D")
    dates = pd.date_range(day0 + pd.Timedelta(days=1), periods=DAYS, freq="1D")  # i번째 = i+1일 뒤 종가 시점
    qs = np.array(list(QUANTILES.values()))
    # 기간별 요약
    run_hi = np.maximum.accumulate(hi, axis=1)
    run_lo = np.minimum.accumulate(lo, axis=1)
    horizons = {}
    for h in LONG_HORIZONS:
        x = cum[:, h - 1]
        q = np.quantile(x, qs)
        f = FACTOR[h]
        up_lbl = f"+{round((f - 1) * 100)}% 이상" if f < 2 else "2배 이상"
        dn_lbl = f"-{round((1 - 1 / f) * 100)}% 이하" if f < 2 else "절반 이하"
        horizons[str(h)] = {
            "label_ko": HORIZON_KO[h],
            "quantiles": {k: round(float(price * np.exp(v)), 2) for k, v in zip(QUANTILES, q)},
            "prob_up": round(float((x > 0).mean()), 3),
            "expected_return": round(float(np.exp(x.astype(np.float64)).mean() - 1), 4),
            "threshold_factor": f,
            "scenarios": [
                {"key": "up", "label_ko": up_lbl, "prob": round(float((x >= np.log(f)).mean()), 3)},
                {"key": "flat", "label_ko": "그 사이", "prob": round(float(((x < np.log(f)) & (x > -np.log(f))).mean()), 3)},
                {"key": "down", "label_ko": dn_lbl, "prob": round(float((x <= -np.log(f)).mean()), 3)},
            ],
            "level_touch": [
                {"price": lv["price"], "type": lv["type"],
                 "prob": round(float(((run_hi[:, h - 1] >= np.log(lv["price"] / price)) if lv["price"] > price
                                      else (run_lo[:, h - 1] <= np.log(lv["price"] / price))).mean()), 3)}
                for lv in levels
            ],
        }

    # fan: 각 봉 단위의 미래 봉 시작 시각마다 분위수
    fans = {}
    for iv, start in bar_starts.items():
        if iv == "1w":
            times = pd.date_range(start + pd.Timedelta(days=7), periods=262, freq="7D")
        else:
            times = pd.date_range(start + pd.offsets.MonthBegin(1), periods=61, freq="MS")
        days = ((times - now) / pd.Timedelta(days=1)).to_numpy()
        keep = (days >= 1) & (days <= DAYS)
        times, idx = times[keep], np.clip(np.round(days[keep]).astype(int) - 1, 0, DAYS - 1)
        Q = np.quantile(cum[:, idx], qs, axis=0)
        pts = [{"t": int(start.timestamp()), **{k: round(price, 2) for k in QUANTILES}}]
        pts += [{"t": int(t.timestamp()), **{k: round(float(price * np.exp(Q[i, j])), 2) for i, k in enumerate(QUANTILES)}}
                for j, t in enumerate(times)]
        fans[iv] = pts

    # 시나리오: 경로 모양 묶음
    X = cum[:, CHECKPOINTS - 1].astype(np.float64)
    lab, C = kmeans(X, K_CLUSTERS, seed)
    sizes = np.bincount(lab, minlength=K_CLUSTERS)
    order = np.argsort(-sizes)
    groups = []
    for rank, j in enumerate(order):
        mem = np.where(lab == j)[0]
        shape = C[j]
        mcum = cum[mem].astype(np.float64)
        mdd = np.median((mcum - np.maximum.accumulate(np.maximum(mcum, 0), axis=1)).min(1))
        g = {"rank": rank + 1, "prob": round(float(sizes[j] / n_paths), 3), "label_ko": describe(shape),
             "typical_max_drawdown": round(float(np.exp(mdd) - 1), 4),
             "checkpoints": [{"day": int(d), "price": round(float(price * np.exp(v)), 2)} for d, v in zip(CHECKPOINTS, shape)],
             "end_range80": [round(float(price * np.exp(np.quantile(X[mem, -1], 0.1))), 2),
                             round(float(price * np.exp(np.quantile(X[mem, -1], 0.9))), 2)]}
        if rank < 2:
            med = mem[np.argmin(((X[mem] - shape) ** 2).sum(1))]  # 중심에 가장 가까운 실제 경로
            path = cum[med].astype(np.float64)
            peak_i, trough_i = int(path.argmax()), int(path.argmin())
            dd = float((path - np.maximum.accumulate(np.maximum(path, 0))).min())
            g.update({
                "representative": {
                    "end_price": round(float(price * np.exp(path[-1])), 2),
                    "end_return": round(float(np.exp(path[-1]) - 1), 4),
                    "peak": {"price": round(float(price * np.exp(path[peak_i])), 2), "date": dates[peak_i].strftime("%Y-%m-%d")},
                    "trough": {"price": round(float(price * np.exp(path[trough_i])), 2), "date": dates[trough_i].strftime("%Y-%m-%d")},
                    "max_drawdown": round(float(np.exp(dd) - 1), 4),
                },
                "candles": {iv: _ohlc_from_daily(price, cum[med], hi[med], lo[med], dates, iv, bar_starts[iv])
                            for iv in bar_starts},
            })
            g["text_ko"] = _text(g, price)
        groups.append(g)

    # 같은 이름이 여러 묶음에 붙으면 5년 뒤 배수로 구분
    names = [g["label_ko"] for g in groups]
    for g in groups:
        if names.count(g["label_ko"]) > 1:
            g["label_ko"] += f" (5년 ×{g['checkpoints'][-1]['price'] / price:.1f})"
    for g in groups:
        if "text_ko" in g:
            g["text_ko"] = _text(g, price)
    return {"horizons": horizons, "fan": fans, "scenario_groups": groups,
            "top_scenarios": [g for g in groups if "candles" in g]}


def _text(g: dict, price: float) -> str:
    cp = {c["day"]: c["price"] for c in g["checkpoints"]}
    pct = lambda v: f"{(v / price - 1) * 100:+.0f}%"  # noqa: E731
    rep = g["representative"]
    return (f"이 묶음의 중심 경로: 1년 뒤 {pct(cp[364])}, 3년 뒤 {pct(cp[1092])}, 5년 뒤 {pct(cp[1820])}. "
            f"묶음 안 경로들은 보통 중간에 {abs(g['typical_max_drawdown']) * 100:.0f}% 정도 떨어지는 구간을 거칩니다"
            f"(대표 경로는 {abs(rep['max_drawdown']) * 100:.0f}%).")


def backtest(daily: pd.DataFrame, start: str = "2019-01-01", step: int = 14, n_paths: int = 800, seed: int = 5) -> dict:
    """3개월·6개월·1년 구간 포함률을 추세 가정별로. 3년·5년은 독립 표본이 너무 적어 검증하지 않는다.

    각 시점의 추세는 그 시점까지의 데이터로만 계산(미래 정보 없음).
    above_median: 실제 가격이 예측 중앙값보다 높았던 비율(0.5가 이상적, 높으면 예측이 비관적이었다는 뜻).
    """
    lc = np.log(daily["close"].to_numpy())
    last = len(daily) - 1
    t0 = max(int(np.searchsorted(daily.index, pd.Timestamp(start, tz="UTC"))), 800)
    hs = (91, 182, 365)
    rec = {k: {h: [] for h in hs} for k in VARIANTS}
    for t in range(t0, last - min(hs) + 1, step):
        hist = daily.iloc[: t + 1]
        base = simulate(returns_pool(hist), n_paths, max(hs), seed + t)["cum"]
        for kind in VARIANTS:
            mu = drift(hist, kind)
            for h in hs:
                if t + h > last:
                    continue
                y = lc[t + h] - lc[t]
                p = float((base[:, h - 1] + mu * h <= y).mean())
                rec[kind][h].append(p)
    out = {}
    for kind in VARIANTS:
        out[kind] = {}
        for h in hs:
            p = np.array(rec[kind][h])
            a = np.abs(2 * p - 1)
            out[kind][str(h)] = {
                "n": int(len(p)),
                "independent_approx": int(len(p) * step / h) if len(p) else 0,
                "raw": {f"cov{int(lv * 100)}": round(float((a <= lv).mean()), 3) for lv in (0.5, 0.8, 0.95)},
                "above_median": round(float((p > 0.5).mean()), 3),
            }
        out[kind]["1095"] = None
        out[kind]["1826"] = None
        out[kind]["note_ko"] = ("3개월~1년은 2019년부터 2주 간격으로 검증(구간이 서로 겹쳐 실제 독립 표본은 적음). "
                                "3년·5년은 비교할 과거가 2~3번뿐이라 검증할 수 없어, 참고용 통계 추정입니다.")
    return out
