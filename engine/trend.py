"""추세 판정: 이동평균 배열 + 50MA 기울기 + ADX."""
from __future__ import annotations

import math

import pandas as pd

LABELS = {
    "strong_up": "강한 상승 추세",
    "up": "상승 추세",
    "sideways": "횡보",
    "down": "하락 추세",
    "strong_down": "강한 하락 추세",
}


def judge(df: pd.DataFrame, ind: pd.DataFrame) -> dict:
    last = ind.iloc[-1]
    c = float(df["close"].iloc[-1])
    s20, s50, s200 = (last.get(f"sma{n}") for n in (20, 50, 200))
    has200 = s200 is not None and not math.isnan(s200)
    slope50 = float(ind["sma50"].iloc[-1] / ind["sma50"].iloc[-11] - 1) if len(ind) > 60 else 0.0
    adx = float(last["adx14"]) if not math.isnan(last["adx14"]) else 0.0

    score = 0
    score += 1 if c > s20 else -1
    score += 1 if c > s50 else -1
    score += 1 if s20 > s50 else -1
    if has200:
        score += 1 if c > s200 else -1
        score += 1 if s50 > s200 else -1
    score += 1 if slope50 > 0.005 else (-1 if slope50 < -0.005 else 0)
    # score 범위 대략 -6 ~ +6
    if score >= 4:
        state = "strong_up" if adx >= 25 else "up"
    elif score >= 2:
        state = "up"
    elif score <= -4:
        state = "strong_down" if adx >= 25 else "down"
    elif score <= -2:
        state = "down"
    else:
        state = "sideways"

    parts = []
    above = [f"{n}" for n, v in (("20", s20), ("50", s50), ("200", s200 if has200 else None))
             if v is not None and not math.isnan(v) and c > v]
    below = [f"{n}" for n, v in (("20", s20), ("50", s50), ("200", s200 if has200 else None))
             if v is not None and not math.isnan(v) and c <= v]
    if above:
        parts.append(f"가격이 {'·'.join(above)}선 위")
    if below:
        parts.append(f"{'·'.join(below)}선 아래")
    parts.append(f"50선 {'상승' if slope50 > 0.005 else '하락' if slope50 < -0.005 else '평탄'} 중")
    parts.append(f"추세 강도(ADX) {adx:.0f}{' — 뚜렷함' if adx >= 25 else ' — 약함' if adx < 20 else ''}")
    return {
        "state": state,
        "label_ko": LABELS[state],
        "score": score,
        "adx": round(adx, 1),
        "sma50_slope_10": round(slope50, 4),
        "text_ko": ", ".join(parts),
    }
