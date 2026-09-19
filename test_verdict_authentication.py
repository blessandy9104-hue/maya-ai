"""Authenticated external-verdict regression suite.

Closes the local log-writer forgery path demonstrated by the negative
verification drill: an attacker who appends (or rewrites records in) the
verification journal can no longer manufacture a trustable ``external_verdict``
because ``stabilization.confirm`` now requires an HMAC-SHA256 tag valid under
the current run's ephemeral key (held only in the deploy process's memory).

Covered here, all ``=OK`` markers:

1. a genuinely recorded authenticated verdict grants ready;
2. an INDEPENDENT subprocess (stdlib ``hmac``/``hashlib`` only, never importing
   this scheme) recomputes the recorded tag and it verifies;
3. a byte-level tamper of ``ok_total`` fails closed both for the original and
   for a report rewritten to match the tampered record;
4. tampering the recorded ``clean`` state fails closed both ways;
5. altering the recorded ``run_nonce`` fails closed;
6. altering the recorded ``suite_count`` fails closed;
7. removing the recorded ``mac`` (unsigned record) fails closed;
8. forging a fresh ``external_verdict`` line with an attacker-chosen key is
   rejected under the deploy session's key (the original injection vector);
9. a verifier without a key (no authentication installed) fails closed, and a
   restored key re-accepts the still-valid verdict;
10. replaying a genuinely signed verdict from an earlier run under a new run
    key is rejected (per-run key rotation kills replay);
11. final suite marker.

Journals are isolated to a temporary directory; nothing is written to the live
metadata logs.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verification import authenticity, monitor  # noqa: E402
from maya_identity import stabilization  # noqa: E402

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="verdict_auth_"))
_LOG = _TMP / "verification.jsonl"
_PROTO = _TMP / "stabilization_protocol.jsonl"
monitor._LOG = _LOG
stabilization._VERIFICATION_LOG = _LOG
stabilization._PROTOCOL_LOG = _PROTO

_KEY = authenticity.fresh_key()
monitor.set_verdict_key(_KEY)
stabilization.set_verdict_key(_KEY)


def _make_report(nonce, clean=True, suite_count=3, ok_total=45):
    """A confirm()-shaped report carrying the per-run fields."""
    return {
        "report": "stabilization",
        "clean": clean,
        "run_nonce": nonce,
        "suite_count": suite_count,
        "ok_total": ok_total,
        "protocol": stabilization.PROTOCOL_VERSION,
        "source": "authenticity_suite",
    }


def _record(nonce, clean=True, suite_count=3, ok_total=45, evidence=None):
    """Record a genuine authenticated verdict and return a matching report."""
    monitor.record_verdict(nonce, clean, suite_count, ok_total,
                           protocol=stabilization.PROTOCOL_VERSION,
                           evidence=evidence)
    return _make_report(nonce, clean, suite_count, ok_total)


def _latest_detail():
    entries = monitor.findings()
    return json.loads(entries[-1]["detail"])


def _rewrite_latest(**changes):
    """Rewrite the journal with the newest verdict's detail fields changed."""
    lines = [json.loads(line)
             for line in _LOG.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    detail = json.loads(lines[-1]["detail"])
    detail.update(changes)
    lines[-1]["detail"] = json.dumps(detail, sort_keys=True)
    with _LOG.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(line, sort_keys=True)
                               for line in lines) + "\n")


def _expect_ready(decision, label):
    assert decision["ready_state"] == "ready", (label, decision)


stabilization.reset()
report = _record("auth-marker-01")
detail = _latest_detail()
assert detail["proto"] == authenticity.VERDICT_PROTOCOL, detail
assert detail["protocol"] == stabilization.PROTOCOL_VERSION, detail
assert isinstance(detail.get("mac"), str) and len(detail["mac"]) == 64, detail
_expect_ready(stabilization.confirm(report), "auth-marker-01")
print("authenticated_verdict_grants_ready=OK")

body = {key: value for key, value in _latest_detail().items() if key != "mac"}
code = (
    "import hashlib,hmac,json,sys;"
    "body=json.loads(sys.argv[1]);key=bytes.fromhex(sys.argv[2]);"
    "canon=json.dumps(body,sort_keys=True,separators=(',',':'),"
    "ensure_ascii=True);"
    "print(hmac.new(key,canon.encode(),hashlib.sha256).hexdigest())"
)
sub = subprocess.run(
    [sys.executable, "-c", code,
     json.dumps(body, sort_keys=True), _KEY.hex()],
    capture_output=True, text=True, timeout=30)
assert sub.returncode == 0, sub.stderr
assert sub.stdout.strip() == _latest_detail()["mac"], (
    "independent HMAC recomputation did not match the recorded tag")
print("independent_hmac_verifies=OK")

stabilization.reset()
report = _record("auth-marker-03")
_rewrite_latest(ok_total=44)
assert stabilization.confirm(report)["ready_state"] == "not_ready", report
assert stabilization.confirm(_make_report(
    "auth-marker-03", ok_total=44))["ready_state"] == "not_ready"
print("tampered_verdict_rejected=OK")

stabilization.reset()
report = _record("auth-marker-04", clean=True)
_rewrite_latest(clean=False)
assert stabilization.confirm(report)["ready_state"] == "not_ready", report
assert stabilization.confirm(_make_report(
    "auth-marker-04", clean=False))["ready_state"] == "not_ready"
print("altered_clean_state_rejected=OK")

stabilization.reset()
report = _record("auth-marker-05")
_rewrite_latest(run_nonce="auth-marker-05-changed")
assert stabilization.confirm(report)["ready_state"] == "not_ready", report
print("altered_run_nonce_rejected=OK")

stabilization.reset()
report = _record("auth-marker-06")
_rewrite_latest(suite_count=5)
assert stabilization.confirm(report)["ready_state"] == "not_ready", report
assert stabilization.confirm(_make_report(
    "auth-marker-06", suite_count=5))["ready_state"] == "not_ready"
print("altered_suite_count_rejected=OK")

stabilization.reset()
report = _record("auth-marker-07")
_rewrite_latest(mac=None)
assert stabilization.confirm(report)["ready_state"] == "not_ready", report
print("missing_mac_fail_closed=OK")

stabilization.reset()
evil_key = authenticity.fresh_key()
forged = {
    "proto": authenticity.VERDICT_PROTOCOL,
    "protocol": stabilization.PROTOCOL_VERSION,
    "run_nonce": "auth-forged-injected",
    "clean": True,
    "suite_count": 3,
    "ok_total": 45,
    "evidence": None,
}
forged["mac"] = authenticity.sign(forged, evil_key)
monitor.record("external_verdict", json.dumps(forged, sort_keys=True),
               source="attacker", run_nonce="auth-forged-injected")
assert stabilization.confirm(
    _make_report("auth-forged-injected"))["ready_state"] == "not_ready"
print("forged_verdict_line_rejected=OK")

stabilization.reset()
report = _record("auth-marker-09")
_expect_ready(stabilization.confirm(report), "auth-marker-09-first")
stabilization.set_verdict_key(None)
assert stabilization.confirm(report)["ready_state"] == "not_ready", report
stabilization.set_verdict_key(_KEY)
_expect_ready(stabilization.confirm(report), "auth-marker-09-restored")
print("missing_authentication_fail_closed=OK")

key_a = authenticity.fresh_key()
key_b = authenticity.fresh_key()
monitor.set_verdict_key(key_a)
stabilization.set_verdict_key(key_a)
monitor.record_verdict("auth-replay-run-a", True, 3, 45,
                       protocol=stabilization.PROTOCOL_VERSION, evidence=None)
replayed_line = _LOG.read_text(encoding="utf-8").splitlines()[-1]
monitor.set_verdict_key(key_b)
stabilization.set_verdict_key(key_b)
with _LOG.open("a", encoding="utf-8") as handle:
    handle.write(replayed_line + "\n")
stabilization.reset()
assert stabilization.confirm(
    _make_report("auth-replay-run-a"))["ready_state"] == "not_ready"
monitor.set_verdict_key(_KEY)
stabilization.set_verdict_key(_KEY)
print("replayed_old_verdict_rejected_under_new_run_key=OK")

print("suite_verdict_authentication=OK")