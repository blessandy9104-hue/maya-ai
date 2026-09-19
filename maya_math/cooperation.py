"""Cooperative adjudication mathematics (Batch 8H extension).

Deterministic math for combining assessments from multiple independent
interpretation engines. Kept in the substrate so the cooperative orchestrator
can pool confidences without inventing truth: everything here is a bounded
[0, 1] composition of caller-supplied values, fails closed on non-finite
input, and never fabricates probability mass.

Conventions:
- ``concordance(a, b)`` = 1 - |a - b|, clamped to [0, 1]. Two identical
  assessments have concordance 1.0; two opposite have 0.0.
- ``agreement_weighted_combine(primary, secondary)`` pools two confidence
  values. At high concordance it approaches the agreeing value; at low
  concordance it approaches the conservative minimum (a contested answer
  must not be reported more confidently than either source alone).
- ``label_similarity(a, b)`` = Jaccard index over tag sets (supporting/
  disputing epistemic source labels), 1.0 for identical sets, 0.0 for
  disjoint non-empty sets, 1.0 for two empty sets.
"""
from __future__ import annotations

import math

from .core import _as_finite, clamp01


def concordance(a, b):
    """Normalized agreement between two [0, 1] assessments."""
    a = _as_finite(a)
    b = _as_finite(b)
    if a < 0.0 or a > 1.0 or b < 0.0 or b > 1.0:
        return 0.0
    return clamp01(1.0 - abs(a - b))


def agreement_weighted_combine(primary, secondary):
    """Pool two confidence values into a single bounded confidence.

    ``concordance`` controls the blend between the agreeing average and the
    conservative minimum: low concordance → the minimum (a contested answer
    is presumed as strong as its weakest support); high concordance → the
    agreeing average. Monotone, bounded, deterministic.
    """
    primary = _as_finite(primary)
    secondary = _as_finite(secondary)
    if (primary < 0.0 or primary > 1.0 or secondary < 0.0
            or secondary > 1.0):
        return 0.0
    c = concordance(primary, secondary)
    agree = (primary + secondary) / 2.0
    return clamp01(c * agree + (1.0 - c) * min(primary, secondary))


def label_similarity(a, b):
    """Jaccard index over two tag collections (supporting/disputing sets)."""
    try:
        set_a = set(a or ())
        set_b = set(b or ())
    except TypeError:
        return 0.0
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    union = set_a | set_b
    overlap = set_a & set_b
    return float(len(overlap)) / float(len(union))


def pooled_agreement(pairs, threshold=0.8):
    """Fraction of assessment pairs above ``threshold`` concordance.

    Deterministic, bounded; ``pairs`` may be an iterable of ``(a, b)``.
    An empty, None, or malformed pool returns 0.0 (fail closed, not open).
    """
    count = 0
    above = 0
    if not pairs:
        return 0.0
    for pair in pairs:
        try:
            a, b = pair
        except (TypeError, ValueError):
            return 0.0
        c = concordance(a, b)
        count += 1
        if c >= threshold:
            above += 1
    if count == 0:
        return 0.0
    return float(above) / float(count)