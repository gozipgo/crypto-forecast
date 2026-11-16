import json
from pathlib import Path

import numpy as np
import pytest

from engine import backtest
from engine.models import analog, montecarlo
from engine.models.common import HORIZON_MAX, Paths, recalibrate, summarize
from engine.schema import validate
from tests.conftest import make_ohlcv


@pytest.fixture(scope="module")
def daily():
    return make_ohlcv(n=1500, seed=3)


def test_mc_paths_shape_and_center(daily):
    p, info = montecarlo.forecast(daily, n_paths=5000)
    assert p.close.shape == (5000, HORIZON_MAX)
    assert (p.high >= p.close - 1e-12).all() and (p.low <= p.close + 1e-12).all()
    assert abs(np.median(p.close[:, -1])) < 0.05  # 잔차 평균 0 → 중앙값이 현재가 근처
    assert info["sigma_daily_now"] > 0


def test_mc_no_lookahead(daily):
    """t 이후 데이터를 바꿔도 t 시점 준비값은 같아야 한다."""
    t = 1000
    a = montecarlo.prepare(daily.iloc[: t + 1])
    d2 = daily.copy()
    d2.iloc[t + 1:] *= 3
    b = montecarlo.prepare(d2.iloc[: t + 1])
    assert np.allclose(a["z"], b["z"]) and a["sig_next"] == b["sig_next"]


def test_analog_no_lookahead(daily):
    """analog: t 시점 검색 결과는 t 이후 가격과 무관해야 한다(특징·후보·결과 경로 모두)."""
    t = 1200

    def run(df):
        F = analog.features(df)
        fwd = analog.forward_paths(df)
        p, rows, _ = analog.search(F[analog.FEATURES].to_numpy(), F["sig"].to_numpy(), t, fwd,
                                   np.random.default_rng(0), 500)
        return p, rows

    p1, r1 = run(daily)
    d2 = daily.copy()
    d2.iloc[t + 1:, :4] *= 1.7
    p2, r2 = run(d2)
    assert r1 == r2
    assert max(r1) + HORIZON_MAX <= t
    assert np.allclose(p1.close, p2.close)


def test_summarize_probabilities(daily):
    p, _ = montecarlo.forecast(daily, n_paths=4000)
    lv = [{"price": 90.0, "type": "support"}, {"price": 120.0, "type": "resistance"}]
    s = summarize(p, 100.0, lv)
    for h in ("7", "14", "30"):
        assert abs(sum(x["prob"] for x in s["horizons"][h]["scenarios"]) - 1) < 0.003
        q = s["horizons"][h]["quantiles"]
        assert q["p2_5"] < q["p10"] < q["p25"] < q["p50"] < q["p75"] < q["p90"] < q["p97_5"]
    # 도달 확률은 기간이 길수록 커진다
    t7 = s["horizons"]["7"]["level_touch"][0]["prob"]
    t30 = s["horizons"]["30"]["level_touch"][0]["prob"]
    assert t30 >= t7


def test_recalibration_narrows_inner_band():
    rng = np.random.default_rng(0)
    p = Paths(rng.normal(0, 1, (20000, HORIZON_MAX)), np.zeros((20000, HORIZON_MAX)), np.zeros((20000, HORIZON_MAX)))
    p.high = p.close + 0.1
    p.low = p.close - 0.1
    c = backtest.RECAL_KNOTS
    c_raw = c.copy()
    c_raw[1:-1] = np.clip(c[1:-1] * 0.8, 0, 1)  # 모든 구간을 원래의 80% 수준으로
    rc = {"c": c.tolist(), "c_raw": c_raw.tolist()}
    q = recalibrate(p, {7: rc, 14: rc, 30: rc})
    w_before = np.subtract(*np.quantile(p.close[:, 13], [0.75, 0.25]))
    w_after = np.subtract(*np.quantile(q.close[:, 13], [0.75, 0.25]))
    assert w_after < w_before * 0.85
    assert np.allclose(q.high - q.close, 0.1)
    assert abs(np.median(q.close[:, 13]) - np.median(p.close[:, 13])) < 0.02


def test_backtest_perfect_model_is_calibrated():
    """실제값이 예측 분포에서 뽑힌 경우 커버리지는 목표와 같아야 한다."""
    rng = np.random.default_rng(1)
    S = np.sort(rng.normal(0, 1, (3000, 2000)), axis=1)
    y = rng.normal(0, 1, 3000)
    c = backtest.coverage_from_level(backtest.fold(backtest.pit(S, y)))
    assert abs(c["cov50"] - 0.5) < 0.03 and abs(c["cov80"] - 0.8) < 0.03 and abs(c["cov95"] - 0.95) < 0.015


def test_generated_json_matches_schema():
    out = Path("site/data")
    if not (out / "manifest.json").exists():
        pytest.skip("site/data 없음 — python -m engine.run 먼저 실행")
    validate(json.loads((out / "manifest.json").read_text(encoding="utf-8")), "manifest")
    validate(json.loads((out / "summary.json").read_text(encoding="utf-8")), "summary")
    for a in ("BTC", "ETH"):
        validate(json.loads((out / a / "forecast.json").read_text(encoding="utf-8")), "forecast")
        validate(json.loads((out / a / "candles_1d.json").read_text(encoding="utf-8")), "candles")
