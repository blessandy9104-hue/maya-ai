"""Maya Identity Presentation package.

Layered architecture:
  Maya Core -> Cognitive State Layer -> Identity Presentation -> Visual Interface

This package owns identity (``identity.py``), cognitive state signals
(``cognitive_state.py``), config-driven animation (``animation.py``), and the
visual embodiment widget (``face.py``). The Maya application imports only the
widget and the state bridge; it never hardcodes identity data.
"""
from .identity import (
    capabilities,
    finalize_canonical_face,
    geometry_version,
    get_animation_config,
    get_appearance_config,
    get_avatar_path,
    get_face_source,
    get_identity_context,
    get_render_config,
    identity_version,
    load_effects_config,
    load_engine_config,
    load_expression,
    load_geometry_bundle,
    load_identity,
    log_identity_version,
)
from . import animation, cognitive_state, validation
from .face import MayaFace
from .renderer import ProceduralFace
from .wireframe import MayaWireframeFace
from . import awareness, embodiment, evolution, nervous_system, visual_language, voice_sync
from . import capability_registry, cognition, domains, interaction, readiness, stabilization

__all__ = [
    "MayaFace",
    "MayaWireframeFace",
    "ProceduralFace",
    "animation",
    "awareness",
    "capabilities",
    "capability_registry",
    "cognition",
    "cognitive_state",
    "domains",
    "embodiment",
    "evolution",
    "finalize_canonical_face",
    "geometry_version",
    "get_animation_config",
    "get_appearance_config",
    "get_avatar_path",
    "get_face_source",
    "get_identity_context",
    "get_render_config",
    "identity_version",
    "interaction",
    "load_effects_config",
    "load_engine_config",
    "load_expression",
    "load_geometry_bundle",
    "load_identity",
    "log_identity_version",
    "nervous_system",
    "readiness",
    "stabilization",
    "validation",
    "visual_language",
    "voice_sync",
]