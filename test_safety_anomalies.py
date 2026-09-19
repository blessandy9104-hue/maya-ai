"""Safety thresholds enforced through the Math Coordination Agent.

Every safety decision is mathematically derived and validated by the agent:
resource usage is evaluated with ``clamp01`` (bounded margins), variance-based
anomaly detection, and explicit threshold comparison. The engine detects CPU
anomalies, memory anomalies, multi-process violations, motion instability,
and world-state drift. No heuristic safety reasoning.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from maya_identity.wireframe.math_coordinator import MATH_AGENT, SAFETY_POLICY  # noqa: E402
import maya_safety_monitor as monitor  # noqa: E402

# --- 1. resource math is clamp01-bounded and variance-based -------------
report = MATH_AGENT.resource_anomaly([50.0, 50.0, 50.0], 52.0)
assert report["ok"] is True and 0.0 <= report["anomaly"] <= 1.0
assert abs(report["anomaly"] - 0.5) < 1e-9          # 2 / (2 * 2)
assert MATH_AGENT.resource_anomaly([50.0, 50.0, 50.0], 95.0)["anomaly"] == 1.0
print("math_agent_safety_math=OK")

# --- 2. CPU anomaly detected (below the threshold ceiling) --------------
# Flat 20% baseline, current 50%: a threshold check passes (50 < 60) but the
# variance anomaly report flags the jump, and the composite rejects it.
report = MATH_AGENT.resource_anomaly([20.0, 20.0, 20.0], 50.0)
assert report["ok"] is False and report["anomaly"] == 1.0
composite = MATH_AGENT.safety_evaluate(50.0, 40.0, 1, 0, cpu_history=[20.0] * 5)
assert composite["safe"] is False
assert composite["violations"] == ["CPU usage anomaly"]
assert composite["checks"]["cpu_anomaly"] is False
print("cpu_anomaly_detected=OK")

# --- 3. memory anomaly detected (below the threshold ceiling) ------------
report = MATH_AGENT.resource_anomaly([20.0, 20.0, 20.0], 55.0)
assert report["ok"] is False and report["anomaly"] == 1.0
composite = MATH_AGENT.safety_evaluate(20.0, 55.0, 1, 0,
                                       memory_history=[20.0] * 5)
assert composite["safe"] is False
assert composite["violations"] == ["memory usage anomaly"]
print("memory_anomaly_detected=OK")

# --- 4. insufficient history cannot be judged anomalous -----------------
assert MATH_AGENT.resource_anomaly([60.0], 30.0)["ok"] is True
print("insufficient_history_is_safe=OK")

# --- 5. multi-process violations are detected by threshold comparison ---
composite = MATH_AGENT.safety_evaluate(20.0, 40.0, 3, 1)
assert composite["safe"] is False
assert "Maya process-count limit exceeded" in composite["violations"]
assert composite["checks"]["thresholds"] is False
print("multi_process_violation=OK")

# --- 6. motion instability detected -------------------------------------
# High-variance oscillation and equilibrium drift both flag the motion series.
oscillating = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
motion = MATH_AGENT.motion_instability(oscillating)
assert motion["ok"] is False and motion["instability"] == 1.0
composite = MATH_AGENT.safety_evaluate(20.0, 40.0, 1, 0,
                                       motion_series=oscillating)
assert composite["safe"] is False
assert composite["violations"] == ["motion instability"]
print("motion_instability_detected=OK")

# --- 7. stable motion keeps an aligned margin ---------------------------
calm = [0.5, 0.51, 0.49, 0.5, 0.51, 0.49]
motion = MATH_AGENT.motion_instability(calm)
assert motion["ok"] is True
assert 0.0 <= motion["instability"] <= 1.0
composite = MATH_AGENT.safety_evaluate(20.0, 40.0, 1, 0, motion_series=calm)
assert composite["safe"] is True
assert 0.0 <= composite["margin"] <= 1.0
print("motion_stable_margin_aligned=OK")

# --- 8. world-state drift detected --------------------------------------
drifting = [0.1, 0.1, 0.1, 0.15, 0.2, 0.5, 0.8]
composite = MATH_AGENT.safety_evaluate(20.0, 40.0, 1, 0, world_series=drifting)
assert composite["safe"] is False
assert composite["violations"] == ["world-state drift"]
assert composite["checks"]["world_drift"] is False
print("world_state_drift_detected=OK")

# --- 9. a noisy but equilibrium-anchored world is not drifting ----------
settled = [0.5, 0.52, 0.48, 0.51, 0.49, 0.5]
assert MATH_AGENT.world_drift(settled)["ok"] is True
composite = MATH_AGENT.safety_evaluate(20.0, 40.0, 1, 0, world_series=settled)
assert composite["safe"] is True
print("world_state_stable_noisy=OK")

# --- 10. the wired monitor evaluates through the agent ------------------
import tempfile

with tempfile.TemporaryDirectory() as directory:
    monitor.STOP_PATH = Path(directory) / "PRESENCE_STOP"
    snap = monitor.ResourceSnapshot(cpu_percent=21.0, memory_percent=21.0,
                                    maya_process_count=1, launches_last_minute=0)
    calm = monitor.evaluate(snap,
                            cpu_history=[20.0, 21.0, 20.0, 21.0],
                            memory_history=[20.0, 21.0, 20.0, 21.0],
                            motion_series=[0.5] * 6)
    assert calm["safe"] is True and calm["reasons"] == []
    assert calm["checks"]["cpu_anomaly"] is True
    assert calm["checks"]["memory_anomaly"] is True
    assert 0.0 <= calm["margin"] <= 1.0
    bad = monitor.evaluate(
        monitor.ResourceSnapshot(cpu_percent=50.0, memory_percent=40.0,
                                 maya_process_count=1, launches_last_minute=0),
        cpu_history=[20.0] * 5, memory_history=[40.0, 41.0, 40.0],
        motion_series=[0.5] * 6)
    assert bad["safe"] is False
    assert bad["reasons"] == ["CPU usage anomaly"]
    assert all(isinstance(reason, str) for reason in bad["reasons"])
print("composite_validated_by_agent=OK")

print("safety_anomaly_detection=OK")