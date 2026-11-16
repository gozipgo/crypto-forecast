"""기술적 지표. 입력: OHLCV DataFrame, 출력: 같은 인덱스의 Series/DataFrame.

외부 TA 라이브러리 없이 표준 정의대로 구현한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder 평활(RMA) = alpha 1/n 지수평균."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = wilder(d.clip(lower=0), n)
    dn = wilder((-d).clip(lower=0), n)
    rs = up / dn
    out = 100 - 100 / (1 + rs)
    return out.where(dn != 0, 100.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    return pd.DataFrame({
        "mid": mid, "upper": upper, "lower": lower,
        "pctb": (close - lower) / (upper - lower),
        "width": (upper - lower) / mid,
    })


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return wilder(tr, n)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = up.where((up > dn) & (up > 0), 0.0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0.0)
    a = atr(df, n)
    pdi = 100 * wilder(plus_dm, n) / a
    mdi = 100 * wilder(minus_dm, n) / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return wilder(dx, n)


def volume_ratio(vol: pd.Series, n: int = 20) -> pd.Series:
    """현재 거래량 / 직전 n봉 평균 거래량."""
    return vol / vol.shift(1).rolling(n, min_periods=n).mean()


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """차트·요약·유사패턴 특징에 쓰는 지표를 한 번에 계산."""
    c = df["close"]
    out = pd.DataFrame(index=df.index)
    for n in (20, 50, 200):
        out[f"sma{n}"] = sma(c, n)
    out["rsi14"] = rsi(c, 14)
    out = out.join(macd(c))
    bb = bollinger(c)
    out = out.join(bb.add_prefix("bb_"))
    out["atr14"] = atr(df, 14)
    out["adx14"] = adx(df, 14)
    out["vol_ratio"] = volume_ratio(df["volume"])
    return out
