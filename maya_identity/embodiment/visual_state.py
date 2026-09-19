"""VisualState — the bounded, deterministic embodiment descriptor.

Batch 8C architecture:

    Maya understanding  ->  semantic FaceState  ->  VisualState  ->  renderer

Batch 8D adds the cognitive pathway upstream: the intelligence-bridge cognitive
frame is projected to a ``SemanticCue`` (``semantic_interpretation.py``) which
feeds ``focus`` (confidence, ambiguity-gated) and ``activity`` (meaning, health-
and-restriction-gated) with documented provenance — see ``build_visual_state``.
With ``semantic=None`` the output is byte-identical to the 8C contract.

``VisualState`` says *what* the embodiment should do, never *how* a specific
renderer draws it. It is derived only from the already-validated driven
FaceState (``maya_runtime.face_drive.runtime_face_state``), plus the same
``meta`` / ``commands`` consumed by the face pipeline. It is a pure function of
its inputs: the same inputs always produce the same VisualState, on every
device and interpreter. No randomness, no wall clock.

Every field has an explicit domain and an authoritative source:

- ``semantic``   — the semantic anchor name (``face_semantics.SEMANTIC_NAMES``)
                   taken from ``fs.extra`` (``semantic`` / ``anchor``).
- ``attention``  — [0, 1] from the semantic spec's ``attention`` control, lifted
                   by ``meta["attention"]`` (the face pipeline's own convention
                   of blending scene attention over the semantic base).
- ``focus``      — [0, 1] deterministic focus tier: a small, documented table
                   of validated semantic anchors; there is no validated numeric
                   focus *signal* beyond the anchor tier.
- ``curiosity``  — [0, 1] 1.0 if and only if the semantic anchor is ``curious``
                   (the *only* validated curiosity signal in the system); no
                   text->curious auto-mapping is manufactured here.
- ``activity``   — [0, 1] semantic activity tier lifted by the presence
                   pipeline's ``neural_activity`` command field.
- ``gaze_dx`` / ``gaze_dy`` — [-1, 1] rig-unit gaze from ``fs.extra``.
- ``rest``       — bool: ``dormant``/``neutral`` anchors rest (stable, no pulse).

Bounds are hard ceilings: derivation clamps every field into its domain, so a
misconfigured upstream can push a value to the ceiling — never past it.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..wireframe.face_semantics import SEMANTIC_NAMES, semantic_spec
from .semantic_interpretation import (
    ACTIVITY_SEMANTIC_GAIN,
    FOCUS_CEILING,
    FOCUS_SEMANTIC_GAIN,
    SemanticCue,
    adapt_semantic,
)

# ---------------------------------------------------------------------------
# Authoritative bounds (these ARE the contract; tests mirror them).
# ---------------------------------------------------------------------------

DOMAIN = {
    "attention": (0.0, 1.0),
    "focus": (0.0, 1.0),
    "curiosity": (0.0, 1.0),
    "activity": (0.0, 1.0),
    "gaze": (-1.0, 1.0),
}

# Focus tier: the validated semantic anchors described as "concentrated /
# quiet" (focused, active) get the highest tier; engaged anchors a mid tier;
# warmth/amusement/concern a low tier; neutrality a floor; dormant the rest.
FOCUS_TIER = {
    "neutral": 0.25,
    "attentive": 0.60,
    "focused": 0.90,
    "curious": 0.60,
    "warm": 0.40,
    "amused": 0.40,
    "concerned": 0.40,
    "speaking": 0.60,
    "listening": 0.60,
    "dormant": 0.10,
    "active": 0.90,
}

# Activity tier: how much of the semantic base is "doing something". The
# presence pipeline's ``neural_activity`` command may lift it, never lower it.
ACTIVITY_TIER = {
    "neutral": 0.15,
    "attentive": 0.45,
    "focused": 0.60,
    "curious": 0.50,
    "warm": 0.30,
    "amused": 0.35,
    "concerned": 0.35,
    "speaking": 0.65,
    "listening": 0.40,
    "dormant": 0.05,
    "active": 0.85,
}

REST_ANCHORS = frozenset({"dormant", "neutral"})


def _float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _round12(value):
    return round(float(value), 12)


@dataclass(frozen=True)
class VisualState:
    """Deterministic embodiment descriptor (immutable, bounded)."""

    semantic: str = "neutral"
    attention: float = 0.0
    focus: float = 0.0
    curiosity: float = 0.0
    activity: float = 0.0
    gaze_dx: float = 0.0
    gaze_dy: float = 0.0
    rest: bool = True

    def signature(self) -> str:
        """Cross-interpreter stable sha256 over the bounded fields."""
        payload = "|".join([
            str(self.semantic),
            "%.12f" % self.attention,
            "%.12f" % self.focus,
            "%.12f" % self.curiosity,
            "%.12f" % self.activity,
            "%.12f" % self.gaze_dx,
            "%.12f" % self.gaze_dy,
            "1" if self.rest else "0",
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict:
        return {
            "semantic": self.semantic,
            "attention": self.attention,
            "focus": self.focus,
            "curiosity": self.curiosity,
            "activity": self.activity,
            "gaze_dx": self.gaze_dx,
            "gaze_dy": self.gaze_dy,
            "rest": self.rest,
            "signature": self.signature(),
        }


def _anchor_of(fs) -> str:
    extra = getattr(fs, "extra", None) or {}
    name = extra.get("semantic") or extra.get("anchor") or "neutral"
    if name not in SEMANTIC_NAMES:
        name = "neutral"
    return name


def _focus_value(anchor, cue):
    """Deterministic focus with optional cognitive lift (Batch 8D).

    Without a cue this is exactly the Batch 8C tier. With a cue, a confident
    reading lifts focus (bounded by ``FOCUS_CEILING``); an ambiguous turn
    suppresses the lift entirely (a classifier-backed ambiguity claim).
    """
    base = FOCUS_TIER.get(anchor, 0.25)
    if cue is None:
        return base
    lift = (cue.confidence * FOCUS_SEMANTIC_GAIN) if not cue.ambiguous else 0.0
    return min(FOCUS_CEILING, base + lift)


def _activity_value(anchor, neural, cue):
    """Deterministic activity with optional cognitive lift (Batch 8D).

    Without a cue this is exactly the Batch 8C path. With a cue, engaged
    meaning lifts activity, gated by meaning/stability health and suppressed
    when the reading is restricted (held / reserved).
    """
    base = ACTIVITY_TIER.get(anchor, 0.15)
    neural = max(base, neural)
    if cue is None:
        return neural
    if cue.meaning_ok and cue.stability_ok and not cue.restricted:
        return max(base + cue.meaning * ACTIVITY_SEMANTIC_GAIN, neural)
    return neural


def build_visual_state(fs, meta=None, commands=None, semantic=None) -> VisualState:
    """Derive the bounded embodiment descriptor from the driven FaceState.

    Pure function: identical ``fs`` / ``meta`` / ``commands`` (and optional
    ``semantic`` cue) always yield the identical ``VisualState`` (and
    signature). When ``semantic`` is ``None`` the output is byte-identical to
    the Batch 8C contract (the 8C pins prove this).
    """
    meta = dict(meta or {})
    commands = dict(commands or {})
    if semantic is not None and not isinstance(semantic, SemanticCue):
        semantic = adapt_semantic(
            semantic if isinstance(semantic, dict) else None)

    anchor = _anchor_of(fs)

    spec = semantic_spec(anchor)
    attention_base = _float((spec.get("controls") or {}).get("attention", 0.0))
    attention = _round12(_clamp(
        max(attention_base, _float(meta.get("attention"), 0.0)),
        *DOMAIN["attention"]))

    focus = _round12(_clamp(
        _focus_value(anchor, semantic), *DOMAIN["focus"]))

    curiosity = 1.0 if anchor == "curious" else 0.0

    activity_base = ACTIVITY_TIER.get(anchor, 0.15)
    activity = _round12(_clamp(
        _activity_value(anchor,
                        _float(commands.get("neural_activity"), 0.0),
                        semantic),
        *DOMAIN["activity"]))

    gaze = getattr(fs, "extra", None) or {}
    gaze = gaze.get("gaze") or (0.0, 0.0)
    try:
        gx = _float(gaze[0])
        gy = _float(gaze[1])
    except (TypeError, IndexError):
        gx = gy = 0.0
    gx = _round12(_clamp(gx, *DOMAIN["gaze"]))
    gy = _round12(_clamp(gy, *DOMAIN["gaze"]))

    return VisualState(
        semantic=anchor,
        attention=attention,
        focus=focus,
        curiosity=curiosity,
        activity=activity,
        gaze_dx=gx,
        gaze_dy=gy,
        rest=anchor in REST_ANCHORS,
    )