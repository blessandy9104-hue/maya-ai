"""Analytic primitives of the mathematical substrate.

Canonical numerical helpers shared across the substrate and available to any
Maya subsystem. Pinned semantics are documented per function. Existing
authoritative implementations in ``maya_identity`` (``rig_math``,
``math_coordinator``, ``visual_state``, ``semantic_interpretation``) remain
unchanged and authoritative for their own call sites; where a convention is
mirrored (``clamp``, ``lerp``, ``cosine_similarity``, ``exp_smooth``) the
behaviour documented here is the substrate-consistent contract.

Determinism: pure functions of their inputs. Non-finite inputs degrade to the
documented safe values; they never raise unless a silent answer would corrupt
a caller's invariant (``normalize_weights``).
"""
from __future__ import annotations

import math

DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi

_TOL = 1e-9


def finite_ok(value) -> bool:
    """True when ``value`` is finite (or not a float, e.g. an int)."""
    return not isinstance(value, float) or math.isfinite(value)


def _as_finite(value, default=0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return float(default)


def clamp(value, low, high):
    """Clamp ``value`` into ``[low, high]`` (inclusive), non-finite -> low."""
    value = _as_finite(value, default=low)
    return low if value < low else high if value > high else value


def clamp01(value):
    """Clamp into ``[0.0, 1.0]``; non-finite degrades to 0.0."""
    value = _as_finite(value, default=0.0)
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def lerp(a, b, t):
    """Linear interpolation ``a + (b - a) * t``, unclamped ``t``."""
    return _as_finite(a) + (_as_finite(b) - _as_finite(a)) * _as_finite(t)


def stable_lerp(a, b, t):
    """Linear interpolation with ``t`` clamped to [0, 1] (the substrate
    default; identical to the wireframe stable-interpolation contract)."""
    t = clamp01(t)
    return _as_finite(a) + (_as_finite(b) - _as_finite(a)) * t


def smoothstep(edge0, edge1, x):
    """Hermite smoothstep on ``[edge0, edge1]``; returns 0.0 below, 1.0 above,
    non-finite x degrades to 0.0. Matches the standard GLSL-style definition
    mirrored by ``math_coordinator.smoothstep``."""
    x = _as_finite(x, default=0.0)
    if edge1 <= edge0:
        return 0.0
    t = clamp01((x - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def exp_smooth(current, target, alpha):
    """Exponential smoothing ``current + alpha * (target - current)`` with
    ``alpha`` clamped to [0, 1]; the same convention as the wireframe
    ``exp_smooth`` and ``world_drift`` smoothing. Non-finite inputs degrade
    to neutral (current 0.0 / target 0.0)."""
    current = _as_finite(current)
    target = _as_finite(target)
    a = clamp01(alpha)
    return current + (target - current) * a


def magnitude(v):
    """Euclidean length of a vector (any length); non-finite entries degrade
    to 0, so a broken vector measures 0 rather than raising."""
    if v is None:
        return 0.0
    return math.sqrt(sum(_as_finite(x) * _as_finite(x) for x in v))


def cosine_similarity(a, b):
    """Cosine of the angle between two equal-length vectors. Zero-length or
    malformed inputs yield 0.0 (mirrors the wireframe ``cosine_similarity``
    non-finite convention)."""
    if a is None or b is None or len(a) != len(b) or not a:
        return 0.0
    if not all(finite_ok(x) for x in a) or not all(finite_ok(x) for x in b):
        return 0.0
    denom_a = math.sqrt(sum(float(x) * float(x) for x in a))
    denom_b = math.sqrt(sum(float(y) * float(y) for y in b))
    if denom_a <= 0.0 or denom_b <= 0.0:
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    return dot / (denom_a * denom_b)


def weighted_mean(values, weights):
    """Weighted arithmetic mean with deterministic guards. Returns 0.0 when
    ``values`` is empty or the total weight is not positive. Non-finite values
    or weights degrade to 0.0."""
    if not values or len(values) != len(weights):
        return 0.0
    acc = 0.0
    total = 0.0
    for value, weight in zip(values, weights):
        v = _as_finite(value)
        w = _as_finite(weight)
        if w < 0.0:
            w = 0.0
        acc += v * w
        total += w
    if total <= 0.0:
        return 0.0
    return acc / total


def normalize_weights(weights):
    """Normalize a list of non-negative weights so the sum is exactly 1.0.

    Raises ``ValueError`` on empty input, negative weights, non-finite weights
    or a zero total: a silently "normalized" corrupt distribution would poison
    every probability/belief consumer, so this is the one primitive that is
    loud instead of safe-neutral.
    """
    if not weights:
        raise ValueError("normalize_weights requires a non-empty list")
    cleaned = []
    for weight in weights:
        w = float(weight)
        if w < 0.0 or not math.isfinite(w):
            raise ValueError("normalize_weights rejects negative or "
                             "non-finite weights")
        cleaned.append(w)
    total = math.fsum(cleaned)
    if total <= 0.0 or not math.isfinite(total):
        raise ValueError("normalize_weights requires a positive total weight")
    scaled = [w / total for w in cleaned]
    # Exact-sum correction on the last entry: fsum(prefix) + last == 1.0.
    prefix = math.fsum(scaled[:-1])
    scaled[-1] = 1.0 - prefix
    if scaled[-1] < 0.0 or scaled[-1] > 1.0:
        raise ValueError("normalize_weights produced an out-of-range entry")
    return scaled


def population_variance(values):
    """Population variance, two-pass for stability. Empty/small inputs or
    non-finite entries degrade to 0.0."""
    values = [_as_finite(v) for v in values]
    if not values:
        return 0.0
    size = len(values)
    m = math.fsum(values) / size
    acc = math.fsum((v - m) * (v - m) for v in values)
    return acc / size


def population_std(values):
    """Population standard deviation (see ``population_variance``)."""
    return math.sqrt(population_variance(values))


def _fsum_ok(items):
    return all(math.isfinite(x) for x in items)


def quantize(value, grid_count, low=0.0, high=1.0):
    """Map ``value`` into one of ``grid_count`` index buckets on [low, high].

    Deterministic flattening: ``index = floor(frac * grid_count + 0.5)`` with
    ``frac`` clamped to [0, 1]; non-finite values and degenerate ranges degrade
    to bucket 0. Documented convention: the same grid an existing Maya
    layer (``world_index`` / one-scale bucket) uses, expressed canonically.
    """
    grid_count = max(0, int(grid_count))
    if grid_count == 0 or high <= low:
        return 0
    frac = _as_finite(value)
    frac = 0.0 if frac < low else 1.0 if frac > high else (frac - low) / (high - low)
    index = int(math.floor(frac * grid_count + 0.5))
    return max(0, min(grid_count, index))


def grid_value(index, grid_count, low=0.0, high=1.0):
    """Bucket midpoint for an index produced by :func:`quantize`."""
    grid_count = max(0, int(grid_count))
    if grid_count == 0 or high <= low:
        return low
    index = max(0, min(grid_count, int(index)))
    step = (high - low) / grid_count
    return low + step * (index + 0.5)