"""자산별 캔들 수집(폴백 체인 사용) + 개발용 로컬 캐시."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from .sources import fetch_candles
from .sources.base import resample_calendar

log = logging.getLogger(__name__)

# (요청 봉 수, 최소 봉 수). 일봉은 모델·백테스트용으로 가능한 전체 이력.
PLAN = {"1d": (5000, 700), "4h": (1500, 300), "1h": (1500, 300)}
CACHE = Path(".cache")


def load_asset(asset: str, use_cache_minutes: float = 0) -> dict:
    """반환: {"1d": df, "4h": df, "1h": df, "sources": {iv: name}}"""
    out: dict = {"sources": {}}
    for iv, (bars, min_bars) in PLAN.items():
        f = CACHE / f"{asset}_{iv}.pkl"
        if use_cache_minutes and f.exists() and time.time() - f.stat().st_mtime < use_cache_minutes * 60:
            df, src = pd.read_pickle(f)
        else:
            df, src = fetch_candles(asset, iv, bars, min_bars=min_bars)
            if use_cache_minutes:
                CACHE.mkdir(exist_ok=True)
                pd.to_pickle((df, src), f)
        out[iv], out["sources"][iv] = df, src
    # 주봉(월요일 00:00 UTC 시작)·월봉(1일 시작)은 일봉 전체 이력에서 만든다 → 추가 요청 없음
    for iv in ("1w", "1M"):
        out[iv] = resample_calendar(out["1d"], iv)
        out["sources"][iv] = out["sources"]["1d"]
    return out
