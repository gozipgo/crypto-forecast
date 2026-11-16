import numpy as np
import pandas as pd

from engine import indicators as I


def test_sma_ema_known_values():
    s = pd.Series([1.0, 2, 3, 4, 5])
    assert I.sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    e = I.ema(s, 3)  # alpha = 0.5, 시작값 = 첫 값
    assert np.isclose(e.iloc[-1], 4.0625)


def test_rsi_extremes_and_wilder_value():
    up = pd.Series(np.arange(1.0, 40))
    assert I.rsi(up).iloc[-1] == 100
    down = pd.Series(np.arange(40.0, 1, -1))
    assert I.rsi(down).iloc[-1] == 0
    # 손계산: 변화 +1,-1 반복이면 평균 상승 ≈ 평균 하락 → RSI ≈ 50
    zz = pd.Series([10.0, 11] * 50)
    assert abs(I.rsi(zz).iloc[-1] - 50) < 3


def test_macd_is_ema_difference(ohlcv):
    c = ohlcv["close"]
    m = I.macd(c)
    expect = I.ema(c, 12) - I.ema(c, 26)
    assert np.allclose(m["macd"].dropna(), expect.dropna().loc[m["macd"].dropna().index])
    assert np.allclose((m["macd"] - m["signal"]).dropna(), m["hist"].dropna())


def test_bollinger_matches_manual(ohlcv):
    c = ohlcv["close"]
    bb = I.bollinger(c)
    w = c.iloc[-20:]
    assert np.isclose(bb["mid"].iloc[-1], w.mean())
    assert np.isclose(bb["upper"].iloc[-1], w.mean() + 2 * w.std(ddof=0))
    assert 0 <= bb["pctb"].dropna().between(-2, 3).mean() <= 1


def test_compute_all_no_lookahead(ohlcv):
    """마지막 봉을 바꿔도 그 이전 지표 값은 변하지 않아야 한다."""
    a = I.compute_all(ohlcv)
    df2 = ohlcv.copy()
    df2.iloc[-1, df2.columns.get_loc("close")] *= 1.5
    df2.iloc[-1, df2.columns.get_loc("high")] *= 1.5
    b = I.compute_all(df2)
    pd.testing.assert_frame_equal(a.iloc[:-1], b.iloc[:-1])
