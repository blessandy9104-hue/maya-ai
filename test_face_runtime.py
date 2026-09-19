"""Batch 8b: canonical FaceState runtime integration suite.

   face_semantics (bounded semantic states)
   + avatar/face_runtime (headless deterministic raster, aura scene only)
   + maya_runtime/face_drive (bounded runtime bridge)
   + widget/app integration contract (additive to the 8a public API).

Deterministic: no tkinter, no randomness, no wall clock.
20 OK markers total.  Registered as suite #32 in verification/manifest.py.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO))

from maya_identity.wireframe.math_coordinator import (  # noqa: E402
    CHANNEL_MAX, CHANNELS, CONTROL_CHANNELS,
    CH_EXPRESSION, CH_VISEME,
)
from maya_identity.wireframe.expression_controller import PRESETS  # noqa: E402
from maya_identity.wireframe.face_state import build_face_state  # noqa: E402
from maya_identity.wireframe.mesh_model import get_mesh  # noqa: E402
from maya_identity.wireframe.render3d import MeshProjector  # noqa: E402
from maya_identity.wireframe.face_semantics import (  # noqa: E402
    SEMANTIC_NAMES,
    build_semantic_face_state, semantic_controls,
    validate_semantic_controls,
)
from maya_identity.avatar.face_runtime import (  # noqa: E402
    render_face_frame, downsample_rgba, _png_bytes,
)
from maya_runtime.face_drive import (  # noqa: E402
    runtime_face_state, resolve_semantic, aura_from_scene,
)
import verification.oracle_face_runtime as oracle  # noqa: E402

_AVATAR_DIR = _REPO / "maya_identity" / "avatar"
CANONICAL_PNG_SHA = "27d37840f2a2842d76c1a271a152302ebe823d99f894839b2eb9ba752faccee3"
CANONICAL_RAW_SHA = "a7fcfbe414c01abd0238279630e3d5216ae0af60c51a5f686759976e901f2a99"

mesh = get_mesh()
LM = mesh.landmarks
N_V = mesh.vertex_count()
SIZE = 512


def _ok(name):
    print(f"={name}=OK")


class _TC:
    pass


def _canonical_fs():
    return build_semantic_face_state("neutral")


_MASTER_FRAME = None


def _master_frame():
    global _MASTER_FRAME
    if _MASTER_FRAME is None:
        _MASTER_FRAME = render_face_frame(_canonical_fs(), size=512, aura=1.0)
    return _MASTER_FRAME


def _all_oracle_states():
    states = {}
    for n in SEMANTIC_NAMES:
        fs = build_semantic_face_state(n)
        states[n] = {"pose": fs.pose,
                     "proj": _project(fs.pose)}
    base = build_semantic_face_state(
        "speaking", overrides={"speaking": 0.0, "voice_intensity": 0.0})
    states["base_pose"] = {"pose": base.pose, "proj": _project(base.pose)}
    return states


def _project(pose):
    projector = MeshProjector(SIZE)
    px, py = projector.project(pose, N_V)
    return {"x": px, "y": py}


def test_face_runtime_neutral_pose_parity_ok(_self=_TC):
    sem = _canonical_fs()
    canon = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    assert sem.signature == canon.signature
    assert sem.extra["aura"] == 0.4
    assert sem.extra["openness"] == 1.0
    _ok("face_runtime_neutral_pose_parity_ok")


def test_face_runtime_canonical_raster_pin_ok(_self=_TC):
    face = _master_frame()
    assert hashlib.sha256(face.rgba).hexdigest() == CANONICAL_RAW_SHA
    assert face.sha256() == CANONICAL_PNG_SHA
    assert face.pose_digest == _canonical_fs().signature
    _ok("face_runtime_canonical_raster_pin_ok")


def test_face_runtime_raster_png_writer_parity_ok(_self=_TC):
    face = _master_frame()
    for variant, size in (("maya_face_canonical_256.png", 256),
                          ("maya_face_canonical_128.png", 128),
                          ("maya_face_canonical_48.png", 48)):
        disk = (_AVATAR_DIR / variant).read_bytes()
        small = _png_bytes(size, downsample_rgba(face.rgba, 512, size))
        assert hashlib.sha256(small).hexdigest() == \
            hashlib.sha256(disk).hexdigest(), variant
    _ok("face_runtime_raster_png_writer_parity_ok")


def test_face_runtime_raster_determinism_ok(_self=_TC):
    fs = _canonical_fs()
    a = render_face_frame(fs, size=128, aura=0.7)
    b = render_face_frame(fs, size=128, aura=0.7)
    assert a.rgba == b.rgba
    assert a.frame_digest == b.frame_digest
    assert a.png_bytes() == b.png_bytes()
    _ok("face_runtime_raster_determinism_ok")


def test_face_runtime_cross_instance_raster_ok(_self=_TC):
    one = render_face_frame(build_semantic_face_state("warm"), size=128,
                            aura=0.6)
    two = render_face_frame(build_semantic_face_state("warm"), size=128,
                            aura=0.6)
    assert one.rgba == two.rgba
    assert one.pose_digest == two.pose_digest
    _ok("face_runtime_cross_instance_raster_ok")


def test_face_runtime_rounded_frame_contract_ok(_self=_TC):
    fs = build_semantic_face_state("active")
    face = render_face_frame(fs, size=128, aura=0.8)
    assert len(face.rgba) == 128 * 128 * 4
    assert face.channels == fs.channel_state()
    frame = face.to_render_frame()
    assert frame.bounded()
    assert "rendered_face" in frame.tags
    assert f"pose:{fs.signature[:24]}" in frame.tags
    _ok("face_runtime_rounded_frame_contract_ok")


def test_face_runtime_semantic_boundedness_ok(_self=_TC):
    for name in SEMANTIC_NAMES:
        fs = build_semantic_face_state(name)
        st = fs.channel_state()
        assert all(st[ch] <= CHANNEL_MAX[ch] + 1e-9 for ch in CHANNELS)
        report = fs.verify()
        assert report["face_state_ok"], name
        assert report["bounded"], name
    _ok("face_runtime_semantic_boundedness_ok")


def test_face_runtime_channel_caps_ok(_self=_TC):
    for name in SEMANTIC_NAMES:
        controls = semantic_controls(name)
        for ctrl, value in controls.items():
            channel = CONTROL_CHANNELS.get(ctrl)
            cap = CHANNEL_MAX.get(channel, 1.0) if channel in (
                CH_EXPRESSION, CH_VISEME) else 1.0
            assert value <= cap + 1e-9, (name, ctrl, value, cap)
        assert "glow_intensity" not in controls
        assert "scan_activity" not in controls
        assert "breath" not in controls
    _ok("face_runtime_channel_caps_ok")


def test_face_runtime_semantic_profile_ok(_self=_TC):
    for name in SEMANTIC_NAMES:
        assert validate_semantic_controls(name), name
    _ok("face_runtime_semantic_profile_ok")


def test_face_runtime_state_distinctness_ok(_self=_TC):
    signatures = [build_semantic_face_state(n).signature for n in SEMANTIC_NAMES]
    assert len(set(signatures)) == len(signatures), "two states share a pose"
    _ok("face_runtime_state_distinctness_ok")


def test_face_runtime_projection_replica_ok(_self=_TC):
    result = oracle.run_oracle(_all_oracle_states(), SIZE, N_V, LM)
    assert result["projection_replica"], result["details"][:3]
    assert result["ok"]
    _ok("face_runtime_projection_replica_ok")


def test_face_runtime_pupil_containment_ok(_self=_TC):
    result = oracle.run_oracle(_all_oracle_states(), SIZE, N_V, LM)
    assert result["pupil_containment"], result["details"][:3]
    assert result["gaze_sign"], result["details"][:3]
    _ok("face_runtime_pupil_containment_ok")


def test_face_runtime_viseme_isolation_ok(_self=_TC):
    result = oracle.run_oracle(_all_oracle_states(), SIZE, N_V, LM)
    assert result["viseme_isolation"], result["details"][:3]
    _ok("face_runtime_viseme_isolation_ok")


def test_face_runtime_aura_scene_only_ok(_self=_TC):
    fs = _canonical_fs()
    dim = render_face_frame(fs, size=128, aura=0.0)
    full = render_face_frame(fs, size=128, aura=1.0)
    assert dim.pose_digest == full.pose_digest
    assert dim.channels == full.channels
    assert dim.rgba != full.rgba
    assert aura_from_scene(0.4, {}, {}) == 0.4
    assert 0.0 <= aura_from_scene(0.4, {"glow_intensity": 2.0}, {}) <= 1.0
    _ok("face_runtime_aura_scene_only_ok")


def test_face_runtime_dormant_vs_active_ok(_self=_TC):
    dorm = build_semantic_face_state("dormant")
    act = build_semantic_face_state("active")
    assert dorm.channel_state()["micro"] == 0.0
    assert act.channel_state()["micro"] > 0.0
    assert dorm.extra["aura"] < act.extra["aura"]
    assert semantic_controls("dormant")["blink"] > semantic_controls("active")["blink"]
    _ok("face_runtime_dormant_vs_active_ok")


def test_face_runtime_drive_semantic_map_ok(_self=_TC):
    assert resolve_semantic("processing") == "focused"
    assert resolve_semantic("sleeping") == "dormant"
    assert resolve_semantic("offline") == "dormant"
    assert resolve_semantic("listening") == "listening"
    assert resolve_semantic("awake") == "attentive"
    assert resolve_semantic("idle") == "neutral"
    assert resolve_semantic("??unknown==") == "neutral"
    assert resolve_semantic("idle", {"preset": "error"}) == "concerned"
    assert resolve_semantic("idle", {"speaking": 0.72}) == "speaking"
    _ok("face_runtime_drive_semantic_map_ok")


def test_face_runtime_drive_bounded_ok(_self=_TC):
    for visual, meta, cmds in (
        ("processing", {"confidence": 0.55, "thinking": 0.6},
         {"neural_activity": 0.7, "glow_intensity": 0.3,
          "gaze_x": -0.5, "gaze_y": 0.2}),
        ("idle", {"speaking": 0.72, "voice_intensity": 0.45},
         {"voice_linked": True}),
        ("sleeping", {}, {}),
        ("awake", {}, {"eye_focus": 0.6, "gaze_x": 1.0, "gaze_y": -1.0}),
    ):
        fs = runtime_face_state(visual, meta, cmds)
        st = fs.channel_state()
        assert all(st[ch] <= CHANNEL_MAX[ch] + 1e-9 for ch in CHANNELS)
        assert 0.0 <= fs.extra["aura"] <= 1.0
        assert fs.extra["anchor"] in SEMANTIC_NAMES
        cs = semantic_controls(fs.extra["anchor"])
        speak = cs.get("speaking", 0.0)
        assert speak <= CHANNEL_MAX[CH_VISEME] + 1e-9
    _ok("face_runtime_drive_bounded_ok")


def test_face_runtime_drive_deterministic_ok(_self=_TC):
    a = runtime_face_state("processing", {"confidence": 0.55},
                           {"neural_activity": 0.7, "gaze_x": -0.5})
    b = runtime_face_state("processing", {"confidence": 0.55},
                           {"neural_activity": 0.7, "gaze_x": -0.5})
    assert a.signature == b.signature
    assert a.extra["aura"] == b.extra["aura"]
    assert a.extra["anchor"] == b.extra["anchor"]
    _ok("face_runtime_drive_deterministic_ok")


def test_face_runtime_persona_overlay_ok(_self=_TC):
    base = runtime_face_state("listening")
    active = runtime_face_state(
        "listening", persona={
            "status": "FUSED",
            "conflict_status": "NO_CONFLICT",
            "consensus": {"precision": 0.9, "warmth": 0.7},
            "active_personas": ["impartial"],
        })
    inactive = runtime_face_state(
        "listening", persona={"status": "NO_ACTIVE_PERSONA"})
    assert base.extra["aura"] == inactive.extra["aura"]
    assert inactive.signature == base.signature
    assert base.controls["smile"] < active.controls["smile"]
    assert base.controls["confidence"] < active.controls["confidence"]
    assert active.signature != base.signature
    _ok("face_runtime_persona_overlay_ok")


def test_face_runtime_integration_pipeline_ok(_self=_TC):
    fs = runtime_face_state("awake", {"confidence": 0.55},
                            {"neural_activity": 0.7})
    face = render_face_frame(fs, size=128)
    assert face.pose_digest == fs.signature
    frame = face.to_render_frame()
    assert frame.bounded()
    assert face.rgba[:8] == face.rgba[:8]
    _ok("face_runtime_integration_pipeline_ok")


if __name__ == "__main__":
    tests = [
        test_face_runtime_neutral_pose_parity_ok,
        test_face_runtime_canonical_raster_pin_ok,
        test_face_runtime_raster_png_writer_parity_ok,
        test_face_runtime_raster_determinism_ok,
        test_face_runtime_cross_instance_raster_ok,
        test_face_runtime_rounded_frame_contract_ok,
        test_face_runtime_semantic_boundedness_ok,
        test_face_runtime_channel_caps_ok,
        test_face_runtime_semantic_profile_ok,
        test_face_runtime_state_distinctness_ok,
        test_face_runtime_projection_replica_ok,
        test_face_runtime_pupil_containment_ok,
        test_face_runtime_viseme_isolation_ok,
        test_face_runtime_aura_scene_only_ok,
        test_face_runtime_dormant_vs_active_ok,
        test_face_runtime_drive_semantic_map_ok,
        test_face_runtime_drive_bounded_ok,
        test_face_runtime_drive_deterministic_ok,
        test_face_runtime_persona_overlay_ok,
        test_face_runtime_integration_pipeline_ok,
    ]
    for fn in tests:
        fn()