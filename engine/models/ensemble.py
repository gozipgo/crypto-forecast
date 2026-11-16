"""(c) 혼합: 두 모델의 경로를 가중치대로 섞는다(기본 50:50)."""
import numpy as np

from .common import Paths


def mix(a: Paths, b: Paths, w_a: float = 0.5, n: int = 8000, seed: int = 2) -> Paths:
    rng = np.random.default_rng(seed)
    na = int(round(n * w_a))
    return Paths.concat([a.subsample(na, rng), b.subsample(n - na, rng)])
