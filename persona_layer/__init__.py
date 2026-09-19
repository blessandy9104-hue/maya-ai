"""Persona Layer -- DEPRECATED package boundary (MAYA BATCH 8J-A).

State: ``deprecated`` (no ambiguous state). See ``STATUS.md`` in this package.

History
    ``persona_layer/`` was authored as a typed presentation-persona stack
    (tone bands, vocabulary sets, emotional ranges, behavioral constraints,
    rule sets, role directives) intended to sit on top of
    ``maya_runtime.core`` channel ceilings. It was committed incomplete: the
    modules imported by the original package ``__init__``
    (``persona_registry`` and ``persona_loader``) were never materialized, so
    ``import persona_layer`` failed with ``ModuleNotFoundError``. Nothing in
    the repository ever imported it, and nothing depended on its templates.

Replacement (Batch 8J-A decision)
    - COGNITIVE persona authority   : ``maya_runtime/intelligence/persona.py``
                                      (protocol ``maya.persona_fusion.v1``,
                                      consumed via the intelligence bridge and
                                      the unified state bus).
    - PRESENTATION personality      : ``maya_runtime/personality.py`` (channel
                                      profiles) plus the deployment profile
                                      deck ``maya_identity/profiles/*.json``.
    The six template modules retained beside this file are historical
    reference ONLY. They are inert, unconnected, and must not be wired until a
    future, non-cleanup decision introduces a presentation adapter.

Rules
    - This package defines no live API. The template modules are not imported
      here and must not be imported by production code going forward.
    - ``PERSONA_LAYER_STATE == "deprecated"`` is the machine-checkable state
      asserted by ``test_persona_boundaries.py``.
    - Retiring this package does not touch memory, identity, or conversation
      stores (see Batch 8J-A memory-separation requirement).
"""
from __future__ import annotations

PERSONA_LAYER_STATE = "deprecated"
DEPRECATED_SINCE = "MAYA BATCH 8J-A"
REPLACEMENT = (
    "maya_runtime/intelligence/persona.py (cognitive; authoritative); "
    "maya_runtime/personality.py + maya_identity/profiles (presentation)"
)

__all__ = [
    "PERSONA_LAYER_STATE",
    "DEPRECATED_SINCE",
    "REPLACEMENT",
]