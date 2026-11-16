import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n=800, seed=0, drift=0.0005, vol=0.03, start="2020-01-01", freq="1D"):
    rng = np.random.default_rng(seed)
    r = rng.standard_t(4, n) * vol / np.sqrt(2) + drift
    close = 100 * np.exp(np.cumsum(r))
    open_ = np.r_[100, close[:-1]]
    spread = np.abs(rng.normal(0, vol / 2, n))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    vol_ = rng.lognormal(10, 0.3, n)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol_}, index=idx)


@pytest.fixture
def ohlcv():
    return make_ohlcv()
