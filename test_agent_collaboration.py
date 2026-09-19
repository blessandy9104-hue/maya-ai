"""Multi-agent collaboration through the Math Coordination Agent.

Agents communicate only as normalized math vectors: state is shared through
clamp01-bounded vectors, goals align by dot similarity, contributions blend
by lerp (voiced move) and exp_smooth (converging shared state), and every
message is peer-validated for semantic meaning and rig_math correctness. No
heuristic agent communication.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from maya_identity.wireframe.math_coordinator import MATH_AGENT  # noqa: E402
from maya_identity.wireframe.math_coordinator import (  # noqa: E402
    AGENT_ALIGNMENT_FLOOR, AGENT_CONTRIBUTION_DEFAULT_ALPHA)
from maya_identity.wireframe.rig_math import lerp, exp_smooth  # noqa: E402


def _message(agent_id, state, contribution, current, alpha=0.15, t=0.5,
             goal=None):
    base = MATH_AGENT.agent_contribution(contribution, current, alpha, t)
    goal = goal if goal is not None else state
    return {
        "agent_id": agent_id,
        "state": tuple(state),
        "goal": tuple(goal),
        "contribution": base["contribution"],
        "current": base["current"],
        "evolved": base["evolved"],
        "voiced": base["voiced"],
        "t": base["t"],
        "alpha": base["alpha"],
        "alignment": MATH_AGENT.pattern_alignment(state, goal),
    }


# --- 1. shared state is communicated as a normalized math vector --------
state = MATH_AGENT.agent_state([0.3, 1.5, -0.2, float("nan"), "x", True])
assert state == (0.3, 1.0, 0.0, 0.0, 0.0, 1.0)
assert all(0.0 <= v <= 1.0 for v in state)
assert MATH_AGENT.agent_state([]) == ()
print("agent_state_normalized_vectors=OK")

# --- 2. goals align by dot similarity on normalized vectors -------------
same = MATH_AGENT.agent_goal_alignment((1.0, 0.2, 0.3), (1.0, 0.2, 0.3))
assert same["ok"] is True and abs(same["alignment"] - 1.0) < 1e-12
zero = MATH_AGENT.agent_goal_alignment((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
assert zero["ok"] is False and zero["alignment"] == 0.0
orthogonal = MATH_AGENT.agent_goal_alignment((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
assert orthogonal["ok"] is False and orthogonal["alignment"] == 0.0
toward_shared = MATH_AGENT.agent_goal_alignment((0.9, 0.8, 0.7), (1.0, 1.0, 1.0))
assert toward_shared["ok"] is True and 0.6 < toward_shared["alignment"] <= 1.0
assert toward_shared["alignment"] == MATH_AGENT.pattern_alignment(
    (0.9, 0.8, 0.7), (1.0, 1.0, 1.0))
print("agent_goal_alignment_dot_similarity=OK")

# --- 3. contribution blending is the canonical lerp transition ---------
contribution = MATH_AGENT.agent_contribution(0.8, current=0.2, alpha=0.15, t=0.5)
assert abs(contribution["voiced"] - lerp(0.2, 0.8, 0.5)) < 1e-12
assert abs(contribution["voiced"] - 0.5) < 1e-12
assert contribution["voiced"] == MATH_AGENT.pattern_transition(0.2, 0.8, 0.5)
assert abs(MATH_AGENT.agent_contribution(0.0, 1.0, 0.3, t=0.0)["voiced"] - 1.0) < 1e-12
print("agent_contribution_uses_lerp=OK")

# --- 4. blended contributions converge through exp_smooth --------------
assert abs(contribution["evolved"] - exp_smooth(0.2, 0.8, 0.15)) < 1e-12
assert abs(contribution["evolved"] - 0.29) < 1e-12
assert contribution["evolved"] == MATH_AGENT.pattern_state(0.2, 0.8, 0.15)
assert abs(MATH_AGENT.agent_contribution(0.0, 0.5, 0.1)["evolved"] - 0.45) < 1e-12
bounded = MATH_AGENT.agent_contribution(1.5, -0.2, 0.3, t=0.2)
assert bounded["contribution"] == 1.0 and bounded["current"] == 0.0
assert 0.0 <= bounded["voiced"] <= 1.0 and 0.0 <= bounded["evolved"] <= 1.0
print("agent_contribution_uses_exp_smooth=OK")

# --- 5. agent messages are guarded for semantic meaning -----------------
valid = _message("peer_a", (0.8, 0.9, 0.7), 0.6, 0.4)
no_id = dict(valid)
no_id.pop("agent_id")
assert any(v["rule"] == "agent_missing_id"
           for v in MATH_AGENT.agent_validate(no_id)["violations"])
missing = _message("peer_a", (0.8, 0.9, 0.7), 0.6, 0.4)
missing.pop("evolved")
assert any(v["rule"] == "agent_missing_field" and v["field"] == "evolved"
           for v in MATH_AGENT.agent_validate(missing)["violations"])
out_of_range = dict(valid, contribution=1.5)
assert any(v["rule"] == "agent_out_of_domain" and v["field"] == "contribution"
           for v in MATH_AGENT.agent_validate(out_of_range)["violations"])
non_finite = dict(valid, current=float("nan"))
assert any(v["rule"] == "agent_non_finite" and v["field"] == "current"
           for v in MATH_AGENT.agent_validate(non_finite)["violations"])
dim_mismatch = dict(valid, goal=(1.0, 1.0))
assert any(v["rule"] == "agent_dimension_mismatch"
           for v in MATH_AGENT.agent_validate(dim_mismatch)["violations"])
print("agent_message_semantic_guards=OK")

# --- 6. messages are validated against rig_math by re-derivation -------
valid = _message("peer_a", (0.8, 0.9, 0.7), 0.6, 0.4)
verdict = MATH_AGENT.agent_validate(valid)
assert verdict["ok"] is True and all(verdict["checks"].values())
tampered_evolved = dict(valid, evolved=0.99)
tampered_verdict = MATH_AGENT.agent_validate(tampered_evolved)
assert tampered_verdict["ok"] is False
assert any(v["rule"] == "agent_math_mismatch" and v["field"] == "evolved"
           for v in tampered_verdict["violations"])
tampered_voiced = dict(valid, voiced=0.01)
assert any(v["rule"] == "agent_math_mismatch" and v["field"] == "voiced"
           for v in MATH_AGENT.agent_validate(tampered_voiced)["violations"])
print("agent_message_math_rederivation=OK")

# --- 7. peer validation checks the alignment an agent claims -----------
assert MATH_AGENT.agent_validate(valid)["checks"]["alignment"] is True
wrong_alignment = dict(valid, alignment=0.99)
wrong_verdict = MATH_AGENT.agent_validate(wrong_alignment)
assert any(v["rule"] == "agent_math_mismatch" and v["field"] == "alignment"
           for v in wrong_verdict["violations"])
print("agent_message_peer_alignment_check=OK")

# --- 8. a team round coordinates the aligned planes --------------------
agents = [
    _message("emotional", (0.8, 0.9, 0.7), 0.5, 0.5, goal=(1.0, 1.0, 1.0)),
    _message("viseme", (0.7, 0.6, 0.4), 0.6, 0.5, goal=(1.0, 1.0, 1.0)),
    _message("world", (0.9, 0.8, 0.9), 0.7, 0.5, goal=(1.0, 1.0, 1.0)),
    _message("safety", (1.0, 0.9, 0.9), 0.8, 0.5, goal=(1.0, 1.0, 1.0)),
    _message("task", (0.9, 0.8, 0.6), 0.9, 0.5, goal=(1.0, 1.0, 1.0)),
]
round_report = MATH_AGENT.agent_collaborate(agents)
assert round_report["ok"] is True
assert len(round_report["pairs"]) == 10
for pair in round_report["pairs"]:
    assert pair["ok"] is True
    left = next(m for m in agents if m["agent_id"] == pair["agents"][0])
    right = next(m for m in agents if m["agent_id"] == pair["agents"][1])
    assert abs(pair["alignment"] - MATH_AGENT.pattern_alignment(
        left["state"], right["state"])) < 1e-12
assert round_report["team_alignment"] == min(
    p["alignment"] for p in round_report["pairs"])
team = agents[0]["contribution"]
for m in agents[1:]:
    team = exp_smooth(team, m["contribution"], m["alpha"])
assert abs(round_report["shared_state"] - team) < 1e-12
assert all(value is True for key, value in round_report["agents"].items())
print("agent_collaborate_team_round=OK")

# --- 9. misaligned or mismatched rounds are rejected -------------------
misaligned = [
    _message("left", (1.0, 0.0, 0.0), 0.5, 0.5, goal=(1.0, 1.0, 1.0)),
    _message("right", (0.0, 1.0, 0.0), 0.5, 0.5, goal=(1.0, 1.0, 1.0)),
]
bad_round = MATH_AGENT.agent_collaborate(misaligned)
assert bad_round["ok"] is False
assert any(v["rule"] == "agent_goals_misaligned"
           for v in bad_round["violations"])
dim_round = MATH_AGENT.agent_collaborate([
    _message("a", (0.8, 0.9), 0.5, 0.5),
    _message("b", (0.8, 0.9, 0.7), 0.5, 0.5),
])
assert dim_round["ok"] is False
assert any(v["rule"] == "agent_round_dimension_mismatch"
           for v in dim_round["violations"])
print("agent_collaborate_rejects_bad_rounds=OK")

# --- 10. the frame contract includes the collaboration round -----------
frame = MATH_AGENT.orchestrate({"agents": agents[:3]})
assert frame["subsystems"]["agents"] is True
assert frame["subsystems"]["team_alignment"] is not None
assert frame["subsystems"]["shared_state"] is not None
assert frame["ok"] is True
bad_frame = MATH_AGENT.orchestrate({"agents": misaligned})
assert bad_frame["subsystems"]["agents"] is False and bad_frame["ok"] is False
print("consumer_orchestrate_agents=OK")

print("agent_collaboration=OK")