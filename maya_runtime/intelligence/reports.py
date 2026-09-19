"""Decision, evidence, and stability reports — deterministic traces of every
math surface the loop touched. Reports are pure: they read an executed
frame and never mutate state.
"""
from __future__ import annotations

from ..core import CHANNEL_MAX
from .feature_map import _neutral


def build_decision_report(frame, encoded=None):
    encoded = encoded or {}
    scalars = encoded.get("scalars", {}) or {}
    coefficients = encoded.get("coefficients", {}) or {}
    decide = frame.get("decide", frame)
    state = frame.get("stabilize", frame.get("stability") or {})
    friction = state.get("std")
    weights = (decide.get("fusion") or {}).get("weights", {})
    coherence = _neutral(scalars.get("coherence"))
    if coherence == 0.0:
        coherence = _neutral((frame.get("meaning") or {})
                             .get("world_component", 0.0))
    glow = _neutral(scalars.get("glow", 0.0))
    thickness = _neutral(coefficients.get("thickness", 1.0))
    depth = _neutral(scalars.get("depth", 0.0))
    return {
        "stage": "decide",
        "pattern_alignment": _neutral(coherence),
        "task_fuse": _neutral(
            (decide.get("confidence") or {}).get("confidence", 0.0)),
        "world_stability": None if friction is None else _neutral(friction),
        "persona_fusion": {
            "weights": dict(weights),
            "dominant": (decide.get("fusion") or {}).get("dominant"),
            "channels": dict((decide.get("fusion") or {}).get("channels", {})),
        },
        "render": {
            "glow01": glow,
            "thickness01": thickness,
            "depth01": depth,
        },
        "primitives": ["pattern_alignment", "task_fuse", "world_stability",
                       "glow01", "thickness01", "depth01"],
    }


def build_evidence_report(frame, encoded=None):
    encoded = encoded or {}
    historical = {k: _neutral(v) for k, v
                  in (encoded.get("scalars") or {}).items()
                  if k in ("coherence", "consensus", "currency") and
                  isinstance(v, (int, float))}
    conflicts = []
    stability = frame.get("stability") or {}
    if not stability.get("stability_ok", True):
        conflicts.append("world_stability_beyond_tolerance")
    if stability.get("drift", 0.0) and _neutral(stability.get("drift")) > 0.35:
        conflicts.append("drift_beyond_tolerance")
    evidence = frame.get("evidence") or {}
    ok = bool(evidence.get("ok", True)) and not conflicts
    return {
        "stage": "interpret",
        "coherence": historical.get("coherence", 0.0),
        "consensus": historical.get("consensus", 0.0),
        "currency": historical.get("currency", 0.0),
        "conflicts": conflicts,
        "ok": ok,
    }


def build_stability_report(frame, state=None):
    state = state or frame.get("stabilize", frame.get("stability") or {})
    boundaries = state.get("safety_boundaries", {}) or {}
    return {
        "stage": "stabilize",
        "std": _neutral(state.get("std")),
        "stability": _neutral(state.get("stability", 0.0)),
        "drift": _neutral(state.get("drift", 0.0)),
        "alignment": _neutral(state.get("alignment", 0.0)),
        "safety_margin": _neutral(boundaries.get("margin", 0.0)),
        "safety_violations": list(boundaries.get("violations", [])),
        "ok": bool(state.get("ok", False)),
    }