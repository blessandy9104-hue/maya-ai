"""Meaning: the stabilized internal vector produced after state, persona
fusion, alignment, and safety have all run. Meaning does not exist before
those stages, and language is generated only from meaning.
"""
from __future__ import annotations

from ..core import MATH_AGENT, clamp01
from .feature_map import _neutral, _as_vector


class MeaningComputer:
    """Computes meaning; refuses to run before its prerequisites."""

    prerequisites = ("state", "fusion", "alignment", "safety")

    def compute(self, state=None, fusion=None, alignment=None, safety=None,
                reference=None, alpha=0.15):
        missing = [p for p in self.prerequisites if
                   not state or not fusion or not alignment or not safety]
        if missing:
            raise RuntimeError(
                "meaning requires %s; measured before fusion/safety is a "
                "violation" % ", ".join(sorted(set(missing))))
        state = state or {}
        fusion = fusion or {}
        safety = safety or {}
        emotional = _neutral(state.get("emotional_intensity", 0.0))
        clarity = _neutral(state.get("cognitive_clarity", 0.0))
        world_alignment = _neutral(alignment.get("alignment")
                                   if isinstance(alignment, dict)
                                   else alignment)
        stability = _neutral(state.get("stability", 0.0))

        fused = MATH_AGENT.task_fuse(
            emotional, clarity, world_alignment).get("fused", 0.0)
        if reference is not None:
            fused = MATH_AGENT.pattern_state(
                fused, _neutral(reference), clamp01(alpha))
        meaning_vector = _as_vector([fused, stability, world_alignment])
        ok = bool(state.get("ok", False)) and bool(safety.get("ok", True))
        return {
            "meaning_scalar": clamp01(fused),
            "meaning_vector": tuple(round(float(v), 12) for v in meaning_vector),
            "emotional_component": clamp01(emotional),
            "cognitive_component": clamp01(clarity),
            "world_component": clamp01(world_alignment),
            "stability": clamp01(stability),
            "ok": ok,
        }


MEANING = MeaningComputer()


def compute(*args, **kwargs):
    return MEANING.compute(*args, **kwargs)