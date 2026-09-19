"""Emotion-to-expression mapper â€” validates and normalizes raw metadata.

Every incoming metadata dict is parsed defensively: missing fields get safe
defaults, numbers are clamped to 0.0â€“1.0, and unknown keys are ignored. The
output is a validated control vector suitable for the expression controller.
"""
from __future__ import annotations

from .interp import clamp01
from .expression_controller import (
    ALL_CONTROLS, PRESETS, EMOTION_CONTROLS, STATE_CONTROLS,
    VOICE_CONTROLS, MATERIAL_CONTROLS,
)
from .math_coordinator import MATH_AGENT

# Canonical visual-state weight: a fallback visual preset settles into the
# rig at this alpha through exp_smooth, owned by the Math Coordination Agent.
_VISUAL_STATE_ALPHA = 0.4

_EMOTION_ALIASES = {
    "happy": "happy", "joy": "happy", "happiness": "happy",
    "cheerful": "happy", "delighted": "happy",
    "sad": "sad", "gloomy": "sad", "unhappy": "sad", "depressed": "sad",
    "neutral": "neutral", "idle": "idle",
    "angry": "angry", "annoyed": "angry", "irritated": "angry", "furious": "angry",
    "fearful": "fear", "afraid": "fear", "scared": "fear", "frightened": "fear",
    "worried": "concerned", "anxious": "concerned",
    "focused": "thinking", "processing": "thinking", "thinking": "thinking",
    "analytical": "thinking", "research": "thinking", "studying": "thinking",
    "listening": "listening", "attentive": "listening", "deep_listen": "listening_deep",
    "calm": "calm", "peaceful": "calm", "serene": "calm", "content": "calm",
    "surprised": "surprised", "shocked": "surprised", "startled": "surprised",
    "concerned": "concerned",
    "uncertain": "uncertain", "doubtful": "uncertain", "confused": "uncertain",
    "unclear": "uncertain",
    "speaking": "speaking", "talk": "speaking", "talking": "speaking",
    "error": "error", "failed": "error", "alert": "error",
}

_CONTROL_ALIASES = {
    "voice_intensity": "voice_intensity", "voiceIntensity": "voice_intensity",
    "glow_intensity": "glow_intensity", "glowIntensity": "glow_intensity",
    "scan_activity": "scan_activity", "scanActivity": "scan_activity",
    "tiredness": "tiredness", "fatigue": "tiredness",
    "attention": "attention", "eyeFocus": "attention", "focus": "attention",
    "thinking": "thinking", "thinkingAmount": "thinking", "neural": "thinking",
    "neural_activity": "thinking", "neuralActivity": "thinking",
    "speaking": "speaking", "speakingAmount": "speaking", "speaking_level": "speaking",
    "confidence": "confidence", "intensity": "intensity",
    "smile": "smile", "happiness": "smile", "joy": "smile",
    "sadness": "sadness", "anger": "anger", "surprise": "surprise",
    "fear": "fear", "calm": "calm", "uncertainty": "uncertainty",
}


def _safe_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def parse_metadata(meta, fallback_visual="sleeping"):
    """Parse raw metadata into validated controls dict.

    Returns (controls_dict, preset_name, warnings_list).
    """
    if meta is None or not isinstance(meta, dict):
        return {}, "neutral", ["empty or invalid metadata"]
    if not meta:
        return {}, "neutral", []

    warnings = []
    controls = {}
    preset_used = None

    preset_key = None
    for alias in ("preset", "emotion", "emotionLabel", "mood", "state"):
        raw = meta.get(alias)
        if raw is not None:
            preset_key = str(raw).strip().lower()
            if preset_key:
                break

    if preset_key:
        mapped = _EMOTION_ALIASES.get(preset_key)
        if mapped and mapped in PRESETS:
            preset_used = mapped
            for k, v in PRESETS[mapped].items():
                if k in ALL_CONTROLS:
                    controls[k] = MATH_AGENT.control(v)
        elif preset_key in PRESETS:
            preset_used = preset_key
            for k, v in PRESETS[preset_key].items():
                if k in ALL_CONTROLS:
                    controls[k] = MATH_AGENT.control(v)
        else:
            warnings.append(f"unknown preset/emotion: {preset_key}")

    for raw_key, val in meta.items():
        target = _CONTROL_ALIASES.get(raw_key)
        if target and target in ALL_CONTROLS:
            controls[target] = MATH_AGENT.control(val)

    for key in EMOTION_CONTROLS:
        controls.setdefault(key, 0.0)
    for key in STATE_CONTROLS:
        controls.setdefault(key, 0.0)
    for key in VOICE_CONTROLS:
        controls.setdefault(key, 0.0)
    for key in MATERIAL_CONTROLS:
        controls.setdefault(key, 0.0)

    if fallback_visual:
        state_preset = None
        for alias in ("visual_state", "visualState", "state", "activity"):
            raw = meta.get(alias)
            if raw:
                state_preset = str(raw).strip().lower()
                break
        if state_preset and state_preset in PRESETS:
            # Visual-state application is a pattern-driven state change: it
            # settles at the canonical visual-state weight through exp_smooth,
            # computed by the Math Coordination Agent (never a raw heuristic).
            for k, v in PRESETS[state_preset].items():
                if k in controls and controls[k] == 0.0:
                    controls[k] = MATH_AGENT.pattern_state(0.0, v, _VISUAL_STATE_ALPHA)

    return controls, preset_used or preset_key or "neutral", warnings
