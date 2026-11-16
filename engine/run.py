"""진입점: python -m engine.run --out site/data

데이터 수집 → 지표 → (모델·백테스트) → JSON 저장. 화면은 이 JSON만 읽는다.
"""
from __future__ import annotations

import argparse
import pandas as pd
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from . import backtest
from .schema import validate
from . import levels as levels_mod
from .data import load_asset
from .models import analog, ensemble, montecarlo
from .models.common import HORIZONS, recalibrate, summarize
from .technicals import analyze_tf, candles_payload

SCHEMA_VERSION = "1.0.0"
ASSETS = ["BTC", "ETH"]
DISCLAIMER = "투자 조언이 아니며, 확률은 과거 데이터에 기반한 통계적 추정입니다."
log = logging.getLogger("engine")
MODEL_LABEL = {"montecarlo": "몬테카를로", "analog": "유사 패턴", "ensemble": "혼합"}


def iso(ts) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, obj, kind: str | None = None) -> None:
    if kind:
        validate(obj, kind)  # 스키마에 안 맞으면 저장하지 않고 실패(배포 중단)
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
                   {"schema_version": SCHEMA_VERSION, "asset": asset, **candles_payload(data[tf], ind, tf)}, "candles")
    atr_d = float(inds["1d"]["atr14"].iloc[-1])
    lv = levels_mod.find_levels(data["1d"], data["4h"], price, atr_d)

    # 확률 모델: 완성된 일봉만 사용(진행 중인 오늘 봉 제외), 출발점은 현재가(최신 1시간봉 종가)
    daily = data["1d"]
    if daily.index[-1] + pd.Timedelta(days=1) > h1.index[-1] + pd.Timedelta(hours=1):
        daily = daily.iloc[:-1]
    t1 = time.time()
    cal = backtest.calibrate(backtest.run(daily))
    log.info("%s 백테스트 %.1fs", asset, time.time() - t1)
    p_mc, i_mc = montecarlo.forecast(daily)
    p_an, i_an = analog.forecast(daily)
    p_en = ensemble.mix(p_mc, p_an)
    forecasts = {}
    for name, paths, info in (("montecarlo", p_mc, i_mc), ("analog", p_an, i_an),
                              ("ensemble", p_en, {"weights": {"montecarlo": 0.5, "analog": 0.5}})):
        rc = {h: cal[name][str(h)]["recal"] for h in HORIZONS}
        forecasts[name] = {
            "label_ko": MODEL_LABEL[name],
            "info": info,
            "calibrated": any(v is not None for v in rc.values()),
            **summarize(recalibrate(paths, rc), price, lv),
        }
    first = cal["montecarlo"]["7"]["period"]

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
        "forecast_origin": {"price": round(price, 2), "time": iso(h1.index[-1] + pd.Timedelta(hours=1)),
                            "daily_history_from": iso(daily.index[0]), "daily_history_to": iso(daily.index[-1])},
        "forecasts": forecasts,
        "calibration": {"method": "walk_forward", "step_days": 3, "period": [first[0], first[1]],
                        "target": {"cov50": 0.5, "cov80": 0.8, "cov95": 0.95}, "models": cal},
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
        write_json(out / a / "forecast.json", r["doc"], "forecast")

    write_json(out / "summary.json", {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "assets": {a: {
            "price": d["price"], "change_24h": d["change_24h"],
            "trend": d["trend"]["state"], "trend_label_ko": d["trend"]["label_ko"],
            "horizon_days": 14,
            "median_14d": d["forecasts"]["ensemble"]["horizons"]["14"]["quantiles"]["p50"],
            "range80_14d": [d["forecasts"]["ensemble"]["horizons"]["14"]["quantiles"]["p10"],
                            d["forecasts"]["ensemble"]["horizons"]["14"]["quantiles"]["p90"]],
            "scenarios_14d": d["forecasts"]["ensemble"]["horizons"]["14"]["scenarios"],
            "prob_up_14d": d["forecasts"]["ensemble"]["horizons"]["14"]["prob_up"],
        } for a, d in docs.items()},
        "disclaimer_ko": DISCLAIMER,
    }, "summary")
    write_json(out / "manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "assets": assets,
        "summary": "summary.json",
        "files": {a: {"forecast": f"{a}/forecast.json",
                      "candles": {tf: f"{a}/candles_{tf}.json" for tf in ("1h", "4h", "1d")}} for a in assets},
        "build_seconds": round(time.time() - t0, 1),
    }, "manifest")
    log.info("완료: %s (%.1fs)", out, time.time() - t0)


if __name__ == "__main__":
    main()
