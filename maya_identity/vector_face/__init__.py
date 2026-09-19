"""Identity-owned canonical vector face layer (Maya Batch 8M).

Layering: Identity -> Geometry -> Face Representation -> Expression State
-> Renderer.

- ``vector_face``   the canonical neutral face model + geometry/symmetry
                    validation + version digest + explicit activation
- ``expression``    bounded expression anchors from the verified semantic
                    vocabulary (never invented emotion)
- ``render``        a separate, pure renderer mapping the model + anchors to
                    QML-consumable draw commands

This package represents Maya; it never defines her. The model is write-free
and deterministic; only ``activate_canonical_vector_face`` (operator-only)
may append a versioning record.
"""
from .expression import (
    VECTOR_VISUAL_TO_SEMANTIC,
    VISEMES_NAMES,
    VectorExpression,
    anchors_for_face_extra,
    anchors_for_visual_command,
    anchors_for_visual_state,
    clamp_rig,
    clamp01,
    resolve_anchor,
    validate_expression,
)
from .render import (
    BROW_LIFT_AMPLITUDE,
    IRIS_FOCUS_LIFT,
    IRIS_GAZE_AMPLITUDE,
    MOUTH_OPEN_AMPLITUDE,
    render_face_commands,
    to_qml_payload,
    validate_render_commands,
)
from .vector_face import (
    RENDERER_VERSION,
    VECTOR_FACE_VERSION,
    VECTOR_SCHEMA_VERSION,
    CanonicalVectorFace,
    VectorFeature,
    activate_canonical_vector_face,
    build_canonical_vector_face,
    mirror_pts,
    mirror_x,
    validate_canonical_face,
)

__all__ = [
    "RENDERER_VERSION",
    "VECTOR_FACE_VERSION",
    "VECTOR_SCHEMA_VERSION",
    "CanonicalVectorFace",
    "VectorFeature",
    "VectorExpression",
    "activate_canonical_vector_face",
    "anchors_for_face_extra",
    "anchors_for_visual_command",
    "anchors_for_visual_state",
    "build_canonical_vector_face",
    "clamp01",
    "clamp_rig",
    "mirror_pts",
    "mirror_x",
    "render_face_commands",
    "resolve_anchor",
    "to_qml_payload",
    "validate_canonical_face",
    "validate_expression",
    "validate_render_commands",
    "VECTOR_VISUAL_TO_SEMANTIC",
    "VISEMES_NAMES",
    "BROW_LIFT_AMPLITUDE",
    "IRIS_FOCUS_LIFT",
    "IRIS_GAZE_AMPLITUDE",
    "MOUTH_OPEN_AMPLITUDE",
]