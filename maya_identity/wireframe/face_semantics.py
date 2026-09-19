"""Face semantics — the bounded semantic vocabulary of the runtime face.

Makes the canonical FaceState meaningful as *state*, not just a static
snapshot. Every entry below is a semantic face state with:

- ``meaning``      — what the state means (never a claim about truth).
- ``controls``     — bounded ExpressionController targets. Every value is a
                     control on the canonical [0, 1] domain and is capped at
                     its channel's displacement ceiling (the same conservative
                     control cap the persona bridge uses), so a semantic state
                     can never drive a muscle past the validated anatomy.
- ``gaze``         — gaze direction in rig units on [-1, 1]: ``gx > 0``
                     shifts the pupils toward the viewer's right; ``gy > 0``
                     lowers them on screen (the rig's ``gaze_y`` convention,
                     where positive gaze lowers the iris toward the lower lid).
- ``openness``     — eye openness on [0, 1]; the blink target is the exact
                     complement ``1 - openness``.
- ``viseme``       — a named viseme shape from ``speech_adapter.VISEMES``,
                     carried as ``open``/``spread``/``round`` mouth
                     parameters (bounded). Viseme meaning is confined to the
                     mouth/jaw (viseme channel), never the emotional rig.
- ``aura``         — bounded scene/neural glow intensity on [0, 1]. Aura is
                     presentation, not identity: it never changes the face's
                     geometry, only the rendered halo and sparkle.

Isolation ceilings are preserved exactly: expression/viseme/micro/anatomical
stay independent channels, anatomical detail is applied at full weight, and
the 0.6/0.3/0.1 blend law is untouched. No randomness, no wall-clock.

Neutral is pinned to the Batch 8a canonical pose: the constructor leaves the
gaze targets untouched (the canonical neutral pose implicitly carries the
rig's default zero-target gaze) so ``build_semantic_face_state("neutral")``
reproduces ``build_face_state(PRESETS["neutral"], t=0.5)`` byte-for-byte, and
therefore renders to the identical canonical raster.
"""
from __future__ import annotations

from dataclasses import replace

from .rig_math import clamp01, math_isclose, POSE_EPSILON
from .math_coordinator import (
    CHANNEL_MAX,
    CH_EXPRESSION,
    CH_VISEME,
    CONTROL_CHANNELS,
    MATH_AGENT,
)
from .expression_controller import ALL_CONTROLS, PRESETS
from .speech_adapter import VISEMES
from .face_state import build_face_state, channel_state


def _control_cap(control: str) -> float:
    """Control-value cap: expression/viseme controls may not exceed their
    channel's displacement ceiling (matching the persona bridge policy);
    anatomical and micro controls stay on the natural [0, 1] domain."""
    channel = CONTROL_CHANNELS.get(control)
    if channel in (CH_EXPRESSION, CH_VISEME):
        return CHANNEL_MAX.get(channel, 1.0)
    return 1.0


def _bounded(control: str, value: float) -> float:
    return round(min(clamp01(value), _control_cap(control)), 12)


# ---------------------------------------------------------------------------
# Semantic state definitions (all values bounded; see module docstring).
# ---------------------------------------------------------------------------

SEMANTIC_STATES = {
    "neutral": {
        "meaning": "identity-resting neutrality — the canonical Batch 8a pose, byte-for-byte",
        "controls": dict(PRESETS["neutral"]),
        "gaze": None,           # keep the rig's default zero targets (8a parity)
        "openness": 1.0,
        "viseme": "REST",
        "aura": 0.40,
    },
    "attentive": {
        "meaning": "engaged, alert, eyes centred — attention raises the brow",
        "controls": {"attention": 0.50, "confidence": 0.45, "calm": 0.30,
                     "smile": 0.04},
        "gaze": (0.0, 0.0),
        "openness": 1.0,
        "viseme": "REST",
        "aura": 0.55,
    },
    "focused": {
        "meaning": "concentrated, quiet, eyes centred and slightly narrowed",
        "controls": {"thinking": 0.50, "attention": 0.45, "confidence": 0.50,
                     "uncertainty": 0.10},
        "gaze": (0.0, 0.0),
        "openness": 0.95,
        "viseme": "REST",
        "aura": 0.65,
    },
    "curious": {
        "meaning": "attentive with a lateral glance and inner-brow asymmetry",
        "controls": {"attention": 0.50, "thinking": 0.30, "uncertainty": 0.35,
                     "confidence": 0.30, "smile": 0.06},
        "gaze": (-0.25, 0.05),
        "openness": 1.0,
        "viseme": "REST",
        "aura": 0.60,
    },
    "warm": {
        "meaning": "settled warmth — soft smile, open eyes, calm confidence",
        "controls": {"smile": 0.45, "calm": 0.55, "confidence": 0.48,
                     "attention": 0.30},
        "gaze": (0.0, 0.0),
        "openness": 1.0,
        "viseme": "REST",
        "aura": 0.60,
    },
    "amused": {
        "meaning": "bright amusement — full smile, slight surprise lift",
        "controls": {"smile": 0.50, "calm": 0.35, "confidence": 0.50,
                     "attention": 0.30, "surprise": 0.05},
        "gaze": (0.0, 0.0),
        "openness": 1.0,
        "viseme": "REST",
        "aura": 0.65,
    },
    "concerned": {
        "meaning": "watchful concern — raised inner brow, soft worry",
        "controls": {"uncertainty": 0.48, "sadness": 0.22, "attention": 0.45,
                     "tiredness": 0.14, "confidence": 0.20},
        "gaze": (0.0, 0.0),
        "openness": 0.90,
        "viseme": "REST",
        "aura": 0.45,
    },
    "speaking": {
        "meaning": "voiced speech — viseme OPEN confines deformation to the mouth/jaw",
        "controls": {"speaking": 0.35, "voice_intensity": 0.35,
                     "attention": 0.45, "confidence": 0.42, "calm": 0.28},
        "gaze": (0.0, 0.0),
        "openness": 0.95,
        "viseme": "OPEN",
        "aura": 0.60,
    },
    "listening": {
        "meaning": "attentive listening — open attention, calm and soft smile",
        "controls": {"attention": 0.50, "calm": 0.35, "confidence": 0.45,
                     "smile": 0.08},
        "gaze": (0.0, 0.0),
        "openness": 1.0,
        "viseme": "REST",
        "aura": 0.50,
    },
    "dormant": {
        "meaning": "quiet and dimmed — lowered lids, micro off, minimal aura",
        "controls": {"calm": 0.0, "attention": 0.15, "confidence": 0.20},
        "gaze": (0.0, 0.0),
        "openness": 0.80,
        "viseme": "REST",
        "aura": 0.20,
    },
    "active": {
        "meaning": "elevated engagement — focused posture with a bright aura",
        "controls": {"thinking": 0.50, "attention": 0.50, "confidence": 0.50,
                     "calm": 0.25},
        "gaze": (0.0, 0.0),
        "openness": 0.95,
        "viseme": "REST",
        "aura": 0.85,
    },
}

SEMANTIC_NAMES = tuple(SEMANTIC_STATES)


def semantic_spec(name: str) -> dict:
    if name not in SEMANTIC_STATES:
        raise ValueError(
            f"unknown semantic face state {name!r} (one of {SEMANTIC_NAMES})")
    return SEMANTIC_STATES[name]


def semantic_parameters(name: str) -> dict:
    """The semantic-level parameters of a state (bounded, audit-friendly)."""
    spec = semantic_spec(name)
    viseme_key = str(spec.get("viseme", "REST")).strip().upper()
    mouth = dict(VISEMES.get(viseme_key, VISEMES["REST"]))
    base_gaze = spec["gaze"]
    gaze = None if base_gaze is None else tuple(
        round(float(v), 6) for v in base_gaze)
    return {
        "semantic": name,
        "meaning": spec["meaning"],
        "openness": round(clamp01(spec["openness"]), 6),
        "gaze": gaze,
        "viseme": viseme_key,
        "mouth": {k: round(clamp01(v), 6) for k, v in mouth.items()},
        "aura": round(max(0.0, min(1.0, float(spec["aura"]))), 6),
    }


def semantic_controls(name: str, overrides: dict | None = None) -> dict:
    """Bounded, channel-capped control targets for a semantic state.

    The merged vector contains only recognised rig controls (``ALL_CONTROLS``,
    scene/body controls excluded), every value clamped to [0, 1] and capped at
    its channel's displacement ceiling. Gaze and blink targets are derived
    from the state's ``gaze``/``openness`` parameters.
    """
    spec = semantic_spec(name)
    controls = {}
    controls.update((c, _bounded(c, v)) for c, v in spec["controls"].items())
    gaze = spec.get("gaze")
    if gaze is not None:
        gx, gy = gaze
        # rig unit [-1, 1] -> control target [0, 1]; null gaze -> centred 0.5.
        controls["gaze_x"] = _bounded("gaze_x", float(gx) * 0.5 + 0.5)
        controls["gaze_y"] = _bounded("gaze_y", float(gy) * 0.5 + 0.5)
    controls["blink"] = _bounded("blink", 1.0 - clamp01(spec["openness"]))
    for over, value in (overrides or {}).items():
        if over not in ALL_CONTROLS:
            continue
        controls[over] = _bounded(over, value)
    return {name: controls[name] for name in sorted(controls)}


def validate_semantic_controls(name: str) -> dict:
    """Every control in the semantic vector must carry exactly one semantic
    meaning; a channel-category error raises rather than being guessed."""
    controls = semantic_controls(name)
    return MATH_AGENT.semantic_profile(controls)


def build_semantic_face_state(
    name: str,
    t: float = 0.5,
    mesh=None,
    size: int = 1000,
    overrides: dict | None = None,
    aura: float | None = None,
):
    """Deterministic FaceState for a semantic state, with the bounded
    semantic parameters attached in ``extra``.

    ``controls`` stay bounded and channel-capped; the pose is built through
    the canonical ``face_state.build_face_state`` (fresh controller, blink
    disabled, immediate targets, fixed ``t``), so it is byte-for-byte
    reproducible across runs and interpreters. ``aura`` defaults to the
    state's spec value.
    """
    spec = semantic_spec(name)
    controls = semantic_controls(name, overrides=overrides)
    fs = build_face_state(controls, t=t, mesh=mesh, size=size)
    aura_v = aura if aura is not None else float(spec.get("aura", 0.5))
    params = semantic_parameters(name)
    st = channel_state(fs.fields)
    extra = {
        "semantic": name,
        "meaning": spec["meaning"],
        "aura": round(max(0.0, min(1.0, aura_v)), 6),
        "openness": params["openness"],
        "gaze": params["gaze"],
        "viseme": params["viseme"],
        "mouth": params["mouth"],
        "channel_state": st,
    }
    return replace(fs, extra=extra)


def semantic_state_digests(mesh=None, t: float = 0.5) -> dict:
    """Per-semantic-state pose signature map (deterministic)."""
    return {name: build_semantic_face_state(
        name, t=t, mesh=mesh).signature for name in SEMANTIC_NAMES}


def neutral_matches_canonical(mesh=None) -> bool:
    """Neutral semantics MUST equal the canonical 8a FaceState pose — the
    fixed point that makes the runtime's neutral render the canonical one."""
    sem = build_semantic_face_state("neutral", mesh=mesh)
    canon = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    for a, b in zip(sem.pose, canon.pose):
        for ka, kb in zip(a, b):
            if not math_isclose(ka, kb, POSE_EPSILON):
                return False
    return sem.signature == canon.signature