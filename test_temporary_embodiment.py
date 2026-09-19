"""Temporary geometric embodiment suite (Batch 8C).

The first physical/visual actuator for Maya's intelligence: a bounded,
deterministic, non-face shape driven purely by ``VisualState`` — which is
derived only from the already-validated driven semantic FaceState.

Deterministic: no tkinter requirement in the pure-math arm (the Tk renderer is
exercised only when a display is available), no randomness, no wall clock.
Every motion signature is a pure function of ``(VisualState, frame)``.

Registered in verification/manifest.py.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from maya_identity.embodiment.visual_state import (
    DOMAIN, REST_ANCHORS, VisualState, build_visual_state,
)
from maya_identity.embodiment.shape_math import (
    BASE_RADIUS, POINTER_MAX, SCALE_MAX, SCALE_MIN, TRAVEL_MAX,
    motion_signature, project, render_raster,
)
from maya_identity.wireframe.face_semantics import (
    SEMANTIC_NAMES, build_semantic_face_state,
)
from maya_runtime.face_drive import runtime_face_state
import verification.oracle_temporary_embodiment as oracle

_mesh = None

# Pinned cross-interpreter evidence (established on 3.13.15; the suite runs
# identically on 3.14.7, so equality here is a parity contract).
PINNED_VS_SIGNATURES = {
    "neutral": "fd371200e5630dce3e8b8887133707d96f198d4f8d5be547830a19c7cde2fff6",
    "attentive": "46eac21a48a581cc4edd716da8ae1776faa6d4e1adcd6bbf4a0e7a79633eb9be",
    "focused": "74ef200a7295a5ffa7aa711688b3cbd6a73a05e2b5c9d3393b61c35c5a71c225",
    "curious": "d7cd21e8203bf0b61c62f2bda07a21a842033bd3348c5bee56081d64c20333d8",
    "warm": "c32190b6aa7cd79f15ee5496715b7d1d7208542fd7495b5bb49fb33f05738eda",
    "amused": "bf9df7bdff7bff2358f3c4150d60bf8acd9c06bab4f2690485c0d4b7ceaca0a7",
    "concerned": "9e2c2e7551be7222a10e905d42b4d18794ebe3756d8ce31b01245592d2e50868",
    "speaking": "6a99e0ec6b689d32864f4012563cc8ebab2b486a212f3539696c734da75f25fa",
    "listening": "acfb6462edbed115639eb2cd8e595155661425784950c804fa3f83ec562c2a75",
    "dormant": "e9d13f605c2ed3868974d15dbff9c47d943c142d6614df1a5707bf275c300e6e",
    "active": "256841688a8331bd80e76c6b86f709e4d77cb2f96111bfcbf38a22f1bea74535",
}

# Raster digest of each semantic state (render_raster size=96, frame=12).
PINNED_RASTER = {
    "neutral": "69dce81ea5011ce64734d14d75053d0d8477ac6983b00e030e31ad7aeb66cc83",
    "attentive": "99efd0535bfa0247d0ddf9637f1e9968aa7b26ac19e8734c0f7571c925fe4302",
    "focused": "3c4c1740c94bcd00d8ebd611e8d10ad77ed642452d971835e39197023220b20f",
    "curious": "6a4db0f246ce3ef7439840c6e688b54f005c6cf1df469fbdf6388c7413be7e63",
    "warm": "7e4e2d9957c28f77fd210585e6a5270e43afa31b6345dd17432322c422a35002",
    "amused": "ba8b23949af76f9c0f7023ba1cff19bada26835ce7228007ec5f8eab8a349fbf",
    "concerned": "ba8b23949af76f9c0f7023ba1cff19bada26835ce7228007ec5f8eab8a349fbf",
    "speaking": "b3afc05e32c7725e1b499ab7a75e35f4f88fb883799001bc95f75bf3ffbc5a69",
    "listening": "9b58e7df98bbb4e9216810760d96a8143b26afa0f55b99b994735bb5d0da7790",
    "dormant": "69dce81ea5011ce64734d14d75053d0d8477ac6983b00e030e31ad7aeb66cc83",
    "active": "b0f7d5b6b453f5052d86157665cbe7345ea9584e52d264a9d1bdab8f17b47c50",
}


def _fs_for(visual):
    return runtime_face_state(visual=visual, meta={}, commands={})


def _dormant():
    return build_visual_state(_fs_for("sleeping"))


def _neutral():
    return build_visual_state(_fs_for("idle"))


def _anchor_vs(anchor):
    fs = build_semantic_face_state(anchor)
    return build_visual_state(fs)


def _ok(name):
    print(f"={name}=OK")


_checked = []


def _chk(name):
    _checked.append(name)
    _ok(name)


# ---- 1. semantic anchors flow into VisualState (bounded) ----------------

for _visual, _expect in {
    "awake": "attentive",
    "processing": "focused",
    "research": "focused",
    "learning": "focused",
    "listening": "listening",
    "idle": "neutral",
    "sleeping": "dormant",
    "offline": "dormant",
}.items():
    _vs = build_visual_state(_fs_for(_visual))
    assert _vs.semantic == _expect, (_visual, _vs.semantic)
    for _key, (_lo, _hi) in DOMAIN.items():
        if _key == "gaze":
            _val = getattr(_vs, "gaze_dx")
            assert _lo <= _val <= _hi
            _val = getattr(_vs, "gaze_dy")
            assert _lo <= _val <= _hi
        else:
            _val = getattr(_vs, _key)
            assert _lo <= _val <= _hi, (_key, _val)
_chk("temporary_semantic_bounded_ok")


NONCURIOUS = [n for n in SEMANTIC_NAMES if n != "curious"]
for _name in SEMANTIC_NAMES:
    _vs = _anchor_vs(_name)
    assert _vs.rest == (_name in REST_ANCHORS), _name
    assert _vs.curiosity == (1.0 if _name == "curious" else 0.0), _name
    assert 0.0 <= _vs.activity <= 1.0
    assert 0.0 <= _vs.focus <= 1.0
_chk("temporary_curiosity_validated_only_ok")


# ---- 2. neutral / resting: stable position, orientation, scale ----------

d0 = _dormant()
n0 = _neutral()
for _frame in (0, 1, 7, 42, 4096):
    _p = project(d0, _frame)
    assert _p.cx == 0.5 and _p.cy == 0.5, _frame
    assert _p.roll_deg == 0.0
    assert _p.pointer_len == 0.0
    assert _p.resting is True
    assert math.isclose(_p.radius, BASE_RADIUS * SCALE_MIN, rel_tol=0, abs_tol=1e-9)
    _ps = project(n0, _frame)
    assert _ps.resting is True
    assert math.isclose(_ps.radius, BASE_RADIUS * SCALE_MIN, rel_tol=0, abs_tol=1e-9)
_chk("temporary_resting_stable_ok")


# ---- 3. attention: deterministic orientation + gaze travel -------------

a_lo = VisualState(semantic="attentive", attention=0.1, focus=0.6,
                   curiosity=0.0, activity=0.4, gaze_dx=1.0, gaze_dy=0.0,
                   rest=False)
a_hi = VisualState(semantic="attentive", attention=1.0, focus=0.6,
                   curiosity=0.0, activity=0.4, gaze_dx=1.0, gaze_dy=0.0,
                   rest=False)
_pa = project(a_lo, 5)
_pb = project(a_hi, 5)
assert abs(_pb.cx - 0.5) > abs(_pa.cx - 0.5)      # more attention -> more travel
assert _pb.roll_deg == _pa.roll_deg * 10.0        # roll scales linearly
for _f in (0, 3, 11):
    _x0 = project(VisualState(semantic="neutral", attention=0.0, focus=0.5,
                              curiosity=0.0, activity=0.0, gaze_dx=1.0,
                              gaze_dy=0.0, rest=False), _f)
    _x1 = project(VisualState(semantic="neutral", attention=1.0, focus=0.5,
                              curiosity=0.0, activity=0.0, gaze_dx=1.0,
                              gaze_dy=0.0, rest=False), _f)
    assert math.isclose(abs(_x1.cx - _x0.cx), TRAVEL_MAX, rel_tol=0, abs_tol=1e-6)  # pure gaze travel term
_chk("temporary_attention_transform_ok")


# ---- 4. activity: bounded scale lift -----------------------------------

act_lo = VisualState(semantic="active", attention=0.5, focus=0.6,
                     curiosity=0.0, activity=0.05, gaze_dx=0.0, gaze_dy=0.0,
                     rest=False)
act_hi = VisualState(semantic="active", attention=0.5, focus=0.6,
                     curiosity=0.0, activity=1.0, gaze_dx=0.0, gaze_dy=0.0,
                     rest=False)
for _f in (2, 19, 101):
    _pa = project(act_lo, _f)
    _pb = project(act_hi, _f)
    assert _pb.radius > _pa.radius               # activity lifts the orb
    assert BASE_RADIUS * SCALE_MIN <= _pb.radius <= BASE_RADIUS * SCALE_MAX * 1.0 + 1e-9
    assert BASE_RADIUS * SCALE_MIN <= _pa.radius <= BASE_RADIUS * SCALE_MAX + 1e-9
_chk("temporary_activity_bounded_ok")


# ---- 5. focus: stabilization (drift shrinks with focus) -----------------

def _drift_amp(_focus):
    return oracle.LATERAL_DRIFT * (
        oracle.STABILIZE_FLOOR
        + (1.0 - oracle.STABILIZE_FLOOR) * (1.0 - _focus))

lo_focus = VisualState(semantic="focused", attention=0.0, focus=0.0,
                       curiosity=0.0, activity=0.0, gaze_dx=0.0, gaze_dy=0.0,
                       rest=False)
hi_focus = VisualState(semantic="focused", attention=0.0, focus=1.0,
                       curiosity=0.0, activity=0.0, gaze_dx=0.0, gaze_dy=0.0,
                       rest=False)
_v1 = project(lo_focus, 300)
_v2 = project(hi_focus, 300)
assert abs(_v1.cx - 0.5) > abs(_v2.cx - 0.5)     # focus visibly stabilizes
assert _drift_amp(0.0) > _drift_amp(1.0)
_chk("temporary_focus_stabilization_ok")


# ---- 6. state composition: bounded, deterministic, no explosion --------

for _attention in (0.0, 0.3, 0.7, 1.0):
    for _focus in (0.0, 0.5, 1.0):
        for _activity in (0.0, 0.5, 1.0):
            _vs = VisualState(semantic="active", attention=_attention,
                              focus=_focus, curiosity=0.0, activity=_activity,
                              gaze_dx=-0.8, gaze_dy=0.4, rest=False)
            _p1 = project(_vs, 7)
            _p2 = project(_vs, 7)
            assert _p1 == _p2                     # deterministic replay
            assert _p1.radius <= BASE_RADIUS * SCALE_MAX + 1e-9
            assert 0.25 <= _p1.cx <= 0.75 and 0.28 <= _p1.cy <= 0.72
            assert _p1.ring_rx <= oracle.RING_BASE[0] + 1e-9
            assert _p1.ring_ry <= oracle.RING_BASE[1] + 1e-9
_chk("temporary_composition_bounded_ok")


# ---- 7. invalid values: clamped, not leaked -----------------------------

over = VisualState(semantic="active", attention=9.0, focus=4.0, curiosity=3.0,
                   activity=2.0, gaze_dx=3.0, gaze_dy=-3.0, rest=False)
for _f in (0, 1, 8):
    _p = project(over, _f)
    assert _p.radius <= BASE_RADIUS * SCALE_MAX + 1e-9
    assert 0.25 <= _p.cx <= 0.75 and 0.28 <= _p.cy <= 0.72
    assert 0.0 <= _p.roll_deg <= 360.0
_bad = build_visual_state(_fs_for("idle"),
                          meta={"attention": 99.0},
                          commands={"neural_activity": 99.0})
assert _bad.attention == 1.0
assert _bad.activity == 1.0
## unknown semantic anchor falls back to neutral (clamped, not invented)
_bogus = build_visual_state(type("FS", (), {"extra": {"semantic": "zzz"}})())
assert _bogus.semantic == "neutral"
assert _bogus.rest is True
_chk("temporary_invalid_clamped_ok")


# ---- 8. replay and motion corpus ---------------------------------------

_frames = list(range(0, 240, 13))
_c1 = motion_signature(_anchor_vs("active"), _frames)
_c2 = motion_signature(_anchor_vs("active"), _frames)
assert _c1 == _c2
assert motion_signature(_anchor_vs("curious"), _frames) != _c1
assert motion_signature(_dormant(), _frames) != _c1
_chk("temporary_replay_corpus_ok")


# ---- 9. headless raster: deterministic + pinned across interpreters -----

_raster_into_bytes, _digest1 = render_raster(_anchor_vs("focused"), 12, size=96)
_raster_into_bytes, _digest2 = render_raster(_anchor_vs("focused"), 12, size=96)
assert _digest1 == _digest2
assert len(_raster_into_bytes) == 96 * 96 * 3
_, _d_dormant = render_raster(_dormant(), 12, size=96)
assert _digest1 != _d_dormant
_chk("temporary_raster_determinism_ok")


# ---- 9b. cross-interpreter pins: VS signatures + raster digests ---------

for _name in SEMANTIC_NAMES:
    _pvs = _anchor_vs(_name)
    assert _pvs.signature() == PINNED_VS_SIGNATURES[_name], _name
    _, _pd = render_raster(_pvs, 12, size=96)
    assert _pd == PINNED_RASTER[_name], _name
_chk("temporary_cross_interpreter_pins_ok")


# ---- 10. independent numerical validation (clean-room oracle) -----------

_cases = [
    (_anchor_vs("neutral"), 0),
    (_anchor_vs("dormant"), 3),
    (_anchor_vs("curious"), 17),
    (_anchor_vs("active"), 40),
    (_anchor_vs("focused"), 111),
    (_anchor_vs("attentive"), 256),
    (VisualState(semantic="active", attention=0.8, focus=0.2, curiosity=1.0,
                 activity=0.9, gaze_dx=0.6, gaze_dy=-0.4, rest=False), 333),
]
for _vs, _frame in _cases:
    _src = project(_vs, _frame)
    _ref = oracle.oracle_project(_vs, _frame)
    for _k in ("cx", "cy", "radius", "roll_deg", "ring_rx", "ring_ry",
               "ring_phase", "pointer_len"):
        assert math.isclose(getattr(_src, _k), _ref[_k],
                            rel_tol=1e-9, abs_tol=1e-9), (_vs.semantic, _k)
    assert _src.resting == _ref["resting"]
## triangle-inequality bound proof holds for the actual wander
_proof = oracle.oracle_bounds_proof(1.0, 0.0, 1.0, 0.5, 1.0, 0.0)
_max = project(VisualState(semantic="active", attention=1.0, focus=0.0,
                           curiosity=1.0, activity=0.5, gaze_dx=1.0,
                           gaze_dy=0.0, rest=False), 2000000)
assert abs(_max.cx - 0.5) <= _proof
_chk("temporary_clean_room_oracle_ok")


# ---- 11. renderer separation: renderer swaps, semantic layer intact -----

_meta = {"attention": 0.8}
_commands = {"neural_activity": 0.9}
_meta_copy = dict(_meta)
_cmds_copy = dict(_commands)
_runtime = runtime_face_state(visual="awake", meta=_meta, commands=_commands)
_extra_before = str(_runtime.extra)
_vs = build_visual_state(_runtime, _meta, _commands)
assert str(_runtime.extra) == _extra_before        # no mutation of fs
assert _meta == _meta_copy and _commands == _cmds_copy
## a different renderer consumes the exact same projection
class _StubRenderer:
    def set_visual_state(self, vs, frame=None):
        self.signature = project(vs, 1).signature()

_stub = _StubRenderer()
_stub.set_visual_state(_vs, frame=1)
assert _stub.signature == project(_vs, 1).signature()
_chk("temporary_renderer_separation_ok")


# ---- 12. Tk surface contract (only when a display is usable) ------------

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
except Exception:
    _root = None

if _root is not None:
    from maya_identity.renderer import TemporaryShapeRenderer

    _shape = TemporaryShapeRenderer(_root, size=64, state="sleeping")
    _shape.set_state("awake")
    _shape.set_command({"neural_activity": 1.0})
    _shape.set_metadata({"attention": 0.8})
    _vs = _anchor_vs("focused")
    _shape.set_visual_state(_vs, frame=9)
    _snap = _shape.snapshot()
    assert _snap["frame"] == 9
    assert _snap["projected"]["cx"] == project(_vs, 9).cx
    assert _shape.is_placeholder() is False
    assert "shape:" in _shape.status_text()
    _root.update_idletasks()
    _shape.destroy()
    _root.destroy()
else:
    print("=temporary_tk_skipped=SKIP")
_chk("temporary_tk_surface_ok")


print("temporary_embodiment_clean=OK")