"""지지선·저항선: 스윙 고점/저점(프랙탈)을 가격대별로 묶어 강도를 매긴다."""
from __future__ import annotations

import numpy as np
import pandas as pd


def swing_points(df: pd.DataFrame, w: int) -> list[tuple[pd.Timestamp, float, str]]:
    """좌우 w봉 안에서 최고(저항 후보)/최저(지지 후보)인 봉."""
    hi, lo = df["high"].to_numpy(), df["low"].to_numpy()
    pts = []
    for i in range(w, len(df) - w):
        if hi[i] == hi[i - w:i + w + 1].max():
            pts.append((df.index[i], float(hi[i]), "high"))
        if lo[i] == lo[i - w:i + w + 1].min():
            pts.append((df.index[i], float(lo[i]), "low"))
    return pts


def find_levels(daily: pd.DataFrame, h4: pd.DataFrame | None, price: float, atr_d: float,
                max_each: int = 3, lookback_days: int = 365) -> list[dict]:
    """현재가 아래 지지 max_each개, 위 저항 max_each개.

    - 일봉(최근 1년, w=5)과 4시간봉(w=8) 스윙 포인트를 모은다.
    - 일봉 ATR의 0.6배 이내 가격들을 하나의 가격대로 묶는다.
    - 강도 = 접촉 횟수 × 최근성 가중(반감기 90일)의 합을 0~1로 정규화.
    """
    end = daily.index[-1]
    d = daily[daily.index >= end - pd.Timedelta(days=lookback_days)]
    # (시각, 가격, 종류, 가중치): 일봉 스윙은 4시간봉보다 2배 중요
    pts = [(*p, 2.0) for p in swing_points(d, 5)]
    if h4 is not None and len(h4) > 50:
        pts += [(*p, 1.0) for p in swing_points(h4.iloc[-1000:], 8)]
    if not pts:
        return []
    tol = max(atr_d * 0.5, price * 0.005)
    pts.sort(key=lambda p: p[1])
    clusters: list[list] = []
    for p in pts:
        # 군집의 첫(최저) 가격 기준으로 폭을 제한 → 줄줄이 이어 붙는 현상 방지
        if clusters and p[1] - clusters[-1][0][1] <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = []
    for cl in clusters:
        prices = np.array([p[1] for p in cl])
        age = np.array([(end - p[0]).total_seconds() / 86400 for p in cl])
        wts = np.array([p[3] for p in cl]) * 0.5 ** (age / 90)
        levels.append({
            "price": float(np.average(prices, weights=wts)),
            "touches": len(cl),
            "score": float(wts.sum()),
            "last_touch": max(p[0] for p in cl).isoformat(),
        })
    smax = max(lv["score"] for lv in levels)
    for lv in levels:
        lv["strength"] = round(lv.pop("score") / smax, 3)
    # 현재가에 너무 가까운(±0.3 ATR) 가격대는 제외하고 위/아래 강한 순→가까운 순
    sup = [lv for lv in levels if lv["price"] < price - 0.3 * atr_d]
    res = [lv for lv in levels if lv["price"] > price + 0.3 * atr_d]
    pick = lambda arr: sorted(sorted(arr, key=lambda x: -x["strength"])[: max_each * 2],  # noqa: E731
                              key=lambda x: abs(x["price"] - price))[:max_each]
    out = [{"type": "support", **lv} for lv in pick(sup)] + [{"type": "resistance", **lv} for lv in pick(res)]
    for lv in out:
        lv["price"] = round(lv["price"], 2)
        lv["distance_pct"] = round(lv["price"] / price - 1, 4)
    return sorted(out, key=lambda x: x["price"])
