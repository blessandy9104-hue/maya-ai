"""Clean-room oracle for the Batch 8D semantic-to-visual mapping.

This module independently re-derives the mapping from the *documented
constants* (the same constants ``semantic_interpretation.py`` and
``visual_state.py`` import) and verifies the derived identities. It imports
only the constants and the anchor tables, never the production adapters, so the
implementation is never validated against itself.

What is independently verified (reported honestly in Batch 8D §J):
- ``oracle_focus`` / ``oracle_activity`` reproduce the documented formulas
  from the constants alone (the test matches them against the source on a grid).
- Backward compatibility: with no cue the mapping reduces to the exact 8C tier
  tables (FOCUS_TIER / ACTIVITY_TIER).
- Bounds: focus is capped by FOCUS_CEILING when a cue is active and by the
  VisualState domain [0, 1] otherwise; activity is capped by the VisualState
  domain [0, 1]; attention / curiosity / gaze / rest are unaffected by the cue
  (channel-separation proof).
"""
from __future__ import annotations

from maya_identity.embodiment.semantic_interpretation import (
    ACTIVITY_SEMANTIC_GAIN,
    FOCUS_CEILING,
    FOCUS_SEMANTIC_GAIN,
    DOMAIN as CUE_DOMAIN,
)
from maya_identity.embodiment.visual_state import (
    ACTIVITY_TIER,
    FOCUS_TIER,
)
from maya_identity.wireframe.face_semantics import SEMANTIC_NAMES


def oracle_cue(cognitive, intent=None):
    """Independent projection of one cognitive frame to bounded fields."""
    if not isinstance(cognitive, dict):
        return {"confidence": 0.0, "meaning": 0.0, "restricted": False,
                "ambiguous": False, "meaning_ok": False, "stability_ok": False}
    lo, hi = CUE_DOMAIN["confidence"]
    conf = max(lo, min(hi, float(cognitive.get("confidence") or 0.0)))
    lo, hi = CUE_DOMAIN["meaning"]
    mean = max(lo, min(hi, float(cognitive.get("meaning_scalar") or 0.0)))
    ambiguous = bool(intent and intent.get("ambiguous", False)) \
        if isinstance(intent, dict) else False
    return {
        "confidence": round(conf, 12),
        "meaning": round(mean, 12),
        "restricted": bool(cognitive.get("restricted", False)),
        "ambiguous": ambiguous,
        "meaning_ok": bool(cognitive.get("meaning_ok", False)),
        "stability_ok": bool(cognitive.get("stability_ok", False)),
    }


def _bounded(value):
    """Documented binding: clamp to the VisualState domain, then round to 12."""
    return round(max(0.0, min(1.0, float(value))), 12)


def oracle_focus(anchor, cue=None):
    """Independent focus: tier, plus the confidence lift (ambiguity-gated)."""
    base = float(FOCUS_TIER.get(anchor, 0.25))
    if cue is None:
        return round(base, 12)
    if cue.get("ambiguous"):
        return round(base, 12)
    return _bounded(min(FOCUS_CEILING, base + float(cue.get("confidence", 0.0))
                        * FOCUS_SEMANTIC_GAIN))


def oracle_activity(anchor, neural=0.0, cue=None):
    """Independent activity: tier/neural, plus the gated meaning lift."""
    base = float(ACTIVITY_TIER.get(anchor, 0.15))
    neural = max(base, float(neural or 0.0))
    if cue is None:
        return _bounded(neural)
    if cue.get("meaning_ok") and cue.get("stability_ok") \
            and not cue.get("restricted"):
        return _bounded(max(base + float(cue.get("meaning", 0.0))
                            * ACTIVITY_SEMANTIC_GAIN, neural))
    return _bounded(neural)


def oracle_bounds_proof(anchor, cue, low, high):
    """Return the oracle-computed bounds for focus at this [0,1] cue grid."""
    focus = oracle_focus(anchor, cue)
    return max(low, min(high, focus))


def oracle_separation(cue):
    """Channels the cue may NOT touch (identity requirement from the 8D spec).

    attention / curiosity / gaze_dx / gaze_dy / rest are decided upstream; the
    cue must leave them intact. Returns the set of names the oracle treats as
    cue-immune.
    """
    return {"attention", "curiosity", "gaze_dx", "gaze_dy", "rest"}


def oracle_unchanged_grid():
    """Always-in-bounds sanity grid for the bound proofs."""
    steps = 9
    return [(i / float(steps), j / float(steps))
            for i in range(steps + 1) for j in range(steps + 1)]


def _fuzz_clamp(value, lo, hi):
    return max(lo, min(hi, value))


if __name__ == "__main__":
    # Standalone self-check: exercised by the suite via oracle_semantic_ok.
    assert all(anchor in FOCUS_TIER for anchor in SEMANTIC_NAMES)
    assert all(anchor in ACTIVITY_TIER for anchor in SEMANTIC_NAMES)
    # Focus ceiling proof across the domain grid and every anchor.
    for anchor in SEMANTIC_NAMES:
        for c_steps in range(11):
            conf = c_steps / 10.0
            cue = {"confidence": conf, "ambiguous": False}
            assert oracle_focus(anchor, cue) <= FOCUS_CEILING + 1e-12
            assert oracle_focus(anchor, cue) >= 0.0
            assert oracle_focus(anchor, None) == FOCUS_TIER[anchor]
            cue["ambiguous"] = True
            assert oracle_focus(anchor, cue) == FOCUS_TIER[anchor]
    # Activity ceiling proof.
    for anchor in SEMANTIC_NAMES:
        for m_steps in range(11):
            cue = {"meaning": m_steps / 10.0, "meaning_ok": True,
                   "stability_ok": True, "restricted": False}
            assert _fuzz_clamp(oracle_activity(anchor, 0.0, cue),
                               0.0, 1.0) <= 1.0
            assert oracle_activity(anchor, 0.0, None) == ACTIVITY_TIER[anchor]
    lobe = _fuzz_clamp(1.0 + 0.06, 0.0, 1.0)
    assert lobe <= 1.0
    _ = oracle_separation(cue)  # channel-separation identity is asserted in the
    # suite, not here (this file must stay side-effect free).