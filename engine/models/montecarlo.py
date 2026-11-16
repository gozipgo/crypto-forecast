"""(a) 몬테카를로: 필터드 히스토리컬 시뮬레이션(FHS) + 블록 부트스트랩.

1) 일간 로그수익률 r_t 를 EWMA 변동성 σ_t(λ=0.94, t-1까지 정보)로 나눠 표준화 잔차 z_t 를 만든다.
2) 같은 날의 고가/저가 이탈폭도 σ_t 로 표준화(u_t, d_t)해 함께 뽑는다 → 지지/저항 '도달' 확률에 사용.
3) 잔차를 5일 블록으로 복원추출(자기상관·변동성 군집 일부 보존)하고,
   현재 변동성에서 장기 변동성으로 서서히 돌아가는 σ 경로를 곱한다.
4) 잔차 평균은 0으로 맞춘다(과거 강세장의 추세를 미래에 그대로 가정하지 않기 위해).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import HORIZON_MAX, Paths

LAMBDA = 0.94
BLOCK = 5
PHI = 0.98          # 변동성 평균회귀 속도(일), 반감기 ≈ 34일
LR_WINDOW = 730     # 장기 변동성 추정 구간(일)


def prepare(daily: pd.DataFrame) -> dict:
    """완성된 일봉으로 표준화 잔차 풀과 현재 σ를 만든다(백테스트에서도 t 시점까지 잘라 호출)."""
    c, h, lo = (np.log(daily[k].to_numpy()) for k in ("close", "high", "low"))
    r = np.diff(c)
    var = np.empty_like(r)
    var[0] = np.var(r[:30]) if len(r) > 30 else r[0] ** 2
    for t in range(1, len(r)):
        var[t] = LAMBDA * var[t - 1] + (1 - LAMBDA) * r[t - 1] ** 2
    sig = np.sqrt(var)
    warm = 60
    z = r[warm:] / sig[warm:]
    u = (h[1:] - c[1:])[warm:] / sig[warm:]
    d = (lo[1:] - c[1:])[warm:] / sig[warm:]
    sig_next = np.sqrt(LAMBDA * var[-1] + (1 - LAMBDA) * r[-1] ** 2)
    sig_lr = np.sqrt(np.mean(r[-LR_WINDOW:] ** 2))
    return {"z": z - z.mean(), "u": u, "d": d, "sig_next": sig_next, "sig_lr": sig_lr}


def simulate(prep: dict, n_paths: int = 10000, seed: int = 0) -> Paths:
    rng = np.random.default_rng(seed)
    z, u, d = prep["z"], prep["u"], prep["d"]
    nb = -(-HORIZON_MAX // BLOCK)
    starts = rng.integers(0, len(z) - BLOCK, size=(n_paths, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)).reshape(n_paths, -1)[:, :HORIZON_MAX]
    k = np.arange(HORIZON_MAX)
    v_lr, v0 = prep["sig_lr"] ** 2, prep["sig_next"] ** 2
    sig_path = np.sqrt(v_lr + PHI ** k * (v0 - v_lr))
    ret = z[idx] * sig_path
    close = np.cumsum(ret, axis=1)
    high = close + u[idx] * sig_path
    low = close + d[idx] * sig_path
    return Paths(close, high, low)


def forecast(daily: pd.DataFrame, n_paths: int = 10000, seed: int = 0) -> tuple[Paths, dict]:
    prep = prepare(daily)
    info = {
        "sigma_daily_now": round(float(prep["sig_next"]), 5),
        "sigma_daily_longrun": round(float(prep["sig_lr"]), 5),
        "n_paths": n_paths,
        "block": BLOCK,
        "residual_pool": int(len(prep["z"])),
    }
    return simulate(prep, n_paths, seed), info
