"""World-state math validation for Maya — stability, coherence, drift,
classification, and prediction alignment, all through the Math
Coordination Agent with normalized vectors, dot similarity, exp_smooth
smoothing, and lerp/clamp01 transitions. No heuristic world reasoning."""
from __future__ import annotations

from maya_identity.wireframe.math_coordinator import (
    MATH_AGENT,
    WORLD_STATE_FEATURES,
    WORLD_STATE_PATTERNS,
)
from maya_identity.wireframe.rig_math import clamp01, lerp

# ---- instability is detected by variance -------------------------------
_burst = [0.3, 0.9, 0.12, 0.88, 0.3]
assert MATH_AGENT.world_stability(_burst, max_std=0.05)["ok"] is False
assert MATH_AGENT.world_stability(_burst, max_std=0.05)["reason"] == "drift_beyond_tolerance"
assert MATH_AGENT.world_stability([0.0, float("nan"), 0.0])["ok"] is False

# ---- feature space and canonical reference patterns --------------------
assert WORLD_STATE_FEATURES == ("stability", "drift", "currency", "consensus")
assert set(WORLD_STATE_PATTERNS) == {
    "stable_equilibrium", "drifting", "unstable", "conflicted"}

# ---- normalized world vectors ------------------------------------------
n = MATH_AGENT.world_normalize((3.0, 4.0, 0.0))
assert abs(n[0] - 0.6) < 1e-12 and abs(n[1] - 0.8) < 1e-12 and abs(n[2]) < 1e-12
assert MATH_AGENT.world_normalize((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)

# ---- drift is detected by an equilibrium (exp_smooth) check ------------
sd = MATH_AGENT.world_drift([0.5, 0.49, 0.51, 0.5, 0.5], alpha=0.03, tolerance=0.35)
dd = MATH_AGENT.world_drift([0.1, 0.3, 0.5, 0.7, 0.9], alpha=0.03, tolerance=0.35)
assert sd["ok"] is True and dd["ok"] is False
assert dd["reason"] == "drift_beyond_equilibrium"
assert MATH_AGENT.world_drift([0.4])["ok"] is True and MATH_AGENT.world_drift([0.4])["drift"] == 0.0
assert MATH_AGENT.world_drift([0.4, float("nan")])["ok"] is False
assert MATH_AGENT.world_drift([0.4, 1.6])["ok"] is False

# ---- world patterns are classified by normalized-vector dot similarity --
cls = MATH_AGENT.world_classify((1.0, 0.02, 0.98, 0.99), floor=0.6)
assert cls["ok"] is True and cls["best"] == "stable_equilibrium"
assert MATH_AGENT.world_classify((0.5, 0.95, 0.55, 0.9))["best"] == "drifting"
unaligned = MATH_AGENT.world_classify((0.0, 0.0, 0.0, 0.0), floor=0.6)
assert unaligned["ok"] is False

# ---- alignment with expected reference --------------------------------
coh = MATH_AGENT.world_coherence((0.95, 0.05, 0.9, 0.85), floor=0.6)
assert coh["ok"] is True and 0.6 <= coh["coherence"] <= 1.0
assert abs(coh["coherence"] - MATH_AGENT.pattern_alignment(
    (0.95, 0.05, 0.9, 0.85), (1.0, 0.0, 1.0, 1.0))) < 1e-12

# ---- prediction aligns to expectation through lerp/clamp01 -------------
pred = MATH_AGENT.world_predict((0.8, 0.7, 0.1), (0.9, 1.0, 0.0), alpha=1.0)
assert pred["ok"] is True and pred["aligned"] == (0.9, 1.0, 0.0)
pred_half = MATH_AGENT.world_predict((0.2, 0.4, 0.6), (1.0, 0.0, 0.0), alpha=0.5)
assert pred_half["aligned"] == (
    lerp(clamp01(0.2), clamp01(1.0), 0.5),   # = 0.6
    lerp(clamp01(0.4), clamp01(0.0), 0.5),   # = 0.2
    lerp(clamp01(0.6), clamp01(0.0), 0.5),   # = 0.3
)
assert all(0.0 <= v <= 1.0 for v in pred_half["aligned"])

# ---- composite evaluation ----------------------------------------------
ev = MATH_AGENT.world_evaluate((0.97, 0.03, 0.95, 0.9), floor=0.5)
assert ev["ok"] is True
assert ev["classification"]["best"] == "stable_equilibrium"
assert 0.0 <= ev["coherence"]["coherence"] <= 1.0
assert ev["pattern_vector"] == (0.97, 0.03, 0.95, 0.9)

# ---- world model exposes agent-backed stability report -------------------
from maya_world_model import stability_status
r = stability_status()
assert r["status"] in ("stable", "review")
assert r["evidence_count"] >= 0
assert "uncertainty_std" in r and "world_pattern" in r
assert isinstance(r["drift"], dict) and "drift" in r["drift"]
assert isinstance(r["coherence"], dict) and "coherence" in r["coherence"]
assert isinstance(r["classification"], dict) and "best" in r["classification"]
assert isinstance(r["prediction"], dict) and "aligned" in r["prediction"]
assert r["classification"]["best"] in set(WORLD_STATE_PATTERNS)

print("world_stability_variance=OK")
print("world_feature_space=OK")
print("world_vector_normalized=OK")
print("world_drift_equilibrium=OK")
print("world_pattern_classification=OK")
print("world_prediction_alignment=OK")
print("world_transition_lerp_clamp01=OK")
print("world_coherence_dot=OK")
print("world_evaluate=OK")
print("world_model_agent_backed=OK")
