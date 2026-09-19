"""Learning and prediction through the Math Coordination Agent.

Learning evaluates a pattern series over time with population variance,
stability, and a normalized (variance, stability, trend) learning vector.
Trend detection is dot similarity on a normalized movement vector; prediction
is exp_smooth-stabilized toward an expected reference; every prediction is
validated for semantic meaning and rejected when it violates rig_math
correctness. The interest ledger computes and stores only validated signal.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from maya_identity.wireframe.math_coordinator import MATH_AGENT  # noqa: E402
from maya_identity.wireframe.math_coordinator import (  # noqa: E402
    LEARNING_DEFAULT_HORIZON, LEARNING_FEATURES)
from maya_identity.wireframe.rig_math import exp_smooth  # noqa: E402
import maya_learning  # noqa: E402

# --- 1. learning summarizes a series by variance and stability -----------
flat = MATH_AGENT.learn_stats([0.3, 0.3, 0.3])
assert flat["ok"] is True and flat["std"] == 0.0 and flat["stable"] is True
assert flat["mean"] == 0.3 and flat["variance"] == 0.0
low = MATH_AGENT.learn_stats([0.1, 0.2, 0.1, 0.2])
assert abs(low["mean"] - 0.15) < 1e-12 and abs(low["variance"] - 0.0025) < 1e-12
assert abs(low["std"] - 0.05) < 1e-9
wide = MATH_AGENT.learn_stats([0.0, 0.5, 1.0])
assert wide["ok"] is True and wide["stable"] is False
assert MATH_AGENT.learn_stats([])["reason"] == "no_samples"
assert MATH_AGENT.learn_stats([0.2, float("nan")])["reason"] == "non_finite_value"
assert MATH_AGENT.learn_stats([0.2, 1.5])["reason"] == "out_of_domain"
print("learning_variance_and_stability=OK")

# --- 2. learning shares a normalized feature vector ----------------------
assert MATH_AGENT.learn_feature([0.3, 0.3, 0.3]) == (0.0, 1.0, 0.0)
assert MATH_AGENT.learn_feature([]) == (0.0, 0.0, 0.0)
assert len(MATH_AGENT.learn_feature([0.1, 0.4, 0.7])) == len(LEARNING_FEATURES)
assert all(0.0 <= v <= 1.0 for v in MATH_AGENT.learn_feature([0.1, 0.4, 0.7]))
print("learning_normalized_feature_vector=OK")

# --- 3. trends are detected by dot similarity ----------------------------
rising = MATH_AGENT.learn_trend([0.0, 0.2, 0.4, 0.6])
assert rising["ok"] is True and abs(rising["alignment"] - 1.0) < 1e-9
falling = MATH_AGENT.learn_trend([0.6, 0.4, 0.2, 0.0])
assert falling["ok"] is False and falling["alignment"] == 0.0
static = MATH_AGENT.learn_trend([0.5, 0.5, 0.5])
assert static["ok"] is False and static["alignment"] == 0.0
custom = MATH_AGENT.learn_trend([0.0, 0.5, 1.0], reference=(0.2, 0.4))
assert custom["ok"] is True
assert custom["alignment"] == MATH_AGENT.pattern_alignment((0.5, 0.5), (0.2, 0.4))
assert MATH_AGENT.learn_trend([0.5])["reason"] == "insufficient_samples"
print("learning_trend_dot_similarity=OK")

# --- 4. trend references must match the movement window ------------------
mismatch = MATH_AGENT.learn_trend([0.0, 0.3, 0.6, 0.9], reference=(1.0,))
assert mismatch["ok"] is False and mismatch["reason"] == "dimension_mismatch"
print("learning_trend_dimension_guard=OK")

# --- 5. predictions are stabilized by exp_smooth -------------------------
predict = MATH_AGENT.predict_signal([0.2, 0.4, 0.6, 0.9], expected=1.0,
                                    alpha=0.15, horizon=1)
assert abs(predict["predicted"] - exp_smooth(0.9, 1.0, 0.15)) < 1e-12
assert abs(predict["predicted"] - 0.915) < 1e-12
assert predict["predicted"] == MATH_AGENT.pattern_state(0.9, 1.0, 0.15)
ahead = MATH_AGENT.predict_signal([0.2, 0.4, 0.6, 0.9], expected=1.0,
                                  alpha=0.15, horizon=2)
assert abs(ahead["predicted"] - exp_smooth(0.915, 1.0, 0.15)) < 1e-12
print("prediction_stabilized_by_exp_smooth=OK")

# --- 6. predictions are guarded for semantic meaning ---------------------
bad_series = MATH_AGENT.predict_signal([], expected=1.0)
assert bad_series["ok"] is False and bad_series["reason"] == "no_samples"
assert MATH_AGENT.predict_signal([0.2, 0.4], expected=1.5)["reason"] == \
    "expected_out_of_domain"
assert MATH_AGENT.predict_signal([0.2, 0.4], expected=float("nan"))["reason"] == \
    "non_finite_expected"
assert MATH_AGENT.predict_signal([0.2, 0.4], expected=1.0, horizon=0)["reason"] == \
    "invalid_horizon"
print("prediction_semantic_guards=OK")

# --- 7. predictions are validated by mathematical re-derivation ---------
verdict = MATH_AGENT.predict_validate([0.2, 0.4, 0.6, 0.9], predict)
assert verdict["ok"] is True and all(verdict["checks"].values())
tampered = dict(predict, predicted=1.0)
assert any(v["rule"] == "prediction_math_mismatch" and v["field"] == "predicted"
           for v in MATH_AGENT.predict_validate([0.2, 0.4, 0.6, 0.9], tampered)["violations"])
wrong_trend = dict(predict, trend=0.0)
assert any(v["rule"] == "prediction_math_mismatch" and v["field"] == "trend"
           for v in MATH_AGENT.predict_validate([0.2, 0.4, 0.6, 0.9], wrong_trend)["violations"])
print("prediction_validated_by_rederivation=OK")

# --- 8. invalid predictions are rejected as reports ----------------------
missing = {key: value for key, value in predict.items() if key != "predicted"}
assert any(v["rule"] == "prediction_missing_field"
           for v in MATH_AGENT.predict_validate([0.2, 0.4, 0.6, 0.9], missing)["violations"])
out_of_range = dict(predict, predicted=1.5)
assert any(v["rule"] == "prediction_out_of_domain"
           for v in MATH_AGENT.predict_validate([0.2, 0.4, 0.6, 0.9], out_of_range)["violations"])
bad_horizon = dict(predict, horizon=0)
assert any(v["rule"] == "prediction_invalid_horizon"
           for v in MATH_AGENT.predict_validate([0.2, 0.4, 0.6, 0.9], bad_horizon)["violations"])
assert any(v["rule"] == "prediction_not_accepted"
           for v in MATH_AGENT.predict_validate([0.2, 0.4, 0.6, 0.9], bad_series)["violations"])
print("prediction_report_guards=OK")

# --- 9. violating predictions are enforced/rejected ----------------------
accepted = MATH_AGENT.predict_enforce([0.2, 0.4, 0.6, 0.9], predict)
assert accepted["ok"] is True
try:
    MATH_AGENT.predict_enforce([0.2, 0.4, 0.6, 0.9], tampered)
    raised = False
except ValueError:
    raised = True
assert raised
print("prediction_enforce_rejects_violations=OK")

# --- 10. the interest ledger learns and predicts through the agent ------
with tempfile.TemporaryDirectory() as directory:
    maya_learning.LEARNING_STATUS = Path(directory) / "learning_status.json"
    maya_learning.INTEREST_MAP = Path(directory) / "andy_interest_map.json"
    maya_learning.LEARNING_LOG = Path(directory) / "learning_events.jsonl"
    maya_learning.set_learning_mode("learning")
    for _ in range(4):
        record = maya_learning.record_signal("pattern learning", "probe")
        assert record["recorded"] is True
        assert record["confidence"] in {"low", "medium", "high"}
    interests = json.loads(maya_learning.INTEREST_MAP.read_text(encoding="utf-8"))["interests"]
    item = interests["pattern learning"]
    assert item["evidence"] == 4
    assert item["confidence"] in {"low", "medium", "high"}
    assert len(item["signal_series"]) == 4
    vector = item["learning_vector"]
    assert all(0.0 <= vector[name] <= 1.0
               for name in ("variance", "stability", "trend"))
    assert 0.0 <= vector["series_std"]
    stored = item["prediction"]
    assert stored["validated"] is True
    assert 0.0 <= stored["signal"] <= 1.0
    expected = MATH_AGENT.predict_signal(item["signal_series"], expected=1.0)
    assert abs(expected["predicted"] - stored["signal"]) < 1e-12
    maya_learning.set_learning_mode("sleeping")
    sleeping = maya_learning.record_signal("while sleeping", "probe")
    assert sleeping["recorded"] is False
    maya_learning.set_learning_mode("learning")
    resumed = maya_learning.record_signal("pattern learning", "resume")
    assert resumed["recorded"] is True and resumed["evidence"] == 5
    maya_learning.set_learning_mode("sleeping")
print("consumer_learning_ledger_agent_math=OK")

print("learning_prediction=OK")