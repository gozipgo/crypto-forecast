"""데이터 소스 공통부와 폴백 체인.

모든 소스는 같은 형태의 DataFrame을 돌려준다:
  index = UTC 시각(캔들 시작 시각, tz-aware), columns = open, high, low, close, volume (float)
"""
from __future__ import annotations

import logging
import time
from typing import Callable

import pandas as pd
import requests

log = logging.getLogger(__name__)

INTERVALS = ("1h", "4h", "1d")
COLUMNS = ["open", "high", "low", "close", "volume"]
UA = {"User-Agent": "crypto-forecast/1.0 (+https://github.com/gozipgo/crypto-forecast)"}


class SourceError(RuntimeError):
    pass


def http_get(url: str, params: dict | None = None, timeout: float = 20, retries: int = 3):
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                last = SourceError(f"429 rate limited: {url}")
                continue
            if r.status_code != 200:
                raise SourceError(f"HTTP {r.status_code}: {url} {r.text[:200]}")
            return r.json()
        except (requests.RequestException, ValueError) as e:  # 연결 실패, JSON 오류
            last = e
            time.sleep(1 + attempt)
    raise SourceError(f"요청 실패: {url}: {last}")


def finalize(df: pd.DataFrame) -> pd.DataFrame:
    """정렬·중복 제거·타입 정리·미완성(진행 중) 캔들은 그대로 둔다(마지막 봉은 진행 중일 수 있음)."""
    df = df[COLUMNS].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[(df["close"] > 0) & (df["high"] >= df["low"])]
    return df


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """1h → 4h 등 재집계 (UTC 00시 기준 정렬)."""
    out = df.resample(rule, label="left", closed="left", origin="epoch").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna()


def resample_calendar(daily: pd.DataFrame, iv: str) -> pd.DataFrame:
    """일봉 → 주봉(월요일 시작, Binance와 동일) 또는 월봉(매월 1일 시작)."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return daily.groupby(bar_start(daily.index, iv)).agg(agg).dropna()


def bar_start(idx: pd.DatetimeIndex, iv: str) -> pd.DatetimeIndex:
    """각 시각이 속한 주봉(월요일 00:00 UTC) 또는 월봉(1일 00:00 UTC) 시작 시각."""
    d = idx.floor("1D")
    if iv == "1w":
        return d - pd.to_timedelta(d.day_of_week, unit="D")
    if iv == "1M":
        return d - pd.to_timedelta(d.day - 1, unit="D")
    raise ValueError(iv)


# 우선순위 순서. 각 항목: (이름, fetch 함수)
SOURCES: list[tuple[str, Callable[..., pd.DataFrame]]] = []


def register(name: str):
    def deco(fn):
        SOURCES.append((name, fn))
        return fn
    return deco


def fetch_candles(asset: str, interval: str, bars: int, min_bars: int | None = None,
                  order: list[str] | None = None) -> tuple[pd.DataFrame, str]:
    """우선순위대로 소스를 시도하고, 처음 성공한 (DataFrame, 소스이름)을 돌려준다.

    bars: 원하는 봉 개수(최근부터). 일봉 전체 이력을 원하면 큰 값(예: 5000).
    min_bars: 이보다 적게 받으면 실패로 보고 다음 소스로 넘어간다.
    """
    from . import binance_vision, coinbase, kraken, coingecko  # noqa: F401  (등록)

    if interval not in INTERVALS:
        raise ValueError(interval)
    min_bars = min_bars if min_bars is not None else min(bars, 250)
    errors = []
    sources = SOURCES if order is None else [s for n in order for s in SOURCES if s[0] == n]
    for name, fn in sources:
        try:
            df = finalize(fn(asset, interval, bars))
            if len(df) < min_bars:
                raise SourceError(f"봉 개수 부족 {len(df)} < {min_bars}")
            log.info("%s %s: %s에서 %d개", asset, interval, name, len(df))
            return df.iloc[-bars:], name
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 다음 소스로
            log.warning("%s %s: %s 실패 → 다음 소스 (%s)", asset, interval, name, e)
            errors.append(f"{name}: {e}")
    raise SourceError(f"{asset} {interval}: 모든 소스 실패\n" + "\n".join(errors))
