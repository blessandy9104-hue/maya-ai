"""Maya Batch 8M - canonical vector face verification suite.

Covers the identity-owned canonical vector face layer
(``maya_identity.vector_face``): identity derivation with provenance,
geometry determinism, symmetry, expression anchors confined to the verified
semantic vocabulary, renderer separation and boundedness, QML-consumable
payloads, and the explicit activation gate.
"""
from __future__ import annotations

import json
import types
from dataclasses import replace

from maya_identity.vector_face import (
    RENDERER_VERSION,
    VECTOR_FACE_VERSION,
    VECTOR_SCHEMA_VERSION,
    VectorExpression,
    activate_canonical_vector_face,
    anchors_for_face_extra,
    anchors_for_visual_command,
    anchors_for_visual_state,
    build_canonical_vector_face,
    mirror_pts,
    mirror_x,
    render_face_commands,
    resolve_anchor,
    to_qml_payload,
    validate_canonical_face,
    validate_expression,
    validate_render_commands,
)
from maya_identity.vector_face.vector_face import (
    PAIR_FEATURES,
    REQUIRED_FEATURES,
    REQUIRED_LANDMARKS,
)
from maya_identity.vector_face.expression import VECTOR_VISUAL_TO_SEMANTIC
from maya_identity.wireframe.face_semantics import (
    SEMANTIC_NAMES,
    semantic_parameters,
)
from maya_identity.embodiment.visual_command import VisualCommand

face = build_canonical_vector_face()
blend_expr = anchors_for_face_extra({"semantic": "focused", "openness": 0.95,
                                     "gaze": (0.1, -0.2), "aura": 0.7})


def _ok(name):
    print(f"={name}=OK")


def _build_visual_state(semantic="active", attention=0.5, focus=0.9,
                        activity=0.5, curiosity=0.0, gaze=(0.0, 0.0), rest=False):
    return types.SimpleNamespace(
        semantic=semantic, attention=attention, focus=focus, activity=activity,
        curiosity=curiosity, gaze_dx=gaze[0], gaze_dy=gaze[1], rest=rest)


def _build_command(semantic_emphasis="focused", attention=0.5, activity=0.5,
                   focus=0.9):
    return VisualCommand(
        identity_version="1.0.0", face_version="1.0.0",
        geometry_version="1.0.0", visual_identity_version="1.0.0/1.0.0",
        identity_digest="0" * 64, active_rules=(), provenance=(),
        attention=attention, activity=activity, focus=focus, presence=0.5,
        semantic_emphasis=semantic_emphasis, expression_params=(),
        state_signature="0" * 64)


def _all_expressions():
    return {name: anchors_for_face_extra({"semantic": name}) for name in SEMANTIC_NAMES}


def test_vector_face_contract_import_ok():
    assert hasattr(face, "features") and hasattr(face, "landmarks")
    assert hasattr(face, "geometry_digest")
    _ok("vector_face_contract_import_ok")


def test_canonical_versions_ok():
    assert face.vector_schema_version == VECTOR_SCHEMA_VERSION == "1.0.0"
    assert face.face_version == VECTOR_FACE_VERSION == "1.0.0"
    assert face.geometry_version == "1.0.0"
    assert face.identity_version == "1.0.0"
    assert face.renderer_version == RENDERER_VERSION == "1.0.0"
    _ok("canonical_versions_ok")


def test_landmark_positions_ok():
    expected = {
        "crown": (0.5, 0.335), "chin": (0.5, 0.84),
        "left_eye": (0.385, 0.4), "right_eye": (0.615, 0.4),
        "mouth": (0.5, 0.55),
    }
    for key, point in expected.items():
        assert face.landmarks[key] == point, (key, face.landmarks[key])
    _ok("landmark_positions_ok")


def test_iris_pupil_anchor_math_ok():
    import json as _json
    bundle = _json.load(open("maya_identity/geometry/facial_structure.json",
                             encoding="utf-8"))
    eyes = bundle["eyes"]
    spacing = eyes["spacing"]
    level = eyes["level"]
    y_offset = eyes["iris"]["y_offset"]
    assert face.landmarks["iris_left"] == (
        round(0.5 - spacing, 12), round(level + y_offset, 12))
    assert face.landmarks["iris_right"] == (
        round(mirror_x(0.5 - spacing), 12), round(level + y_offset, 12))
    fmap = face.feature_map()
    assert fmap["eye_iris_left"].radius == eyes["iris"]["radius"]
    assert fmap["eye_pupil_left"].radius == eyes["pupil"]["radius"]
    _ok("iris_pupil_anchor_math_ok")


def test_eye_lens_math_ok():
    fmap = face.feature_map()
    lens_l = fmap["eye_lens_left"].points
    lens_r = fmap["eye_lens_right"].points
    assert lens_r == mirror_pts(lens_l, face.symmetry_axis)
    ys = [p[1] for p in lens_l]
    assert max(ys) - min(ys) > 0.01
    import math as _math
    top = min(ys)
    assert top >= 0.4 - 0.02 - 1e-9 and top <= 0.4 - 0.005
    _ok("eye_lens_math_ok")


def test_nose_landmarks_ok():
    assert face.landmarks["nose_tip"] == (0.5, 0.468)
    fmap = face.feature_map()
    assert fmap["nostril_left"].points[0] == (0.481, 0.479)
    assert fmap["nostril_right"].points[0] == (0.519, 0.479)
    assert fmap["nostril_left"].radius == fmap["nostril_right"].radius == 0.005
    assert len(fmap["nose_bridge"].points) == 2
    _ok("nose_landmarks_ok")


def test_mouth_landmarks_ok():
    fmap = face.feature_map()
    assert fmap["mouth_corners_left"].points[0] == (0.438, 0.549)
    assert fmap["mouth_corners_right"].points[0] == (0.562, 0.549)
    idle = fmap["mouth_idle"].points
    assert all(-1e-9 <= y <= 1 + 1e-9 for (x, y) in idle)
    assert all(-1e-9 <= x <= 1 + 1e-9 for (x, y) in idle)
    _ok("mouth_landmarks_ok")


def test_brow_jaw_silhouette_ok():
    fmap = face.feature_map()
    assert len(fmap["brows_left"].points) == 5
    assert len(fmap["jaw_arc"].points) == 10
    sil = fmap["head_silhouette"].points
    assert len(sil) == 17
    assert sil[0] == sil[-1]
    ys = [p[1] for p in sil]
    assert min(ys) >= 0.46 - 0.38 - 1e-9
    assert max(ys) <= 0.46 + 0.38 + 1e-9
    _ok("brow_jaw_silhouette_ok")


def test_provenance_sources_ok():
    for feat in face.features:
        assert feat.source.startswith("facial_structure#"), feat.source
        assert feat.role == "identity"
    _ok("provenance_sources_ok")


def test_required_feature_surface_ok():
    names = {feat.name for feat in face.features}
    assert REQUIRED_FEATURES.issubset(names), sorted(REQUIRED_FEATURES - names)
    assert REQUIRED_LANDMARKS.issubset(face.landmarks)
    for feat in face.features:
        assert feat.kind in ("path", "polyline", "circle", "anchor")
    _ok("required_feature_surface_ok")


def test_unit_space_bounds_ok():
    for feat in face.features:
        for p in feat.points:
            assert -1e-9 <= p[0] <= 1 + 1e-9 and -1e-9 <= p[1] <= 1 + 1e-9
    for key, point in face.landmarks.items():
        assert -1e-9 <= point[0] <= 1 + 1e-9 and -1e-9 <= point[1] <= 1 + 1e-9
    _ok("unit_space_bounds_ok")


def test_symmetry_pairs_ok():
    fmap = face.feature_map()
    for left_name, right_name in PAIR_FEATURES:
        left = fmap[left_name]
        right = fmap[right_name]
        assert len(left.points) == len(right.points)
        mirrored = mirror_pts(left.points, face.symmetry_axis)
        for a, b in zip(mirrored, right.points):
            assert abs(a[0] - b[0]) <= face.symmetry_tolerance + 1e-9
            assert abs(a[1] - b[1]) <= face.symmetry_tolerance + 1e-9
    import math as _math
    assert _math.isclose(mirror_x(mirror_x(0.3)), 0.3, abs_tol=1e-9)
    _ok("symmetry_pairs_ok")


def test_authority_mirror_consistency_ok():
    from maya_identity.identity import load_geometry_bundle
    bundle = load_geometry_bundle()
    ok, reasons = validate_canonical_face(face, bundle=bundle)
    assert ok, reasons
    ok2, reasons2 = validate_canonical_face(face)
    if ok2 is False:
        assert False, reasons2
    _ok("authority_mirror_consistency_ok")


def test_validate_clean_ok():
    ok, reasons = validate_canonical_face(face)
    assert ok is True and reasons == []
    _ok("validate_clean_ok")


def test_double_build_digest_ok():
    second = build_canonical_vector_face()
    assert second.geometry_digest == face.geometry_digest
    assert second.features == face.features
    assert second.landmarks == face.landmarks
    _ok("double_build_digest_ok")


def test_geometry_digest_shape_ok():
    assert len(face.geometry_digest) == 64
    assert int(face.geometry_digest, 16) >= 0
    _ok("geometry_digest_shape_ok")


def test_visual_to_semantic_parity_ok():
    from maya_runtime.face_drive import VISUAL_TO_SEMANTIC
    assert VECTOR_VISUAL_TO_SEMANTIC == VISUAL_TO_SEMANTIC
    _ok("visual_to_semantic_parity_ok")


def test_expression_vocabulary_ok():
    for name in SEMANTIC_NAMES:
        assert resolve_anchor(name) == name
    assert resolve_anchor("processing") == "focused"
    assert resolve_anchor("happy") == "neutral"
    assert resolve_anchor("sad") == "neutral"
    assert resolve_anchor(None) == "neutral"
    _ok("expression_vocabulary_ok")


def test_expression_neutral_ok():
    expr = anchors_for_face_extra({"semantic": "neutral"})
    assert expr.anchor == "neutral"
    assert expr.openness == 1.0
    assert expr.gaze_x == 0.0 and expr.gaze_y == 0.0
    assert expr.rest is True
    assert set(expr.as_dict()["mouth"]) == {"open", "spread", "round"}
    _ok("expression_neutral_ok")


def test_expression_dormant_ok():
    expr = anchors_for_face_extra({"semantic": "dormant"})
    assert expr.anchor == "dormant"
    assert expr.openness == 0.8
    assert expr.aura == 0.2
    assert expr.rest is True
    _ok("expression_dormant_ok")


def test_expression_speaking_ok():
    expr = anchors_for_face_extra({"semantic": "speaking"})
    assert expr.anchor == "speaking"
    assert expr.viseme == "OPEN"
    assert expr.mouth_open == 0.52
    assert expr.mouth_spread == 0.05
    assert expr.gaze_x == 0.0 and expr.gaze_y == 0.0
    _ok("expression_speaking_ok")


def test_visual_state_flow_ok():
    vs = _build_visual_state(semantic="focused", attention=0.6, focus=0.9,
                             activity=0.4)
    expr = anchors_for_visual_state(vs)
    assert expr.anchor == "focused"
    assert expr.attention == 0.6
    assert expr.focus == 0.9
    assert expr.activity == 0.4
    ok, reasons = validate_expression(expr)
    assert ok, reasons
    _ok("visual_state_flow_ok")


def test_visual_command_flow_ok():
    cmd = _build_command(semantic_emphasis="focused", attention=0.7,
                         focus=0.85)
    expr = anchors_for_visual_command(cmd)
    assert expr.anchor == "focused"
    assert expr.attention == 0.7
    assert expr.focus == 0.85
    ok, reasons = validate_expression(expr)
    assert ok, reasons
    _ok("visual_command_flow_ok")


def test_face_extra_flow_ok():
    expr = anchors_for_face_extra(
        {"semantic": "active", "openness": 0.95, "aura": 0.85,
         "gaze": (0.0, 0.0), "viseme": "REST", "rest": False})
    assert expr.anchor == "active"
    assert expr.openness == 0.95
    assert expr.aura == 0.85
    assert expr.rest is False
    ok, reasons = validate_expression(expr)
    assert ok, reasons
    _ok("face_extra_flow_ok")


def test_expression_all_bounded_ok():
    for name, expr in _all_expressions().items():
        assert expr.anchor == name
        ok, reasons = validate_expression(expr)
        assert ok, (name, reasons)
    _ok("expression_all_bounded_ok")


def test_expression_ceilings_ok():
    for expr in _all_expressions().values():
        for field in ("openness", "aura", "mouth_open", "mouth_spread",
                      "mouth_round"):
            assert 0.0 <= getattr(expr, field) <= 1.0
        assert -1.0 <= expr.gaze_x <= 1.0 and -1.0 <= expr.gaze_y <= 1.0
        assert expr.viseme in ("REST", "OPEN", "CLOSED", "WIDE", "NARROW",
                               "ROUND")
    _ok("expression_ceilings_ok")


def test_expression_determinism_ok():
    a = anchors_for_face_extra({"semantic": "focused", "aura": 0.7})
    b = anchors_for_face_extra({"semantic": "focused", "aura": 0.7})
    assert a.as_dict() == b.as_dict()
    assert all(getattr(a, f) == getattr(b, f)
               for f in ("attention", "activity", "focus", "openness", "aura"))
    _ok("expression_determinism_ok")


def test_no_invented_emotion_ok():
    anchors = set()
    for name in SEMANTIC_NAMES:
        anchors.add(resolve_anchor(name))
    for foreign in ("joy", "happy", "sad", "angry", "excited", "moody"):
        assert resolve_anchor(foreign) == "neutral"
    def _spec(names):
        return {name: semantic_parameters(name)["meaning"] for name in names}
    _spec(SEMANTIC_NAMES)
    assert {"joy", "anger", "mood"} & set(VECTOR_VISUAL_TO_SEMANTIC) == set()
    _ok("no_invented_emotion_ok")


def test_render_purity_ok():
    features_before = face.features
    landmarks_before = dict(face.landmarks)
    digest_before = face.geometry_digest
    out = render_face_commands(face, blend_expr)
    assert isinstance(out, dict) and out["digest"]
    assert face.features == features_before
    assert face.landmarks == landmarks_before
    assert face.geometry_digest == digest_before
    _ok("render_purity_ok")


def test_render_bounded_ok():
    out = render_face_commands(face, blend_expr)
    ok, reasons = validate_render_commands(out)
    assert ok, reasons
    _ok("render_bounded_ok")


def test_render_determinism_ok():
    a = render_face_commands(face, blend_expr)
    b = render_face_commands(face, blend_expr)
    assert a["digest"] == b["digest"]
    assert a["commands"] == b["commands"]
    _ok("render_determinism_ok")


def test_render_no_motion_default_ok():
    a = render_face_commands(face, blend_expr, frame=0)
    b = render_face_commands(face, blend_expr, frame=7)
    assert a["commands"] == b["commands"]
    assert a["frame"] == 0 and b["frame"] == 7
    _ok("render_no_motion_default_ok")


def test_qml_payload_serializable_ok():
    payload = to_qml_payload(face, blend_expr)
    _json = json.dumps(payload)
    assert isinstance(_json, str) and len(_json) > 100
    assert payload["schema"] == "maya/canonical-vector-face/1.0.0"
    assert sorted(payload.keys()) == sorted(
        ["schema", "frame", "surface", "expression", "versions", "digest"])
    assert len(payload["surface"]) == len(
        render_face_commands(face, blend_expr)["commands"])
    _ok("qml_payload_serializable_ok")


def test_activation_gate_validation_ok():
    import os
    import tempfile
    tampered = replace(face, renderer_version="")
    path = os.path.join(tempfile.mkdtemp(), "identity_versions.jsonl")
    result = activate_canonical_vector_face(tampered, journal_path=path)
    assert result["status"] == "validation_failed"
    assert not os.path.exists(path) or os.path.getsize(path) == 0
    offgrid = replace(face, landmarks={**face.landmarks, "crown": (2.0, 0.3)})
    result2 = activate_canonical_vector_face(offgrid, journal_path=path)
    assert result2["status"] == "validation_failed"
    _ok("activation_gate_validation_ok")


def test_activation_records_ok():
    import os
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "identity_versions.jsonl")
    result = activate_canonical_vector_face(face, created_by="test",
                                            journal_path=path)
    assert result["status"] == "activated"
    assert result["journal"] == path
    lines = [json.loads(line) for line in open(path, encoding="utf-8")]
    assert len(lines) == 1
    record = lines[0]
    assert record["event"] == "canonical_vector_face_established"
    assert record["face_version"] == "1.0.0"
    assert record["geometry_version"] == "1.0.0"
    assert record["renderer_version"] == "1.0.0"
    assert record["validation"] == {"ok": True, "violations": 0}
    assert record["created_by"] == "test"
    _ok("activation_records_ok")


if __name__ == "__main__":
    for name in sorted(globals()):
        if name.startswith("test_") and callable(globals()[name]):
            globals()[name]()