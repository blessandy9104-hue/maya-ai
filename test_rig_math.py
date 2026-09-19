"""rig_math mathematical cognition layer — projection, interpolation, and
pose blending accuracy.

Script-style test (project convention): module-level asserts, OK labels.

Checks:
- vector operations: add, sub, dot, normalize, magnitude
- interpolation/smoothing: lerp, smoothstep, exp_smooth, clamp, clamp01
- projection/depth: Z' = Z/(1+Z/CAM_D), depth = clamp01((Z'-Zmin)/(Zmax-Zmin)),
  cyan -> violet shading = color_lerp(cyan, violet, depth)
- rendering physics: thickness = 1 + 2*(1-Z'), glow = exp(-Z'*2.5)
- pose blending: final_pose = 0.6*expression + 0.3*viseme + 0.1*micro,
  jaw_open = clamp(amplitude*1.2, 0, 1)
- all modules (MeshProjector, MaterialEngine, ExpressionController, Smoother)
  reference the rig_math layer, and the wireframe derives exact pose
  displacements from these equations (compute, not approximate)
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity.wireframe import rig_math
from maya_identity.wireframe.rig_math import (
    add, sub, dot, magnitude, normalize,
    lerp, smoothstep, exp_smooth, clamp, clamp01,
    zprime, depth01, shade_of, color_lerp,
    thickness01, glow01,
    blend_pose, jaw_open,
    BLEND_E, BLEND_V, BLEND_M, BLINK_LAMBDA, JAW_GAIN,
    CAM_D, SHADE_LO, SHADE_HI, NB,
)
from maya_identity.wireframe.mesh_model import get_mesh
from maya_identity.wireframe.expression_controller import ExpressionController
from maya_identity.wireframe.render3d import (
    MeshProjector, MaterialEngine, edge_thickness,
)
from maya_identity.wireframe.interp import Smoother
from maya_identity.wireframe.speech_adapter import _interpolate_procedural, _PROC_OPEN_SEQ

# ---- vector operations ----
assert add((1, 2, 3), (4, 5, 6)) == (5, 7, 9)
assert sub((4, 5, 6), (1, 2, 3)) == (3, 3, 3)
assert dot((1, 2, 3), (4, 5, 6)) == 32
assert magnitude((3, 4, 0)) == 5.0
assert normalize((3.0, 0.0, 0.0)) == (1.0, 0.0, 0.0)
n = normalize((1.0, 1.0, 1.0))
assert abs(magnitude(n) - 1.0) < 1e-12
assert normalize((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)
assert 0.577350 < n[0] < 0.577351

# ---- interpolation and smoothing ----
assert lerp(0.0, 10.0, 0.5) == 5.0
assert lerp(0.0, 10.0, 0.0) == 0.0 and lerp(0.0, 10.0, 1.0) == 10.0
assert smoothstep(0.0) == 0.0
assert smoothstep(1.0) == 1.0
assert smoothstep(0.5) == 0.5
assert smoothstep(-3.0) == 0.0 and smoothstep(4.0) == 1.0
assert exp_smooth(0.0, 1.0, 0.5) == 0.5
assert exp_smooth(0.5, 1.0, 0.5) == 0.75
assert abs(exp_smooth(4.0, 10.0, 0.25) - 5.5) < 1e-12
assert clamp(1.5, 0.0, 1.0) == 1.0
assert clamp(-1.0, 0.0, 1.0) == 0.0
assert clamp01(0.37) == 0.37
assert clamp01(2.0) == 1.0 and clamp01(-2.0) == 0.0
assert clamp01("junk") == 0.0  # defensive fallback preserved

# ---- projection and depth normalization ----
assert zprime(0.0) == 0.0
assert abs(zprime(CAM_D) - CAM_D / 2.0) < 1e-12
assert zprime(-CAM_D / 2.0) < 0.0
assert zprime(2.0) > zprime(1.0)  # monotonic up to the singularity
assert depth01(SHADE_LO) == 0.0
assert depth01(SHADE_HI) == 1.0
assert depth01(SHADE_LO - 1.0) == 0.0 and depth01(SHADE_HI + 1.0) == 1.0
mid = depth01((SHADE_LO + SHADE_HI) / 2.0)
assert 0.499 < mid < 0.501
assert abs(0.5 - depth01((SHADE_LO + SHADE_HI) / 2.0)) < 0.01
# shade_of is the composition depth01(zprime(z))
assert shade_of(0.0) == depth01(zprime(0.0))
assert shade_of(1.0) > shade_of(0.0) > shade_of(-1.0)

# ---- colour = lerp(cyan, violet, depth) ----
CYAN = (0x63, 0xd9, 0xff)
VIOLET = (0x8a, 0x7d, 0xff)
assert color_lerp(CYAN, VIOLET, 0.0) == CYAN
assert color_lerp(CYAN, VIOLET, 1.0) == VIOLET
mid_c = color_lerp(CYAN, VIOLET, 0.5)
assert mid_c == tuple((CYAN[k] + VIOLET[k]) // 2 for k in range(3))

# ---- rendering physics ----
assert thickness01(1.0) == 1.0
assert thickness01(0.0) == 3.0
assert thickness01(-1.0) == 5.0
assert abs(glow01(0.0) - 1.0) < 1e-12
assert abs(glow01(1.0) - math.exp(-2.5)) < 1e-12
assert glow01(0.5) > glow01(1.0)  # falls off with distance

# ---- projection scale / colour floor / boost / motion primitives ----
from maya_identity.wireframe.rig_math import (
    project_scale, lift_luminance, boost_rgb,
    oscillate, wave01, wave_range, cycle_sweep,
)
for zz in (-1.2, -0.5, 0.0, 0.4, 0.9):
    assert abs(project_scale(zz) - (CAM_D / (CAM_D - zz))) < 1e-12
    # project_scale diverges exactly where the pinhole denominator hits zero
assert project_scale(0.5) == project_scale(0.5)
def _old_bump(hex_color, floor=110):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = max(r, g, b)
    if m >= floor:
        return hex_color
    extra = floor - m
    return "#{:02x}{:02x}{:02x}".format(min(255, r + extra),
                                        min(255, g + extra),
                                        min(255, b + extra))
from maya_identity.wireframe.face3d import _bump_small
for hx in ("#1a2233", "#3a4a5a", "#5f6b8a", "#ffffff", "#000000", "#90a8c0"):
    assert _bump_small(hx) == _old_bump(hx), (hx, _bump_small(hx), _old_bump(hx))
# highlight boost keeps the exact fixed grid: (r*1.25+28, g*1.25+26, b*1.25+28)
r_, g_, b_ = boost_rgb((120, 90, 200), scale=1.25, offset=(28, 26, 28))
assert r_ == int(min(255, 120 * 1.25 + 28))
assert g_ == int(min(255, 90 * 1.25 + 26))
assert b_ == 255
# sine carriers all derive from canonical oscillate
import math as _math
for xx in (0.0, 0.3, 1.7, 4.0):
    assert oscillate(xx, 0.0, 0.015) == 0.015 * _math.sin(xx)
    assert wave01(xx) == clamp01(0.5 + 0.5 * _math.sin(xx))
    assert abs(wave_range(xx, -0.015, 0.015)
               - (-0.015 + 0.03 * (0.5 + 0.5 * _math.sin(xx)))) < 1e-12
# scan sweep wraps exactly as (t*speed) % span - offset
assert cycle_sweep(1.0, 40.0, 216.0, 20.0) == (40.0 % 216.0) - 20.0
assert cycle_sweep(6.0, 40.0, 216.0, 20.0) == (240.0 % 216.0) - 20.0

# ---- pose blending and constraints ----
assert blend_pose(1.0, 0.0, 0.0) == BLEND_E
assert blend_pose(0.0, 1.0, 0.0) == BLEND_V
assert blend_pose(0.0, 0.0, 1.0) == BLEND_M
assert abs(blend_pose(1.0, 1.0, 1.0) - 1.0) < 1e-12
assert abs(blend_pose(-2.0, 1.0, 3.0) - (-1.2 + 0.3 + 0.3)) < 1e-12
assert jaw_open(0.0) == 0.0
assert abs(jaw_open(0.5) - 0.6) < 1e-12
assert jaw_open(1.2) == 1.0
assert jaw_open(0.9) == 1.0  # 0.9*1.2 = 1.08 clamps
assert abs(jaw_open(0.2) - 0.24) < 1e-12
assert JAW_GAIN == 1.2
assert BLINK_LAMBDA == 0.12

# ---- modules reference the rig_math layer ----
import maya_identity.wireframe.render3d as r3d
import maya_identity.wireframe.interp as _interp
import maya_identity.wireframe.expression_controller as _ec
assert r3d.zprime is rig_math.zprime
assert r3d.shade_of is rig_math.shade_of
assert r3d.CAM_D == CAM_D and r3d.NB == NB
assert _interp.clamp01 is rig_math.clamp01
assert _interp.exp_smooth is rig_math.exp_smooth
assert _ec.BLEND_E == BLEND_E and _ec.BLEND_V == BLEND_V and _ec.BLEND_M == BLEND_M
assert _ec.BLINK_LAMBDA == BLINK_LAMBDA and _ec.JAW_GAIN == JAW_GAIN

# MaterialEngine derives bucket/shade from rig_math
me = MaterialEngine()
for z in (-0.6, -0.1, 0.0, 0.3, 0.65):
    assert me.bucket(z) == int(round(depth01(zprime(z)) * (NB - 1)))
assert edge_thickness(0.0, 176) == int(clamp(thickness01(zprime(0.0)), 1.0, 4))

# Smoother advances with exp_smooth
sm = Smoother(["a"], alpha=0.25)
sm.set_target("a", 1.0)
after = sm.step()
assert after["a"] == exp_smooth(0.0, 1.0, 0.25)

# procedural viseme moution is lerp (rig_math), not raw a + (b-a)*t
t0, v0, r0 = _PROC_OPEN_SEQ[0]
t1, v1, r1 = _PROC_OPEN_SEQ[1]
assert _interpolate_procedural(t0) == v0
assert abs(_interpolate_procedural(1.0) - _PROC_OPEN_SEQ[-1][1]) < 1e-9
assert _interpolate_procedural((t0 + t1) / 2.0) == lerp(v0, v1, 0.5)
assert lerp(v0, v1, 0.5) == v0 + (v1 - v0) * 0.5

# edge depth is the lerp midpoint of its endpoints (rig_math.lerp, not +*0.5)
import maya_identity.wireframe.face3d as _face3d
_src = Path(_face3d.__file__).read_text(encoding="utf-8")
assert "zmid = lerp(pose[a][2], pose[b][2], 0.5)" in _src
assert "zmid = lerp(self.mesh.verts[a][2], self.mesh.verts[b][2], 0.5)" in _src

# ---- expression controller derives exact pose displacements ----
mesh = get_mesh()
ctrl = ExpressionController(mesh)

# MeshProjector is byte-identical to the inline pinhole rig_math projection
n = mesh.vertex_count()
proj = MeshProjector(176)
px, py = proj.project(mesh.verts, n)
s_, cx_, cy_ = proj._s, proj._cx, proj._cy
for i, (x, y, z) in enumerate(mesh.verts):
    inv = CAM_D / (CAM_D - z)
    assert px[i] == cx_ + x * s_ * inv
    assert py[i] == cy_ - y * s_ * inv

# replicate the controller's per-vertex micro seed (same formula, same maths)
def micro_seed(x, y, z):
    return ((hash((round(x, 3), round(y, 3), round(z, 3))) & 0xFFFFFF) % 6283) / 1000.0

# smile-only at t=0.5: corner vertex -> expression channel + 0.1x micro tremor
zero = {name: 0.0 for name in ctrl.controls.names()}
zero.update({"smile": 1.0, "calm": 0.0, "surprise": 0.0, "fear": 0.0,
             "sadness": 0.0, "anger": 0.0})
ctrl.controls.set_all(zero, immediate=True)
pose = ctrl.compute_pose(0.5, reduced=True)

corner = mesh.landmarks["mouth_corner_l"]
cx0, cy0, cz0 = mesh.verts[corner]
ph = micro_seed(cx0, cy0, cz0)
my_ = math.sin(0.5 * 1.7 + ph) * smoothstep(1.0) * 0.012
mx = math.sin(0.5 * 1.1 + ph * 1.7) * smoothstep(1.0) * 0.006
# expression dy for a mouth corner: smile*0.150, dz: smile*0.020
expected_dx = blend_pose(0.0, 0.0, mx)
expected_dy = blend_pose(0.150, 0.0, my_)
expected_dz = blend_pose(0.020, 0.0, 0.0)
ax, ay, az = pose[corner]
assert abs((ax - cx0) - expected_dx) < 1e-12, (ax - cx0, expected_dx)
assert abs((ay - cy0) - expected_dy) < 1e-12, (ay - cy0, expected_dy)
assert abs((az - cz0) - expected_dz) < 1e-12, (az - cz0, expected_dz)

# speaking: viseme channel at full 0.3 weight, micro tremor at 0.1 weight
vzero = {name: 0.0 for name in ctrl.controls.names()}
vzero.update({"speaking": 1.0, "surprise": 0.0})
ctrl.controls.set_all(vzero, immediate=True)
pose2 = ctrl.compute_pose(0.0, reduced=True)  # viseme(t) known phase at t=0
viseme0 = smoothstep(0.5 + 0.5 * math.sin(0.0 * 0.55 + 1.2))
vx0, vy0, vz0 = mesh.verts[corner]
# corners are mouth_rim; viseme uy for mouth_rim = mouth*0.030
mouth0 = jaw_open(1.0) * viseme0  # speaking=1.0 -> jaw_open=1.0
expected_dy2 = blend_pose(0.0, mouth0 * 0.030, my_2 := 0.0)
avx, avy, avz = pose2[corner]
assert abs((avy - vy0) - blend_pose(0.0, mouth0 * 0.030, 0.0)) < 1e-9

# blink/gaze are anatomical detail: applied at FULL strength, not 0.1x
iresh = mesh.landmarks["iris_l"]
iz0 = mesh.verts[iresh][2]
idle = ctrl.compute_pose(0.5, reduced=True)[iresh][2]
blink_set = {name: 0.0 for name in ctrl.controls.names()}
blink_set.update({"blink": 1.0})
ctrl.controls.set_all(blink_set, immediate=True)
blinked = ctrl.compute_pose(0.5, reduced=True)[iresh][2]
assert abs(blinked - idle) > 0.005, abs(blinked - idle)  # NOT attenuated to 0.1x

# ---- hardening: canonical identity + non-finite guards at the primitives -----
assert rig_math.math_isclose(BLEND_E + BLEND_V + BLEND_M, 1.0, 1e-9)
assert rig_math.pose_near(blend_pose(1.0, 1.0, 1.0), 1.0)
assert blend_pose(float("nan"), float("nan"), float("nan")) == 0.0
assert blend_pose(1.0, float("inf"), 0.0) == 0.6
assert thickness01(float("nan")) == 3.0
assert math.isfinite(glow01(float("-inf")))      # never divergent
assert rig_math.zprime(float("inf")) == 0.0
assert rig_math.project_scale(float("nan")) == 1.0
assert normalize((1e308, 1e308, 1e308)) == (0.0, 0.0, 0.0)   # overflow-safe
assert math.isfinite(rig_math.exp_smooth(0.5, float("nan"), 0.5))

print("rig_math_vectors=OK")
print("rig_math_interp=OK")
print("rig_math_projection=OK")
print("rig_math_shade=OK")
print("rig_math_physics=OK")
print("rig_math_render_primitives=OK")
print("rig_math_projection_identity=OK")
print("rig_math_blend=OK")
print("rig_math_modules_reference_layer=OK")
print("rig_math_pose_formula=OK")
print("rig_math_viseme_channel=OK")
print("rig_math_eye_full_weight=OK")
print("rig_math_procedural_lerp=OK")
print("rig_math_edge_depth_lerp=OK")
print("rig_math_hardening=OK")