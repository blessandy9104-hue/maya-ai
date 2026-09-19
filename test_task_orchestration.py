"""Task orchestration through the Math Coordination Agent.

Task priorities, confidence scores, and multi-signal fusion are computed
exclusively by the agent: priority from normalized vectors, fusion through
rig_math.blend_pose (weighted blending), decisions stabilized by exp_smooth,
and final decisions validated for semantic meaning and mathematical
correctness. No heuristic decision-making.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from maya_identity.wireframe.math_coordinator import MATH_AGENT  # noqa: E402
from maya_identity.wireframe.rig_math import blend_pose  # noqa: E402
import andy_decision  # noqa: E402

# --- 1. priority is computed from normalized vectors --------------------
report = MATH_AGENT.task_priority((1.0, 1.0, 1.0))
assert report["priority"] == 1.0
assert MATH_AGENT.task_priority((0.0, 0.0, 0.0))["priority"] == 0.0
skewed = MATH_AGENT.task_priority((0.9, 0.1, 0.1))["priority"]
assert 0.0 < skewed < 1.0
assert skewed == MATH_AGENT.pattern_alignment((0.9, 0.1, 0.1), (1.0, 1.0, 1.0))
print("task_priority_normalized_vectors=OK")

# --- 2. priority is angular, bounded, and scale-invariant ---------------
a = MATH_AGENT.task_priority((0.9, 0.1, 0.1))["priority"]
b = MATH_AGENT.task_priority((0.45, 0.05, 0.05))["priority"]
assert abs(a - b) < 1e-12
assert 0.0 <= a <= 1.0 and 0.0 <= b <= 1.0
assert MATH_AGENT.task_priority((1.0, 1.0, 1.0))["priority"] >= a
print("task_priority_scale_invariant=OK")

# --- 3. fusion uses rig_math.blend_pose ---------------------------------
assert MATH_AGENT.task_fuse(1.0, 0.0, 0.0)["fused"] == blend_pose(1.0, 0.0, 0.0) == 0.6
assert MATH_AGENT.task_fuse(0.0, 1.0, 0.0)["fused"] == blend_pose(0.0, 1.0, 0.0) == 0.3
assert MATH_AGENT.task_fuse(0.0, 0.0, 1.0)["fused"] == blend_pose(0.0, 0.0, 1.0) == 0.1
assert abs(MATH_AGENT.task_fuse(0.25, 0.5, 0.9)["fused"] - blend_pose(0.25, 0.5, 0.9)) < 1e-12
assert abs(MATH_AGENT.task_fuse(1.0, 1.0, 1.0)["fused"] - 1.0) < 1e-12
print("task_fuse_uses_blend_pose=OK")

# --- 4. general weighted blending normalizes weights and clamps ---------
assert abs(MATH_AGENT.task_blend([0.2, 0.6, 0.9], [0.25, 0.25, 0.5])["fused"] - 0.65) < 1e-12
assert abs(MATH_AGENT.task_blend([0.2, 0.6, 0.9], [1, 1, 2])["fused"] - 0.65) < 1e-12
assert abs(MATH_AGENT.task_blend([0.2, 0.6, 0.9])["fused"] - 0.5666666666666667) < 1e-12
assert abs(MATH_AGENT.task_blend([1.5, -0.2, 0.3], [0.6, 0.3, 0.1])["fused"] - 0.63) < 1e-12
print("task_blend_weighted=OK")

# --- 5. confidence is the fused signal stabilized by exp_smooth ---------
first = MATH_AGENT.task_confidence(1.0, 1.0, 1.0)
assert abs(first["confidence"] - 1.0) < 1e-12 and first["current"] is None
stabilized = MATH_AGENT.task_confidence(1.0, 1.0, 1.0, current=0.2, alpha=0.15)
assert abs(stabilized["confidence"] - (0.2 + (1.0 - 0.2) * 0.15)) < 1e-12
assert abs(stabilized["confidence"] - MATH_AGENT.pattern_state(0.2, 1.0, 0.15)) < 1e-12
damped = MATH_AGENT.task_confidence(0.0, 0.0, 0.0, current=0.5, alpha=0.1)
assert abs(damped["confidence"] - 0.45) < 1e-12
print("task_confidence_exp_smooth=OK")

# --- 6. task_state is the canonical exp_smooth pattern state ------------
assert MATH_AGENT.task_state(0.2, 1.0, 0.15) == MATH_AGENT.pattern_state(0.2, 1.0, 0.15)
assert MATH_AGENT.task_state(0.5, 0.0, 0.1) == 0.45
assert 0.0 <= MATH_AGENT.task_state(-0.5, 1.5, 0.3) <= 1.0
print("task_state_exp_smooth=OK")

# --- 7. a complete decision carries its derivation ----------------------
decision = MATH_AGENT.task_decision((0.8, 0.9, 0.6), primary=0.7,
                                    secondary=0.5, context=0.3, current=0.4)
assert set(decision) == {
    "features", "reference", "priority", "primary", "secondary", "context",
    "weights", "fused", "current", "alpha", "confidence"}
assert abs(decision["fused"] - 0.60) < 1e-12
assert abs(decision["confidence"] - (0.4 + (0.60 - 0.4) * 0.15)) < 1e-12
assert decision["priority"] == MATH_AGENT.pattern_alignment(
    decision["features"], decision["reference"])
print("task_decision_derivation=OK")

# --- 8. final decisions are validated for mathematical correctness ------
assert MATH_AGENT.task_decision_ok(decision)["ok"] is True
tampered = dict(decision, priority=0.9)
verdict = MATH_AGENT.task_decision_ok(tampered)
assert verdict["ok"] is False
assert any(v["rule"] == "task_math_mismatch" and v["field"] == "priority"
           for v in verdict["violations"])
print("task_decision_ok_validates=OK")

# --- 9. decisions are guarded for semantic meaning ----------------------
missing = {key: value for key, value in decision.items() if key != "confidence"}
assert any(v["rule"] == "task_missing_field"
           for v in MATH_AGENT.task_decision_ok(missing)["violations"])
out_of_domain = dict(decision, confidence=1.5)
assert any(v["rule"] == "task_out_of_domain"
           for v in MATH_AGENT.task_decision_ok(out_of_domain)["violations"])
non_finite = dict(decision, context=float("nan"))
assert any(v["rule"] == "task_non_finite"
           for v in MATH_AGENT.task_decision_ok(non_finite)["violations"])
dim_mismatch = dict(decision, reference=(1.0, 1.0, 1.0, 0.0))
assert any(v["rule"] == "task_dimension_mismatch"
           for v in MATH_AGENT.task_decision_ok(dim_mismatch)["violations"])
print("task_decision_semantic_guards=OK")

# --- 10. the decision ledger computes task math through the agent -------
with tempfile.TemporaryDirectory() as directory:
    andy_decision.LEDGER = Path(directory) / "andy_decisions.jsonl"
    andy_decision.record("task_selection", "research first",
                         ["research", "course"], "most urgent signal set",
                         features=(0.9, 0.8, 0.6),
                         primary=0.8, secondary=0.6, context=0.4,
                         current=0.5)
    rows = [json.loads(line)
            for line in andy_decision.LEDGER.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 1
    entry = rows[0]
    assert 0.0 <= entry["priority"] <= 1.0
    assert 0.0 <= entry["confidence"] <= 1.0
    assert 0.0 <= entry["fused"] <= 1.0
    assert entry["task_decision_ok"] is True
    andy_decision.record("note", "plain", [], "no signals given")
    rows = [json.loads(line)
            for line in andy_decision.LEDGER.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 2 and "priority" not in rows[-1]
print("consumer_andy_decision_agent_math=OK")

print("task_orchestration=OK")