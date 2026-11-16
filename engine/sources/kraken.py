"""Kraken 공개 API. 최근 720개까지만 제공 → 최근 데이터 대체용."""
import pandas as pd

from .base import SourceError, http_get, register

URL = "https://api.kraken.com/0/public/OHLC"
PAIR = {"BTC": "XBTUSD", "ETH": "ETHUSD"}
IV = {"1h": 60, "4h": 240, "1d": 1440}


@register("kraken")
def fetch(asset: str, interval: str, bars: int) -> pd.DataFrame:
    data = http_get(URL, {"pair": PAIR[asset], "interval": IV[interval]})
    if data.get("error"):
        raise SourceError(str(data["error"]))
    key = next(k for k in data["result"] if k != "last")
    # [time, open, high, low, close, vwap, volume, count]
    df = pd.DataFrame([[r[0], r[1], r[2], r[3], r[4], r[6]] for r in data["result"][key]],
                      columns=["t", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True)
    return df
