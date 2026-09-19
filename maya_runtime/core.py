"""Maya Runtime core: canonical math surface, device-neutral.

Re-exports the single source of truth (``maya_identity.wireframe.rig_math``
and ``maya_identity.wireframe.math_coordinator``). No ``random``, ``time`` or
``tkinter`` lives in this module.

Determinism contract (device-independent): identical inputs yield identical
outputs on every host -- no hardware probes, no GPU, no wall-clock, no RNG.
"""
from __future__ import annotations

from . import _loader

_RIG = _loader.module("rig_math")
_COORD = _loader.module("math_coordinator")

_RIG_NAMES = (
    "clamp01",
    "clamp",
    "lerp",
    "smoothstep",
    "exp_smooth",
    "stable_lerp",
    "stable_exp_smooth",
    "cosine_similarity",
    "math_isclose",
    "glow01",
    "depth01",
    "thickness01",
    "zprime",
    "blend_pose",
    "jaw_open",
    "NUMERIC_CONTRACTS",
)

_COORD_NAMES = (
    "MATH_AGENT",
    "WORLD_DOMAIN",
    "WORLD_STATE_PATTERNS",
    "CHANNEL_MAX",
    "CH_EXPRESSION",
    "CH_VISEME",
    "CH_MICRO",
    "PRECISION_STANDARD",
    "PRECISION_EXPERT",
    "PRECISION_TOLERANCE",
)

__all__ = tuple(sorted(set(_RIG_NAMES) | set(_COORD_NAMES)))


def _bind() -> None:
    for name in _RIG_NAMES:
        globals()[name] = getattr(_RIG, name)
    for name in _COORD_NAMES:
        globals()[name] = getattr(_COORD, name)


_bind()
del _bind