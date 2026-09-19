"""Mathematical integrity probe for Maya's calculation system.

Script-style test (project convention): module-level asserts, OK labels.

This probe sweeps the full working domain of every rig_math primitive and
every derivation that consumes it, and locks the invariants against
irregularities:

- symmetry and continuity of lerp / smoothstep / exp_smooth
- convexity: exp_smooth with alpha in [0,1] can never overshoot its endpoints
- non-finite inputs (NaN / +/-Inf) fall back to the clamp null instead of
  being coerced to a boundary
- projection/depth: monotone, bounded, and the documented poles sit exactly
  at -CAM_D (zprime) and +CAM_D (project_scale)
- shade-grade buckets quantize on the canonical nb-1 scale and their inverse
  (bucket_midpoint) uses the SAME scale — no off-by-one-cell drift between
  the quantizer, MaterialEngine, verify_render, or highlight_color
- render physics (thickness01 / glow01 / line width / shade_of chains)
  are monotone on the mesh domain
- pose blending weights and channel constraints are exact
- pattern math always lands on [0,1] regardless of its inputs
- Smoother alpha is clamped to [0,1] so eased controls never leave their
  [0,1] contract
- safety/world/orchestration domain checks
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
    zprime, zprime_inv, depth01, shade_of, color_lerp,
    thickness01, glow01, project_scale,
    blend_pose, jaw_open,
    bucket_of, bucket_midpoint,
    math_isclose, pose_near, POSE_EPSILON,
    CAM_D, SHADE_LO, SHADE_HI, NB,
    BLEND_E, BLEND_V, BLEND_M, BLINK_LAMBDA, JAW_GAIN,
    oscillate, wave01, wave_range, cycle_sweep,
)
from maya_identity.wireframe.math_coordinator import (
    MATH_AGENT as AGENT,
    MICRO_AMP, MICRO_AMP_X, WORLD_DOMAIN,
    PATTERN_ALIGNMENT_DOMAINS, SAFETY_POLICY,
)
from maya_identity.wireframe.render3d import MaterialEngine, edge_thickness
from maya_identity.wireframe.interp import Smoother


def _sweep(lo, hi, n=41):
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


# ---- 1. vectors ---------------------------------------------------------
a3, b3 = (1.0, 2.0, 3.0), (4.0, 5.0, 6.0)
assert add(a3, b3) == (5.0, 7.0, 9.0)
assert sub(b3, a3) == (3.0, 3.0, 3.0)
assert dot(a3, b3) == 32.0
assert abs(magnitude(a3) - math.sqrt(14.0)) < 1e-12
assert normalize(a3) == tuple(v / math.sqrt(14.0) for v in a3)
assert normalize((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)

# ---- 2. interpolation: symmetry, continuity, convexity --------------------
assert lerp(0.0, 10.0, 0.0) == 0.0 and lerp(0.0, 10.0, 1.0) == 10.0
assert lerp(0.0, 10.0, 0.5) == 5.0
for t in _sweep(-2.0, 3.0):
    assert lerp(2.0, 8.0, t) == 2.0 + 6.0 * t
    assert abs(lerp(0.0, 1.0, t) - (1.0 - lerp(1.0, 0.0, t))) < 1e-12
# smoothstep: antisymmetric if you flip x and f, endpoints at 0/1
for x in _sweep(0.0, 1.0):
    assert abs(smoothstep(x) + smoothstep(1.0 - x) - 1.0) < 1e-12
    assert 0.0 <= smoothstep(x) <= 1.0
assert smoothstep(3.0) == 1.0 and smoothstep(-3.0) == 0.0
# exp_smooth is a convex combination when alpha in [0,1]
for a in _sweep(0.0, 1.0):
    lo_, hi_ = sorted((0.2, 0.9))
    v = exp_smooth(0.2, 0.9, a)
    assert lo_ - 1e-15 <= v <= hi_ + 1e-15
    assert abs(exp_smooth(0.2, 0.9, a) - exp_smooth(0.9, 0.2, 1.0 - a)) < 1e-12

# ---- 3. clamp / clamp01: bounds and non-finite fallback -------------------
assert clamp(1.5, 0.0, 1.0) == 1.0 and clamp(-1.0, 0.0, 1.0) == 0.0
assert clamp01(0.37) == 0.37
assert clamp01("junk") == 0.0 and clamp01(None) == 0.0
# non-finite input must NOT be coerced to a boundary (NaN -> 1.0 irregularity)
assert clamp01(float("nan")) == 0.0
assert clamp01(float("inf")) == 0.0
assert clamp01(float("-inf")) == 0.0
assert clamp(float("nan"), 0.0, 1.0) == 0.0
assert clamp(float("nan"), 1.0, 4.0) == 1.0  # lo is the null of that call

# ---- 4. projection / depth chain ------------------------------------------
# documented poles sit exactly at the singularities, nowhere else
try:
    zprime(-CAM_D)
    raise AssertionError("zprime(-CAM_D) must hit its pole")
except ZeroDivisionError:
    pass
try:
    project_scale(CAM_D)
    raise AssertionError("project_scale(CAM_D) must hit its pole")
except ZeroDivisionError:
    pass
assert zprime(0.0) == 0.0
assert project_scale(0.0) == 1.0
# monotone, bounded, finite on the working mesh band
mesh_zs = _sweep(-1.5, 0.95)
for i in range(1, len(mesh_zs)):
    z1, z2 = mesh_zs[i - 1], mesh_zs[i]
    assert zprime(z1) < zprime(z2)          # near is strictly nearer
    assert project_scale(z1) < project_scale(z2)
    assert depth01(zprime(z1)) <= depth01(zprime(z2))  # monotone, no reversal
    assert 0.0 <= shade_of(z1) <= 1.0
    assert math.isfinite(zprime(z1)) and math.isfinite(project_scale(z1))
# strictly interior band where the grade is not clamped
for z1, z2 in zip(_sweep(-0.7, 0.9), _sweep(-0.7, 0.9)[1:]):
    assert depth01(zprime(z1)) < depth01(zprime(z2))  # no wrap, no reversal
assert depth01(SHADE_LO) == 0.0
assert depth01(SHADE_HI) == 1.0   # depth01's band IS the Z' interval [LO, HI]
z_near = CAM_D * SHADE_HI / (CAM_D - SHADE_HI)   # z whose Z' == SHADE_HI
z_far = CAM_D * SHADE_LO / (CAM_D - SHADE_LO)   # z whose Z' == SHADE_LO
assert abs(shade_of(z_near) - 1.0) < 1e-12 and abs(shade_of(z_far)) < 1e-12
assert shade_of(10.0) == 1.0  # near floors at 1.0
# behind the pole (z < -CAM_D) the Z' curve wraps to the near side; this is
# the documented singularity of zprime at z = -CAM_D, and the rig mesh stays
# well above it (min vertex z ~ -1.5), so it is outside the working domain.
assert zprime(-12.0) > 0.0 and zprime(-100.0) > 0.0

# ---- 5. shade-grade buckets: one scale, both directions -------------------
# quantizer fills exactly NB buckets 0..NB-1
assert bucket_of(0.0) == 0 and bucket_of(1.0) == NB - 1
assert bucket_of(-5.0) == 0 and bucket_of(5.0) == NB - 1
assert bucket_of(0.5) == round(0.5 * (NB - 1))
# inverse uses the SAME nb-1 scale: round-trip error <= half a cell
max_cell = 0.5 / (NB - 1)
for t in _sweep(0.0, 1.0, n=97):
    b = bucket_of(t)
    assert 0 <= b <= NB - 1
    assert abs(bucket_midpoint(b) - t) <= max_cell + 1e-9
assert bucket_midpoint(0) == 0.0
assert bucket_midpoint(NB - 1) == 1.0
assert bucket_midpoint(999) == 1.0 and bucket_midpoint(-3) == 0.0
# the engine and the agent share the exact quantizer
eng = MaterialEngine()
for z in mesh_zs:
    assert eng.bucket(z) == AGENT.depth_bucket(z) == bucket_of(shade_of(z))
# bucket-mode color path agrees between engine and agent (both use the inverse)
materials = {"line_brightness": 0.72, "cyan_blue_balance": 0.55,
             "violet_diagnostic": 0.18, "eye_brightness": 0.95,
             "glow_intensity": 0.0, "wireframe_opacity": 0.85}
for b in (0, 1, 19, 20, 38, NB - 1):
    assert (eng.edge_color("mouth_rim_l", materials, bucket=b)
            == AGENT.verify_render("mouth_rim_l", materials, bucket=b)["color"])
# depth chain inverts across the grade band: bucket -> Z' -> shade == midpoint
for b in range(NB):
    m = bucket_midpoint(b)
    z_rec = zprime_inv(SHADE_LO + m * (SHADE_HI - SHADE_LO))
    assert abs(shade_of(z_rec) - m) < 1e-12
    assert abs(zprime_inv(zprime(z_rec)) - z_rec) < 1e-12  # true algebraic inverse
assert abs(zprime_inv(zprime(0.42)) - 0.42) < 1e-12

# ---- 6. render physics: vetted monotonicity on the mesh domain -------------
zps = _sweep(-1.0, 1.2)
for i in range(1, len(zps)):
    zp_a, zp_b = zps[i - 1], zps[i]
    assert zp_a < zp_b
    assert thickness01(zp_a) > thickness01(zp_b)       # far -> thicker
    assert glow01(zp_a) > glow01(zp_b)                 # far -> brighter glow
    assert glow01(zp_b) > 0.0 and math.isfinite(glow01(zp_b))
assert thickness01(1.0) == 1.0 and thickness01(0.0) == 3.0 and thickness01(-1.0) == 5.0
assert abs(glow01(0.0) - 1.0) < 1e-12
# canvas line width is thickness01 capped, monotone, bounded
cap = max(1, int(176 / 40))
for z1, z2 in zip(mesh_zs, mesh_zs[1:]):
    w1, w2 = AGENT.line_width(z1, 176), AGENT.line_width(z2, 176)
    assert 1 <= w1 <= cap and w1 >= w2               # near -> no thicker than far
assert edge_thickness(mesh_zs[0], 176) == AGENT.line_width(mesh_zs[0], 176)

# ---- 7. pose blend: exact weights, bounded channels ------------------------
assert blend_pose(1.0, 0.0, 0.0) == BLEND_E == 0.6
assert blend_pose(0.0, 1.0, 0.0) == BLEND_V == 0.3
assert blend_pose(0.0, 0.0, 1.0) == BLEND_M == 0.1
assert abs(blend_pose(0.01, 0.02, 0.03) - (0.6 * 0.01 + 0.3 * 0.02 + 0.1 * 0.03)) < 1e-15
assert jaw_open(0.0) == 0.0 and jaw_open(1.0) == 1.0
assert abs(jaw_open(0.5) - 0.6) < 1e-12
assert jaw_open(2.0) == 1.0 and jaw_open(-1.0) == 0.0
# micro displacement stays inside its exact amplitude ceilings
for t in _sweep(0.0, 6.0, n=25):
    amp = 0.8
    mi_x, mi_y, mi_z = AGENT.micro_displacement(t, 1.0, amp)
    assert abs(mi_x) <= amp * MICRO_AMP_X + 1e-12
    assert abs(mi_y) <= amp * MICRO_AMP + 1e-12
    assert mi_z == 0.0
# compose_vertex = 0.6/0.3/0.1 blend + anatomical at full weight, per axis
px_, py_, pz_ = AGENT.compose_vertex((0.1, 0.2, 0.3), (0.4, 0.5, 0.6),
                                     (0.7, 0.8, 0.9), (0.10, 0.20, 0.30))
assert abs(px_ - (blend_pose(0.1, 0.4, 0.7) + 0.10)) < 1e-14
assert abs(py_ - (blend_pose(0.2, 0.5, 0.8) + 0.20)) < 1e-14
assert abs(pz_ - (blend_pose(0.3, 0.6, 0.9) + 0.30)) < 1e-14
# canonical pose identity holds on a full controller pose
from maya_identity.wireframe.mesh_model import get_mesh
from maya_identity.wireframe.expression_controller import ExpressionController


def _ctrl():
    return ExpressionController(get_mesh())


ctrl_pose = AGENT.verify_pose(_ctrl(), 0.5, reduced=True)
assert ctrl_pose["ok"]

# ---- 8. pattern math: inputs may misbehave, outputs must stay on [0,1] -----
assert AGENT.pattern_transition(5.0, -3.0, 2.0) == lerp(1.0, 0.0, 1.0) == 0.0
assert AGENT.pattern_transition(-2.0, 7.0, -1.0) == lerp(0.0, 1.0, 0.0) == 0.0
assert AGENT.pattern_transition(0.1, 0.9, 0.5) == 0.5
assert AGENT.pattern_priority(42.0) == 1.0 and AGENT.pattern_priority(-9.0) == 0.0
for _ in range(50):
    cur, tgt, alp = (_sweep(-2.0, 3.0)[(i * 7) % 41] for i in (3, 11, 29))
    s = AGENT.pattern_state(cur, tgt, alp)
    assert 0.0 <= s <= 1.0
pa = AGENT.pattern_similarity((0.1, 0.2, 0.3), (0.3, 0.2, 0.1))
pb = AGENT.pattern_similarity((0.3, 0.2, 0.1), (0.1, 0.2, 0.3))
assert abs(pa - pb) < 1e-15                      # symmetric
assert abs(AGENT.pattern_similarity((1.0, 0.0), (1.0, 0.0)) - 1.0) < 1e-15
assert AGENT.pattern_similarity((0.0, 0.0), (0.3, 0.4)) == 0.0  # zero vector
assert 0.0 <= pa <= 1.0
for _ in range(16):
    aligned = {d: abs(math.sin(i + j)) for i, (j, d) in enumerate(enumerate(PATTERN_ALIGNMENT_DOMAINS))}
    aligned["_"] = aligned  # a stray key must be ignored, not rejected
    assert AGENT.pattern_alignment_ok(aligned)["ok"] is True
    bad = dict(aligned, emotional=1.7)
    assert AGENT.pattern_alignment_ok(bad)["ok"] is False
    bad = dict(aligned, viseme=float("inf"))
    assert AGENT.pattern_alignment_ok(bad)["ok"] is False

# ---- 9. Smoother: clamped alpha keeps the [0,1] contract in every step -----
sm = Smoother(["a", "b"], alpha=2.5)          # pathological alpha gets clamped
assert sm.alpha == 1.0
sm.set_target("a", 1.0, immediate=True)
sm.set_alpha("a", 3.0)                         # alpha beyond [0,1] is invalid
assert sm._alpha["a"] == 1.0
assert sm.step()["a"] <= 1.0 + 1e-15           # proves the overshoot is gone
sm = Smoother(["x"], alpha=0.5)
sm.set_target("x", 1.0)
history = []
for _ in range(60):
    history.append(sm.step()["x"])
assert all(0.0 <= v <= 1.0 for v in history)
assert all(later >= earlier for later, earlier in zip(history[1:], history))
assert abs(history[-1] - 1.0) < 1e-9           # converged, no overshoot
sm.set_alpha("x", -5.0)                        # negative alpha is invalid too
assert sm._alpha["x"] == 0.0
assert sm.step()["x"] == sm.snapshot()["x"]    # a frozen value, not a reverse

# ---- 10. safety / world / orchestration domain -----------------------------
assert AGENT.pattern_safety_margin(0, 0, 0, 0) == 1.0
assert AGENT.pattern_safety_margin(
    SAFETY_POLICY["max_cpu_percent"], 0, 0, 0) == 0.0
m = AGENT.pattern_safety_margin(30, 0, 0, 0)
assert 0.5 <= m <= 1.0
assert AGENT.check_limits(59.9, 10, 0, 0)["safe"] is True
assert AGENT.check_limits(60.0, 10, 0, 0)["safe"] is False     # >= exact
assert AGENT.check_limits(10, 10, 2, 1)["safe"] is True
assert AGENT.check_limits(10, 10, 3, 1)["safe"] is False       # > exact
ws = AGENT.world_stability([0.5, 0.5, 0.5])
assert ws["ok"] is True and ws["std"] == 0.0
assert AGENT.world_stability([0.1, 0.5, 0.9])["ok"] is False
assert AGENT.world_stability([])["ok"] is False
assert AGENT.world_state_ok({"a": 0.5, "b": 2})["ok"] is False
full = AGENT.orchestrate(
    {"aligned": {d: 0.5 for d in PATTERN_ALIGNMENT_DOMAINS},
     "world": [0.4, 0.4, 0.4],
     "safety": {"cpu_percent": 30, "memory_percent": 40,
                "process_count": 1, "launches": 0}})
assert full["ok"] is True, full["violations"]
assert AGENT.orchestrate(
    {"aligned": dict(emotional=1.2,
                     **{d: 0.5 for d in PATTERN_ALIGNMENT_DOMAINS[1:]})})["ok"] is False

# ---- 11. tolerance-based equality (math_isclose / pose_near) ----------------
# canonical identity: 0.6 + 0.3 + 0.1 must be within POSE_EPSILON of 1.0.
# rig_math and the coordinator both assert this at import; here we lock the
# equality semantics themselves.
assert math_isclose(BLEND_E + BLEND_V + BLEND_M, 1.0, POSE_EPSILON) is True
assert math_isclose(0.6 + 0.3 + 0.1, 1.0) is True
assert math_isclose(0.6 + 0.3 + 0.1, 1.0, POSE_EPSILON) is True
assert math_isclose(1.00000001, 1.0, POSE_EPSILON) is False
assert math_isclose(1.0000000005, 1.0, 1e-8) is True
assert math_isclose(0.0, 0.0) is True
assert math_isclose(0.0, 1e-12, 1e-9) is True        # absolute floor of 1.0
assert math_isclose(0.0, 1e-8, 1e-9) is False
assert math_isclose(1e300, 1.0000000000000001e300, 1e-9) is True   # relative
assert math_isclose(1e300, 1e300 + 2e292, 1e-9) is False
assert math_isclose(float("nan"), 1.0) is False
assert math_isclose(float("inf"), 1.0) is False
assert math_isclose(float("-inf"), float("-inf")) is False  # never equal
# pose_near is the pose-facing alias of math_isclose
assert pose_near(blend_pose(0.5, 0.4, 0.1), 0.6 * 0.5 + 0.3 * 0.4 + 0.1 * 0.1)
assert pose_near(blend_pose(1.0, 1.0, 1.0), 1.0)      # weights sum to ~1.0
assert not pose_near(0.0, 1.0)
assert not pose_near(blend_pose(1.0, 0.0, 0.0), 1.0)  # 0.6 is not 1.0
# task fusion reproduces the same 0.6/0.3/0.1 proportions as the pose blend
tf = AGENT.task_fuse(0.5, 0.4, 0.1)
assert math_isclose(tf["fused"], 0.6 * 0.5 + 0.3 * 0.4 + 0.1 * 0.1, POSE_EPSILON)
assert tf["weights"] == (0.6, 0.3, 0.1)

# ---- 12. non-finite guards per primitive ------------------------------------
# interpolation: a non-finite operand becomes its neutral 0.0, the output
# stays finite and well-defined instead of propagating NaN
assert rig_math.lerp(float("nan"), 2.0, 0.5) == 1.0
assert rig_math.lerp(1.0, float("inf"), 0.5) == 0.5
assert rig_math.exp_smooth(0.5, float("nan"), 0.5) == 0.25
assert rig_math.exp_smooth(0.5, 0.9, float("nan")) == 0.5
assert math.isfinite(rig_math.exp_smooth(0.5, float("inf"), float("nan")))
# projection/depth: documented poles preserved, non-finite degrades to neutral
assert zprime(float("inf")) == 0.0
assert zprime_inv(float("nan")) == 0.0
assert project_scale(float("inf")) == 1.0
assert project_scale(float("nan")) == 1.0
assert depth01(float("inf")) == 0.0      # all non-finite degrade via clamp01
assert depth01(float("-inf")) == 0.0
assert depth01(float("nan")) == 0.0
assert depth01(0.3, lo=0.3, hi=0.3) == 0.5   # degenerate band -> midpoint
# render physics: bounded, never NaN, never divergent
assert thickness01(float("nan")) == 3.0
assert glow01(float("-inf")) == 1.0      # was exp(inf) == inf, now bounded
assert math.isfinite(glow01(-50.0))
assert rig_math.color_lerp((99, 139, 255), (255, 128, 128),
                           float("nan")) == (99, 139, 255)
assert rig_math.boost_rgb((250, 0, 20), 1.25, 28.0) == (255, 28, 53)
assert rig_math.boost_rgb((250, 0, 20), scale=float("nan"),
                          offset=0.0) == (250, 0, 20)
assert rig_math.boost_rgb((10, 10, 10), offset=float("nan")) == (12, 12, 12)
assert rig_math.lift_luminance((100, 20, 200), float("nan")) == (100, 20, 200)
assert rig_math.jaw_open(float("nan")) == 0.0
assert rig_math.oscillate(float("nan"), mid=0.5, amp=0.4) == 0.5
assert rig_math.cycle_sweep(10.0, 2.0, 0.0) == 1.0
# vectors: overflow-safe magnitude/normalize, never NaN directions
assert magnitude((1e308, 1e308, 1e308)) == 0.0
assert normalize((1e308, 1e308, 1e308)) == (0.0, 0.0, 0.0)
assert normalize((float("nan"), 0.0, 0.0)) == (0.0, 0.0, 0.0)
assert magnitude(a3) == math.sqrt(14.0)
# pattern math: non-finite inputs still land on [0, 1]
assert AGENT.pattern_similarity(
    (1.0, 0.0, 0.0), (float("inf"), 0.0, 0.0)) == 0.0
assert AGENT.pattern_similarity((0.6, 0.4), (0.6, 0.4)) > 1.0 - 1e-15
assert 0.0 <= AGENT.pattern_alignment((float("nan"), 1.0), (1.0, 0.0)) <= 1.0

# ---- 13. blend-weights are guarded, channels are coerced to neutral ---------
try:
    blend_pose(1.0, 1.0, 1.0, we=float("nan"))
    raise AssertionError("blend must reject a non-finite weight")
except ValueError:
    pass
try:
    blend_pose(1.0, 1.0, 1.0, wv=-0.2)
    raise AssertionError("blend must reject a negative weight")
except ValueError:
    pass
assert blend_pose(float("nan"), 0.0, 0.0) == 0.0
assert blend_pose(float("nan"), float("inf"), float("nan")) == 0.0
assert blend_pose(1.0, float("inf"), 0.0) == 0.6   # neutral channel == 0.0

# ---- 14. safety fail-closed: unreadable metrics can never pass as safe -------
r = AGENT.check_limits(float("nan"), 10, 0, 0)
assert r["safe"] is False and "CPU metric invalid" in r["violations"]
r = AGENT.check_limits(10, float("inf"), 0, 0)
assert r["safe"] is False and "memory metric invalid" in r["violations"]
r = AGENT.check_limits(10, 10, float("nan"), 1)
assert r["safe"] is False and "process-count metric invalid" in r["violations"]
r = AGENT.check_limits(10, 10, 1, float("nan"))
assert r["safe"] is False and "launch-rate metric invalid" in r["violations"]
assert AGENT.check_limits("junk", 10, 0, 0)["safe"] is False
assert AGENT.check_limits(59.9, 10, 0, 0)["safe"] is True
assert AGENT.check_limits(60.0, 10, 0, 0)["safe"] is False
near = AGENT.pattern_safety_margin(59.999, 0, 0, 0)
assert 0.0 < near <= 1.0
assert AGENT.pattern_safety_margin(0, 0, 0, 0) == 1.0
assert AGENT.pattern_safety_margin(float("nan"), 0, 0, 0) == 0.0
assert AGENT.pattern_safety_margin(0, 0, 0, float("nan")) == 0.0
assert math_isclose(AGENT.world_index(0.4, 1.0), 0.6)
assert AGENT.world_index(float("nan"), 1.0) == 0.0
assert AGENT.world_index(0.4, float("nan")) == 0.0
ra = AGENT.resource_anomaly([30.0, 31.0, 29.0], float("nan"))
assert ra["ok"] is False and ra["reason"] == "non_finite_current"
assert AGENT.resource_anomaly([30.0, 31.0, 29.0], 32.0)["ok"] is True

# ---- 15. extremes and determinism -------------------------------------------
def _noisy_series(seed, n=24):
    return [clamp01(0.5 + 0.4 * math.sin(seed * 1.3 + i * 0.7)
                    + 0.15 * math.sin(i * 2.9)) for i in range(n)]

noise_a = _noisy_series(7)
noise_b = _noisy_series(7)
assert noise_a == noise_b                        # generator is not stateful
assert AGENT.world_drift(noise_a)["drift"] == AGENT.world_drift(noise_b)["drift"]
assert AGENT.world_stability(noise_a)["std"] == AGENT.world_stability(noise_b)["std"]
assert AGENT.learn_feature(noise_a) == AGENT.learn_feature(noise_b)
assert math.isfinite(AGENT.world_drift(noise_a)["drift"])
# a world series that steps away from its equilibrium must drift
stage = [0.2] * 5 + [0.95, 0.95]
assert AGENT.world_drift(stage)["ok"] is False
assert AGENT.world_stability([0.41, 0.42, 0.40, 0.41, 0.42])["ok"] is True
# extreme finite values stay finite and deterministic
assert math.isfinite(rig_math.lerp(1e300, -1e300, 0.5))
assert math.isfinite(rig_math.exp_smooth(1e300, -1e300, 0.5))
# task / agent / prediction round-trips must re-derive exactly (math_isclose)
dec = AGENT.task_decision((0.9, 0.7, 0.5), primary=0.9,
                          secondary=0.6, context=0.4)
assert AGENT.task_decision_ok(dec)["ok"] is True
assert AGENT.task_decision_ok(dict(dec, fused=dec["fused"] + 1e-4))["ok"] is False
am = {"agent_id": "a", "state": (0.6, 0.4), "goal": (0.7, 0.3),
      "contribution": 0.8, "current": 0.5,
      "evolved": AGENT.pattern_state(0.5, 0.8, 0.2),
      "voiced": AGENT.pattern_transition(0.5, 0.8, 0.6),
      "alpha": 0.2, "t": 0.6}
assert AGENT.agent_validate(am)["ok"] is True
assert AGENT.agent_validate(dict(am, voiced=am["voiced"] - 1e-4))["ok"] is False
pred = AGENT.predict_signal([0.4, 0.45, 0.5, 0.55], expected=0.65,
                            alpha=0.15, horizon=1)
assert AGENT.predict_validate([0.4, 0.45, 0.5, 0.55], pred)["ok"] is True
assert AGENT.predict_validate(
    [0.4, 0.45, 0.5, 0.55],
    dict(pred, predicted=pred["predicted"] + 1e-4))["ok"] is False

print("math_integrity_vectors=OK")
print("math_integrity_interp=OK")
print("math_integrity_nonfinite_fallback=OK")
print("math_integrity_projection=OK")
print("math_integrity_bucket_scale=OK")
print("math_integrity_render_physics=OK")
print("math_integrity_blend=OK")
print("math_integrity_pattern=OK")
print("math_integrity_smoother_domain=OK")
print("math_integrity_safety_world=OK")
print("math_integrity_pose_identity=OK")
print("math_integrity_math_isclose=OK")
print("math_integrity_nonfinite_guards=OK")
print("math_integrity_blend_guards=OK")
print("math_integrity_safety_fail_closed=OK")
print("math_integrity_extremes_determinism=OK")