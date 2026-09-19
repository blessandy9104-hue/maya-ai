"""World-model confidence scoring and output restriction.

Confidence is a fused weight of world-state alignment, evidence
sufficiency, and stability. Below an architect-set floor the loop
restricts the output budget instead of editing facts: a restricted state
reduces confidence-derived attributes toward neutral but never invents
information.
"""
from __future__ import annotations

from ..core import MATH_AGENT, clamp01
from .feature_map import _neutral, ALIGNMENT_FLOOR


class ConfidenceScorer:
    """Fuses world alignment, evidence sufficiency, and stability."""

    floor = ALIGNMENT_FLOOR

    def score(self, state=None, evidence_ok=True, stability=None,
              alignment=None, reference=None):
        stability_v = _neutral(stability if stability is not None
                               else (state or {}).get("stability", 0.0))
        alignment_v = _neutral(alignment if alignment is not None
                               else (state or {}).get("alignment", 0.5))
        evidence = 1.0 if evidence_ok else clamp01(alignment_v)
        confidence = MATH_AGENT.task_fuse(
            alignment_v, stability_v, evidence).get("fused", 0.0)
        confidence = clamp01(_neutral(confidence))
        restricted = confidence < self.floor
        output_budget = clamp01(confidence / max(self.floor, 1e-12))
        return {
            "confidence": confidence,
            "restricted": bool(restricted),
            "output_budget": output_budget,
            "restriction": clamp01(1.0 - output_budget),
            "floor": self.floor,
            "ok": bool(not restricted),
        }

    def restrict(self, confidence=None, output_budget=None, scalar=None):
        """Scale an output scalar by the budget; restricted frames yield a
        neutral value instead of a fabricated one."""
        budget = clamp01(_neutral(
            output_budget if output_budget is not None
            else confidence if confidence is not None else 0.0))
        value = clamp01(_neutral(scalar))
        if budget < self.floor:
            return 0.0
        return clamp01(value * budget)


CONFIDENCE = ConfidenceScorer()


def score(*args, **kwargs):
    return CONFIDENCE.score(*args, **kwargs)