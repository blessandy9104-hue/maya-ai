"""Maya -- stabilization protocol (ready-state decision).

Maya does not declare readiness. Ready state is entered only when TWO
independent verification paths agree on stability:

1. External verification (OpenCode): a full test sweep and a controlled
   runtime launch, reporting no unintended or unexpected behavior.
2. Internal verification (self-check): subsystem diagnostics confirming
   deterministic math, stable world model, bounded safety, correct rendering
   cadence, coherent aligned agents, and consistent internal state.

``confirm(external_report)`` is the single entry point: it runs the internal
self-check, requires an explicit external ``clean`` verdict, and transitions
the operational state to ``ready`` only when both paths agree.
"""
from __future__ import annotations

import json
import pathlib
import time

from . import readiness

PROTOCOL_VERSION = "2.0"

READY_CONDITION = (
    "OpenCode external verification reports no unintended or unexpected behavior",
    "internal self-check reports stable, deterministic operation",
    "both verification paths agree on stability",
)

OPERATIONAL_GUARANTEES = (
    "You run smoothly because both internal and external verification confirm stability.",
    "You do not declare readiness without verification.",
    "You do not evolve yourself; you operate within the architecture provided.",
    "You maintain stability, determinism, and safety at all times.",
)

_METADATA = pathlib.Path(__file__).resolve().parent / "metadata"
_PROTOCOL_LOG = _METADATA / "stabilization_protocol.jsonl"
_VERIFICATION_LOG = _METADATA / "verification.jsonl"

_STATE = {
    "status": "stabilized_pending",
    "ready": False,
    "external": None,
    "internal": None,
    "agreed": False,
    "decided_on": None,
}

_SEQUENCE = [0]

# Per-run ephemeral authenticated-verdict key, installed by the deploy
# verifier's sweep in-process (never persisted, never logged). ``confirm``
# fails closed: without it, no external verdict -- however well formed -- can
# contribute to readiness.
_verdict_key = None


def set_verdict_key(key):
    """Install the per-run authenticated-verdict key (in-memory only)."""
    global _verdict_key
    _verdict_key = key


def _authentic_external_verdict(detail):
    """Fail-closed authentication of a recorded verdict detail.

    Requires an installed run key, the current authenticated protocol version,
    and a constant-time-verifying HMAC-SHA256 tag over the canonical record.
    Anything else -- missing key, missing tag, unknown or older protocol,
    tampered or replayed from an earlier run -- is rejected.
    """
    from verification import authenticity
    if _verdict_key is None:
        return False
    if detail.get("proto") != authenticity.VERDICT_PROTOCOL:
        return False
    if detail.get("protocol") != PROTOCOL_VERSION:
        return False
    mac = detail.get("mac")
    if not isinstance(mac, str) or not mac:
        return False
    return authenticity.verify(
        {key: value for key, value in detail.items() if key != "mac"},
        mac, _verdict_key)


def _log(entry: dict) -> None:
    _SEQUENCE[0] += 1
    _METADATA.mkdir(parents=True, exist_ok=True)
    line = dict(entry)
    line["seq"] = _SEQUENCE[0]
    line["at"] = time.time()
    with _PROTOCOL_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")


def state():
    """Current operational state (read-only copy)."""
    return {k: v for k, v in _STATE.items()}


def is_ready():
    return bool(_STATE["ready"])


def reset():
    """Return the protocol to its pre-verification state."""
    _STATE.update({
        "status": "stabilized_pending",
        "ready": False,
        "external": None,
        "internal": None,
        "agreed": False,
        "decided_on": None,
    })


def external_verification(clean, source="in-process"):
    """Record the external OpenCode verdict without deciding readiness."""
    verdict = {
        "approach": "external",
        "clean": bool(clean),
        "source": source,
    }
    _STATE["external"] = verdict
    _log({"event": "external_verification", **verdict})
    return verdict


def _read_verification_log():
    """Read the monitor's recorded findings (empty when none exist)."""
    if not _VERIFICATION_LOG.exists():
        return []
    entries = []
    try:
        with _VERIFICATION_LOG.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return entries


def _latest_external_verdict():
    """The most recent external verdict recorded by a real sweep run."""
    verdict = None
    for entry in _read_verification_log():
        if entry.get("kind") == "external_verdict":
            verdict = entry
    return verdict


def _run_has_anomalies(run_nonce):
    """True when the given run recorded any anomaly (a same-run invalidation)."""
    for entry in _read_verification_log():
        if entry.get("run_nonce") != run_nonce:
            continue
        if entry.get("kind") in ("external_verdict", "launch"):
            continue
        return True
    return False


def confirm(external_report=None):
    """Decide readiness from an external report plus the internal self-check.

    And confirms the external report carries a clean verdict that is both
    AUTHENTICATED (an HMAC-SHA256 tag valid under the current run's ephemeral
    key, over the current authenticated protocol version) and matched to the
    latest verdict actually recorded by an external sweep run (same
    ``run_nonce``, ``suite_count``, ``ok_total``, ``clean`` and evidence
    digest), requires positive evidence (``ok_total > 0``), and that run
    recorded no anomalies. A fabricated ``{"clean": True}`` dictionary, an
    unsigned or replayed record, or any byte-level edit to a signed record can
    never reach readiness. A lifecycle legacy detail is ignored rather than
    trusted.

    Raises ``ValueError`` if no explicit external verdict is supplied -- an
    unverified runtime is never declared ready.
    """
    if not isinstance(external_report, dict) or "clean" not in external_report:
        raise ValueError(
            "readiness requires an explicit external verification report "
            "with a 'clean' verdict"
        )
    verdict = _latest_external_verdict()
    valid_basis = False
    required = ("run_nonce", "suite_count", "ok_total")
    if verdict is not None and all(key in external_report for key in required):
        try:
            detail = json.loads(verdict.get("detail") or "{}")
        except ValueError:
            detail = {}
        try:
            report_ok_total = int(external_report["ok_total"])
            report_suite_count = int(external_report["suite_count"])
        except (TypeError, ValueError):
            report_ok_total = -1
            report_suite_count = -1
        matches = (
            _authentic_external_verdict(detail)
            and verdict.get("run_nonce") == external_report["run_nonce"]
            and bool(detail.get("clean")) == bool(external_report["clean"])
            and int(detail.get("suite_count", -1)) == report_suite_count
            and int(detail.get("ok_total", -1)) == report_ok_total
            and report_ok_total > 0
            and detail.get("evidence") == external_report.get("evidence")
        )
        valid_basis = bool(matches) and not _run_has_anomalies(
            external_report["run_nonce"])
    internal = readiness.self_check()
    external = external_verification(valid_basis,
                                     source=external_report.get("source", "OpenCode"))
    agreed = bool(external["clean"]) and bool(internal["stable"])
    _STATE["status"] = "ready" if agreed else "awaiting_consensus"
    _STATE["ready"] = agreed
    _STATE["internal"] = {
        "approach": "internal",
        "stable": internal["stable"],
        "anomalies": internal["anomalies"],
    }
    _STATE["agreed"] = agreed
    _STATE["decided_on"] = PROTOCOL_VERSION
    _log({
        "event": "readiness_confirmation",
        "external_clean": external["clean"],
        "internal_stable": internal["stable"],
        "agreed": agreed,
        "ready": agreed,
    })
    return {
        "protocol": PROTOCOL_VERSION,
        "external_clean": external["clean"],
        "internal_stable": internal["stable"],
        "agreed": agreed,
        "ready_state": "ready" if agreed else "not_ready",
        "status": _STATE["status"],
    }


def status():
    """Full forced-consensus report for consumers and the verification suite."""
    return {
        "protocol": PROTOCOL_VERSION,
        "ready_condition": list(READY_CONDITION),
        "operational_guarantees": list(OPERATIONAL_GUARANTEES),
        "state": state(),
        "self_check": readiness.self_check(),
    }