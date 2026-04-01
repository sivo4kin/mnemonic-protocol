from __future__ import annotations

import math
from operator import mul as _mul
from typing import List, Tuple


def dot(a: List[float], b: List[float]) -> float:
    return sum(map(_mul, a, b))


def l2_norm(vec: List[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def normalize(vec: List[float]) -> Tuple[List[float], float]:
    norm = l2_norm(vec)
    if norm == 0.0:
        return [0.0 for _ in vec], 0.0
    return [x / norm for x in vec], norm


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
