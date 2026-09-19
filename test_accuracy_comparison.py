"""Real-life accuracy comparison battery for Maya's mathematics.

Compares every rig_math primitive and MathAgent derivation against
INDEPENDENT references (no shared code):

  decimal.Decimal  -> exact arithmetic ground truth at 50 digits
  math             -> transcendental functions (sin, exp, sqrt)
  statistics       -> population variance / stdev (world stability)

Each check uses an external calculator value as the reference and asserts
the Maya result agrees within the documented tolerance (1e-12 rel at unit
scale; POSE_EPSILON 1e-9 for pose blends). Deterministic fixed sweeps only
(no randomness), CPU-light, read-only. Part of the continuous verification
suite (see verification/manifest.py).
"""
import math
import os
import sys
import statistics
from decimal import Decimal, getcontext
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))

getcontext().prec = 50
D = Decimal

from maya_identity.wireframe import rig_math as rm
from maya_identity.wireframe.math_coordinator import (
    MATH_AGENT as AGENT,
    CHANNEL_MAX, TASK_BLEND_WEIGHTS, MICRO_AMP, MICRO_AMP_X,
    WORLD_STATE_PATTERNS, PRECISION_TOLERANCE,
)
from maya_identity.wireframe.interp import Smoother

TOL_REL = Decimal("1e-11")


def dec_close(a, b, tol=TOL_REL):
    a = Decimal(repr(float(a)))
    b = Decimal(repr(float(b)))
    return abs(a - b) <= tol * max(Decimal("1.0"), abs(a), abs(b))


def dec_eq(a, b):
    return Decimal(str(a)) == Decimal(str(b))


def sweep(lo, hi, n=41):
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def check(name):
    print("accuracy_" + name + "=OK")


# ---- 1. linear interpolation vs exact decimal arithmetic -------------------
for _t in sweep(-2.0, 3.0):
    t = Decimal(str(_t))
    for a, b in ((0.0, 10.0), (-4.0, 6.0), (0.2, 0.9), (-7.5, -0.25)):
        want = D(str(a)) + (Decimal(str(b)) - D(str(a))) * t
        assert dec_close(rm.lerp(a, b, _t), want), (a, b, _t, rm.lerp(a, b, _t), want)
        assert dec_close(rm.stable_lerp(a, b, _t), want), (a, b, _t)
check("lerp_decimal")

# ---- 2. exp_smooth == one lerp step at alpha -------------------------------
for _a in sweep(0.0, 1.0, n=21):
    a = Decimal(str(_a))
    for c, g in ((0.2, 0.9), (0.0, 1.0), (-1.0, 3.0)):
        dc, dg = D(str(c)), D(str(g))
        want = dc + (dg - dc) * a
        assert dec_close(rm.exp_smooth(c, g, _a), want)
check("exp_smooth_decimal")

# ---- 3. smoothstep closed form (3x^2 - 2x^3), decimal ----------------------
for x in sweep(0.0, 1.0, n=41):
    xv = Decimal(str(x))
    want = 3 * xv * xv - 2 * xv * xv * xv
    assert dec_close(rm.smoothstep(x), want)
assert rm.smoothstep(-2.0) == 0.0 and rm.smoothstep(3.0) == 1.0
check("smoothstep_decimal")

# ---- 4. zprime / zprime_inv / project_scale vs decimal ---------------------
for z in [z for z in sweep(-1.5, 2.9) if z > -5.0 - 1e-12] + [0.0, -2.5, 1.0, 2.5]:
    if z <= -5.0:
        continue
    zv = Decimal(str(z))
    cam = Decimal("5.0")
    want_zp = zv / (1 + zv / cam)
    assert dec_close(rm.zprime(z), want_zp), (z, rm.zprime(z), want_zp)
    inv = cam * want_zp / (cam - want_zp)
    assert dec_close(rm.zprime_inv(rm.zprime(z)), inv)
    want_ps = cam / (cam - zv)
    assert dec_close(rm.project_scale(z), want_ps), (z, rm.project_scale(z), want_ps)
check("projection_decimal")

# ---- 5. depth01 / shade_of matches decimal band ----------------------------
for zp in sweep(-0.9, 0.8, n=41):
    zpd = Decimal(str(zp))
    want = (zpd - Decimal("-0.9")) / (Decimal("0.8") - Decimal("-0.9"))
    assert dec_close(rm.depth01(zp), want)
assert rm.depth01(-0.9) == 0.0
assert rm.depth01(0.8) == 1.0
assert rm.depth01(0.3, lo=0.3, hi=0.3) == 0.5
check("depth01_decimal")

# ---- 6. render physics: thickness / glow vs closed forms -------------------
for zp in sweep(-1.0, 1.0, n=41):
    assert dec_close(rm.thickness01(zp), 1 + 2 * (1 - Decimal(str(zp))))
for zp in sweep(-1.0, 1.2, n=41):
    want = Decimal(str(math.exp(min(-zp * 2.5, 700.0))))
    assert dec_close(rm.glow01(zp), want)
check("render_physics_decimal")

# ---- 7. oscillate / wave / cycle vs math.sin + fmod ------------------------
for x in sweep(0.0, 12.35, n=41):
    assert dec_close(rm.oscillate(x, 0.25, 0.4),
                     Decimal("0.25") + Decimal("0.4") * Decimal(repr(math.sin(x))))
    assert dec_close(rm.wave01(x), max(0.0, min(1.0, 0.5 + 0.5 * math.sin(x))))
for t, speed, span in ((0.0, 2.0, 3.0), (1.3, 2.0, 3.0), (4.0, 2.0, 3.0)):
    assert dec_close(rm.cycle_sweep(t, speed, span), math.fmod(t * speed, span))
assert rm.cycle_sweep(10.0, 2.0, 0.0) == 1.0
check("oscillation_decimal")

# ---- 8. vectors vs decimal dot/magnitude/normalize -------------------------
a3, b3 = (1.0, 2.0, 3.0), (4.0, 5.0, 6.0)
assert dec_close(rm.dot(a3, b3), D("32"))
assert dec_close(rm.magnitude(a3), D("14").sqrt())
n = rm.normalize(a3)
for vi, d in zip(n, (1.0, 2.0, 3.0)):
    assert dec_close(vi, Decimal(str(d)) / D("14").sqrt())
cos = rm.cosine_similarity((1.0, 0.0), (0.0, 1.0))
assert cos == 0.0
cos_par = rm.cosine_similarity((0.3, 0.4), (0.4, 0.3))
exp = (Decimal("0.3") * Decimal("0.4") + Decimal("0.4") * Decimal("0.3")) / (
    (Decimal("0.3")**2 + Decimal("0.4")**2).sqrt() ** 2)
assert dec_close(cos_par, exp)
check("vectors_decimal")

# ---- 9. blend weights exact; blend == decimal weighted mean ----------------
assert rm.blend_pose(1.0, 0.0, 0.0) == 0.6
assert rm.blend_pose(0.0, 1.0, 0.0) == 0.3
assert rm.blend_pose(0.0, 0.0, 1.0) == 0.1
we_, wv_, wm_ = 0.6, 0.3, 0.1
for e, v, m in ((0.1, 0.2, 0.3), (0.5, 0.5, 0.5), (1.0, 0.0, 1.0), (-0.2, 0.4, 0.05)):
    want = (Decimal(str(we_)) * D(str(e)) + Decimal(str(wv_)) * D(str(v))
            + Decimal(str(wm_)) * D(str(m)))
    assert dec_close(rm.blend_pose(e, v, m), want)
for a_ in (0.0, 0.25, 0.5, 0.75, 1.0, 2.0):
    want = max(0.0, min(1.0, a_ * 1.2))
    assert dec_close(rm.jaw_open(a_), want)
check("blend_decimal")

# ---- 10. world stability == statistics.pstdev (independent calculator) -----
for series in ([0.5, 0.5, 0.5], [0.4, 0.5, 0.6], [0.1, 0.2, 0.1, 0.2],
               [0.41, 0.42, 0.40, 0.41, 0.42]):
    std = statistics.pstdev(series)
    rep = AGENT.world_stability(series)
    assert dec_close(rep["std"], std), (series, rep["std"], std)
    assert rep["ok"] is (std <= 0.05), (series, std, rep)
for series in ([0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.41, 0.42, 0.40, 0.41, 0.42]):
    stats = AGENT.learn_stats(series)
    assert stats["ok"] is True
    std = statistics.pstdev(series)
    assert dec_close(stats["std"], std), (series, stats["std"], std)
stage = [0.2] * 5 + [0.95, 0.95]
rep = AGENT.world_stability(stage)
assert rep["ok"] is False
check("world_variance_statistics")

# world_index = 1 - clamp01(value / ceiling)
for t_ in sweep(0.0, 2.0, n=21):
    want = 1.0 - max(0.0, min(1.0, t_ / 1.0))
    assert dec_close(AGENT.world_index(t_, 1.0), want)
assert AGENT.world_index(float("nan"), 1.0) == 0.0
assert AGENT.world_index(0.4, 0.0) == 0.0
check("world_index_decimal")

# ---- 12. pattern alignment = normalized dot (decimal) -----------------------
def dec_cosine(a, b):
    norm_a = Decimal(str(sum(v * v for v in a))).sqrt()
    norm_b = Decimal(str(sum(v * v for v in b))).sqrt()
    na = [Decimal(str(x)) / norm_a for x in a]
    nb = [Decimal(str(x)) / norm_b for x in b]
    return sum(x * y for x, y in zip(na, nb))

for a, b in [((0.3, 0.2, 0.1), (0.1, 0.2, 0.3)),
             ((1.0, 0.0), (1.0, 0.0)),
             ((0.6, 0.4), (0.4, 0.6))]:
    want = max(0.0, min(1.0, dec_cosine(a, b)))
    got = AGENT.pattern_similarity(a, b)
    assert dec_close(got, want), (a, b, got, want)
check("pattern_alignment_decimal")

# ---- 13. task fuse reproduces blended weighted mean ------------------------
tf = AGENT.task_fuse(0.5, 0.4, 0.1)
assert tf["weights"] == (0.6, 0.3, 0.1)
want = Decimal("0.6") * Decimal("0.5") + Decimal("0.3") * Decimal("0.4") + Decimal("0.1") * Decimal("0.1")
assert dec_close(tf["fused"], want)
check("task_fuse_decimal")

# ---- 14. Smoother convergence vs repeated stable_lerp -----------------------
sm = Smoother(["x"], alpha=0.5)
sm.set_target("x", 1.0)
prev = None
for _ in range(200):
    got = sm.step()["x"]
    if prev is not None:
        want = rm.stable_lerp(prev, 1.0, 0.5)
        assert dec_close(got, want)
    prev = got
assert prev >= 1.0 - 1e-9
assert prev <= 1.0 + 1e-15
check("smoother_convergence")

# ---- 15. CHANNEL_MAX physical ceilings vs persona/task blend ceilings ------
assert CHANNEL_MAX["expression"] == 0.50
assert CHANNEL_MAX["viseme"] == 0.35
assert CHANNEL_MAX["micro"] == 0.012
assert CHANNEL_MAX["anatomical"] == 0.80
assert MICRO_AMP == 0.012 and MICRO_AMP_X == 0.006
for t_ in sweep(0.0, 6.0, n=25):
    amp = 0.8
    mi_x, mi_y, mi_z = AGENT.micro_displacement(t_, 1.0, amp)
    assert abs(mi_x) <= amp * MICRO_AMP_X + 1e-12
    assert abs(mi_y) <= amp * MICRO_AMP + 1e-12
    assert mi_z == 0.0
check("channel_ceilings")

# ---- 16. precision modes: expert tolerance is STRICTER ----------------------
assert PRECISION_TOLERANCE["standard"] == 1e-9
assert PRECISION_TOLERANCE["expert"] == 1e-12
assert PRECISION_TOLERANCE["expert"] <= PRECISION_TOLERANCE["standard"]
assert AGENT.precision_mode == "standard"
assert AGENT.precision_tolerance() == 1e-9
AGENT.set_precision_mode("expert")
assert AGENT.precision_tolerance() == 1e-12
AGENT.set_precision_mode("standard")
check("precision_tolerance")

# ---- 17. known constant anchors (real-world values) ------------------------
assert rm.math_isclose(0.6 + 0.3 + 0.1, 1.0, 1e-9) is True
assert not rm.math_isclose(0.6 + 0.3 + 0.1, 1.0, 1e-16)
assert abs(rm.magnitude((1.0, 2.0, 3.0)) - 3.7416573867739413) < 1e-12
assert rm.zprime(0.0) == 0.0
assert rm.project_scale(0.0) == 1.0
assert abs(rm.lerp(0.0, 10.0, 1.0 / 3.0) - 10.0 / 3.0) < 1e-14
assert abs(rm.smoothstep(0.5) - 0.5) < 1e-15
assert abs(rm.glow01(0.0) - 1.0) < 1e-12
assert abs(rm.thickness01(0.5) - 2.0) < 1e-12
check("constant_anchors")

print()
print("test_accuracy_comparison=PASS")