"""Independent signature reference for the controlled runtime launch.

Three of the four signature dimensions are recomputed here from the pure
mathematical definitions only -- no constant is copied from the runtime
implementation, so the oracle cannot drift together with the code:

- ``pattern_state(0.0, 1.0, 0.5)``: one exponential-smoothing blend step,
  ``current + (target - current) * alpha`` = 0.5.
- ``cosine_similarity((1, 0), (1, 0))``: normalized dot product = 1.0.
- ``world_stability([1, 1, 1, 1])``: standard deviation of a constant
  series = 0.0.

The fourth dimension, ``len(CHANNEL_MAX)``, is a pure counting of a
declared ceiling constant and cannot be derived without restating that
constant: it is therefore intentionally self-referential and is validated
only against the runtime's own ``CHANNEL_MAX`` (documented residual).
"""
from __future__ import annotations

import math
from decimal import Decimal


def expected_signature_triple():
    """Independently recomputed (pattern_state, cosine, stability_std)."""
    blended = Decimal("0.0") + (Decimal("1.0") - Decimal("0.0")) * Decimal("0.5")
    pattern_state = float(blended)

    norm_a = math.sqrt(1.0 ** 2 + 0.0 ** 2)
    norm_b = math.sqrt(1.0 ** 2 + 0.0 ** 2)
    cosine = (1.0 * 1.0 + 0.0 * 0.0) / (norm_a * norm_b)

    series = [1.0, 1.0, 1.0, 1.0]
    mean = sum(series) / len(series)
    variance = sum((value - mean) ** 2 for value in series) / len(series)
    stability_std = math.sqrt(variance)

    return (round(pattern_state, 15), round(cosine, 15), round(stability_std, 15))