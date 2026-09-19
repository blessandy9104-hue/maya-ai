"""Information-theory domain of the substrate.

Shannon information measures over discrete distributions (base-2, "bits").
Conventions (documented, externally validated): 0 log 0 := 0; ``validated``
distributions must be non-negative and finite with positive sum. Measures
describe the structure of uncertainty — they never rank truth or fabricate
evidence.
"""
from __future__ import annotations

import math

from .core import _as_finite


def validate_pmf(pmf):
    """Validate a probability mass function (list of non-negative, finite
    values with positive total). Raises ``ValueError`` otherwise."""
    if not isinstance(pmf, (list, tuple)) or not pmf:
        raise ValueError("pmf must be a non-empty sequence")
    total = 0.0
    for p in pmf:
        v = _as_finite(p)
        if v < 0.0:
            raise ValueError("pmf entries must be non-negative")
        total += v
    if total <= 0.0:
        raise ValueError("pmf total must be positive")
    return True


def _log2x(p):
    """``-p * log2(p)`` with the 0 log 0 := 0 convention."""
    if p <= 0.0:
        return 0.0
    return -p * math.log2(p)


def entropy(pmf, base=2.0):
    """Shannon entropy of a PMF in ``base`` units (default bits, base=2).

    The PMF is normalized internally by its total, so any non-negative finite
    weights may be passed. ``entropy_bits`` is the base-2 form.
    """
    validate_pmf(pmf)
    total = math.fsum(_as_finite(v) for v in pmf)
    normalized = [_as_finite(v) / total for v in pmf]
    units = math.log(2.0) / math.log(base) if base > 0.0 and base != 1.0 else 1.0
    return math.fsum(_log2x(p) for p in normalized) * units


def entropy_bits(pmf):
    """Shannon entropy in bits (base 2)."""
    return entropy(pmf, base=2.0)


def normalized_entropy(pmf):
    """Entropy normalized to [0, 1]: ``H / log2(n)`` for ``n > 1``, 0.0 for
    single-outcome distributions (a sure outcome carries zero information)."""
    validate_pmf(pmf)
    size = len(pmf)
    if size <= 1:
        return 0.0
    total = math.fsum(_as_finite(v) for v in pmf)
    normalized = [_as_finite(v) / total for v in pmf]
    h = math.fsum(_log2x(p) for p in normalized)
    max_h = math.log2(size)
    return max(0.0, min(1.0, h / max_h))


def outcome_information(probability):
    """Self-information ``-log2(p)`` of a single outcome; 0 for p=1,
    positive otherwise; ``math.inf`` for p=0."""
    p = _as_finite(probability)
    if p <= 0.0:
        return math.inf
    if p >= 1.0:
        return 0.0
    return -math.log2(p)


def information_gain(prior_pmf, branches):
    """Expected information gain of a split: ``H(prior) - sum(w_i * H(pmf_i))``
    where ``branches`` is a list of ``(weight, pmf)`` pairs (weights need not
    sum to 1; they are normalized). Determines how much residual uncertainty a
    subdivision removes — the substrate's basis for evidence-prioritization
    reasoning.
    """
    validate_pmf(prior_pmf)
    if not branches:
        return 0.0
    h_prior = entropy_bits(prior_pmf)
    weights = [(_as_finite(w), pmf) for w, pmf in branches]
    total_w = math.fsum(w for w, _ in weights)
    if total_w <= 0.0:
        return 0.0
    h_cond = math.fsum(
        (w / total_w) * entropy_bits(pmf) for w, pmf in weights)
    return max(0.0, h_prior - h_cond)


def kl_divergence(p, q):
    """KL divergence ``sum p_i log2(p_i/q_i)`` (bits). ``p`` values with zero
    probability contribute nothing (0 log 0 := 0); a zero in ``q`` where ``p``
    is positive yields ``math.inf`` (explicit, not silent)."""
    validate_pmf(pmf=p)
    validate_pmf(pmf=q)
    if len(p) != len(q):
        raise ValueError("KL divergence requires equal-length PMFs")
    total_p = math.fsum(_as_finite(v) for v in p)
    total_q = math.fsum(_as_finite(v) for v in q)
    acc = 0.0
    for a, b in zip(p, q):
        pa = _as_finite(a) / total_p
        qa = _as_finite(b) / total_q
        if pa > 0.0:
            if qa <= 0.0:
                return math.inf
            acc += pa * math.log2(pa / qa)
    return acc