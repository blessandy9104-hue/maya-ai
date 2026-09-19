"""Verification monitor: records unintended or unexpected behavior.

Findings are appended to ``metadata/verification.jsonl`` for the record,
each one tied to the external sweep's ``run_nonce``. The external verdict is
recorded as an ``external_verdict`` entry carrying the same ``run_nonce``
plus ``clean``/``suite_count``/``ok_total``, so the readiness decision can
validate a report against the real run (never against a fabricated dict).
"""
from __future__ import annotations

import json
import pathlib
import time

from . import authenticity

_METADATA = pathlib.Path(__file__).resolve().parent.parent / "maya_identity" / "metadata"
_LOG = _METADATA / "verification.jsonl"

# Per-run ephemeral authenticating key. Supplied by the deploy verifier's
# sweep (``secrets.token_bytes``); held only in process memory, never written
# to the journal. When unset, verdicts are recorded unsigned and are never
# trusted by ``stabilization.confirm``.
_verdict_key = None


def set_verdict_key(key):
    """Install the per-run authenticated-verdict key (in-memory only)."""
    global _verdict_key
    _verdict_key = key

FINDING_TYPES = (
    "unintended_behavior",
    "unexpected_output",
    "instability_drift",
    "rendering_anomaly",
    "safety_boundary_violation",
    "timing_irregularity",
    "launch",
    "external_verdict",
)


def record(kind, detail, source="external", run_nonce=None):
    if kind not in FINDING_TYPES:
        raise ValueError(f"unknown finding type: {kind!r}")
    _METADATA.mkdir(parents=True, exist_ok=True)
    entry = {
        "kind": kind,
        "detail": detail,
        "source": source,
        "run_nonce": run_nonce,
        "at": time.time(),
    }
    with _LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


def record_verdict(run_nonce, clean, suite_count, ok_total, protocol=None,
                   evidence=None):
    """Record the single authenticated external verdict for one sweep run.

    The recorded detail binds an authenticated protocol version (via
    HMAC-SHA256 under the ephemeral run key, when one is installed) to the
    ``run_nonce``, ``clean``/``suite_count``/``ok_total`` verdict fields and to
    the digest of the per-suite evidence summary. Without a key the record is
    written unsigned (``mac: None``) and is never trusted.
    """
    if protocol is None:
        from maya_identity import stabilization as _stabilization
        protocol = _stabilization.PROTOCOL_VERSION
    payload = {
        "proto": authenticity.VERDICT_PROTOCOL,
        "protocol": protocol,
        "run_nonce": run_nonce,
        "clean": bool(clean),
        "suite_count": int(suite_count),
        "ok_total": int(ok_total),
        "evidence": authenticity.evidence_digest(evidence),
    }
    signed = dict(payload)
    signed["mac"] = (authenticity.sign(payload, _verdict_key)
                     if _verdict_key is not None else None)
    return record("external_verdict", json.dumps(signed, sort_keys=True),
                  source="external", run_nonce=run_nonce)


def findings():
    if not _LOG.exists():
        return []
    entries = []
    with _LOG.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def anomalies():
    return [e for e in findings()
            if e["kind"] not in ("launch", "external_verdict")]