"""Face drive — bounded runtime FaceState for the canonical face (Batch 8b).

Turns the presence runtime's visual state, app metadata, render commands and
(optional) person consensuses into ONE deterministic FaceState per tick:

    visual + meta + commands + persona  ->  semantic anchor
                                        ->  bounded control overrides
                                        ->  canonical FaceState (extra: aura)

The bridge is bounded by construction: every overlay is clamped to [0, 1] and
capped at its channel's displacement ceiling (the persona bridge policy), gaze
targets are mapped from rig units ``[-1, 1]`` to ``[0, 1]``, and aura is a pure
function of scene pressure. Nothing here animates on its own: identical inputs
give the identical face, on every device and interpreter.

This module never touches the widget or the renderer; ``maya_app`` and the
test suites are the only consumers.
"""
from __future__ import annotations

import json
from dataclasses import replace

from maya_identity.wireframe.face_semantics import (
    build_semantic_face_state,
    semantic_spec,
)
from maya_identity.wireframe.rig_math import clamp01
from maya_runtime.intelligence.visual_bridge import persona_signals

# visual_state -> semantic anchor (deterministic, bounded vocabulary).
VISUAL_TO_SEMANTIC = {
    "awake": "attentive",
    "processing": "focused",
    "research": "focused",
    "learning": "focused",
    "listening": "listening",
    "sleeping": "dormant",
    "offline": "dormant",
    "idle": "neutral",
}

# Conversation-phase wire protocol: the chat process (maya_chat) emits one
# "[face] {"state": ...}" machine line per phase when MAYA_FACE_LINES=1;
# interface readers feed the parsed value into the same activity channel as
# the visual states above. Values are exactly the four activity keys both
# readers already accept, and every key maps onto a pre-validated semantic
# anchor in VISUAL_TO_SEMANTIC, so no new parameter surface is introduced.
FACE_LINE_PREFIX = "[face] "
CONVERSATION_STATES = ("idle", "processing", "listening", "research")

# How long user typing keeps the listening overlay before the face settles
# back to idle. One constant shared by both interfaces so the two faces
# agree on the timing.
TYPING_SETTLE_SECONDS = 3.0


def typing_activity(current) -> str | None:
    """Face overlay while the user is typing.

    Typing means attention, so a resting (idle) face lifts to listening;
    working states (processing/research) already express the conversation
    and win — typing never degrades or flickers them. Returns None when
    the current state must be kept. Interfaces re-check this on every
    keystroke and settle back to idle after TYPING_SETTLE_SECONDS of
    inactivity; chat-driven state changes (the [face] producer) always
    take precedence and cancel the pending settle.
    """
    return "listening" if current == "idle" else None


def parse_face_line(text) -> str | None:
    """Parse one conversation-phase machine line into a bounded state.

    Tolerant by contract: malformed JSON, unknown states, or missing fields
    return None (the reader keeps its previous activity). Prompt text may be
    concatenated in front of the line (the Tk reader merges stderr into the
    same pipe), so the prefix is located, not assumed at offset zero.
    """
    if not isinstance(text, str):
        return None
    start = text.rfind(FACE_LINE_PREFIX)
    if start < 0:
        return None
    remainder = text[start + len(FACE_LINE_PREFIX):].strip()
    data = None
    try:
        data = json.loads(remainder)
    except (json.JSONDecodeError, ValueError):
        end = remainder.rfind("}")
        if end > 0:
            try:
                data = json.loads(remainder[: end + 1])
            except (json.JSONDecodeError, ValueError):
                data = None
    if not isinstance(data, dict):
        return None
    state = data.get("state")
    return state if state in CONVERSATION_STATES else None


def _float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_semantic(visual=None, meta=None, commands=None) -> str:
    """Pick the bounded semantic anchor: error > voice > visual state."""
    meta = dict(meta or {})
    commands = dict(commands or {})
    if str(meta.get("preset") or "").lower() == "error":
        return "concerned"
    if (_float(meta.get("speaking"), 0.0) > 0.25
            or _float(meta.get("voice_intensity"), 0.0) > 0.25
            or bool(commands.get("voice_linked"))):
        return "speaking"
    key = str(visual or "").strip().lower()
    return VISUAL_TO_SEMANTIC.get(key, "neutral")


def aura_from_scene(base: float, meta=None, commands=None) -> float:
    """Bounded aura: the semantic base lifted by scene pressure.

    Pressure is a deterministic weighted max of neural/glow/density inputs;
    the face pose and materials never change, only the presentation aura.
    """
    meta = dict(meta or {})
    commands = dict(commands or {})
    pressure = max(
        _float(commands.get("neural_activity"), 0.0),
        _float(commands.get("glow_intensity"), 0.0),
        0.5 * _float(commands.get("particle_density"), 0.0),
        _float(meta.get("glow_intensity"), 0.0),
    )
    pressure = clamp01(pressure)
    base = clamp01(base)
    return round(base + (1.0 - base) * pressure * 0.6, 9)


def runtime_face_state(visual=None, meta=None, commands=None, persona=None,
                       aura: float | None = None):
    """The deterministic FaceState the app renders this tick.

    ``aura`` may be forced (headless previews/tests); otherwise it is derived
    from the semantic state's base and the scene pressure. ``persona`` is a
    FusedPersonaState; consensus signals overlay the semantic base only when
    the bridge is active, exactly like the Batch 7 persona path.
    """
    meta = dict(meta or {})
    commands = dict(commands or {})
    anchor = resolve_semantic(visual, meta, commands)
    spec = semantic_spec(anchor)

    overrides: dict = {}

    attention = max(
        _float(meta.get("attention"), 0.0),
        0.6 * _float(commands.get("eye_focus"), 0.0),
    )
    thinking = max(
        _float(meta.get("thinking"), 0.0),
        0.9 * _float(commands.get("neural_activity"), 0.0),
    )
    if attention > 0.0:
        overrides["attention"] = attention
    if thinking > 0.0:
        overrides["thinking"] = thinking
    if _float(meta.get("confidence")) > 0.0:
        overrides["confidence"] = _float(meta.get("confidence"))

    if anchor == "speaking":
        speaking = max(
            _float(meta.get("speaking"), 0.0),
            0.6 if bool(commands.get("voice_linked")) else 0.0,
        )
        overrides["speaking"] = speaking
        if _float(meta.get("voice_intensity"), 0.0) > 0.0:
            overrides["voice_intensity"] = _float(meta.get("voice_intensity"))

    gx = commands.get("gaze_x")
    gy = commands.get("gaze_y")
    if gx is not None and _float(gx, -1.0) >= -1.0:
        overrides["gaze_x"] = clamp01(_float(gx) * 0.5 + 0.5)
    if gy is not None and _float(gy, -1.0) >= -1.0:
        overrides["gaze_y"] = clamp01(_float(gy) * 0.5 + 0.5)

    if persona is not None:
        bridged = persona_signals(persona)
        if bridged.get("active"):
            for control, value in (bridged.get("signals") or {}).items():
                overrides[control] = max(
                    clamp01(overrides.get(control, 0.0)), clamp01(value))

    aura_v = aura if aura is not None else aura_from_scene(
        _float(spec.get("aura", 0.5)), meta, commands)
    fs = build_semantic_face_state(anchor, overrides=overrides, aura=aura_v)
    extra = dict(fs.extra)
    extra["anchor"] = anchor
    if persona is not None:
        bridged = persona_signals(persona)
        extra["persona"] = {
            "active": bool(bridged.get("active")),
            "reason": bridged.get("reason"),
            "persona_ids": list(persona.get("active_personas") or []),
        }
    return replace(fs, extra=extra)


def drive_digest(fs) -> str:
    """Deterministic summary key for the driven face (tests/cache use)."""
    return "|".join([
        str(fs.extra.get("anchor", "neutral")),
        str(fs.extra.get("aura", 0.0)),
        fs.signature,
    ])