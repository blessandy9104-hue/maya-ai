"""Identity anchors: stable vectors that keep persona fusion coherent.

Anchors are derived deterministically from the canonical per-persona
ceilings, normalized onto the [0, 1] channel space. They are constant:
fusion pulls toward them with ``pattern_similarity``, so long-term persona
identity never drifts and no persona is ever switched on directly.
"""
from __future__ import annotations

from ..core import CHANNEL_MAX, MATH_AGENT, clamp01
from ..isolation.ceilings import PERSONA_CEILINGS, WEB_PERSONA_ALLOWLIST

_CHANNELS = ("expression", "viseme", "micro")

ANCHOR_VECTORS = {}
for _persona in WEB_PERSONA_ALLOWLIST:
    _ceiling = PERSONA_CEILINGS[_persona]
    _vector = tuple(
        clamp01(_ceiling.get(ch, 0.0) / CHANNEL_MAX[ch]) for ch in _CHANNELS
    )
    ANCHOR_VECTORS[_persona] = _vector
del _persona, _ceiling, _vector


class IdentityAnchors:
    """Read-only anchor registry; anchors are never mutable at runtime."""

    vectors = ANCHOR_VECTORS
    channels = _CHANNELS

    def anchor(self, persona):
        if persona not in ANCHOR_VECTORS:
            raise ValueError("unknown persona %r" % persona)
        return ANCHOR_VECTORS[persona]

    def alignment(self, persona, state_vector):
        return MATH_AGENT.pattern_similarity(state_vector, self.anchor(persona))

    def pull(self, persona, current_weight, alpha=0.15):
        anchor = sum(self.anchor(persona)) / max(1, len(self.anchor(persona)))
        return clamp01(MATH_AGENT.pattern_state(current_weight, anchor, clamp01(alpha)))


IDENTITY_ANCHORS = IdentityAnchors()