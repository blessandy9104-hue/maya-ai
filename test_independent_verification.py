"""Regression tests for independent external-source verification.

Each marker is one intentional assertion group: cross-source consensus,
disagreement and fail-closed behavior, static forbidden-import detection, the
external oracle against a deliberately altered implementation, and the rule
that Maya's own ready claim can never be the proof. Exactly 10 markers.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verification import independent  # noqa: E402


def _arm(source, result="pass", sig=(0.5, 1.0, 0.0, 4),
         oracle=(0.5, 1.0, 0.0), ok_count=10, suite_exit=0, optional=False):
    observed = {
        "signatures": list(sig) if isinstance(sig, tuple) else sig,
        "oracle": list(oracle) if isinstance(oracle, tuple) else oracle,
        "suite_results": {"test_readiness.py": {
            "ok_labels": ok_count, "returncode": suite_exit}},
    }
    return {
        "source": source,
        "identity": f"{source} @ test",
        "tool_version": "0",
        "command": ["<test>"],
        "at": "test",
        "exit_code": 0,
        "observed": observed,
        "anomalies": [],
        "result": result,
        "optional": optional,
    }


# --- two agreeing external sources reach consensus ------------------------

sources = [
    _arm("python-interpreter"),
    _arm("python-interpreter"),
    _arm("powershell", ok_count=10, suite_exit=0),
]
result = independent.consensus(sources)
assert result["consensus"] is True, result
assert result["cross_agreement"] is True
assert result["disagreements"] == []
assert all(s["result"] == "pass" for s in result["sources"])
print("consensus_two_agreeing_sources=OK")

# --- one source disagrees -> no consensus -----------------------------------

sources = [
    _arm("python-interpreter"),
    _arm("python-interpreter", sig=(0.5, 1.0, 0.0, 5)),
    _arm("powershell", ok_count=10, suite_exit=0),
]
result = independent.consensus(sources)
assert result["consensus"] is False
assert result["cross_agreement"] is False
assert result["disagreements"], result
print("one_source_disagrees_no_consensus=OK")

# --- optional unavailable source: recorded, never success -------------------

sources = [
    _arm("python-interpreter"),
    _arm("powershell", ok_count=10, suite_exit=0),
    _arm("cmd", result="unavailable", optional=True),
]
result = independent.consensus(sources)
assert result["consensus"] is True, result  # optional absence does not fail
assert "cmd" in result["optional_unavailable"]
assert "cmd" not in result["passing_sources"]
assert [s for s in sources if s["source"] == "cmd"][0]["result"] == "unavailable"
print("unavailable_optional_not_success=OK")

# --- a REQUIRED unavailable source fails closed -----------------------------

sources = [
    _arm("python-interpreter"),
    _arm("python-interpreter", result="unavailable"),
    _arm("powershell", ok_count=10, suite_exit=0),
]
result = independent.consensus(sources)
assert result["consensus"] is False
assert result["required_unavailable"], result
print("unavailable_required_fails_closed=OK")

# --- static scan catches a forbidden import -----------------------------------

tmp = pathlib.Path(tempfile.mkdtemp(prefix="static_scan_"))
bad = tmp / "fake_intel_bad.py"
bad.write_text("import random\n", encoding="utf-8")
good = tmp / "fake_intel_good.py"
good.write_text("import math\n", encoding="utf-8")
ok, reports = independent.scan_forbidden_imports([bad, good])
assert ok is False
assert any("random" in report for report in reports)
ok, reports = independent.scan_forbidden_imports([good])
assert ok is True and reports == []
print("static_scan_catches_forbidden_import=OK")

# --- the mathematical oracle rejects an altered implementation ---------------

sources = [
    _arm("python-interpreter"),
    _arm("python-interpreter", sig=(0.4, 1.0, 0.0, 4)),
    _arm("powershell", ok_count=10, suite_exit=0),
]
result = independent.consensus(sources)
assert result["consensus"] is False  # all "pass", but oracle disagrees
assert result["oracle_ok"] is False, result
print("oracle_rejects_altered_implementation=OK")

# --- Maya's own ready claim alone is never proof -----------------------------

decision = independent.final_verdict(True, {"consensus": False})
assert decision["verdict"] == "NOT READY"
assert decision["maya_reports_ready"] is True
assert decision["independent_consensus"] is False
assert "disagrees" in decision["message"]
print("ready_string_alone_is_not_proof=OK")

# --- consensus alone cannot override a non-ready Maya ------------------------

decision = independent.final_verdict(False, {"consensus": True})
assert decision["verdict"] == "NOT READY"
assert decision["maya_reports_ready"] is False
assert decision["independent_consensus"] is True
print("consensus_alone_is_not_proof=OK")

# --- audit records are observable and secret-free ----------------------------

audit_path = pathlib.Path(tempfile.mkdtemp(prefix="audit_")) / "audit.jsonl"
run_record = {"kind": "consensus", "consensus": True, "sources": [
    {"source": "python-interpreter", "identity": "py",
     "tool_version": "3.14", "command": ["python", "--version"],
     "at": "2026-09-09T00:00:00+00:00", "exit_code": 0,
     "observed": {"ok": True}, "anomalies": [], "result": "pass"},
], "at": "2026-09-09T00:00:00+00:00"}
independent._write_audit([run_record], path=audit_path)
lines = [json.loads(line) for line in
         audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
assert lines and lines[0]["kind"] == "consensus"
source = lines[0]["sources"][0]
for field in ("source", "identity", "tool_version", "command", "at",
              "exit_code", "observed", "anomalies", "result"):
    assert field in source, field
serialized = audit_path.read_text(encoding="utf-8").lower()
assert "password" not in serialized and "secret" not in serialized
assert "token" not in serialized
print("audit_record_observable_and_secret_free=OK")

# --- final ---------------------------------------------------------------------

print("independent_verification_suite=OK")