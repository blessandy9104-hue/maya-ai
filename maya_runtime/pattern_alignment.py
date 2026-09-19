"""Maya Runtime: pattern alignment facade -- deterministic, device-neutral.

Pure delegation to the canonical ``MATH_AGENT`` pattern-* methods.
"""
from __future__ import annotations

from .core import MATH_AGENT


class PatternAlignment:
    """Stateless pattern gateway; outputs confined to [0, 1]."""

    def similarity(self, a, b):
        return MATH_AGENT.pattern_similarity(a, b)

    def state(self, current, target, alpha):
        return MATH_AGENT.pattern_state(current, target, alpha)

    def transition(self, old, new, t):
        return MATH_AGENT.pattern_transition(old, new, t)

    def alignment(self, pattern, state):
        return MATH_AGENT.pattern_alignment(pattern, state)

    def priority(self, value):
        return MATH_AGENT.pattern_priority(value)

    def ok(self, aligned_states):
        return MATH_AGENT.pattern_alignment_ok(aligned_states)

    def spectral(self, series, sample_rate=1.0):
        return MATH_AGENT.spectral_analysis(series, sample_rate)

    def signal_quality(self, series, **kwargs):
        return MATH_AGENT.signal_quality(series, **kwargs)

    def periodicity(self, series):
        return MATH_AGENT.periodicity(series)

    def spectral_alignment(self, a, b):
        return MATH_AGENT.spectral_alignment(a, b)


PATTERN_ALIGNMENT = PatternAlignment()