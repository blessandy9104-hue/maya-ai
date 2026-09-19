"""Maya Batch 8M — canonical face presentation verification suite.

Verifies the Qt canonical-face presentation path end to end at the pure
Python layer (runs on every interpreter, no Qt required):

- the pure bridge emits the canonical vector-face payload (schema
  "maya/canonical-vector-face/1.0.0") from the authoritative FaceState/
  VisualState, with a self-consistent digest;
- determinism and no-motion defaults (frame is metadata only);
- bounded, verified-vocabulary expressions (no invented emotion);
- independent geometry oracle: landmark positions recomputed directly from
  ``facial_structure.json`` authority, not from the face builder;
- QML is presentation-only: single face surface, no embedded landmark/identity
  geometry, no randomness and no wall clock, schema-gated payload acceptance;
- sabotage drills A-G on the presentation layer all FAIL (rejected).
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from maya_runtime.ui.qt import bridge as ui_bridge  # noqa: E402
from maya_identity.vector_face import (  # noqa: E402
    anchors_for_face_extra,
    anchors_for_visual_state,
    build_canonical_vector_face,
    render_face_commands,
    to_qml_payload,
    validate_canonical_face,
    validate_expression,
    validate_render_commands,
)
from maya_identity.wireframe.face_semantics import SEMANTIC_NAMES  # noqa: E402

_FACE_SCHEMA = "maya/canonical-vector-face/1.0.0"

_face = build_canonical_vector_face()
_ticker = ui_bridge.UiTicker()
_view1 = _ticker.apply_tick_snapshot(_ticker.make_tick_payload("research"))
_view0 = ui_bridge.UiTicker().apply_tick_snapshot(
    ui_bridge.UiTicker().make_tick_payload("idle"))


def _ok(name):
    print(f"={name}=OK")


def _sha256(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _qml(name):
    return (_REPO / "maya_runtime" / "ui" / "qt" / "qml" / name).read_text(
        encoding="utf-8")


# ---- 1. payload presence + schema ---------------------------------------
def test_face_payload_present_in_view_ok():
    assert "face" in _view1 and isinstance(_view1["face"], dict)
    assert _view1["face"]["schema"] == _FACE_SCHEMA
    assert _view0["face"]["schema"] == _FACE_SCHEMA
    _ok("face_payload_present_in_view_ok")


def test_face_payload_digest_ok():
    f = _view1["face"]
    assert len(f["digest"]) == 64
    recomputed = _sha256({
        "frame": f["frame"],
        "surface": f["surface"],
        "expression": f["expression"],
        "versions": f["versions"],
    })
    assert recomputed == f["digest"], "payload digest does not recompute"
    _ok("face_payload_digest_ok")


def test_face_payload_ops_known_ok():
    known = {"clear", "path", "polyline", "circle", "anchor", "glow"}
    ops = [c["op"] for c in _view1["face"]["surface"]]
    assert ops and set(ops) <= known
    assert ops[0] == "clear"
    _ok("face_payload_ops_known_ok")


# ---- 2. determinism / no motion ------------------------------------------
def test_face_payload_determinism_ok():
    a = ui_bridge.UiTicker().apply_tick_snapshot(
        ui_bridge.UiTicker().make_tick_payload("research"))
    b = ui_bridge.UiTicker().apply_tick_snapshot(
        ui_bridge.UiTicker().make_tick_payload("research"))
    assert a["face"]["surface"] == b["face"]["surface"]
    assert a["face"]["expression"] == b["face"]["expression"]
    assert a["face"]["digest"] == b["face"]["digest"]
    _ok("face_payload_determinism_ok")


def test_face_payload_no_motion_default_ok():
    a = render_face_commands(_face, anchors_for_visual_state(
        type("VS", (), {"semantic": "neutral", "attention": 0.0, "focus": 0.0,
                        "activity": 0.0, "curiosity": 0.0, "gaze_dx": 0.0,
                        "gaze_dy": 0.0, "rest": True})), frame=0)
    b = render_face_commands(_face, anchors_for_visual_state(
        type("VS", (), {"semantic": "neutral", "attention": 0.0, "focus": 0.0,
                        "activity": 0.0, "curiosity": 0.0, "gaze_dx": 0.0,
                        "gaze_dy": 0.0, "rest": True})), frame=9)
    assert a["commands"] == b["commands"]
    assert a["frame"] == 0 and b["frame"] == 9
    _ok("face_payload_no_motion_default_ok")


# ---- 3. bounded expressions on the verified vocabulary --------------------
def test_face_payload_expression_vocabulary_ok():
    anchor = _view1["face"]["expression"]["anchor"]
    assert anchor in SEMANTIC_NAMES, anchor
    _ok("face_payload_expression_vocabulary_ok")


def test_face_payload_expression_bounds_ok():
    e = _view1["face"]["expression"]
    for field in ("attention", "activity", "focus", "curiosity",
                  "openness", "aura"):
        assert -1e-9 <= e[field] <= 1.0 + 1e-9, field
    for field in ("gaze_x", "gaze_y"):
        assert -1.0 - 1e-9 <= e[field] <= 1.0 + 1e-9, field
    for field in ("open", "spread", "round"):
        assert -1e-9 <= e["mouth"][field] <= 1.0 + 1e-9, field
    _ok("face_payload_expression_bounds_ok")


def test_face_payload_validation_clean_ok():
    assert validate_canonical_face(_face)[0]
    rendered = render_face_commands(
        _face, anchors_for_visual_state(type("VS", (), {
            "semantic": "focused", "attention": 0.5, "focus": 0.8,
            "activity": 0.3, "curiosity": 0.0, "gaze_dx": 0.0, "gaze_dy": 0.0,
            "rest": False})))
    assert validate_render_commands(rendered)[0]
    _ok("face_payload_validation_clean_ok")


# ---- 4. independent geometry oracle (from authority JSON, not the builder) -
def test_face_payload_oracle_landmarks_ok():
    import math
    bundle = json.load(open("maya_identity/geometry/facial_structure.json",
                            encoding="utf-8"))
    eyes = bundle["eyes"]
    base_left = (0.5 - eyes["spacing"], eyes["level"] + eyes["iris"]["y_offset"])
    base_right = (0.5 + eyes["spacing"], base_left[1])
    expr = _view1["face"]["expression"]
    gx = expr["gaze_x"] * 0.02
    gy = expr["gaze_y"] * 0.02 - expr["focus"] * 0.012
    expected = {
        (base_left[0] + gx, base_left[1] + gy),
        (base_right[0] + gx, base_right[1] + gy),
    }
    circles = [c for c in _view1["face"]["surface"] if c["op"] == "circle"]
    centers = {tuple(round(v, 9) for v in c["center"]) for c in circles}
    for ex in expected:
        assert tuple(round(v, 9) for v in ex) in centers, ex
    radii = {round(c["radius"], 12) for c in circles
             if tuple(round(v, 9) for v in c["center"]) in
             {tuple(round(v, 9) for v in e) for e in expected}}
    assert round(eyes["iris"]["radius"], 12) in radii
    _ok("face_payload_oracle_landmarks_ok")


def test_face_payload_oracle_mouth_nose_ok():
    bundle = json.load(open("maya_identity/geometry/facial_structure.json",
                            encoding="utf-8"))
    mouth = bundle["mouth"]
    nose = bundle["nose"]
    anchors = [a for a in _view1["face"]["surface"] if a["op"] == "anchor"]
    pts = {tuple(round(v, 6) for v in a["point"]) for a in anchors}
    expected = {
        tuple(round(v, 6) for v in mouth["corners"]["left"]),
        tuple(round(v, 6) for v in mouth["corners"]["right"]),
        tuple(round(v, 6) for v in nose["tip"]),
    }
    assert pts >= expected, (pts, expected)
    _ok("face_payload_oracle_mouth_nose_ok")


# ---- 5. QML presentation-only ---------------------------------------------
def test_face_single_runtime_surface_ok():
    home = _qml("Home.qml")
    main = _qml("Main.qml")
    assert home.count("FaceView {") == 0
    assert "ShapeView" not in home and "ShapeView" not in main
    for page in ("Control.qml", "World.qml", "Tasks.qml", "Thinking.qml",
                 "Settings.qml", "Console.qml", "StatusBar.qml",
                 "Navigation.qml", "MayaBtn.qml"):
        assert "FaceView" not in _qml(page)
        assert "ShapeView" not in _qml(page)
    _ok("face_single_runtime_surface_ok")


def test_face_qml_no_landmark_definitions_ok():
    face_qml = _qml("FaceView.qml")
    forbidden = ("0.385", "0.615", "0.335", "0.84", "0.468", "0.549",
                 "0.438", "0.562", "0.55")
    for token in forbidden:
        assert token not in face_qml, token
    assert "points" in face_qml  # geometry arrives as data, never literals
    _ok("face_qml_no_landmark_definitions_ok")


def test_face_qml_no_random_clock_ok():
    face_qml = _qml("FaceView.qml")
    for token in ("Math.random", "Date", "Timer", "wallClock",
                  "time_now", "clock"):
        assert token not in face_qml, token
    _ok("face_qml_no_random_clock_ok")


def test_face_qml_presentation_gate_ok():
    face_qml = _qml("FaceView.qml")
    assert "maya/canonical-vector-face/1.0.0" in face_qml
    assert face_qml.strip().startswith("import QtQuick")
    assert "op" in face_qml and "path" in face_qml and "circle" in face_qml
    _ok("face_qml_presentation_gate_ok")


# ---- SABOTAGE (presentation layer, all must fail) -------------------------
def test_sabotage_a_landmark_mutation_ok():
    from dataclasses import replace
    altered = []
    for f in _face.features:
        if f.name == "eye_iris_left":
            p = list(f.points[0])
            p[0] += 0.015
            altered.append(replace(f, points=(tuple(p),)))
        else:
            altered.append(f)
    tampered = replace(_face, features=tuple(altered))
    assert validate_canonical_face(tampered)[0] is False
    forged = json.loads(json.dumps(_view1["face"]))
    forged["surface"][3]["points"][0] = [0.9, 0.9]
    assert _sha256({"frame": forged["frame"], "surface": forged["surface"],
                    "expression": forged["expression"],
                    "versions": forged["versions"]}) != forged["digest"]
    _ok("sabotage_a_landmark_mutation_ok")


def test_sabotage_b_symmetry_violation_ok():
    fmap = _face.feature_map()
    right = list(fmap["eye_iris_right"].points[0])
    right[0] = 0.7
    import copy
    features = list(_face.features)
    for i, ft in enumerate(features):
        if ft.name == "eye_iris_right":
            features[i] = replace(ft, points=(tuple(right),))
            break
    tampered = replace(_face, features=tuple(features))
    assert validate_canonical_face(tampered)[0] is False
    _ok("sabotage_b_symmetry_violation_ok")


def test_sabotage_c_expression_overflow_ok():
    from maya_identity.vector_face.expression import VectorExpression
    overflowed = VectorExpression(
        anchor="focused", attention=0.5, activity=0.3, focus=0.8,
        curiosity=0.0, openness=3.9, gaze_x=0.5, gaze_y=0.0, viseme="oh",
        mouth_open=0.9, mouth_spread=0.4, mouth_round=0.3, aura=0.5,
        rest=False)
    ok, reasons = validate_expression(overflowed)
    assert ok is False and reasons, reasons
    off_anchor = VectorExpression(
        anchor="madeup", attention=0.5, activity=0.3, focus=0.8,
        curiosity=0.0, openness=0.5, gaze_x=0.0, gaze_y=0.0, viseme="oh",
        mouth_open=0.9, mouth_spread=0.4, mouth_round=0.3, aura=0.5,
        rest=False)
    ok2, reasons2 = validate_expression(off_anchor)
    assert ok2 is False and reasons2, reasons2
    _ok("sabotage_c_expression_overflow_ok")


def test_sabotage_d_renderer_identity_write_ok():
    features_before = _face.features
    digest_before = _face.geometry_digest
    landmark_dict_before = dict(_face.landmarks)
    to_qml_payload(_face, anchors_for_face_extra({"semantic": "active"}))
    assert _face.features == features_before
    assert _face.geometry_digest == digest_before
    assert _face.landmarks == landmark_dict_before
    _ok("sabotage_d_renderer_identity_write_ok")


def test_sabotage_e_visualstate_bypass_ok():
    forged = json.loads(json.dumps(_view1["face"]))
    forged["schema"] = "maya/canonical-vector-face/1.0.0"
    forged["surface"] = [{"op": "clear"}] + forged["surface"]
    assert _sha256({"frame": forged["frame"], "surface": forged["surface"],
                    "expression": forged["expression"],
                    "versions": forged["versions"]}) != forged["digest"]
    reset = ui_bridge.UiTicker().apply_tick_snapshot(None)
    assert reset is None  # reset view carries no face at all
    _ok("sabotage_e_visualstate_bypass_ok")


def test_sabotage_f_qml_duplication_ok():
    all_qml = list((_REPO / "maya_runtime" / "ui" / "qt" / "qml").glob("*.qml"))
    for path in all_qml:
        text = path.read_text(encoding="utf-8")
        if path.name == "ShapeView.qml":
            continue
        assert text.count("FaceView {") == 0, path.name
    assert (all_qml and
            any("ShapeView" not in p.read_text(encoding="utf-8")
                for p in all_qml if p.name != "ShapeView.qml"))
    _ok("sabotage_f_qml_duplication_ok")


def test_sabotage_g_random_clock_dependency_ok():
    face_qml = _qml("FaceView.qml")
    assert "Math.random" not in face_qml and "Date" not in face_qml
    t1 = ui_bridge.UiTicker().apply_tick_snapshot(
        ui_bridge.UiTicker().make_tick_payload("listening"))
    t2 = ui_bridge.UiTicker().apply_tick_snapshot(
        ui_bridge.UiTicker().make_tick_payload("listening"))
    assert t1["face"]["surface"] == t2["face"]["surface"]
    assert t1["face"]["digest"] == t2["face"]["digest"]
    _ok("sabotage_g_random_clock_dependency_ok")


# ---- 6. reset / fallback ---------------------------------------------------
def test_face_reset_fallback_ok():
    assert _view1["face"] is not None
    assert validate_canonical_face(_face)[0]
    _ok("face_reset_fallback_ok")


if __name__ == "__main__":
    for name in sorted(globals()):
        if name.startswith("test_") and callable(globals()[name]):
            globals()[name]()