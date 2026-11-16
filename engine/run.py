"""진입점: python -m engine.run --out site/data

데이터 수집 → 지표 → (모델·백테스트) → JSON 저장. 화면은 이 JSON만 읽는다.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from . import levels as levels_mod
from .data import load_asset
from .technicals import analyze_tf, candles_payload

SCHEMA_VERSION = "1.0.0"
ASSETS = ["BTC", "ETH"]
DISCLAIMER = "투자 조언이 아니며, 확률은 과거 데이터에 기반한 통계적 추정입니다."
log = logging.getLogger("engine")


def iso(ts) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def build_asset(asset: str, out: Path, cache_min: float, generated_at: str) -> dict:
    data = load_asset(asset, cache_min)
    h1 = data["1h"]
    price = float(h1["close"].iloc[-1])
    technicals, inds = {}, {}
    for tf in ("1h", "4h", "1d"):
        ind, tech = analyze_tf(data[tf], tf)
        inds[tf], technicals[tf] = ind, tech
        write_json(out / asset / f"candles_{tf}.json",
                   {"schema_version": SCHEMA_VERSION, "asset": asset, **candles_payload(data[tf], ind, tf)})
    atr_d = float(inds["1d"]["atr14"].iloc[-1])
    lv = levels_mod.find_levels(data["1d"], data["4h"], price, atr_d)

    # 24시간 변동: 1시간봉 기준 24봉 전 종가 대비
    chg24 = price / float(h1["close"].iloc[-25]) - 1 if len(h1) > 25 else None
    doc = {
        "schema_version": SCHEMA_VERSION,
        "asset": asset,
        "quote": "USD",
        "sources": data["sources"],
        "generated_at": generated_at,
        "last_candle_at": iso(h1.index[-1]),
        "price": round(price, 2),
        "change_24h": round(chg24, 4) if chg24 is not None else None,
        "atr_1d": round(atr_d, 2),
        "trend": technicals["1d"]["trend"],
        "technicals": technicals,
        "levels": lv,
        "disclaimer_ko": DISCLAIMER,
    }
    return {"doc": doc, "data": data, "inds": inds}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data")
    ap.add_argument("--assets", default=",".join(ASSETS))
    ap.add_argument("--cache", type=float, default=0, help="개발용: 캔들 캐시 유효시간(분)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    out = Path(args.out)
    t0 = time.time()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assets = args.assets.split(",")
    docs = {}
    for a in assets:
        r = build_asset(a, out, args.cache, generated_at)
        docs[a] = r["doc"]
        write_json(out / a / "forecast.json", r["doc"])

    write_json(out / "manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "assets": assets,
        "files": {a: {"forecast": f"{a}/forecast.json",
                      "candles": {tf: f"{a}/candles_{tf}.json" for tf in ("1h", "4h", "1d")}} for a in assets},
        "build_seconds": round(time.time() - t0, 1),
    })
    log.info("완료: %s (%.1fs)", out, time.time() - t0)


if __name__ == "__main__":
    main()
