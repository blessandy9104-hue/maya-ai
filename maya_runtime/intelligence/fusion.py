"""Persona fusion: no persona may activate directly.

Every persona contributes only through a normalized weight computed from
context alignment, world-model alignment, stability, and identity anchors.
The fused voice is a weighted blend of the canonical persona ceilings
(``task_blend``), so the output is always within the sanctioned channel
space and no persona is ever switched on by itself.
"""
from __future__ import annotations

from ..core import (
    MATH_AGENT,
    CHANNEL_MAX,
    clamp01,
    math_isclose,
    WORLD_STATE_PATTERNS,
)
from ..isolation.ceilings import PERSONA_CEILINGS, WEB_PERSONA_ALLOWLIST
from .anchors import IDENTITY_ANCHORS
from .feature_map import _neutral, _as_vector

CHANNELS = ("expression", "viseme", "micro")


class PersonaFusion:
    """Weighted, anchor-stabilized persona blending."""

    personas = WEB_PERSONA_ALLOWLIST

    def compute(self, encoded, state=None, context_vector=None,
                alpha=0.15):
        state = state or {}
        context_vector = _as_vector(context_vector) if context_vector is not None \
            else tuple(float(v) for v in WORLD_STATE_PATTERNS["stable_equilibrium"])[:3]
        stability = _neutral(state.get("stability", 0.0))
        world_alignment = _neutral(state.get("alignment", 0.5))
        reference = WORLD_STATE_PATTERNS["stable_equilibrium"]
        world_match = MATH_AGENT.pattern_alignment(
            context_vector,
            tuple(float(ref) for ref in reference[:len(context_vector)]))
        raw = {}
        for persona in self.personas:
            anchor = IDENTITY_ANCHORS.anchor(persona)
            context_match = MATH_AGENT.pattern_alignment(context_vector, anchor)
            primary = context_match
            secondary = clamp01((world_alignment + world_match) / 2.0)
            fused_signal = MATH_AGENT.task_fuse(
                primary, secondary, stability).get("fused", 0.0)
            anchor_norm = sum(anchor) / max(1.0, float(len(anchor)))
            pulled = MATH_AGENT.pattern_state(
                fused_signal, anchor_norm, clamp01(alpha))
            raw[persona] = clamp01(pulled)

        ordered = [p for p in self.personas]
        raw_list = [raw[p] for p in ordered]
        total = sum(raw_list)
        if total <= 0.0:
            return {
                "ok": False,
                "weights": {p: 0.0 for p in ordered},
                "raw_weights": raw,
                "dominant": None,
                "fused_channels": {ch: 0.0 for ch in CHANNELS},
                "channels": {ch: 0.0 for ch in CHANNELS},
                "math": {"surface": "task_blend", "state": "neutral"},
            }
        blend = MATH_AGENT.task_blend(raw_list, weights=raw_list)
        normalized = tuple(float(w) for w in blend["weights"])
        weights = {p: w for p, w in zip(ordered, normalized)}
        dominant = ordered[max(range(len(normalized)),
                              key=normalized.__getitem__)]
        fused_channels = {}
        for ch in CHANNELS:
            values = [float(PERSONA_CEILINGS[p].get(ch, 0.0)) for p in ordered]
            fused = MATH_AGENT.task_blend(values, weights=normalized)["fused"]
            cap = float(CHANNEL_MAX[ch])
            fused_channels[ch] = clamp01(min(fused, cap))
        ok = all(0.0 <= w <= 1.0 for w in normalized) and \
            math_weights_sum(normalized)
        return {
            "ok": ok,
            "weights": weights,
            "raw_weights": raw,
            "dominant": dominant,
            "fused_channels": fused_channels,
            "channels": fused_channels,
            "math": {
                "surface": "task_blend",
                "weights": normalized,
                "weights_sum": sum(normalized),
            },
        }


def math_weights_sum(weights):
    total = sum(float(w) for w in weights)
    return math_isclose(total, 1.0)


PERSONA_FUSION = PersonaFusion()


def compute(*args, **kwargs):
    return PERSONA_FUSION.compute(*args, **kwargs)