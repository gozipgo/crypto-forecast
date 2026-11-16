"""Binance 공개 시세 미러 (data-api.binance.vision). API 키 불필요, 1000개/요청."""
import pandas as pd

from .base import http_get, register

URL = "https://data-api.binance.vision/api/v3/klines"
SYMBOL = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
IV = {"1h": "1h", "4h": "4h", "1d": "1d"}


@register("binance_vision")
def fetch(asset: str, interval: str, bars: int) -> pd.DataFrame:
    rows: list = []
    end = None
    while len(rows) < bars:
        params = {"symbol": SYMBOL[asset], "interval": IV[interval], "limit": 1000}
        if end is not None:
            params["endTime"] = end
        chunk = http_get(URL, params)
        if not chunk:
            break
        rows = chunk + rows
        if len(chunk) < 1000:
            break  # 상장 시점까지 도달
        end = chunk[0][0] - 1
    df = pd.DataFrame([r[:6] for r in rows], columns=["t", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    return df
