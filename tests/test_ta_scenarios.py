import numpy as np
import pytest

from engine import indicators, ta_scenarios as ta
from tests.conftest import make_ohlcv


def _prep(n=900, seed=1, drift=0.0005, freq="1D"):
    df = make_ohlcv(n=n, seed=seed, drift=drift, freq=freq)
    return df, indicators.compute_all(df)


def test_zigzag_is_causal():
    """앞부분만 넣어 확정된 피벗은 전체를 넣었을 때의 앞쪽 피벗과 같아야 한다(미래 정보 없음)."""
    df, ind = _prep()
    thr = 2.5 * np.log1p((ind["atr14"] / df["close"]).fillna(0.03).to_numpy())
    full, _, _ = ta.zigzag(df["high"].to_numpy(), df["low"].to_numpy(), thr)
    part, _, _ = ta.zigzag(df["high"].to_numpy()[:600], df["low"].to_numpy()[:600], thr[:600])
    assert len(part) >= 3
    assert full[:len(part)] == part


@pytest.mark.parametrize("seed,drift", [(1, 0.004), (2, -0.004), (3, 0.0)])
def test_scenarios_shape_and_sides(seed, drift):
    df, ind = _prep(seed=seed, drift=drift)
    r = ta.analyze(df, ind, "1d")
    assert r is not None and len(r["scenarios"]) == 2
    price = float(df["close"].iloc[-1])
    H = ta.TF_CFG["1d"]["horizon"]
    for sc in r["scenarios"]:
        c = sc["candles"]
        assert len(c["t"]) == len(c["c"]) == H
        assert all(h >= max(o, cl) - 1e-6 and lo <= min(o, cl) + 1e-6 for o, h, lo, cl in zip(c["o"], c["h"], c["l"], c["c"]))
        assert c["t"][0] > df.index[-1].timestamp()
        if sc["direction"] == "up":
            assert sc["first_target"]["price"] > price
            assert sc["invalidation"]["price"] < price
        elif sc["direction"] == "down":
            assert sc["first_target"]["price"] < price
            assert sc["invalidation"]["price"] > price
        else:
            assert sc["box"][0] < price < sc["box"][1]
    # 두 시나리오는 방향이 달라야 한다
    assert r["scenarios"][0]["direction"] != r["scenarios"][1]["direction"]


def test_strong_trend_picks_trend_primary():
    df, ind = _prep(seed=4, drift=0.006)
    r = ta.analyze(df, ind, "1d")
    assert r["scenarios"][0]["direction"] == "up"


def test_backtest_runs():
    df, ind = _prep(n=900)
    bt = ta.backtest(df, ind, "1d")
    assert bt is None or (bt["n"] >= 20 and 0 <= bt["target_first"] <= 1)


def test_stat_check():
    df, ind = _prep()
    r = ta.analyze(df, ind, "1d")
    rng = np.random.default_rng(0)
    cum = np.cumsum(rng.normal(0, 0.03, (500, 30)), axis=1)
    out = ta.stat_check(cum, cum + 0.01, cum - 0.01, float(df["close"].iloc[-1]), r["scenarios"][0], 30)
    assert 0 <= out["target_touch"] <= 1
