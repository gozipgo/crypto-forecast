import pandas as pd

from engine import levels, technicals
from engine.sources import base
from tests.conftest import make_ohlcv


def test_analyze_tf_outputs_korean_text(ohlcv):
    ind, tech = technicals.analyze_tf(ohlcv, "1d")
    assert tech["trend"]["state"] in {"strong_up", "up", "sideways", "down", "strong_down"}
    for k in ("ma", "rsi14", "macd", "bollinger", "volume"):
        assert tech["indicators"][k]["text_ko"]
    p = technicals.candles_payload(ohlcv, ind, "1d")
    assert len(p["t"]) == len(p["c"]) == min(len(ohlcv), 1000)


def test_levels_split_around_price(ohlcv):
    price = float(ohlcv["close"].iloc[-1])
    h4 = make_ohlcv(n=1200, seed=1, freq="4h")
    lv = levels.find_levels(ohlcv, h4, price, atr_d=price * 0.03)
    assert all(l["price"] < price for l in lv if l["type"] == "support")
    assert all(l["price"] > price for l in lv if l["type"] == "resistance")
    assert all(0 < l["strength"] <= 1 for l in lv)


def test_fallback_chain(monkeypatch, ohlcv):
    calls = []

    def bad(asset, iv, bars):
        calls.append("bad")
        raise base.SourceError("down")

    def good(asset, iv, bars):
        calls.append("good")
        return ohlcv

    from engine.sources import binance_vision, coinbase, kraken, coingecko  # noqa: F401
    monkeypatch.setattr(base, "SOURCES", [("bad", bad), ("good", good)])
    df, name = base.fetch_candles("BTC", "1d", 500)
    assert name == "good" and calls == ["bad", "good"] and len(df) == 500


def test_resample_4h():
    h1 = make_ohlcv(n=48, freq="1h")
    h4 = base.resample(h1, "4h")
    assert len(h4) == 12
    assert h4["high"].iloc[0] == h1["high"].iloc[:4].max()
    assert h4["volume"].iloc[0] == h1["volume"].iloc[:4].sum()
