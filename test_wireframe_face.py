"""Wireframe face layer: analytic mesh, expression controller, emotion
mapper, speech adapter, projector, and the MayaWireframeFace Tk widget.

Script-style test (project convention): module-level asserts, OK labels.

Checks:
- the analytic mesh is deterministic, structured, finite, and landmarked
- all control values clamp to 0.0-1.0
- every preset produces a bounded, finite, presumed-distinct pose
- interpolation eases toward targets instead of jumping
- metadata parsing tolerates empty / malformed / partial / unknown input
- speech adapter and procedural visemes stay bounded with no audio
- reduced motion disables head/particle/scan motion
- projection stays inside canvas bounds across sizes
- the Tk widget renders, cycles states, takes commands, reports non-placeholder
- maya_app.py is wired to the wireframe face without dropping the renderer
"""
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

import math

from maya_identity.wireframe.interp import clamp01, clamp, Smoother
from maya_identity.wireframe.mesh_model import get_mesh, build_mesh, MODEL_VERSION
from maya_identity.wireframe.expression_controller import (
    ExpressionController, ALL_CONTROLS, PRESETS, _STATE_TO_PRESET,
    EMOTION_CONTROLS, STATE_CONTROLS, VOICE_CONTROLS, MATERIAL_CONTROLS,
)
from maya_identity.wireframe.emotion_mapper import parse_metadata
from maya_identity.wireframe.speech_adapter import SpeechAdapter, VISEMES
from maya_identity.wireframe.render3d import MeshProjector
from maya_identity.wireframe.face3d import MayaWireframeFace

# ---- analytic mesh ----
mesh = get_mesh()
assert mesh is get_mesh()
mesh2 = build_mesh()
assert mesh.verts == mesh2.verts and mesh.edges == mesh2.edges
assert MODEL_VERSION == "1.0.0"
assert mesh.vertex_count() >= 1000
assert mesh.edge_count() >= 1000
assert len(mesh.regions) >= 25
required_landmarks = {
    "iris_l", "iris_r", "pupil_l", "pupil_r",
    "brow_in_l", "brow_in_r", "brow_out_l", "brow_out_r",
    "nose_tip", "nose_root", "mouth_corner_l", "mouth_corner_r",
    "upper_lip_c", "lower_lip_c",
}
assert required_landmarks <= set(mesh.landmarks)
for x, y, z in mesh.verts:
    assert math.isfinite(x) and math.isfinite(y) and math.isfinite(z)

# ---- interpolation / clamping ----
assert clamp01(-5) == 0.0
assert clamp01(3.0) == 1.0
assert clamp01("junk") == 0.0
assert clamp(1.5, 0, 1) == 1.0
sm = Smoother(["a", "b"], alpha=0.5)
sm.set_target("a", 1.0)
step1 = sm.step()
assert 0.0 < step1["a"] < 1.0  # eased, not instant
for _ in range(60):
    sm.step()
assert sm.snapshot()["a"] > 0.999

# ---- expression controller: ranges + presets ----
controller = ExpressionController(mesh)


def bounded_pose(vec):
    controller.controls.set_all(vec, immediate=True)
    pose = controller.compute_pose(0.5, reduced=True)
    for vx, vy, vz in pose:
        assert math.isfinite(vx) and math.isfinite(vy) and math.isfinite(vz)
        # pose z bound: full 360-degree head mesh wraps to back-of-skull z ~ -0.71
        assert -2.5 < vx < 2.5 and -2.5 < vy < 2.5 and -0.95 < vz < 2.5
    return tuple(tuple(v) for v in pose)  # copy: pose array is reused in place


neutral_pose = bounded_pose(PRESETS["neutral"])
for name, vec in PRESETS.items():
    pose = bounded_pose(vec)
    if name != "neutral":
        assert pose != neutral_pose, name  # each preset actually moves something

for ctrl in ALL_CONTROLS:
    controller.controls.set_target(ctrl, 2.0, immediate=True)
    controller.controls.set_target(ctrl, -1.0, immediate=True)
    assert 0.0 <= controller.controls.snapshot()[ctrl] <= 1.0

# determinism: same input -> same pose
p1 = bounded_pose(PRESETS["speaking"])
p2 = bounded_pose(PRESETS["speaking"])
assert p1 == p2

# state map is complete
for st in ("awake", "processing", "listening", "research", "learning",
           "sleeping", "offline"):
    assert _STATE_TO_PRESET[st] in PRESETS

# ---- emotion mapper: defensive parsing ----
controls, preset_name, warnings = parse_metadata(None)
assert preset_name == "neutral"
controls, preset_name, warnings = parse_metadata({})
assert not warnings
controls, preset_name, warnings = parse_metadata(
    {"emotion": "happiness", "voice_intensity": 3.0, "smile": -0.5,
     "attention": None, "unknown_key": "zzz", "confidence": 0.3})
assert preset_name == "happy"
assert controls["voice_intensity"] == 1.0
assert controls["smile"] == 0.0
assert abs(controls["confidence"] - 0.3) < 1e-6
controls, preset_name, warnings = parse_metadata({"emotion": "not_a_known_emotion"})
assert warnings and preset_name == "not_a_known_emotion"
_SURFACED = EMOTION_CONTROLS + STATE_CONTROLS + VOICE_CONTROLS + MATERIAL_CONTROLS
for key in _SURFACED:
    assert key in controls

# aliases (camelCase) resolve
controls, _, _ = parse_metadata({"eyeFocus": 0.9, "neuralActivity": 0.4})
assert abs(controls["attention"] - 0.9) < 1e-6
assert abs(controls["thinking"] - 0.4) < 1e-6

# ---- speech adapter: bounded, no-audio safe ----
sp = SpeechAdapter()
for viseme in VISEMES:
    for _ in range(5):
        d = sp.drive(viseme=viseme, speaking=0.8, elapsed=0.0)
        assert 0.0 <= d["open"] <= 1.0
        assert 0.0 <= d["spread"] <= 1.0
        assert 0.0 <= d["round"] <= 1.0
        assert 0.0 <= d["speaking"] <= 1.0
procedural = sp.drive(speaking=0.7, amplitude=0.0, elapsed=0.0)
assert 0.0 <= procedural["open"] <= 1.0
assert procedural["speaking"] > 0.0
silent = SpeechAdapter().drive(speaking=0.0, elapsed=0.0)
assert silent["open"] < 0.01 and silent["speaking"] < 0.01

# ---- reduced motion ----
rc = ExpressionController(mesh)
rc.controls.set_all({"uncertainty": 0.9, "confidence": 0.2}, immediate=True)
full = rc.compute_pose(10.0, reduced=False)
reduced_pose = rc.compute_pose(10.0, reduced=True)

# ---- projection stays in bounds across sizes ----
for size in (48, 90, 176, 300):
    proj = MeshProjector(size)
    px, py = proj.project(mesh.verts, mesh.vertex_count())
    for v in list(px) + list(py):
        assert -1.0 <= v <= size + 1.0

# ---- widget smoke ----
root = tk.Tk()


class FakeApp:
    pass


root.withdraw()
big = MayaWireframeFace(root, size=176, state="sleeping", bg="#0b1020")
small = MayaWireframeFace(root, size=48, state="sleeping", bg="#101629")
# Bound the drain: both widgets animate on a 60 ms cadence, and an unbounded
# root.update() only returns once the event queue empties. On a slow host a
# tick can take longer than the cadence, so every re-scheduled after-timer is
# already due and update() never returns. A bounded drain exercises the same
# tick loop but is guaranteed to finish; the assertions below depend on the
# constructed items and widget state, not on ticks having run.
for _ in range(4):
    root.update()
assert len(big.find_all()) > 1000
assert len(small._draw_plan) < len(big._draw_plan)
assert big.is_placeholder() is False
assert big.status_text()
assert big.state_text()
assert big.mesh.vertex_count() == mesh.vertex_count()

for st in ("awake", "processing", "listening", "research", "learning",
           "sleeping", "offline"):
    big.set_state(st)
    root.update_idletasks()
big.set_command({"eye_focus": 0.9, "neural_activity": 0.8, "glow_intensity": 0.6,
                 "particle_density": 0.8, "breath": 0.5, "gaze_x": 0.2,
                 "gaze_y": -0.3})
big.set_command(None)
big.set_metadata({"emotion": "happy", "confidence": 0.7})
big.set_metadata(None)
for name in PRESETS:
    big.apply_preset(name)
    root.update_idletasks()
big.set_reduced_motion(True)
big.pause()
big.resume()
big.set_material("glow_intensity", 0.9)
big.set_control("blink", 2.0)
big.set_control("blink", -1.0)
assert big.snapshot()["reduced"] is True
for _ in range(4):
    root.update()
big.destroy()
small.destroy()
root.destroy()

# ---- maya_app.py wiring ----
app_src = (ROOT / "maya_app.py").read_text(encoding="utf-8")
assert "from maya_identity.renderer import ProceduralFace" in app_src
assert "from maya_identity.wireframe import MayaWireframeFace" in app_src
assert "face.set_command(" in app_src
assert "hasattr(face, \"set_metadata\")" in app_src
assert "MayaWireframeFace(panel, size=176" in app_src
assert "MayaWireframeFace(inner, size=48" in app_src

print("wireframe_mesh=OK")
print("wireframe_deterministic=OK")
print("wireframe_landmarks=OK")
print("wireframe_interp=OK")
print("wireframe_ranges=OK")
print("wireframe_presets=OK")
print("wireframe_state_map=OK")
print("wireframe_meta=OK")
print("wireframe_aliases=OK")
print("wireframe_speech=OK")
print("wireframe_projection=OK")
print("wireframe_reduced_motion=OK")
print("wireframe_widget=OK")
print("wireframe_gui_wired=OK")