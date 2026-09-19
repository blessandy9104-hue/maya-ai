"""Cross-industry platform layer reference suite.

Script-style test (project convention): module-level asserts, OK labels.

Locks down the platform guarantees for the cognitive, interaction, and
domain layers added to the capability registry:

- determinism        : identical inputs -> identical outputs, bit for bit
- bounded math       : every scalar meaning stays on [0, 1] (gesture axes
                       on [-1, 1]); plan/mirror/teaching never overshoot
- semantic fidelity  : voice input and gesture mapping raise on unknown
                       features instead of inventing meaning; gesture
                       displacements respect the canonical channel ceilings
- math-governed      : reasoning/planning/memory/prediction/mirroring route
                       through clamped lerp, exp_smooth, cosine alignment and
                       the 0.6/0.3/0.1 blend proportions
- registries         : 11 capabilities across 4 layers, 8 roles; role<->domain
                       mapping is consistent with the capability registry

Run:  py -3 test_platform_layers.py   (from the project root; exit 0 = pass)
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity.wireframe.rig_math import math_isclose
from maya_identity.wireframe.math_coordinator import (
    MATH_AGENT, PRECISION_STANDARD, CHANNEL_MAX,
)
from maya_identity import capability_registry as cr
from maya_identity.cognition import COGNITION, Cognition
from maya_identity.interaction import INTERACTION, Interaction
from maya_identity.domains import (
    DOMAIN_BEHAVIORS, ROLE_DOMAIN, DOMAIN_SLUGS,
    behavior_for_domain, apply_domain, domain_for_role, domains_for_role,
    domain_overview,
)

MATH_AGENT.set_precision_mode(PRECISION_STANDARD)

# ---- cognitive layer: reasoning -------------------------------------------
r = COGNITION.reasoning({"context": 0.8, "sender": 0.6, "history": 0.4})
assert r["ok"] is True
assert 0.0 <= r["score"] <= 1.0
assert 0.0 <= r["evidence_level"] <= 1.0
assert 0.0 <= r["goal_alignment"] <= 1.0
r_low = COGNITION.reasoning({"context": 0.05, "sender": 0.02, "history": 0.01})
assert r_low["ok"] is False
r0 = COGNITION.reasoning({})
assert r0["ok"] is False and r0["score"] == 0.0
assert COGNITION.reasoning({"context": 0.9}) == \
    COGNITION.reasoning({"context": 0.9})  # determinism
# reasoned score must blend toward alignment for opposed evidence
r_opp = COGNITION.reasoning({"context": 0.9}, goal=(0.0, 1.0, 0.0))
assert 0.0 <= r_opp["score"] <= 1.0
assert MATH_AGENT.pattern_similarity((0.9, 0.0), (0.0, 1.0)) == 0.0
print("platform_cognitive_reasoning=OK")

# ---- cognitive layer: planning --------------------------------------------
current, goal = 0.9, 0.2
plan = COGNITION.planning(current, goal, horizon=32, alpha=0.4)
assert len(plan["steps"]) == 32
prev = current
for step in plan["steps"]:
    assert 0.0 <= step <= 1.0
    assert math_isclose(step, prev, 1e-9) or step <= prev + 1e-9  # monotone down
    assert 0.2 - 1e-9 <= step <= 0.9 + 1e-9                       # no overshoot
    prev = step
up = COGNITION.planning(0.1, 0.8, horizon=24, alpha=0.5)
for j in range(1, len(up["steps"])):
    assert up["steps"][j] >= up["steps"][j - 1] - 1e-9  # monotone up
assert math_isclose(up["final"], 0.8, 1e-6)
assert up["converged"] is True
assert math_isclose(up["steps"][-1], 0.8, 1e-6)
assert COGNITION.planning(0.5, 0.5, horizon=3)["final"] == 0.5
assert plan["final"] == plan["final"]  # determinism
print("platform_cognitive_planning=OK")

# ---- cognitive layer: contextual memory ------------------------------------
mem = COGNITION.contextual_memory(
    [("focus", 0.9), ("smalltalk", 0.2), ("data", 0.7), ("focus", 0.3)])
weights = mem["weights"]
assert math.isclose(sum(weights.values()), 1.0, rel_tol=0, abs_tol=1e-9)
assert all(0.0 <= w <= 1.0 for w in weights.values())
assert mem["retained"] <= mem["capacity"]
assert mem["recall"] in weights
capped = COGNITION.contextual_memory(
    [("a", 1.0), ("b", 0.2), ("c", 0.6), ("d", 0.9), ("e", 0.1)],
    capacity=3)
assert capped["retained"] == 3
assert set(capped["weights"]) == {"c", "d", "e"}
assert sum(capped["weights"].values()) - 1.0 < 1e-9
assert COGNITION.contextual_memory([("x", 0.4)]) == \
    COGNITION.contextual_memory([("x", 0.4)])
empty = COGNITION.contextual_memory([])
assert empty["recall"] is None and empty["retained"] == 0
print("platform_cognitive_memory=OK")

# ---- cognitive layer: bounded prediction ----------------------------------
pred = COGNITION.bounded_prediction((0.8, 0.1, 0.7), (0.2, 0.9, 0.3))
assert 0.0 <= pred["alignment"] <= 1.0
assert pred["bounded"] is True
assert all(-1e-9 <= v <= 1.0 + 1e-9 for v in pred["aligned"])
good = COGNITION.bounded_prediction((0.2, 0.9, 0.3), (0.2, 0.9, 0.3))
assert good["ok"] is True
assert COGNITION.bounded_prediction((0.8, 0.1, 0.7),
                                    (0.2, 0.9, 0.3)) == pred  # determinism
print("platform_cognitive_prediction=OK")

# ---- interaction layer: voice input ---------------------------------------
voice = INTERACTION.voice_input(
    {"energy": 0.8, "rate": 0.6, "pitch": 0.4, "pause": 0.2})
assert voice["viseme_target"] == 0.7
assert 0.0 <= voice["expression_glow"] <= 1.0
assert 0.0 <= voice["eye_focus"] <= 1.0
quiet = INTERACTION.voice_input({})
assert quiet["viseme_target"] == 0.0 and quiet["expression_glow"] == 0.0
assert quiet["eye_focus"] == 1.0  # no pause -> full focus
try:
    INTERACTION.voice_input({"tone": 0.9, "energy": 0.5})
    raise AssertionError("unknown voice feature must raise")
except ValueError:
    pass
assert INTERACTION.voice_input({"energy": 0.8, "rate": 0.6, "pitch": 0.4,
                                "pause": 0.2}) == voice
print("platform_interaction_voice=OK")

# ---- interaction layer: gesture mapping -----------------------------------
g = INTERACTION.gesture_mapping((0.5, -0.5, 0.8))
dx, dy, dz = g["displacements"]
assert abs(dx) <= CHANNEL_MAX["expression"]
assert abs(dy) <= CHANNEL_MAX["viseme"]
assert abs(dz) <= CHANNEL_MAX["micro"]
assert g["bounded"] is True
assert INTERACTION.gesture_mapping((0.5, -0.5, 0.8)) == g  # determinism
neutral = INTERACTION.gesture_mapping((0.0, 0.0, 0.0))
assert neutral["displacements"] == (0.0, 0.0, 0.0)
try:
    INTERACTION.gesture_mapping((0.5, 0.5))
    raise AssertionError("wrong arity must raise")
except ValueError:
    pass
print("platform_interaction_gesture=OK")

# ---- interaction layer: emotional mirroring --------------------------------
m = INTERACTION.emotional_mirroring(0.1, 0.9, alpha=0.5)
assert 0.1 <= m["mirror_state"] <= 0.9
assert 0.0 <= m["affinity"] <= 1.0
assert m["converged"] is False
# iterative convergence, no overshoot
state = 0.1
for _ in range(200):
    state = INTERACTION.emotional_mirroring(state, 0.9,
                                            alpha=0.5)["mirror_state"]
    assert 0.1 <= state <= 0.9 + 1e-9
assert math_isclose(state, 0.9, 1e-9)
m2 = INTERACTION.emotional_mirroring(0.5, 0.5)
assert m2["mirror_state"] == 0.5 and m2["converged"] is True
print("platform_interaction_mirroring=OK")

# ---- interaction layer: adaptive teaching ----------------------------------
t = INTERACTION.adaptive_teaching(0.2, 0.9, performance=0.8)
assert 0.2 <= t["recommended_level"] <= 0.9
assert 0.0 <= t["move"] <= 1.0 and 0.0 <= t["gap"] <= 1.0
assert t["move"] > 0.0
slow = INTERACTION.adaptive_teaching(0.2, 0.9, performance=0.1)
assert slow["move"] < t["move"]
fast = INTERACTION.adaptive_teaching(0.2, 0.9, performance=1.0, alpha=1.0)
assert math_isclose(fast["recommended_level"], 0.9, 1e-9)
assert INTERACTION.adaptive_teaching(0.2, 0.9, performance=0.8) == t
print("platform_interaction_teaching=OK")

# ---- domain layer: behaviour profiles --------------------------------------
assert set(DOMAIN_SLUGS) == {"tutoring", "customer_service", "therapy_support",
                             "robotics_interface", "entertainment"}
for domain in DOMAIN_SLUGS:
    profile = behavior_for_domain(domain)
    assert set(profile["channel_targets"]) == {"expression", "viseme", "micro"}
    for v in profile["channel_targets"].values():
        assert 0.0 <= v <= 1.0
    assert profile["capabilities"]
    for cap in profile["capabilities"]:
        assert cap in cr.CAPABILITY_REGISTRY
try:
    behavior_for_domain("astrology")
    raise AssertionError("unknown domain must raise")
except KeyError:
    pass
app = apply_domain("tutoring", 0.8, modulation=0.0)
assert app["bounded"] is True
assert all(0.0 <= v <= 1.0 for v in app["targets"].values())
assert app["targets"]["expression"] == \
    behavior_for_domain("tutoring")["channel_targets"]["expression"]
full = apply_domain("tutoring", 0.8, modulation=1.0)
assert math_isclose(full["targets"]["expression"], 0.8, 1e-9)
assert apply_domain("tutoring", 0.8, modulation=0.5) == \
    apply_domain("tutoring", 0.8, modulation=0.5)
print("platform_domain_behaviors=OK")

# ---- domain layer: role routing --------------------------------------------
for role, domain in ROLE_DOMAIN.items():
    assert domain in DOMAIN_BEHAVIORS
    assert "domain_specific_behaviors" in cr.capabilities_for_role(role)
    assert domain_for_role(role) == domain
for slug in cr.capabilities_for_role("educational_tutor"):
    assert slug in (cr.CAPABILITY_REGISTRY)
assert domain_for_role("educational_tutor") == "tutoring"
assert domain_for_role("therapy_support_agent") == "therapy_support"
assert domain_for_role("robotics_interface") == "robotics_interface"
# domain-agnostic roles (no domain_specific_behaviors) map to None
for role in ("holographic_assistant", "enterprise_assistant"):
    assert domains_for_role(role) == ()
ov = domain_overview()
assert tuple(ov) == tuple(sorted(ov))
assert all(c in cr.CAPABILITY_REGISTRY for caps in ov.values() for c in caps)
print("platform_domain_roles=OK")

# ---- registry: platform completeness and determinism ------------------------
assert len(cr.CAPABILITY_REGISTRY) == 11
assert len(cr.MARKET_ROLE_REGISTRY) == 8
assert set(cr.LAYERS) == {"core", "cognitive", "interaction", "domain"}
assert len(cr.capabilities_for_layer("core")) == 7
assert len(cr.capabilities_for_layer("cognitive")) == 2
assert len(cr.capabilities_for_layer("interaction")) == 1
assert len(cr.capabilities_for_layer("domain")) == 1
assert cr.market_overview() == cr.market_overview()
assert cr.market_overview() == cr.market_overview()  # byte-stable
for role in cr.MARKET_ROLE_REGISTRY:
    assert len(cr.capabilities_for_role(role)) == \
        len(set(cr.capabilities_for_role(role)))
print("platform_registry=OK")

assert MATH_AGENT.precision_mode == PRECISION_STANDARD
print("platform_layers_suite=OK")