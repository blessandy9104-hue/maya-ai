"""Maya Runtime: personality layer -- deterministic, bounded, device-neutral.

PRESENTATION personality (Batch 8J-A naming contract): this module maps a
presentation persona id to canonical channel targets (``expression``,
``viseme``, ``micro``, ``pace``). It delivers communication *style* only. It
is NOT a cognitive persona source (that is
``maya_runtime/intelligence/persona.py``, ``persona_fusion`` protocol) and NOT
an identity definition (that is ``maya_identity/identity.json``). This module
must never become a hidden intelligence source: it carries no world facts, no
geometry, no memory, no cognition.

Personas are immutable constant profiles mapped onto the canonical channel
space (``expression``, ``viseme``, ``micro``) plus an interaction ``pace``.
The engine blends from a neutral baseline toward the persona using canonical
math only (``lerp`` / ``stable_exp_smooth`` / ``clamp01``) and never exceeds
``CHANNEL_MAX`` ceilings. No RNG, no wall-clock, no GPU.

Blend-weight policy preserved: expressions and visemes follow the canonical
neutral baseline, and any projected channel is ceiling-clamped afterwards.
"""
from __future__ import annotations

from .core import (
    CHANNEL_MAX,
    CH_EXPRESSION,
    CH_MICRO,
    CH_VISEME,
    clamp01,
    lerp,
    stable_exp_smooth,
)

_CHANNELS = (CH_EXPRESSION, CH_VISEME, CH_MICRO)

_NEUTRAL = {
    CH_EXPRESSION: 0.25,
    CH_VISEME: 0.12,
    CH_MICRO: 0.0,
    "pace": 0.6,
}

PERSONAS = {
    "calm": (0.30, 0.15, 0.000, 0.55),
    "warm": (0.45, 0.25, 0.008, 0.65),
    "authoritative": (0.35, 0.18, 0.004, 0.50),
    "playful": (0.50, 0.32, 0.011, 0.75),
}
# all personas respect canonical ceilings in every channel
for _persona_name, _profile in PERSONAS.items():
    assert _profile[0] <= CHANNEL_MAX[CH_EXPRESSION], _persona_name
    assert _profile[1] <= CHANNEL_MAX[CH_VISEME], _persona_name
    assert _profile[2] <= CHANNEL_MAX[CH_MICRO], _persona_name
del _persona_name, _profile


class PersonalityEngine:
    """Stateless, deterministic persona -> channel-target mapping."""

    personas = PERSONAS
    neutral = _NEUTRAL

    def available(self):
        return tuple(sorted(PERSONAS))

    def profile(self, persona):
        if persona not in PERSONAS:
            raise ValueError(f"unknown persona: {persona!r}")
        p = PERSONAS[persona]
        return {
            CH_EXPRESSION: p[0],
            CH_VISEME: p[1],
            CH_MICRO: p[2],
            "pace": p[3],
        }

    def channel_targets(self, persona, blend=1.0):
        """Persona projected onto channel targets, ceiling-clamped."""
        if not (0.0 <= blend <= 1.0):
            raise ValueError("blend must be in [0, 1]")
        prof = self.profile(persona)
        factor = clamp01(blend)
        targets = {}
        for ch in _CHANNELS:
            targets[ch] = min(_NEUTRAL[ch] + factor * (prof[ch] - _NEUTRAL[ch]),
                              CHANNEL_MAX[ch])
        targets["pace"] = clamp01(_NEUTRAL["pace"] + factor * (prof["pace"] - _NEUTRAL["pace"]))
        return targets

    def paced_state(self, persona, current, factor=0.6):
        """One deterministic smoothing step toward the persona's targets."""
        if not (0.0 <= factor <= 1.0):
            raise ValueError("factor must be in [0, 1]")
        targets = self.channel_targets(persona, blend=factor)
        out = {}
        for ch in _CHANNELS:
            base = float(current.get(ch, 0.0))
            out[ch] = stable_exp_smooth(base, targets[ch], clamp01(factor))
            assert out[ch] <= CHANNEL_MAX[ch] + 1e-12
        out["pace"] = targets["pace"]
        return out


PERSONALITY = PersonalityEngine()