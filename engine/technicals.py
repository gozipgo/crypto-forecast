"""봉 단위별 지표·추세·요약과 차트용 캔들 묶음을 만든다."""
from __future__ import annotations

import math

import pandas as pd

from . import indicators, narrative, trend

TF_LABEL = {"1h": "1시간봉", "4h": "4시간봉", "1d": "일봉"}
CHART_BARS = {"1h": 720, "4h": 540, "1d": 1000}


def _r(x, nd=2):
    x = float(x)
    return None if math.isnan(x) else round(x, nd)



def analyze_tf(df: pd.DataFrame, tf: str) -> tuple[pd.DataFrame, dict]:
    ind = indicators.compute_all(df)
    return ind, {
        "trend": trend.judge(df, ind),
        "indicators": narrative.summarize(df, ind, TF_LABEL[tf]),
    }


def candles_payload(df: pd.DataFrame, ind: pd.DataFrame, tf: str, nd: int = 2) -> dict:
    """열(column) 단위 배열로 저장해 용량을 줄인다. t = 봉 시작 UNIX 초(UTC)."""
    n = CHART_BARS[tf]
    d, i = df.iloc[-n:], ind.iloc[-n:]
    col = lambda s, k=nd: [_r(v, k) for v in s]  # noqa: E731
    return {
        "interval": tf,
        "t": [int(ts.timestamp()) for ts in d.index],
        "o": col(d["open"]), "h": col(d["high"]), "l": col(d["low"]), "c": col(d["close"]),
        "v": col(d["volume"], 3),
        "sma20": col(i["sma20"]), "sma50": col(i["sma50"]), "sma200": col(i["sma200"]),
        "bb_upper": col(i["bb_upper"]), "bb_lower": col(i["bb_lower"]),
    }
