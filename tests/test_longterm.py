import numpy as np
import pandas as pd

from engine.models import longterm as lt
from engine.sources.base import resample_calendar
from tests.conftest import make_ohlcv


def test_calendar_bars_align():
    d = make_ohlcv(n=400, start="2024-01-03")
    w = resample_calendar(d, "1w")
    m = resample_calendar(d, "1M")
    assert set(w.index.day_of_week) == {0}          # 월요일 시작
    assert set(m.index.day) == {1}                   # 1일 시작
    wk = w.index[3]
    part = d[(d.index >= wk) & (d.index < wk + pd.Timedelta(days=7))]
    assert w.loc[wk, "high"] == part["high"].max() and w.loc[wk, "close"] == part["close"].iloc[-1]


def test_longterm_forecast_structure():
    daily = make_ohlcv(n=2000, seed=4)
    price = float(daily["close"].iloc[-1])
    now = daily.index[-1] + pd.Timedelta(hours=12)
    bs = {"1w": resample_calendar(daily, "1w").index[-1], "1M": resample_calendar(daily, "1M").index[-1]}
    lv = [{"price": price * 0.8, "type": "support"}, {"price": price * 1.3, "type": "resistance"}]
    r = lt.forecast(daily, price, now, bs, lv, n_paths=1500)
    assert abs(sum(g["prob"] for g in r["scenario_groups"]) - 1) < 0.01
    probs = [g["prob"] for g in r["scenario_groups"]]
    assert probs == sorted(probs, reverse=True)
    assert len(r["top_scenarios"]) == 2
    for g in r["top_scenarios"]:
        for iv in ("1w", "1M"):
            c = g["candles"][iv]
            assert c["t"][0] > int(bs[iv].timestamp())
            assert all(h >= max(o, cl) - 1e-6 and l <= min(o, cl) + 1e-6 for o, h, l, cl in zip(c["o"], c["h"], c["l"], c["c"]))
        assert len(g["candles"]["1M"]["t"]) >= 59
    for h, v in r["horizons"].items():
        q = v["quantiles"]
        assert q["p2_5"] < q["p25"] < q["p50"] < q["p75"] < q["p97_5"]
        assert abs(sum(s["prob"] for s in v["scenarios"]) - 1) < 0.003
    # 넓어지는 분포: 5년 폭 > 1년 폭
    w = lambda h: np.log(r["horizons"][h]["quantiles"]["p90"] / r["horizons"][h]["quantiles"]["p10"])  # noqa: E731
    assert w("1826") > w("365") > w("91")
    # fan 시각은 봉 시작 시각과 맞아야 한다(가상 캔들과 같은 격자)
    fw = [p["t"] for p in r["fan"]["1w"]]
    assert all((t - fw[0]) % (7 * 86400) == 0 for t in fw)


def test_longterm_no_lookahead():
    daily = make_ohlcv(n=1500, seed=6)
    t = 1200
    a = lt.returns_pool(daily.iloc[: t + 1])
    d2 = daily.copy()
    d2.iloc[t + 1:] *= 5
    b = lt.returns_pool(d2.iloc[: t + 1])
    assert np.allclose(a["r"], b["r"])


def test_drift_variants():
    daily = make_ohlcv(n=1600, seed=8, drift=0.001)
    price = float(daily["close"].iloc[-1])
    bs = {"1w": resample_calendar(daily, "1w").index[-1], "1M": resample_calendar(daily, "1M").index[-1]}
    r = lt.forecast(daily, price, daily.index[-1] + pd.Timedelta(hours=1), bs, [], n_paths=1200)
    v = r["variants"]
    assert r["default_variant"] == "shrunk" and r["horizons"] == v["shrunk"]["horizons"]
    med = {k: v[k]["horizons"]["1826"]["quantiles"]["p50"] for k in v}
    assert med["zero"] < med["shrunk"] < med["historical"]       # 추세가 클수록 중앙값이 높다
    # 추세는 모든 경로를 같은 기울기로 옮기므로 묶음 비율은 같다
    assert [g["prob"] for g in v["zero"]["scenario_groups"]] == [g["prob"] for g in v["historical"]["scenario_groups"]]
    assert lt.drift(daily, "zero") == 0
    assert abs(lt.drift(daily.iloc[:1001], "historical") - lt.drift(daily, "historical")) > 0  # 시점까지의 데이터만 사용
