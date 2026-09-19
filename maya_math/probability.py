"""Probability / belief-domain operations of the substrate.

Uncertainty is represented honestly: a normalized belief distribution over an
outcome space, and deterministic composition rules. Belief scores are for
*composition and comparison*; they never assert truth and never fabricate
facts. The tier→belief constants are an explicit modelling convention (see
``TIER_BELIEF``); the composition rule mirrors the bus convention
(min-if-conflict, max-if-agree) exactly so substrate output is consistent with
the rest of Maya's state handling.
"""
from __future__ import annotations

import math

from .core import _as_finite, clamp01, normalize_weights

# Explicit modelling convention for the evidence store's string tiers.
# These values exist only to give composed distributions shape; they are not
# calibrated external probabilities and must never be reported as such.
TIER_BELIEF = {"low": 0.35, "medium": 0.60, "high": 0.85}

ALLOWED_TIERS = frozenset(TIER_BELIEF)


def tier_belief(tier):
    """Belief weight for an evidence-store confidence tier.

    Raises ``ValueError`` for anything not in ``ALLOWED_TIERS`` (a hard error
    is deliberate: an unknown tier must never silently become a fabricated
    probability).
    """
    if tier not in TIER_BELIEF:
        raise ValueError(
            "unknown confidence tier %r; allowed: %s"
            % (tier, ", ".join(sorted(ALLOWED_TIERS))))
    return TIER_BELIEF[tier]


def combine_confidences(agreeing: list, conflicting: list) -> float:
    """Compose belief values the way the state bus combines confidence.

    Rule (mirrors ``bus.merge_state``): when any conflicting evidence exists
    the result is the minimum of the conflicting beliefs; otherwise it is the
    maximum of the agreeing beliefs. Degrades to 0.0 for empty input or
    non-finite values.
    """
    conflicting = [_as_finite(v) for v in conflicting]
    agreeing = [_as_finite(v) for v in agreeing]
    if conflicting:
        return clamp01(min(conflicting))
    return clamp01(max(agreeing) if agreeing else 0.0)


def belief_distribution(beliefs):
    """Normalize a list of belief values into a probability mass function.

    Passes through :func:`maya_math.core.normalize_weights` (which raises on
    negative/non-finite weights or a zero total), so a distribution is always
    a valid, exactly-summing-to-one PMF.
    """
    return normalize_weights(list(beliefs))


def distribution_mean(pmf, values):
    """Expectation ``sum(p_i * x_i)`` of a PMF over given outcome values."""
    if len(pmf) != len(values) or not pmf:
        raise ValueError("pmf and values must be non-empty and equal length")
    return math.fsum(_as_finite(p) * _as_finite(x) for p, x in zip(pmf, values))



def distribution_entropy(pmf):
    """Shannon entropy (bits) of a PMF; convenience over
    ``maya_math.information.entropy`` for composed distributions."""
    from .information import entropy_bits
    return entropy_bits(pmf)