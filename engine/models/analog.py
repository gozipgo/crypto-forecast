"""(b) 유사 패턴 검색(analog / kNN).

매일의 '차트 상태'를 숫자 벡터로 만들고, 지금과 가장 비슷했던 과거 날짜들을 찾아
그 뒤 30일 동안 실제로 어떻게 움직였는지를 모아 분포를 만든다.

- 특징은 모두 변동성으로 나눠 '모양'만 비교(가격 수준·변동성 크기 차이 제거)
- 후보는 결과(30일 뒤)가 이미 확정된 날짜만 → 미래 정보 누수 없음
- 서로 3일 이내로 붙은 이웃은 하나만(같은 국면 중복 방지)
- 이웃의 이후 경로는 (현재 변동성 / 당시 변동성) 비율로 스케일
- 이웃 수가 적어 꼬리가 거칠어지므로, 가중 복원추출 + 작은 잡음(커널 평활)으로 경로 묶음을 만든다
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicators as I
from .common import HORIZON_MAX, Paths, realized_vol

K = 50
MIN_GAP = 3
NOISE = 0.25
FEATURES = ["ret5", "ret20", "ret60", "ma20", "ma50", "ma200", "rsi", "macd", "pctb", "volu", "volpct", "volreg"]


def features(daily: pd.DataFrame) -> pd.DataFrame:
    c = daily["close"]
    lc = np.log(c)
    sig = realized_vol(c, 30)
    ind = I.compute_all(daily)
    f = pd.DataFrame(index=daily.index)
    for n in (5, 20, 60):
        f[f"ret{n}"] = (lc - lc.shift(n)) / (sig * np.sqrt(n))
    for n in (20, 50, 200):
        f[f"ma{n}"] = np.log(c / ind[f"sma{n}"]) / (sig * np.sqrt(n))
    f["rsi"] = ind["rsi14"]
    f["macd"] = ind["hist"] / c / sig
    f["pctb"] = ind["bb_pctb"].clip(-1, 2)
    f["volu"] = np.log(daily["volume"].rolling(20).mean() / daily["volume"].rolling(100).mean())
    f["volpct"] = sig.rolling(365, min_periods=120).rank(pct=True)
    f["volreg"] = np.log(sig / sig.rolling(365, min_periods=120).mean())
    f["sig"] = sig
    return f


def forward_paths(daily: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """각 날짜 s에서 s+1..s+30일의 log(종가/C_s), log(고가/C_s), log(저가/C_s). 미래가 없으면 NaN."""
    lc, lh, ll = (np.log(daily[k].to_numpy()) for k in ("close", "high", "low"))
    n = len(lc)
    out = [np.full((n, HORIZON_MAX), np.nan) for _ in range(3)]
    for j in range(1, HORIZON_MAX + 1):
        out[0][: n - j, j - 1] = lc[j:] - lc[: n - j]
        out[1][: n - j, j - 1] = lh[j:] - lc[: n - j]
        out[2][: n - j, j - 1] = ll[j:] - lc[: n - j]
    return out[0], out[1], out[2]


def search(F: np.ndarray, sig: np.ndarray, t: int, fwd, rng: np.random.Generator,
           n_paths: int = 4000, k: int = K) -> tuple[Paths, list[int], np.ndarray]:
    """F: 특징 행렬(전체), t: 기준 행(지금). 후보 = s + 30 <= t 이고 특징이 유효한 행."""
    cand = np.arange(0, max(t - HORIZON_MAX + 1, 0))
    valid = cand[~np.isnan(F[cand]).any(axis=1)]
    if len(valid) < k * 3 or np.isnan(F[t]).any():
        raise ValueError("유사 패턴 후보 부족")
    X = F[valid]
    mu, sd = X.mean(0), X.std(0) + 1e-9
    dist = np.sqrt((((X - mu) / sd - (F[t] - mu) / sd) ** 2).sum(1))
    order = np.argsort(dist)
    chosen: list[int] = []
    taken = np.zeros(len(F), bool)
    for o in order:
        s = valid[o]
        if taken[max(0, s - MIN_GAP): s + MIN_GAP + 1].any():
            continue
        chosen.append(o)
        taken[s] = True
        if len(chosen) == k:
            break
    ch = np.array(chosen)
    rows, d = valid[ch], dist[ch]
    h = np.median(d) + 1e-9
    w = np.exp(-0.5 * (d / h) ** 2)
    w /= w.sum()
    scale = (sig[t] / sig[rows])[:, None]
    fc, fh, fl = (a[rows] * scale for a in fwd)
    pick = rng.choice(len(rows), size=n_paths, p=w)
    noise = np.cumsum(rng.normal(0, NOISE * sig[t], size=(n_paths, HORIZON_MAX)), axis=1)
    paths = Paths(fc[pick] + noise, fh[pick] + noise, fl[pick] + noise)
    return paths, rows.tolist(), np.c_[d, w]


def forecast(daily: pd.DataFrame, n_paths: int = 4000, seed: int = 1) -> tuple[Paths, dict]:
    F = features(daily)
    fwd = forward_paths(daily)
    rng = np.random.default_rng(seed)
    t = len(daily) - 1
    paths, rows, dw = search(F[FEATURES].to_numpy(), F["sig"].to_numpy(), t, fwd, rng, n_paths)
    h = np.median(dw[:, 0])
    neigh = []
    for r, (d, w) in sorted(zip(rows, dw), key=lambda x: x[1][0])[:10]:
        item = {"date": daily.index[r].strftime("%Y-%m-%d"), "similarity": round(float(np.exp(-0.5 * (d / h) ** 2)), 3),
                "weight": round(float(w), 4)}
        for hz in (7, 14, 30):
            item[f"ret_{hz}d"] = round(float(np.exp(fwd[0][r, hz - 1]) - 1), 4)
        neigh.append(item)
    info = {"k": len(rows), "n_paths": n_paths, "features": FEATURES, "neighbors": neigh,
            "neighbor_prob_up_14d": round(float((fwd[0][rows, 13] > 0).mean()), 3)}
    return paths, info
