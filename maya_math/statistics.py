"""Statistics domain of the substrate.

Deterministic, bounded descriptive statistics with stable computation and
documented guard behaviour for empty or non-finite input. Uses two-pass sums
and ``math.fsum``; quantiles use the classic **nearest-rank** method
(deterministic, order-stable); streaming statistics use the standard Welford
single-pass update (identical results to the two-pass form up to float
rounding, verified by the oracle).
"""
from __future__ import annotations

import math

from .core import _as_finite


def _clean(data):
    return [_as_finite(float(v)) for v in data]


def mean(data):
    """Arithmetic mean via ``math.fsum``; 0.0 for empty or non-finite data."""
    data = _clean(data)
    if not data:
        return 0.0
    return math.fsum(data) / len(data)


def population_variance(data):
    """Population variance, two-pass (see core). 0.0 for degenerate input."""
    from .core import population_variance as _pv
    return _pv(data)


def std_deviation(data, ddof=0):
    """Standard deviation with degrees-of-freedom ``ddof`` (0 = population,
    1 = sample). Degenerate input yields 0.0."""
    data = _clean(data)
    size = len(data) - ddof
    if data and size > 0:
        m = math.fsum(data) / len(data)
        acc = math.fsum((v - m) * (v - m) for v in data)
        return math.sqrt(acc / size)
    return 0.0


def sample_variance(data):
    """Sample variance (ddof=1); 0.0 when fewer than 2 observations."""
    data = _clean(data)
    if len(data) >= 2:
        m = math.fsum(data) / len(data)
        acc = math.fsum((v - m) * (v - m) for v in data)
        return acc / (len(data) - 1)
    return 0.0


def population_std(data):
    """Population standard deviation (ddof=0); 0.0 for degenerate input."""
    return std_deviation(data, ddof=0)


def quantile_nearest_rank(data, q):
    """Nearest-rank quantile: returns the k-th smallest value with
    ``k = ceil(q * n)`` (classic textbook rule). ``q`` is clamped to
    [0, 1]; empty data degrades to 0.0. Deterministic and independent of any
    interpolation-policy choice."""
    data = _clean(data)
    if not data:
        return 0.0
    if q <= 0.0:
        return data[0]
    if q >= 1.0:
        return max(data)
    ordered = sorted(data)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def median(data):
    """Median via nearest-rank quantile at 0.5 (deterministic)."""
    return quantile_nearest_rank(data, 0.5)


def data_min(data):
    data = _clean(data)
    return min(data) if data else 0.0


def data_max(data):
    data = _clean(data)
    return max(data) if data else 0.0


def data_range(data):
    """max - min; 0.0 for empty or single-value input."""
    data = _clean(data)
    return (max(data) - min(data)) if len(data) > 1 else 0.0


def coeff_variation(data):
    """Coefficient of variation ``std / mean``; 0.0 when mean is 0.0."""
    data = _clean(data)
    if not data:
        return 0.0
    m = mean(data)
    if math.isclose(m, 0.0, abs_tol=1e-12):
        return 0.0
    return std_deviation(data) / m


def turn_points(data):
    """Indices where the sign of the first difference changes (turning points
    of the discrete series). Ties are skipped (no direction change). This is
    the deterministic monotonic-regime signal that ``world_drift`` consumes
    conceptually; it makes no wall-clock claim."""
    data = _clean(data)
    out = []
    prev_diff = 0.0
    for index in range(1, len(data)):
        diff = data[index] - data[index - 1]
        if diff == 0.0:
            continue
        if prev_diff != 0.0 and (diff > 0.0) != (prev_diff > 0.0):
            out.append(index - 1)
        prev_diff = diff
    return out


class OnlineStats:
    """Welford single-pass mean / variance / std.

    Deterministic given the same update sequence. ``variance`` and ``std``
    report population estimates to match the substrate's two-pass default;
    pass ``ddof=1`` for sample estimates.
    """

    __slots__ = ("_count", "_mean", "_m2")

    def __init__(self):
        self._count = 0
        self._mean = 0.0
        self._m2 = 0.0

    def update(self, value):
        value = _as_finite(value)
        self._count += 1
        delta = value - self._mean
        self._mean += delta / self._count
        self._m2 += delta * (value - self._mean)

    @property
    def count(self):
        return self._count

    @property
    def mean_value(self):
        return self._mean

    def variance(self, ddof=0):
        if self._count - ddof > 0:
            return self._m2 / (self._count - ddof)
        return 0.0

    def std(self, ddof=0):
        return math.sqrt(self.variance(ddof=ddof))