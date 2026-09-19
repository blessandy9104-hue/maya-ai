"""Relevance and alignment: the fused persona must stay grounded in the
world model. Relevance is the alignment between the fused channel vector
and the world-state constraint pattern; below the architect floor the
relevance report marks the frame for restriction by the safety stage.
"""
from __future__ import annotations

from ..core import MATH_AGENT, WORLD_STATE_PATTERNS, clamp01
from .feature_map import _neutral, _as_vector, ALIGNMENT_FLOOR


class Relevance:
    """Validates fusion output against world-model constraints."""

    floor = ALIGNMENT_FLOOR

    def evaluate(self, fused_channels=None, state=None, reference=None,
                 constraint_vector=None):
        channels = fused_channels or {}
        vector = _as_vector([
            channels.get("expression", 0.0),
            channels.get("viseme", 0.0),
            channels.get("micro", 0.0),
        ])
        if constraint_vector is None and reference is None:
            constraint = _as_vector(WORLD_STATE_PATTERNS["stable_equilibrium"])[:3]
        else:
            constraint = _as_vector(constraint_vector or reference)
        constraint = tuple(float(c) for c in constraint)
        alignment = clamp01(_neutral(
            MATH_AGENT.pattern_alignment(vector, constraint)))
        drift = _neutral((state or {}).get("drift", 0.0))
        stability = _neutral((state or {}).get("stability", 0.0))
        ok = bool(alignment >= self.floor and drift <= 0.35)
        return {
            "alignment": alignment,
            "drift": drift,
            "stability": stability,
            "ok": ok,
            "floor": self.floor,
            "reason": None if ok else (
                "below_alignment_floor" if alignment < self.floor
                else "drift_beyond_tolerance"),
        }

    def aligned(self, fused_channels=None, state=None, **kwargs):
        return self.evaluate(fused_channels, state, **kwargs)["ok"]


RELEVANCE = Relevance()


def evaluate(*args, **kwargs):
    return RELEVANCE.evaluate(*args, **kwargs)