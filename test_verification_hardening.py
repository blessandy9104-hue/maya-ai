"""Hardening regression tests for the verification repairs.

Each `...=OK` marker is one intentional, autonomous assertion group covering a
repaired flaw: the evidence gate, the controlled launch handshake, the
nonce-anchored verdict, evidence-based anomaly categories, internal
intelligence coverage, the independent signature reference, and timeout
handling. This suite is contracted for exactly 25 markers.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import uuid
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maya_identity.stabilization as stabilization  # noqa: E402
import maya_identity.readiness as readiness  # noqa: E402
from verification import authenticity  # noqa: E402
from verification import monitor, reference, runner  # noqa: E402

# The verified deploy run authenticates its single recorded verdict with a
# per-run ephemeral key (see verification/authenticity). This suite simulates
# that in-process key so genuinely recorded verdicts are signed and confirm()
# accepts them while every forged/injected path still fails closed.
_TEST_KEY = authenticity.fresh_key()
monitor.set_verdict_key(_TEST_KEY)
stabilization.set_verdict_key(_TEST_KEY)

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="verification_hardening_"))


def _write(name, body):
    path = _TMP / name
    path.write_text(body, encoding="utf-8")
    return str(path)


# --- 1. empty suite output is a failure, never clean ---------------------------

_empty = _write("empty_suite.py", "# deliberately produces no output\n")
_rec = runner.run_suite(_empty)
assert _rec["clean"] is False, _rec
assert any(a["detail"] == "empty output" for a in _rec["anomalies"])
assert _rec["ok_labels"] == 0
print("empty_output_rejected=OK")

# --- 2. matching ok-evidence keeps a clean suite clean -------------------------

_rec = runner.run_suite("test_rig_math.py")
assert _rec["clean"] is True, _rec["anomalies"]
assert _rec["ok_labels"] == 15
print("ok_count_matched_clean=OK")

# --- 3. ok-evidence mismatch is rejected against the manifest contract ---------

_mismatched = _write(
    "test_rig_math.py",
    "print('a=OK')\n" * 10,
)
_rec = runner.run_suite(_mismatched)
assert _rec["ok_labels"] == 10
assert _rec["clean"] is False
assert any("ok evidence mismatch" in a["detail"] for a in _rec["anomalies"])
print("ok_count_mismatch_rejected=OK")

# --- 4. an explicitly contradictory status line can never look clean -----------

_contradictory = _write("contradictory_suite.py",
                        "import sys\nprint('clean=False')\n")
_rec = runner.run_suite(_contradictory)
assert _rec["returncode"] == 0
assert _rec["clean"] is False
assert any(a["kind"] == "unexpected_output" for a in _rec["anomalies"])
print("contradictory_output_rejected=OK")

# --- 5. benign key=value summaries stay benign ---------------------------------

_benign = _write("benign_suite.py", "\n".join([
    "print('status=ok')", "print('exit=0')",
    "print('runtime_profile=local')", "print('profile=fast')",
    "print('DECISION RECORDED')", "print('alpha.flag=OK')",
]))
_rec = runner.run_suite(_benign)
assert _rec["returncode"] == 0
assert _rec["clean"] is True, _rec["anomalies"]
print("benign_key_value_preserved=OK")

# --- 6. missing headless signature is an anomaly --------------------------------

_fake_proc = mock.Mock(returncode=0, stdout="", stderr="")
with mock.patch("verification.runner.subprocess.run", return_value=_fake_proc):
    launch = runner.launch_runtime()
assert launch["clean"] is False, launch["anomalies"]
assert any(a["detail"] == "headless signature missing" for a in launch["anomalies"])
print("missing_headless_signature=OK")

# --- 7. malformed headless signature shape is an anomaly -----------------------

_fake_proc = mock.Mock(returncode=0, stdout="['not', 'a', 'tuple']\n", stderr="")
with mock.patch("verification.runner.subprocess.run", return_value=_fake_proc):
    launch = runner.launch_runtime()
assert launch["clean"] is False, launch["anomalies"]
assert any(a["kind"] == "unexpected_output" and "shape invalid" in a["detail"]
           for a in launch["anomalies"])
print("malformed_signature_shape=OK")

# --- 8. native and headless arms share one operation source --------------------

launch = runner.launch_runtime()
assert launch["clean"] is True, launch["anomalies"]
assert runner._signature() == (0.5, 1.0, 0.0, 4)
assert launch["signature_native"] == launch["signature_headless"]
assert launch["signature_native"] == (0.5, 1.0, 0.0, 4)
print("signature_ops_shared_and_launch_clean=OK")

# --- 9. independent reference recomputes the launch math -----------------------

assert reference.expected_signature_triple() == (0.5, 1.0, 0.0)
assert runner._signature()[:3] == reference.expected_signature_triple()
print("derived_signature_reference=OK")

# --- 10. the monitor records a nonce-anchored verdict --------------------------

monitor_nonce = "hardening-monitor-" + uuid.uuid4().hex[:8]
monitor.record_verdict(monitor_nonce, True, 3, 45)
entries = [f for f in monitor.findings()
           if f.get("run_nonce") == monitor_nonce]
assert len(entries) == 1 and entries[0]["kind"] == "external_verdict"
print("monitor_record_writes=OK")

# --- 11. a fabricated clean dict (no recorded run) cannot unlock ready ---------

stabilization.reset()
forged = {"clean": True, "source": "hardening_forged", "run_nonce": "deadbeef",
          "suite_count": 3, "ok_total": 45}
decision = stabilization.confirm(forged)
assert decision["ready_state"] == "not_ready"
assert stabilization.is_ready() is False
print("forged_external_verdict_rejected=OK")

# --- 12. a genuinely recorded clean verdict unlocks ready ----------------------

grant_nonce = "hardening-grant"
monitor.record_verdict(grant_nonce, True, 3, 45)
stabilization.reset()
report = {"clean": True, "source": "hardening_sweep", "run_nonce": grant_nonce,
          "suite_count": 3, "ok_total": 45}
decision = stabilization.confirm(report)
assert decision["ready_state"] == "ready", decision
assert stabilization.is_ready() is True
print("recorded_verdict_grants_ready=OK")

# --- 13. suite_count mismatch against the recorded run is rejected -------------

count_nonce = "hardening-suitecount"
monitor.record_verdict(count_nonce, True, 3, 45)
stabilization.reset()
decision = stabilization.confirm({"clean": True, "source": "x",
                                  "run_nonce": count_nonce,
                                  "suite_count": 2, "ok_total": 45})
assert decision["ready_state"] == "not_ready"
print("mismatched_suite_count_rejected=OK")

# --- 14. ok_total mismatch against the recorded run is rejected ----------------

ok_nonce = "hardening-oktotal"
monitor.record_verdict(ok_nonce, True, 3, 45)
stabilization.reset()
decision = stabilization.confirm({"clean": True, "source": "x",
                                  "run_nonce": ok_nonce,
                                  "suite_count": 3, "ok_total": 44})
assert decision["ready_state"] == "not_ready"
print("mismatched_ok_total_rejected=OK")

# --- 15. a stale/replayed nonce (not the newest) is rejected -------------------

old_nonce = "hardening-old"
new_nonce = "hardening-new"
monitor.record_verdict(old_nonce, True, 3, 45)
monitor.record_verdict(new_nonce, True, 3, 45)
stabilization.reset()
decision = stabilization.confirm({"clean": True, "source": "x",
                                  "run_nonce": old_nonce,
                                  "suite_count": 3, "ok_total": 45})
assert decision["ready_state"] == "not_ready", decision
print("replayed_nonce_rejected=OK")

# --- 16. an anomaly recorded for the same run invalidates it -------------------

stale_nonce = "hardening-stale"
monitor.record_verdict(stale_nonce, True, 2, 30)
monitor.record("unexpected_output", "later anomaly marks the run",
               source="test", run_nonce=stale_nonce)
stabilization.reset()
decision = stabilization.confirm({"clean": True, "source": "x",
                                  "run_nonce": stale_nonce,
                                  "suite_count": 2, "ok_total": 30})
assert decision["ready_state"] == "not_ready", decision
print("later_anomaly_invalidates_run=OK")

# --- 17. a clean verdict with zero ok evidence is rejected ---------------------

zero_nonce = "hardening-zero"
monitor.record_verdict(zero_nonce, True, 3, 0)
stabilization.reset()
decision = stabilization.confirm({"clean": True, "source": "x",
                                  "run_nonce": zero_nonce,
                                  "suite_count": 3, "ok_total": 0})
assert decision["ready_state"] == "not_ready", decision
print("ok_total_zero_rejected=OK")

# --- 18. a fresh (unverified) runtime never reports ready ----------------------

stabilization.reset()
import maya_runtime as rt  # noqa: E402
status = rt.readiness_status()
assert status["ready"] is False
assert status["status_code"] == "maya-unverified"
print("fresh_process_no_ready=OK")

# --- 19. broken intelligence stage ordering is caught --------------------------

ok, _ = readiness._check_intelligence_stage_ordering(None)
broken, _ = readiness._check_intelligence_stage_ordering(
    ("sense", "reflect", "interpret", "stabilize", "decide", "express", "log"))
assert ok is True
assert broken is False
print("broken_stage_order_caught=OK")

# --- 20. forbidden runtime imports in intelligence are caught ------------------

banned_path = _write("fake_intel_banned.py", "import random\n")
ok, _ = readiness._check_intelligence_no_runtime_imports([pathlib.Path(banned_path)])
assert ok is False

clean_path = _write("fake_intel_clean.py", "import math\n")
ok, _ = readiness._check_intelligence_no_runtime_imports([pathlib.Path(clean_path)])
assert ok is True
print("forbidden_import_caught=OK")

# --- 21. nondeterministic intelligence output is caught ------------------------

_shape = {
    "semantic": {"coherence": 0.8, "salience": 0.6},
    "emotional": {"intensity": 0.4, "arousal": 0.5, "valence": 0.6},
    "contextual": {"urgency": 0.3, "impact": 0.4, "effort": 0.5},
    "historical": {"stability": [0.5, 0.51, 0.5, 0.505, 0.5]},
    "render": {"glow": 0.6, "depth": 0.5, "thickness": 2.0},
    "reference": (0.5, 0.5, 0.5),
    "metrics": {"cpu_percent": 10, "memory_percent": 20,
                "process_count": 1, "launches": 0},
    "now": "2026-09-09T00:00:00Z",
    "sequence": 1,
    "environment": "local",
}
calls = [0]


def drifty_run(**kwargs):
    calls[0] += 1
    return calls[0]


def steady_run(**kwargs):
    return kwargs["semantic"]["coherence"]


assert readiness._check_intelligence_deterministic(drifty_run)[0] is False
assert readiness._check_intelligence_deterministic(steady_run)[0] is True
print("nondeterministic_output_caught=OK")

# --- 22. safety boundary marker is counted from real evidence ------------------

_safety = _write("safety_marker_suite.py",
                 "import sys\nprint('safety_boundary_violation')\n"
                 "raise SystemExit(2)\n")
_rec = runner.run_suite(_safety)
assert _rec["returncode"] == 2
assert any(a["kind"] == "safety_boundary_violation" for a in _rec["anomalies"])
print("safety_marker_category_counted=OK")

# --- 23. rendering anomaly marker is counted from real evidence ----------------

_rendering = _write("rendering_marker_suite.py",
                    "import sys\nprint('rendering_anomaly')\n"
                    "raise SystemExit(3)\n")
_rec = runner.run_suite(_rendering)
assert _rec["returncode"] == 3
assert any(a["kind"] == "rendering_anomaly" for a in _rec["anomalies"])
print("rendering_marker_category_counted=OK")

# --- 24. a timed-out suite is recorded and the sweep continues -----------------

_sleepy = _write("sleepy_suite.py",
                 "import time\ntime.sleep(3)\nprint('x=OK')\n")
_fast_ok = _write("fast_ok_suite.py", "print('x=OK')\n")
_result = runner.sweep(suites=(str(_sleepy), str(_fast_ok)), timeout_ms=1)
assert _result["clean"] is False
assert _result["suite_count"] == 2
assert any(any(a["kind"] == "timing_irregularity" for a in s["anomalies"])
           for s in _result["suites"])
assert any(s["clean"] for s in _result["suites"])  # later suite still ran
print("timeout_recorded_and_sweep_continues=OK")

# --- final ---------------------------------------------------------------------

print("verification_hardening=OK")