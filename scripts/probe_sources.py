"""각 데이터 소스를 개별로 실측한다. 로컬과 GitHub Actions(미국 러너) 양쪽에서 실행.

python scripts/probe_sources.py  → 표 출력 + probe_result.json
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from engine.sources.base import SOURCES, finalize  # noqa: E402
from engine.sources import binance_vision, coinbase, kraken, coingecko  # noqa: E402,F401

RAW = {  # 참고용: 계획에서 제외한 엔드포인트도 접속 여부만 기록
    "api.binance.com": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=2",
    "api.upbit.com": "https://api.upbit.com/v1/candles/minutes/60?market=KRW-BTC&count=2",
    "okx.com": "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=1H&limit=2",
}

results = []
for name, fn in SOURCES:
    for iv, bars in (("1h", 300), ("4h", 300), ("1d", 300)):
        t0 = time.time()
        try:
            df = finalize(fn("BTC", iv, bars))
            res = {"source": name, "interval": iv, "ok": True, "rows": len(df),
                   "last": df.index[-1].isoformat(), "close": float(df["close"].iloc[-1])}
        except Exception as e:  # noqa: BLE001
            res = {"source": name, "interval": iv, "ok": False, "error": str(e)[:160]}
        res["sec"] = round(time.time() - t0, 2)
        results.append(res)
        print(("OK  " if res["ok"] else "FAIL"), name, iv, res.get("rows", ""), res.get("last", res.get("error", "")))
for name, url in RAW.items():
    try:
        code = requests.get(url, timeout=15).status_code
    except Exception as e:  # noqa: BLE001
        code = f"ERR {type(e).__name__}"
    print("RAW ", name, code)
    results.append({"source": name, "raw_status": code})
Path("probe_result.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
