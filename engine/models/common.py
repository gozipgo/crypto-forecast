"""모델 공통: 경로 묶음, 폭 배율 적용, 요약(분위수·시나리오·도달확률)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HORIZON_MAX = 30
HORIZONS = (7, 14, 30)
QUANTILES = {"p2_5": 0.025, "p10": 0.10, "p25": 0.25, "p50": 0.50, "p75": 0.75, "p90": 0.90, "p97_5": 0.975}
SCENARIO_TH = {7: 0.05, 14: 0.10, 30: 0.15}


@dataclass
class Paths:
    """현재가 대비 로그수익률 경로. shape = (경로 수, 30일).

    close: k일 뒤 종가, high/low: k번째 날의 고가/저가(누적 아님).
    """
    close: np.ndarray
    high: np.ndarray
    low: np.ndarray

    def subsample(self, n: int, rng: np.random.Generator) -> "Paths":
        idx = rng.choice(len(self.close), size=min(n, len(self.close)), replace=False)
        return Paths(self.close[idx], self.high[idx], self.low[idx])

    @staticmethod
    def concat(parts: list["Paths"]) -> "Paths":
        return Paths(*(np.concatenate([getattr(p, f) for p in parts]) for f in ("close", "high", "low")))


def recalibrate(p: Paths, recal_by_h: dict[int, dict | None] | None) -> Paths:
    """백테스트로 얻은 대칭 분위수 재보정 지도를 날짜별로 보간해 경로에 적용.

    각 날짜 열에서 표본의 중앙 기준 수준 c(=|2u-1|)를 c_raw 로 바꿔 같은 쪽의 원래 분위수 값을 가져온다.
    고가/저가는 종가가 움직인 만큼 같이 옮긴다(장중 이탈폭 유지).
    """
    if not recal_by_h or not any(recal_by_h.values()):
        return p
    hs = sorted(recal_by_h)
    knots_c = None
    rows = []
    for h in hs:
        rc = recal_by_h[h]
        if rc is not None:
            knots_c = np.array(rc["c"])
    for h in hs:
        rc = recal_by_h[h]
        rows.append(np.array(rc["c_raw"]) if rc is not None else knots_c.copy())
    R = np.array(rows)  # (기간 수, 매듭 수)
    n = p.close.shape[0]
    u = (np.arange(n) + 0.5) / n
    close = p.close.copy()
    for d in range(HORIZON_MAX):
        c_raw_knots = np.array([np.interp(d + 1, hs, R[:, j]) for j in range(R.shape[1])])
        order = np.argsort(p.close[:, d])
        c = np.abs(2 * u - 1)
        lv = 0.5 + np.sign(u - 0.5) * np.interp(c, knots_c, c_raw_knots) / 2
        newvals = np.quantile(p.close[:, d], lv)
        close[order, d] = newvals
    shift = close - p.close
    return Paths(close, p.high + shift, p.low + shift)


def summarize(p: Paths, price: float, levels: list[dict]) -> dict:
    qs = np.array(list(QUANTILES.values()))
    qv = np.quantile(p.close, qs, axis=0)  # (7, 30)
    path_daily = [
        {"day": d + 1, **{k: round(float(price * np.exp(qv[i, d])), 2) for i, k in enumerate(QUANTILES)}}
        for d in range(HORIZON_MAX)
    ]
    run_hi = np.maximum.accumulate(np.maximum(p.high, p.close), axis=1)
    run_lo = np.minimum.accumulate(np.minimum(p.low, p.close), axis=1)
    horizons = {}
    for h in HORIZONS:
        r = p.close[:, h - 1]
        th = SCENARIO_TH[h]
        lr_up, lr_dn = np.log(1 + th), np.log(1 - th)
        pct = round(th * 100)
        touch = []
        for lv in levels:
            lp = np.log(lv["price"] / price)
            hit = run_hi[:, h - 1] >= lp if lp > 0 else run_lo[:, h - 1] <= lp
            touch.append({"price": lv["price"], "type": lv["type"], "prob": round(float(hit.mean()), 3)})
        horizons[str(h)] = {
            "quantiles": {k: round(float(price * np.exp(qv[i, h - 1])), 2) for i, k in enumerate(QUANTILES)},
            "prob_up": round(float((r > 0).mean()), 3),
            "expected_return": round(float(np.exp(r).mean() - 1), 4),
            "threshold": th,
            "scenarios": [
                {"key": "up", "label_ko": f"+{pct}% 이상", "prob": round(float((r >= lr_up).mean()), 3)},
                {"key": "flat", "label_ko": f"±{pct}% 이내", "prob": round(float(((r < lr_up) & (r > lr_dn)).mean()), 3)},
                {"key": "down", "label_ko": f"-{pct}% 이하", "prob": round(float((r <= lr_dn).mean()), 3)},
            ],
            "level_touch": touch,
        }
    return {"horizons": horizons, "path_daily": path_daily}


def realized_vol(close: pd.Series, n: int = 30) -> pd.Series:
    return np.log(close).diff().rolling(n, min_periods=n).std()
