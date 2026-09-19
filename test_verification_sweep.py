from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verification  # noqa: E402
from verification import manifest, monitor, report as report_mod, runner  # noqa: E402
from verification.report import stabilization_report  # noqa: E402
from maya_identity import stabilization  # noqa: E402

# --- manifest ------------------------------------------------------------------

assert manifest.all_suites() == manifest.SUITES
assert len(manifest.SUITES) >= 15
assert all(name.endswith(".py") for name in manifest.SUITES)
assert all(isinstance(name, str) and name for name in manifest.SUITES)
assert manifest.CONTROLLED_RUNTIME["module"] == "maya_runtime"
assert len(manifest.CONTROLLED_RUNTIME["signature_ops"]) == 4
print("verification_manifest=OK")

# --- controlled suite execution is observed, not assumed -----------------------

record = runner.run_suite("test_rig_math.py")
assert record["returncode"] == 0, record["anomalies"]
assert record["ok_labels"] == 15
assert record["clean"] is True
assert record["anomalies"] == []
assert record["duration_s"] >= 0.0
print("verification_controlled_run=OK")

# --- anomaly detection is honest --------------------------------------------------

anomaly_report = runner.run_suite("test_rig_math.py")
assert anomaly_report["returncode"] == 0
assert anomaly_report["clean"] is True
_isolated = runner.run_suite(
    str(pathlib.Path(__file__).parent / "test_rig_math.py"),
    cwd=tempfile.mkdtemp(),
)
assert _isolated["returncode"] == 0, _isolated["anomalies"]
assert _isolated["clean"] is True  # unaffected by working directory
bad_dir = tempfile.mkdtemp()
bad_file = pathlib.Path(bad_dir) / "failing_suite.py"
bad_file.write_text(
    "raise SystemExit(1)\n",
    encoding="utf-8",
)
failing = runner.run_suite(str(bad_file))
assert failing["returncode"] == 1
assert any(a["kind"] == "unintended_behavior" for a in failing["anomalies"])
assert failing["clean"] is False
print("verification_anomaly_detection=OK")

# --- controlled runtime launch is device-invariant -------------------------------

launch = runner.launch_runtime()
assert launch["clean"] is True, launch["anomalies"]
assert launch["signature_native"] == launch["signature_headless"]
assert launch["signature_native"] == (0.5, 1.0, 0.0, 4)
assert launch["duration_s"] >= 0.0
print("verification_controlled_launch=OK")

# --- sweep over a fast subset produces a clean external verdict ------------------

subset = runner.sweep(suites=("test_rig_math.py", "test_readiness.py"))
assert subset["clean"] is True
assert subset["suite_count"] == 2
assert subset["ok_total"] == 15 + 10
assert all(s["clean"] for s in subset["suites"])
assert {s["suite"] for s in subset["suites"]} == {"test_rig_math.py", "test_readiness.py"}
print("verification_sweep_clean=OK")

# --- stabilization report aggregates the six required categories -----------------

rep = stabilization_report(subset, launch)
assert rep["report"] == "stabilization"
assert rep["clean"] is True
for kind, _label in report_mod.CATEGORIES:
    assert rep["categories"][kind] == 0, kind
assert rep["decision"] == "ready_condition_met"
assert rep["signature_native"] == rep["signature_headless"]
print("verification_report_clean=OK")

# --- report is not clean when an anomaly is present --------------------------------

dirty_launch = dict(launch)
dirty_launch["anomalies"] = [
    {"kind": "safety_boundary_violation", "detail": "test-injected"}
]
dirty_launch["clean"] = False
dirty = stabilization_report(subset, dirty_launch)
assert dirty["clean"] is False
assert dirty["categories"]["safety_boundary_violation"] == 1
assert dirty["decision"] == "not_cleared"
print("verification_report_detects_anomaly=OK")

# --- monitor records findings deterministically ------------------------------------

monitor.record("unintended_behavior", "test-monitor-entry", source="test")
assert monitor.findings()[-1]["detail"] == "test-monitor-entry"
assert any(f["kind"] == "unintended_behavior" and f["detail"] == "test-monitor-entry"
           for f in monitor.findings())
print("verification_monitor=OK")

# --- external sweep result can drive the protocol decision ---------------------------

stabilization.reset()
forged = {"clean": True, "source": "external_sweep"}
decision = stabilization.confirm(forged)
assert decision["ready_state"] == "not_ready"  # no recorded run backs this dict
assert stabilization.is_ready() is False
print("verification_protocol_bridge=OK")

# --- final ---------------------------------------------------------------------------

print("verification_suite=OK")