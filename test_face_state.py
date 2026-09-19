"""FaceState + visual bridge + identity record parity suite (Batch 7).

Deterministic: no tkinter, no randomness, no wall-clock.
19 OK markers total.  Suite registered as #31 in verification/manifest.py.
"""
from __future__ import annotations

import importlib
import json
import struct
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO))
_COOR_PATH = _REPO / "maya_identity" / "wireframe" / "math_coordinator.py"

from maya_identity.wireframe import rig_math
from maya_identity.wireframe.math_coordinator import (
    CHANNEL_MAX, CHANNELS, CONTROL_CHANNELS, MATH_AGENT,
    CH_EXPRESSION, CH_VISEME, CH_MICRO, CH_ANATOMICAL,
)
from maya_identity.wireframe.mesh_model import get_mesh, MODEL_VERSION
from maya_identity.wireframe.expression_controller import PRESETS, ExpressionController
from maya_identity.wireframe.render3d import MeshProjector
from maya_identity.wireframe.face_state import (
    FACE_STATE_VERSION, PRESETS as _FS_PRESETS,
    build_face_state, channel_state, cross_frame_report,
    face_state_reference_fractions, measure, pose_digest,
    identity_face_state_record, canonical_contract_ok,
    blend_law_review,
)
from maya_runtime.intelligence.visual_bridge import (
    PRIORITY_TO_CONTROL,
    bridge_gate, persona_signals, fused_to_controls, merged_interpreter_inputs,
)
import verification.oracle_face_state as oracle

_REPO_ROOT = _REPO
_IDENTITY_JSON = _REPO_ROOT / "maya_identity" / "identity.json"
_VERSIONS_JSONL = _REPO_ROOT / "maya_identity" / "metadata" / "identity_versions.jsonl"
_GEOMETRY_JSON = _REPO_ROOT / "maya_identity" / "geometry" / "facial_structure.json"

mesh = get_mesh()
BASE = tuple(tuple(v) for v in mesh.verts)
LM = mesh.landmarks
N_V = mesh.vertex_count()


def _ok(name):
    print(f"={name}=OK")


class _TC:
    pass


def _ok0():
    _ok("face_state_constants_ok")


def test_face_state_constants_ok(_self=_TC):
    assert rig_math.math_isclose(
        rig_math.BLEND_E + rig_math.BLEND_V + rig_math.BLEND_M, 1.0, rig_math.POSE_EPSILON
    )
    assert FACE_STATE_VERSION == "1.0.0"
    for ch in CHANNELS:
        assert ch in CHANNEL_MAX
    for ctrl, ch in CONTROL_CHANNELS.items():
        assert ch in CHANNEL_MAX
    _ok0()


def _ok1():
    _ok("face_state_determinism_ok")


def test_face_state_determinism_ok(_self=_TC):
    fs1 = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    fs2 = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    assert fs1.pose == fs2.pose
    assert fs1.signature == fs2.signature
    assert fs1.fields == fs2.fields

    fs_neutral = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    fs_happy = build_face_state(PRESETS["happy"], t=0.5, mesh=mesh)
    assert fs_neutral.pose != fs_happy.pose
    _ok1()


def _ok2():
    _ok("face_state_boundedness_ok")


def test_face_state_boundedness_ok(_self=_TC):
    for name in _FS_PRESETS:
        fs = build_face_state(_FS_PRESETS[name], t=0.5, mesh=mesh)
        st = fs.channel_state()
        for ch in CHANNELS:
            assert st[ch] <= CHANNEL_MAX[ch] + 1e-9, (
                f"{name}/{ch}: {st[ch]} > {CHANNEL_MAX[ch]}"
            )
    _ok2()


def _ok3():
    _ok("face_state_channel_separation_ok")


def test_face_state_channel_separation_ok(_self=_TC):
    _silent = dict(PRESETS["neutral"])
    _silent["speaking"] = 0.0
    _silent["voice_intensity"] = 0.0
    _talk = dict(PRESETS["neutral"])
    _talk["speaking"] = 1.0
    _talk["voice_intensity"] = 0.5
    fs_silent = build_face_state(_silent, t=0.5, mesh=mesh)
    fs_talk = build_face_state(_talk, t=0.5, mesh=mesh)
    eye_landmarks = ("iris_l", "iris_r", "corner_inner_l", "corner_inner_r",
                     "brow_in_l", "brow_in_r")
    mouth_landmarks = ("mouth_corner_l", "mouth_corner_r",
                       "upper_lip_c", "lower_lip_c")
    for name in eye_landmarks:
        i = LM[name]
        for k in range(3):
            assert abs(fs_silent.pose[i][k] - fs_talk.pose[i][k]) < 1e-9, (
                f"viseme moved eye landmark {name} axis {k}"
            )
    for name in mouth_landmarks:
        i = LM[name]
        delta = sum(abs(fs_silent.pose[i][k] - fs_talk.pose[i][k]) for k in range(3))
        assert delta > 1e-9, f"viseme did not move mouth landmark {name}"
    _ok3()


def _ok4():
    _ok("face_state_landmark_projection_order_ok")


def test_face_state_landmark_projection_order_ok(_self=_TC):
    fs = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    cf = fs.cross_frame_report()
    m = cf["measurements"]
    assert m["brow_level_y"] < m["eye_level_y"], "brow not above eye"
    assert m["eye_level_y"] < m["nose_tip"][1], "eye not above nose"
    assert m["nose_tip"][1] < m["mouth_y"], "nose not above mouth"
    assert abs(m["nose_tip"][0] - 0.5) < 0.008, "nose off-center"
    assert abs(m["mouth_corner_x_l"] - (1.0 - m["mouth_corner_x_r"])) < 0.004, (
        "mouth not symmetric"
    )
    _ok4()


def _ok5():
    _ok("face_state_reference_2d_loads_ok")


def test_face_state_reference_2d_loads_ok(_self=_TC):
    ref = face_state_reference_fractions()
    raw = json.loads(_GEOMETRY_JSON.read_text(encoding="utf-8"))
    assert ref["source"] == "geometry/facial_structure.json"
    assert ref["eye_level_y"] == float(raw["eyes"]["level"])
    assert abs(ref["nose_tip"][0] - float(raw["nose"]["tip"][0])) < 1e-9
    assert abs(ref["mouth_corner_y"] - float(raw["mouth"]["corners"]["left"][1])) < 1e-9
    _ok5()


def _ok6():
    _ok("face_state_cross_frame_residuals_ok")


def test_face_state_cross_frame_residuals_ok(_self=_TC):
    fs = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    cf = fs.cross_frame_report()
    assert cf["structure_ok"], f"structure violations: {cf['violations']}"
    for feature, resid in cf["residuals"].items():
        if resid is not None:
            assert resid <= cf["tolerances"][feature] + 1e-9, (
                f"{feature}: residual {resid} > tol {cf['tolerances'][feature]}"
            )
    _ok6()


def _ok7():
    _ok("face_state_symmetry_neutral_ok")


def test_face_state_symmetry_neutral_ok(_self=_TC):
    fs = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    pose = fs.pose
    # authored boundary: strict antisymmetry in the base mesh
    bx_r = BASE[LM["mouth_corner_r"]][0]
    bx_l = BASE[LM["mouth_corner_l"]][0]
    assert abs(bx_r + bx_l) < 1e-9, f"authored mouth corners not symmetric: {bx_r}, {bx_l}"
    bn_x = BASE[LM["nose_tip"]][0]
    assert abs(bn_x) < 1e-9, f"authored nose tip off x=0: {bn_x}"
    # pose-time: documented micro-tremor band (MIT=0.1 * micro amp)
    rx = pose[LM["mouth_corner_r"]][0]
    lx = pose[LM["mouth_corner_l"]][0]
    residual = abs(rx + lx)
    assert residual < 0.005, f"pose-time mouth corner residual {residual}"
    nx = pose[LM["nose_tip"]][0]
    assert abs(nx) < 0.002, f"pose-time nose tip off center: {nx}"
    _ok7()


def _ok8():
    _ok("face_state_render_frame_bridge_ok")


def test_face_state_render_frame_bridge_ok(_self=_TC):
    fs = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    frame = fs.to_render_frame()
    ch = frame.channels
    assert "expression" in ch and "viseme" in ch and "micro" in ch and "anatomical" in ch
    for c in CHANNELS:
        assert ch[c] <= CHANNEL_MAX[c] + 1e-9, f"channel {c} exceeds ceiling"
    tags = frame.tags
    assert tags[0] == "face_state"
    assert tags[2] == f"v:{FACE_STATE_VERSION}"
    assert tags[3] == f"mesh:{MODEL_VERSION}"
    _ok8()


def _ok9():
    _ok("face_state_audit_consistency_ok")


def test_face_state_audit_consistency_ok(_self=_TC):
    for name in ["neutral", "speaking", "happy", "thinking"]:
        fs = build_face_state(PRESETS[name], t=0.5, mesh=mesh)
        assert fs.audit.get("ok"), f"audit failed for {name}"
        assert fs.audit.get("pose_ok"), f"pose_ok failed for {name}"
        assert fs.audit.get("consistency_ok"), f"consistency failed for {name}"
    _ok9()


def _ok10():
    _ok("persona_bridge_active_ok")


def test_persona_bridge_active_ok(_self=_TC):
    fused = {
        "status": "FUSED",
        "fusion_method": "weighted_multi_persona_fusion",
        "active_personas": ["tutor", "concierge"],
        "weights": {"tutor": 0.7, "concierge": 0.3},
        "consensus": {
            "precision": 0.75,
            "conservatism": 0.40,
            "interpretation": 0.30,
            "empathy": 0.55,
            "curiosity": 0.60,
            "uncertainty": 0.20,
        },
        "per_persona_contributions": [],
        "conflicts": [],
        "conflict_status": "WEIGHTED_DISAGREEMENT",
        "unresolved_dimensions": [],
        "constraints": [],
        "inherited_epistemic": {},
        "safety": {},
        "notes": [],
        "excluded_inactive": [],
        "provenance": {},
    }
    gate = bridge_gate(fused)
    assert gate["active"], f"gate should be active: {gate}"
    sig = persona_signals(fused)
    assert sig["active"]
    assert "confidence" in sig["signals"]
    assert "calm" in sig["signals"]
    assert "thinking" in sig["signals"]
    assert "attention" in sig["signals"]
    assert "smile" in sig["signals"]
    assert sig["signals"]["confidence"] <= CHANNEL_MAX[CH_EXPRESSION] + 1e-9
    assert sig["signals"]["calm"] <= CHANNEL_MAX[CH_EXPRESSION] + 1e-9

    merged = merged_interpreter_inputs({"attention": 0.1}, fused)
    assert merged["attention"] >= 0.1
    _ok10()


def _ok11():
    _ok("persona_bridge_no_active_ok")


def test_persona_bridge_no_active_ok(_self=_TC):
    fused = {
        "status": "NO_ACTIVE_PERSONA",
        "fusion_method": "",
        "active_personas": [],
        "weights": {},
        "consensus": {},
        "per_persona_contributions": [],
        "conflicts": [],
        "conflict_status": "NO_CONFLICT",
        "unresolved_dimensions": [],
        "constraints": [],
        "inherited_epistemic": {},
        "safety": {},
        "notes": [],
        "excluded_inactive": [],
        "provenance": {},
    }
    gate = bridge_gate(fused)
    assert not gate["active"]
    sig = persona_signals(fused)
    assert not sig["active"]
    assert sig["signals"] == {}
    _ok11()


def _ok12():
    _ok("persona_bridge_conflict_blocking_ok")


def test_persona_bridge_conflict_blocking_ok(_self=_TC):
    for status in ("UNRESOLVED_CONFLICT", "INCOMPATIBLE"):
        fused = {
            "status": "FUSED",
            "fusion_method": "weighted_multi_persona_fusion",
            "active_personas": ["tutor", "tutor"],
            "weights": {"tutor": 1.0},
            "consensus": {"precision": 0.9, "empathy": 0.1},
            "per_persona_contributions": [],
            "conflicts": [],
            "conflict_status": status,
            "unresolved_dimensions": ["precision"],
            "constraints": [],
            "inherited_epistemic": {},
            "safety": {},
            "notes": [],
            "excluded_inactive": [],
            "provenance": {},
        }
        gate = bridge_gate(fused)
        assert not gate["active"], f"expected inactive for {status}: {gate}"
        assert gate["reason"] == status
    _ok12()


def _ok13():
    _ok("identity_record_constants_ok")


def test_identity_record_constants_ok(_self=_TC):
    data = json.loads(_IDENTITY_JSON.read_text(encoding="utf-8"))
    fs_block = data.get("face_state")
    assert fs_block is not None, "no face_state block in identity.json"
    assert fs_block["status"] == "established"
    assert fs_block["version"] == FACE_STATE_VERSION
    assert fs_block["mesh_model_version"] == MODEL_VERSION
    assert fs_block["engine"] == "maya_identity.wireframe.face_state"
    assert fs_block["blend_law"]["expression"] == rig_math.BLEND_E
    assert fs_block["blend_law"]["viseme"] == rig_math.BLEND_V
    assert fs_block["blend_law"]["micro"] == rig_math.BLEND_M
    for ch in CHANNELS:
        assert fs_block["channel_ceilings"][ch] == CHANNEL_MAX[ch], (
            f"channel {ch} mismatch: {fs_block['channel_ceilings'][ch]} != {CHANNEL_MAX[ch]}"
        )
    assert data["canonical_face"]["status"] == "established"
    assert data["face_version"] == "1.0.0"
    _ok13()


def _ok14():
    _ok("identity_version_event_ok")


def test_identity_version_event_ok(_self=_TC):
    lines = _VERSIONS_JSONL.read_text(encoding="utf-8").splitlines()
    matches = []
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("version") == FACE_STATE_VERSION:
            matches.append(row)
    assert len(matches) == 1, f"expected exactly 1 event for {FACE_STATE_VERSION}, got {len(matches)}"
    event = matches[0]
    assert event["event"] == "identity_evolution"
    assert event["change_kind"] == "improved_rendering"
    assert event["validation"] == "validated"
    _ok14()


def _ok15():
    _ok("oracle_parity_ok")


def test_oracle_parity_ok(_self=_TC):
    fs = build_face_state(PRESETS["speaking"], t=0.5, mesh=mesh)
    report = oracle.run_oracle(
        runtime_projections=fs.projections,
        runtime_fields=list(fs.fields),
        runtime_pose=list(fs.pose),
        base_verts=list(BASE),
        landmarks=LM,
        mesh_vertex_count=N_V,
    )
    assert report["ok"], f"oracle parity failed: {report['details']}"
    assert report["compose_double_parity"]
    assert report["compose_fraction_parity"]
    assert report["projection_parity"]
    assert report["depth_chain_parity"]
    assert report["jaw_envelope_parity"]
    _ok15()


def _ok16():
    _ok("provenance_readonly_ok")


def _test_hash(path):
    return path.read_bytes().hex()


def test_provenance_readonly_ok(_self=_TC):
    h1 = _test_hash(_IDENTITY_JSON)
    h2 = _test_hash(_VERSIONS_JSONL)
    h3 = _test_hash(_GEOMETRY_JSON)
    build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    build_face_state(PRESETS["happy"], t=0.5, mesh=mesh)
    assert _test_hash(_IDENTITY_JSON) == h1, "identity.json mutated"
    assert _test_hash(_VERSIONS_JSONL) == h2, "identity_versions.jsonl mutated"
    assert _test_hash(_GEOMETRY_JSON) == h3, "facial_structure.json mutated"
    _ok16()


def _ok17():
    _ok("widget_path_stable_ok")


def test_widget_path_stable_ok(_self=_TC):
    from maya_identity.embodiment.presence_engine import PresenceEngine
    from maya_identity.wireframe import MayaWireframeFace
    assert hasattr(PresenceEngine, "tick")
    assert hasattr(MayaWireframeFace, "__init__")
    sig = __import__("inspect").signature(PresenceEngine.tick)
    assert "persona" in sig.parameters, "persona param missing from PresenceEngine.tick"
    _ok17()


def test_face_state_contract_referee_ok(_self=_TC):
    ref = canonical_contract_ok()
    assert ref["recorded"], "no face_state record in identity.json"
    assert ref["all_ok"], f"contract referee failed: {ref['checks']}"
    for name, check in sorted(ref["checks"].items()):
        assert check, f"contract check {name} failed"
    _ok("face_state_contract_referee_ok")


if __name__ == "__main__":
    tests = [
        test_face_state_constants_ok,
        test_face_state_determinism_ok,
        test_face_state_boundedness_ok,
        test_face_state_channel_separation_ok,
        test_face_state_landmark_projection_order_ok,
        test_face_state_reference_2d_loads_ok,
        test_face_state_cross_frame_residuals_ok,
        test_face_state_symmetry_neutral_ok,
        test_face_state_render_frame_bridge_ok,
        test_face_state_audit_consistency_ok,
        test_persona_bridge_active_ok,
        test_persona_bridge_no_active_ok,
        test_persona_bridge_conflict_blocking_ok,
        test_identity_record_constants_ok,
        test_identity_version_event_ok,
        test_oracle_parity_ok,
        test_provenance_readonly_ok,
        test_widget_path_stable_ok,
        test_face_state_contract_referee_ok,
    ]
    for fn in tests:
        fn()
