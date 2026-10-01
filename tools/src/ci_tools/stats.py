"""Small, dependency-free statistics helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence


def percentile(values: Sequence[float], p: float) -> float | None:
    """Nearest-rank percentile (p in 0..100). Returns None for an empty sequence.

    Nearest-rank is used on purpose: with 20-50 samples it never invents a value that was not observed.
    """
    if not values:
        return None
    if not 0 < p <= 100:
        raise ValueError("p must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(p / 100 * len(ordered))
    return ordered[rank - 1]


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def rnd(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)
