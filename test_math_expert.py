"""Expert-grade math reference suite for the Maya math layer.

Script-style test (project convention): module-level asserts, OK labels.

Covers the "production-ready expert grade" contracts:
1. Numeric contract table  : rig_math.NUMERIC_CONTRACTS is complete and
                             every named primitive exists as a callable.
2. Extreme magnitudes      : primitives stay finite/bounded across
                             1e-12 .. 1e12 (and overflow-scale vectors).
3. Non-finite inputs       : deterministic neutral fallbacks, bounded output.
4. Domain boundaries       : exactness at 0 / 1 / -1 and lerp endpoints.
5. Random stress           : 10k+ seeded draws across rig_math, pattern,
                             world, and task math — ranges, closure, monotone
                             transitions, and bit-for-bit determinism.
6. Determinism             : identical inputs -> identical outputs.
7. Tolerance equality      : math_isclose semantics (reverse != and >= decay).
8. Math Precision Mode     : standard vs expert API, strictness, and the
                             no-overshoot stable smoothing over long horizons.
9. Expert invariants       : verify_world / verify_pattern_alignment /
                             verify_task_fusion flag drift and accept truth.
10. Registries              : capability + market-role registries are complete,
                             deterministic, and mutually consistent.

Run:  py -3 test_math_expert.py   (from the project root; exit 0 = pass)
"""
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity.wireframe import rig_math as rm
from maya_identity.wireframe.math_coordinator import (
    MATH_AGENT,
    PRECISION_STANDARD, PRECISION_EXPERT, PRECISION_MODES,
    PRECISION_TOLERANCE, POSE_EPSILON,
    TASK_BLEND_WEIGHTS, WORLD_DOMAIN,
)
from maya_identity.wireframe.rig_math import (
    math_isclose, clamp01, clamp,
    lerp, stable_lerp, exp_smooth, stable_exp_smooth,
    normalize, magnitude, dot, cosine_similarity,
    blend_pose, pose_near,
    POSE_EPSILON as RM_POSE_EPSILON,
)
from maya_identity import capability_registry as cr

RNG = random.Random(22061991)
N_STRESS = 10_000

# ---- 1. numeric contract table ---------------------------------------------
assert len(rm.NUMERIC_CONTRACTS) >= 18
for name, entry in rm.NUMERIC_CONTRACTS.items():
    assert isinstance(entry, tuple) and len(entry) == 5
    assert all(isinstance(part, str) and part.strip() for part in entry)
    assert callable(getattr(rm, name)), f"{name} must be a rig_math primitive"
assert "blend_pose" in rm.NUMERIC_CONTRACTS
assert "math_isclose" in rm.NUMERIC_CONTRACTS
assert "stable_lerp" in rm.NUMERIC_CONTRACTS
assert "stable_exp_smooth" in rm.NUMERIC_CONTRACTS
assert "cosine_similarity" in rm.NUMERIC_CONTRACTS
print("math_expert_contract_table=OK")

# ---- 2. extreme magnitudes -------------------------------------------------
for scale in (1e-12, 1e-4, 1.0, 1e4, 1e12):
    a, b, t = -scale, scale * 0.7, 0.31
    for value in (lerp(a, b, t), stable_lerp(a, b, t),
                  exp_smooth(a, b, t), stable_exp_smooth(a, b, 0.9, 1)):
        assert math.isfinite(value)
        lo, hi = min(a, b), max(a, b)
        assert lo - 1e-9 * max(1.0, abs(lo), abs(hi)) <= value \
            <= hi + 1e-9 * max(1.0, abs(lo), abs(hi))
assert stable_lerp(1e12, -1e12, 0.5) == 0.0
assert math.isfinite(stable_exp_smooth(1e12, -1e12, 0.5, 50))
u = normalize((1e150, 1e150, 1e150))
assert all(math.isfinite(c) for c in u)
assert math_isclose(magnitude(u), 1.0)
v = normalize((1e200, 1e200, 1e200))  # dot overflows -> deterministic 0 vector
assert v == (0.0, 0.0, 0.0)
assert cosine_similarity((1e200, 1e200, 1e200), (1e200, 1e200, 0.0)) == 0.0
for zp in (1e12, 1e4, 1.0, 1e-12, -1e12):
    assert math.isfinite(rm.glow01(zp))  # total, never overflows
    assert 0.0 <= rm.glow01(1.0) <= 1.0  # normal depth band stays in [0, 1]
    assert math.isfinite(rm.thickness01(zp))
    assert math.isfinite(rm.depth01(zp))
    assert math.isfinite(rm.project_scale(zp))
b = blend_pose(1e12, 1e12, 1e12)
assert math.isfinite(b)
b0 = blend_pose(1e12, -1e12, 2e12)
assert math.isfinite(b0)
print("math_expert_extremes=OK")

# ---- 3. non-finite deterministic fallbacks ---------------------------------
NAN, INF = float("nan"), float("inf")
for bad in (NAN, INF, -INF):
    assert clamp01(bad) == 0.0
    assert clamp(bad, 0.1, 0.9) == 0.1
    assert math.isfinite(lerp(bad, 1.0, 0.5))
    assert math.isfinite(stable_lerp(bad, 1.0, 0.5))
    assert math.isfinite(exp_smooth(bad, 1.0, 0.5))
    assert math.isfinite(stable_exp_smooth(bad, 1.0, 0.5, 3))
    assert math.isfinite(rm.zprime(bad))
    assert math.isfinite(rm.zprime_inv(bad))
    assert math.isfinite(rm.depth01(bad))
    assert math.isfinite(rm.project_scale(bad))
    assert math.isfinite(rm.thickness01(bad))
    assert math.isfinite(rm.glow01(bad))
    assert math.isfinite(rm.cycle_sweep(bad, 1.0, 2.0))
    s = MATH_AGENT.pattern_transition(bad, 0.5, 0.5)
    assert math.isfinite(s)
assert rm.thickness01(NAN) == 3.0
assert rm.project_scale(NAN) == 1.0
assert rm.zprime(NAN) == 0.0
assert blend_pose(NAN, 1.0, 0.0) == 0.3  # neutral channel == 0.0, 0.3*1.0 + 0.1*0.0
try:
    blend_pose(1.0, 1.0, 1.0, we=float("nan"), wv=0.3, wm=0.1)
    raise AssertionError("non-finite weight must raise")
except ValueError:
    pass
assert not math_isclose(NAN, NAN)
assert not math_isclose(INF, INF)
print("math_expert_nonfinite=OK")

# ---- 4. domain boundaries --------------------------------------------------
assert clamp01(-1.0) == 0.0 and clamp01(0.0) == 0.0
assert clamp01(1.0) == 1.0 and clamp01(2.0) == 1.0
assert stable_lerp(3.0, 4.0, 0.0) == 3.0
assert stable_lerp(3.0, 4.0, 1.0) == 4.0
assert lerp(3.0, 4.0, 0.0) == 3.0 and lerp(3.0, 4.0, 1.0) == 4.0
assert rm.smoothstep(0.0) == 0.0 and rm.smoothstep(1.0) == 1.0
assert rm.smoothstep(0.5) == 0.5
d = rm.depth01(rm.CAM_D)
assert 0.0 <= d <= 1.0
assert MATH_AGENT.pattern_transition(0.0, 1.0, 0.0) == 0.0
assert MATH_AGENT.pattern_transition(0.0, 1.0, 1.0) == 1.0
print("math_expert_boundaries=OK")

# ---- 5. random stress (10k seeded draws) -----------------------------------
for _ in range(N_STRESS // 2):
    a = RNG.uniform(-1e6, 1e6)
    b = RNG.uniform(-1e6, 1e6)
    t = RNG.uniform(0.0, 1.0)
    lo, hi = min(a, b), max(a, b)
    for value in (lerp(a, b, t), stable_lerp(a, b, t)):
        assert lo - 1e-6 * max(1.0, abs(lo), abs(hi)) <= value \
            <= hi + 1e-6 * max(1.0, abs(lo), abs(hi))
    assert math_isclose(lerp(a, b, t), stable_lerp(a, b, t), 1e-6)
    a0 = RNG.uniform(0.0, 1.0)
    b0 = RNG.uniform(0.0, 1.0)
    t0 = RNG.uniform(0.0, 1.0)
    s = MATH_AGENT.pattern_transition(a0, b0, t0)
    assert -1e-9 <= s <= 1.0 + 1e-9
    mn, mx = min(a0, b0), max(a0, b0)
    assert mn - 1e-9 <= s <= mx + 1e-9
    st = MATH_AGENT.pattern_state(a0, b0, t0)
    assert 0.0 <= st <= 1.0
    st_e = MATH_AGENT.set_precision_mode(PRECISION_EXPERT).pattern_state(a0, b0, t0)
    MATH_AGENT.set_precision_mode(PRECISION_STANDARD)
    assert math_isclose(st, st_e, 1e-9)

for _ in range(N_STRESS // 2):
    vec = tuple(RNG.uniform(-5.0, 5.0) for _ in range(3))
    sim = cosine_similarity(vec, vec)
    assert -1.0 <= sim <= 1.0
    assert math_isclose(sim, 1.0, 1e-9) or magnitude(vec) == 0.0
    other = tuple(RNG.uniform(-5.0, 5.0) for _ in range(3))
    assert -1.0 <= cosine_similarity(vec, other) <= 1.0
    p = MATH_AGENT.pattern_similarity(vec, other)
    assert 0.0 <= p <= 1.0

for _ in range(N_STRESS // 10):
    series = [RNG.uniform(0.0, 1.0) for _ in range(4)]
    stable_r = MATH_AGENT.world_stability(series)
    drift_r = MATH_AGENT.world_drift(series)
    assert stable_r["std"] is None or (math.isfinite(stable_r["std"]) and stable_r["std"] >= 0.0)
    assert drift_r["drift"] is None or (0.0 <= drift_r["drift"] <= 1.0)
    coh = MATH_AGENT.world_coherence(tuple(series))
    assert 0.0 <= coh["coherence"] <= 1.0
    pred = MATH_AGENT.world_predict(tuple(series), (0.0,) * 4)
    assert 0.0 <= pred["alignment"] <= 1.0
    assert all(-1e-9 <= m <= 1.0 + 1e-9 for m in pred["aligned"])
    fusion = MATH_AGENT.task_confidence(0.4, 0.7, 0.2)
    assert 0.0 <= fusion["confidence"] <= 1.0

# monotone transitions: raising alpha moves each aligned component toward the
# expected value without overshoot (lerp monotonicity on clamped endpoints).
expected = (0.2, 0.9, 0.3)
predicted = (0.8, 0.1, 0.7)
steps = [MATH_AGENT.world_predict(predicted, expected, alpha=a)["aligned"]
         for a in (0.0, 0.25, 0.5, 0.75, 1.0)]
for i in range(len(expected)):
    e, p0 = expected[i], predicted[i]
    lo, hi = min(e, p0), max(e, p0)
    vals = [step[i] for step in steps]
    assert math_isclose(vals[0], p0, 1e-12)
    assert math_isclose(vals[-1], e, 1e-12)
    assert all(lo - 1e-9 <= val <= hi + 1e-9 for val in vals)
    moving_up = e >= p0
    assert all(vals[j] <= vals[j + 1] + 1e-9 for j in range(4)) if moving_up \
        else all(vals[j] >= vals[j + 1] - 1e-9 for j in range(4))
print("math_expert_random_stress=OK")

# ---- 6. determinism (bit-for-bit) ------------------------------------------
seeded = random.Random(7)
samples = []
for _ in range(2000):
    t = seeded.uniform(0.0, 1.0)
    a = seeded.uniform(-1e8, 1e8)
    b = seeded.uniform(-1e8, 1e8)
    samples.append((a, b, t))
for a, b, t in samples:
    assert lerp(a, b, t) == lerp(a, b, t)
    assert stable_lerp(a, b, t) == stable_lerp(a, b, t)
    assert stable_exp_smooth(a, b, t, 5) == stable_exp_smooth(a, b, t, 5)
    v1 = tuple(seeded.uniform(-3, 3) for _ in range(3))
    v2 = tuple(seeded.uniform(-3, 3) for _ in range(3))
    assert cosine_similarity(v1, v2) == cosine_similarity(v1, v2)
assert MATH_AGENT.pattern_state(0.2, 0.8, 0.4) == MATH_AGENT.pattern_state(0.2, 0.8, 0.4)
assert stable_exp_smooth(0.0, 1.0, 0.3, 1000) == stable_exp_smooth(0.0, 1.0, 0.3, 1000)
print("math_expert_determinism=OK")

# ---- 7. tolerance equality ------------------------------------------------
assert not math_isclose(0.10, 0.12, 1e-9)          # 0.02 > 1e-9 * 1.0
assert not math_isclose(0.10, 0.10 + 1e-5, 1e-9)
assert math_isclose(0.10, 0.10 + 1e-10, 1e-9)      # within absolute floor
assert math_isclose(1.0, 1.0 + 1e-12, 1e-9)        # relative at unit scale
assert math_isclose(1000.0, 1000.0 + 1e-9, 1e-9)   # relative, not absolute
assert not math_isclose(1000.0, 1000.0 + 1e-3, 1e-9)
assert math_isclose(-0.0, 0.0, 1e-12)
assert pose_near(0.6 + 0.3 + 0.1, 1.0)
assert not math_isclose(0.1, 0.1 + 1e-8 * 10, 1e-9)  # scale-aware decay
print("math_expert_tolerance=OK")

# ---- 8. math precision mode ------------------------------------------------
assert PRECISION_MODES == frozenset({PRECISION_STANDARD, PRECISION_EXPERT})
assert PRECISION_TOLERANCE[PRECISION_EXPERT] \
    <= PRECISION_TOLERANCE[PRECISION_STANDARD]
assert MATH_AGENT.precision_mode == PRECISION_STANDARD
assert MATH_AGENT.precision_tolerance() == POSE_EPSILON
try:
    MATH_AGENT.set_precision_mode("banana")
    raise AssertionError("invalid mode must raise")
except ValueError:
    pass
MATH_AGENT.set_precision_mode(PRECISION_EXPERT)
try:
    assert MATH_AGENT.precision_mode == PRECISION_EXPERT
    assert MATH_AGENT.precision_tolerance() == PRECISION_TOLERANCE[PRECISION_EXPERT]
    # expert uses the stricter (smaller) tolerance
    near_one = 1.0 - 5e-11
    assert math_isclose(1.0, near_one, PRECISION_TOLERANCE[PRECISION_STANDARD])
    assert not math_isclose(1.0, near_one, PRECISION_TOLERANCE[PRECISION_EXPERT])
    # long-horizon stable smoothing never overshoots
    lo, hi = 0.2, 1.0
    prev = hi
    value = hi
    for _ in range(5000):
        value = stable_exp_smooth(value, lo, 0.3, 1)
        assert lo - 1e-12 <= value <= hi + 1e-12
        assert value <= prev + 1e-12
        prev = value
    assert math_isclose(prev, lo, 1e-9)
    p = MATH_AGENT.pattern_state(0.2, 0.8, 0.4)
    assert 0.2 <= p <= 0.8
finally:
    MATH_AGENT.set_precision_mode(PRECISION_STANDARD)
assert MATH_AGENT.precision_mode == PRECISION_STANDARD
print("math_expert_precision_mode=OK")

# ---- 9. expert invariants --------------------------------------------------
series = [0.4, 0.42, 0.45, 0.5]
world_report = {
    "stability": MATH_AGENT.world_stability(series),
    "drift": MATH_AGENT.world_drift(series),
    "coherence": MATH_AGENT.world_coherence(tuple(series)),
    "classify": MATH_AGENT.world_classify(tuple(series)),
    "predict": MATH_AGENT.world_predict(tuple(series), (WORLD_DOMAIN[1],) * 4),
}
v = MATH_AGENT.verify_world(world_report)
assert v["ok"], v["violations"]
assert v["checks"]["std"] >= 0.0
assert 0.0 <= v["checks"]["coherence"] <= 1.0
assert 0.0 <= v["checks"]["predicted_alignment"] <= 1.0

bad_world = {
    "stability": {"std": -0.5},
    "coherence": {"coherence": 1.5},
    "predict": {"alignment": 1.1, "aligned": (1.5, -0.4)},
}
v = MATH_AGENT.verify_world(bad_world)
assert not v["ok"]
rules = {vi["rule"] for vi in v["violations"]}
assert "world_std_negative" in rules
assert "world_coherence_out_of_domain" in rules
assert "world_prediction_out_of_domain" in rules
assert "world_transition_unbounded" in rules

pa = MATH_AGENT.verify_pattern_alignment((1.0, 1.0, 1.0), (1.0, 0.0, 1.0))
assert pa["ok"], pa["violations"]
assert -1.0 <= pa["raw"] <= 1.0
assert math_isclose(pa["clamped"], pa["canonical"])
raw = MATH_AGENT.cosine_alignment((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
assert math_isclose(raw, 0.0, 1e-9)
same = MATH_AGENT.cosine_alignment((1.0, 2.0, 3.0), (1.0, 2.0, 3.0))
assert math_isclose(same, 1.0, 1e-9)
try:
    MATH_AGENT.verify_pattern_alignment((1.0, 0.0), (1.0, 0.0, 0.0))
    raise AssertionError("dimension mismatch must raise")
except ValueError:
    pass

decision = MATH_AGENT.task_decision(
    (1.0, 0.6, 0.3), primary=0.8, secondary=0.2, context=0.5)
tf = MATH_AGENT.verify_task_fusion(decision, weights=TASK_BLEND_WEIGHTS)
assert tf["ok"], tf["violations"]
bad_fusion = {"fused": -0.1, "blended": {"a": 0.2, "b": 1.4}, "alpha": 1.2,
              "confidence": 0.5, "target": 0.9, "current": 0.1}
tf = MATH_AGENT.verify_task_fusion(bad_fusion, weights=TASK_BLEND_WEIGHTS)
assert not tf["ok"]
rules = {vi["rule"] for vi in tf["violations"]}
assert "task_fused_out_of_domain" in rules
assert "task_blend_out_of_domain" in rules
assert "task_alpha_out_of_domain" in rules
print("math_expert_invariants=OK")

# ---- 10. capability & market-role registries ------------------------------
assert len(cr.CAPABILITY_REGISTRY) == 11
assert len(cr.MARKET_ROLE_REGISTRY) == 8
for slug in ("expressive_math_face", "emotional_blending", "world_stability",
             "pattern_intelligence", "safety_monitoring",
             "multi_agent_coordination", "thinkpad_performance",
             "cognitive_reasoning", "contextual_memory",
             "adaptive_interaction", "domain_specific_behaviors"):
    entry = cr.capability(slug)
    assert entry["deterministic"] is True
    assert "dependencies" in entry and "outcome" in entry
    assert entry["layer"] in cr.LAYERS
for role in ("ai_companion", "holographic_assistant", "educational_tutor",
             "vtuber_avatar", "robotics_interface",
             "therapy_support_agent", "customer_service_agent",
             "enterprise_assistant"):
    caps = cr.capabilities_for_role(role)
    assert caps and len(caps) >= 3
    for slug in caps:
        assert slug in cr.CAPABILITY_REGISTRY
for layer in cr.LAYERS:
    owned = cr.capabilities_for_layer(layer)
    assert owned
    for slug in owned:
        assert cr.layer_for_capability(slug) == layer
try:
    cr.capability("flying_toaster")
    raise AssertionError("unknown capability must raise")
except KeyError:
    pass
try:
    cr.role_summary("priest")
    raise AssertionError("unknown role must raise")
except KeyError:
    pass
ov1 = cr.market_overview()
ov2 = cr.market_overview()
assert ov1 == ov2
assert tuple(ov1) == tuple(sorted(ov1))
for slug in cr.CAPABILITY_REGISTRY:
    assert cr.roles_for_capability(slug), f"{slug} deployed by no role"
for role in cr.MARKET_ROLE_REGISTRY:
    assert len(cr.capabilities_for_role(role)) == \
        len(set(cr.capabilities_for_role(role)))
print("math_expert_registry=OK")

assert MATH_AGENT.precision_mode == PRECISION_STANDARD
print("math_expert_suite=OK")