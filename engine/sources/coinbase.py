"""Coinbase Exchange 공개 API. 300개/요청, 4h 없음 → 1h를 재집계."""
from datetime import datetime, timedelta, timezone

import pandas as pd

from .base import http_get, register, resample

URL = "https://api.exchange.coinbase.com/products/{pid}/candles"
PID = {"BTC": "BTC-USD", "ETH": "ETH-USD"}
GRAN = {"1h": 3600, "1d": 86400}


def _fetch_raw(asset: str, gran: int, bars: int) -> pd.DataFrame:
    rows: list = []
    end = datetime.now(timezone.utc)
    step = timedelta(seconds=gran * 300)
    empty = 0
    while len(rows) < bars and empty < 2:
        start = end - step
        chunk = http_get(URL.format(pid=PID[asset]),
                         {"granularity": gran, "start": start.isoformat(), "end": end.isoformat()})
        if not chunk:
            empty += 1  # 상장 이전
        rows.extend(chunk)
        end = start
    # 응답 형식: [time, low, high, open, close, volume]
    df = pd.DataFrame(rows, columns=["t", "low", "high", "open", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True)
    return df.sort_index()


@register("coinbase")
def fetch(asset: str, interval: str, bars: int) -> pd.DataFrame:
    if interval == "4h":
        return resample(_fetch_raw(asset, 3600, bars * 4 + 4), "4h")
    return _fetch_raw(asset, GRAN[interval], bars)
