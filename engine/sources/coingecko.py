"""CoinGecko 공개 API. 최후 수단: 일봉만, 종가 기반(고가/저가는 종가로 근사)."""
import pandas as pd

from .base import SourceError, http_get, register

URL = "https://api.coingecko.com/api/v3/coins/{cid}/market_chart"
CID = {"BTC": "bitcoin", "ETH": "ethereum"}


@register("coingecko")
def fetch(asset: str, interval: str, bars: int) -> pd.DataFrame:
    if interval != "1d":
        raise SourceError("coingecko는 일봉만 지원")
    data = http_get(URL.format(cid=CID[asset]),
                    {"vs_currency": "usd", "days": min(bars, 365), "interval": "daily"})
    px = pd.DataFrame(data["prices"], columns=["t", "close"])
    vol = pd.DataFrame(data["total_volumes"], columns=["t", "volume"])
    df = px.merge(vol, on="t")
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True).dt.floor("1D")
    df["open"] = df["close"].shift(1).fillna(df["close"])
    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)
    return df
