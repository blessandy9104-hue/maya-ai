"""Embodiment layer — foundation for Maya's digital body.

Gaze following, attention direction, presence awareness, emotional
visualization, and environmental reactions flow through PresenceEngine. This
layer only represents state; it never creates intelligence and never writes
identity files.

``VisualState`` is the bounded, deterministic embodiment descriptor derived
from the driven semantic FaceState (Batch 8C): the temporary shape renderer —
and the future face renderer — are pure functions of ``VisualState``.
"""
from .attention_model import AttentionModel
from .presence_engine import PresenceEngine
from .semantic_interpretation import SemanticCue, adapt_semantic, from_line
from .visual_command import (
    IdentityVisualRule,
    VisualCommand,
    activate_visual_identity,
    build_visual_command,
    restrict_visual_state,
    to_visual_state,
    validate_visual_identity,
    visual_identity_version,
)
from .visual_state import VisualState, build_visual_state

__all__ = [
    "AttentionModel",
    "PresenceEngine",
    "SemanticCue",
    "adapt_semantic",
    "from_line",
    "VisualState",
    "build_visual_state",
    "IdentityVisualRule",
    "VisualCommand",
    "activate_visual_identity",
    "build_visual_command",
    "restrict_visual_state",
    "to_visual_state",
    "validate_visual_identity",
    "visual_identity_version",
]