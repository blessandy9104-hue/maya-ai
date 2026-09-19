"""Expression anchors for the canonical vector face.

Anchors are derived only from the verified semantic vocabulary
(``face_semantics.SEMANTIC_NAMES``) and the deterministic visual layer
(VisualState / VisualCommand / FaceState.extra). The vocabulary here equals
the verified face-semantics vocabulary: there is no invented emotion, mood or
personality state in this tree.

An anchor records *what Maya is doing* (attention, activity, focus,
understanding, speaking), never what she feels. Every numeric field is
bounded to its documented domain, mirroring the isolation ceilings of the
face pipeline (expression/viseme/micro/anatomical).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..wireframe.face_semantics import (
    SEMANTIC_NAMES,
    semantic_controls,
    semantic_parameters,
)
from ..wireframe.speech_adapter import VISEMES

# Mirrors ``maya_runtime.face_drive.VISUAL_TO_SEMANTIC`` (the runtime's
# deterministic visual-state -> semantic-anchor mapping). Kept here so the
# identity-owned layer can resolve a visual label without depending on the
# runtime; test suite proves they stay identical.
VECTOR_VISUAL_TO_SEMANTIC = {
    "awake": "attentive",
    "processing": "focused",
    "research": "focused",
    "learning": "focused",
    "listening": "listening",
    "sleeping": "dormant",
    "offline": "dormant",
    "idle": "neutral",
}

VISEMES_NAMES = tuple(VISEMES)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def clamp_rig(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _r12(value: float) -> float:
    return round(float(value), 12)


@dataclass(frozen=True)
class VectorExpression:
    """Bounded expression anchors for one presentation moment.

    ``anchor`` is always one of ``SEMANTIC_NAMES``; ``mouth`` carries the
    bound viseme parameters (confined to the mouth/jaw channel); ``aura`` is
    presentation glow only and never moves geometry.
    """

    anchor: str
    attention: float
    activity: float
    focus: float
    curiosity: float
    openness: float
    gaze_x: float
    gaze_y: float
    viseme: str
    mouth_open: float
    mouth_spread: float
    mouth_round: float
    aura: float
    rest: bool

    def as_dict(self) -> dict:
        return {
            "anchor": self.anchor,
            "attention": self.attention,
            "activity": self.activity,
            "focus": self.focus,
            "curiosity": self.curiosity,
            "openness": self.openness,
            "gaze_x": self.gaze_x,
            "gaze_y": self.gaze_y,
            "viseme": self.viseme,
            "mouth": {
                "open": self.mouth_open,
                "spread": self.mouth_spread,
                "round": self.mouth_round,
            },
            "aura": self.aura,
            "rest": self.rest,
        }


def resolve_anchor(label) -> str:
    """Normalise any label to the verified semantic-anchor vocabulary.

    Foreign or unknown labels deterministically resolve to ``neutral`` -
    the face never invents or guesses a state.
    """
    name = str(label or "").strip().lower()
    if name in SEMANTIC_NAMES:
        return name
    if name in VECTOR_VISUAL_TO_SEMANTIC:
        return VECTOR_VISUAL_TO_SEMANTIC[name]
    return "neutral"


def _from_spec(anchor: str) -> dict:
    return semantic_parameters(anchor)


def _default_controls(anchor: str) -> dict:
    return semantic_controls(anchor)


def _build(anchor: str,
           attention=None, activity=None, focus=None, curiosity=None,
           gaze_x=None, gaze_y=None, openness=None,
           viseme=None, mouth=None, aura=None, rest=None) -> VectorExpression:
    spec = _from_spec(anchor)
    approved_mouth = dict(spec["mouth"])
    for key in ("open", "spread", "round"):
        approved_mouth[key] = _r12(clamp01(
            approved_mouth.get(key, 0.0) if mouth is None
            else mouth.get(key, approved_mouth.get(key, 0.0))))
    viseme_name = str(viseme or spec["viseme"]).strip().upper()
    if viseme_name not in VISEMES_NAMES:
        viseme_name = str(spec["viseme"]).strip().upper()
    gx, gy = spec.get("gaze") or (0.0, 0.0)
    if gaze_x is not None:
        gx = float(gaze_x)
    if gaze_y is not None:
        gy = float(gaze_y)
    openness_value = _r12(clamp01(spec["openness"]
                                  if openness is None else openness))
    aura_value = _r12(clamp01(spec["aura"] if aura is None else aura))
    rest_base = anchor in ("dormant", "neutral")
    rest_flag = rest_base if rest is None else bool(rest)
    controls = _default_controls(anchor)
    return VectorExpression(
        anchor=anchor,
        attention=_r12(clamp01(controls.get("attention", 0.0)
                               if attention is None else attention)),
        activity=_r12(clamp01(controls.get("thinking", 0.0)
                              if activity is None else activity)),
        focus=_r12(clamp01(0.0 if focus is None else focus)),
        curiosity=_r12(clamp01(1.0 if anchor == "curious" and curiosity is None
                               else (0.0 if curiosity is None else curiosity))),
        openness=openness_value,
        gaze_x=_r12(clamp_rig(gx)),
        gaze_y=_r12(clamp_rig(gy)),
        viseme=viseme_name,
        mouth_open=approved_mouth["open"],
        mouth_spread=approved_mouth["spread"],
        mouth_round=approved_mouth["round"],
        aura=aura_value,
        rest=rest_flag,
    )


def anchors_for_face_extra(extra) -> VectorExpression:
    """Build expression anchors from a verified ``FaceState.extra`` dict."""
    extra = dict(extra or {})
    anchor = resolve_anchor(extra.get("semantic") or extra.get("anchor"))
    gaze = extra.get("gaze")
    gx = gy = None
    if isinstance(gaze, (tuple, list)) and len(gaze) == 2:
        gx, gy = gaze[0], gaze[1]
    elif isinstance(gaze, dict):
        gx, gy = gaze.get("x"), gaze.get("y")
    mouth = extra.get("mouth")
    if isinstance(mouth, dict):
        mouth = dict(mouth)
    else:
        mouth = None
    attention = extra.get("attention")
    activity = extra.get("activity")
    focus = extra.get("focus")
    curiosity = extra.get("curiosity")
    return _build(anchor, attention=attention, activity=activity, focus=focus,
                  curiosity=curiosity, gaze_x=gx, gaze_y=gy,
                  openness=extra.get("openness"), viseme=extra.get("viseme"),
                  mouth=mouth, aura=extra.get("aura"), rest=extra.get("rest"))


def anchors_for_visual_state(state) -> VectorExpression:
    """Build expression anchors from a deterministic ``VisualState``."""
    anchor = resolve_anchor(getattr(state, "semantic", None))
    return _build(
        anchor,
        attention=getattr(state, "attention", None),
        activity=getattr(state, "activity", None),
        focus=getattr(state, "focus", None),
        curiosity=getattr(state, "curiosity", None),
        gaze_x=getattr(state, "gaze_dx", None),
        gaze_y=getattr(state, "gaze_dy", None),
        rest=getattr(state, "rest", None),
    )


def anchors_for_visual_command(command) -> VectorExpression:
    """Build expression anchors from an identity-verified ``VisualCommand``."""
    anchor = resolve_anchor(getattr(command, "semantic_emphasis", None))
    return _build(
        anchor,
        attention=getattr(command, "attention", None),
        activity=getattr(command, "activity", None),
        focus=getattr(command, "focus", None),
        rest=False if resolve_anchor(getattr(command, "semantic_emphasis", None))
        in ("dormant", "neutral") else None,
    )


def validate_expression(expr: VectorExpression):
    """Return ``(ok, reasons)`` bounded-anchor validation."""
    ok = True
    reasons = []

    def fail(message):
        nonlocal ok
        ok = False
        reasons.append(message)

    if not isinstance(expr, VectorExpression):
        return False, ["not a VectorExpression"]
    if expr.anchor not in SEMANTIC_NAMES:
        fail("anchor %r not in verified semantics %s"
             % (expr.anchor, SEMANTIC_NAMES))
    for field in ("attention", "activity", "focus", "curiosity",
                  "openness", "mouth_open", "mouth_spread", "mouth_round",
                  "aura"):
        if not (-1e-9 <= getattr(expr, field) <= 1.0 + 1e-9):
            fail("field %s out of [0, 1]: %r" % (field, getattr(expr, field)))
    for field in ("gaze_x", "gaze_y"):
        if not (-1.0 - 1e-9 <= getattr(expr, field) <= 1.0 + 1e-9):
            fail("field %s out of [-1, 1]: %r" % (field, getattr(expr, field)))
    if expr.viseme not in VISEMES_NAMES:
        fail("viseme %r not known" % expr.viseme)
    return ok, reasons