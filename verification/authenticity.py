"""Authenticated external-verdict records.

Protects the on-disk verification journal (``maya_identity/metadata/
verification.jsonl``) against the local log-writer forgery path demonstrated by
the negative verification drill: an attacker who can append (or rewrite)
``external_verdict`` records must now produce a valid HMAC-SHA256 tag under the
current run's key, which exists only in the deploy process's memory.

Threat model (documented honestly):

- We do NOT persist a secret. A persistent local secret would be readable by
  the very local writer we are defending against, so it would be theater.
- Each deploy run mints a fresh 32-byte key with ``secrets.token_bytes`` inside
  ``verification.sweep``. The key is held only in that process's memory, never
  written to disk (including the journal), never logged, and never passed to a
  subprocess. It lives for the few instants between recording the verdict and
  confirming it, in the same process.
- Consequences: a log writer without the run key cannot craft a verdict whose
  tag verifies; a previously valid verdict from an earlier run cannot be
  replayed because its tag was computed under a key that no longer exists; any
  byte-level edit to a signed record invalidates its tag and fails closed.

Residual (unchanged) limits, out of scope for a local record: an attacker who
can modify the verifier itself, read deploy-process memory, or re-run a sweep
against an already-tampered tree controls the process; a fully remote verifier
would be required to lift those. Deleting/truncating historical records does
not manufacture a clean current verdict because readiness always re-keys on the
current run's freshly signed verdict and its per-run anomaly set.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

VERDICT_PROTOCOL = 2  # authenticated external-verdict record


def canonical(record):
    """Deterministic canonical JSON (sorted keys, compact separators)."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def sign(record, key):
    """HMAC-SHA256 tag (hex) over ``canonical(record)`` under ``key``."""
    return hmac.new(key, canonical(record).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def verify(record, mac, key):
    """Constant-time tag verification; anything malformed is a mismatch."""
    if not isinstance(mac, str) or not mac:
        return False
    try:
        expected = sign(record, key)
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, mac)


def fresh_key():
    """One ephemeral per-run authenticating key (never persists)."""
    return secrets.token_bytes(32)


def evidence_digest(evidence):
    """SHA-256 of the canonical per-suite evidence summary (None stays None)."""
    if evidence is None:
        return None
    return hashlib.sha256(canonical(evidence).encode("utf-8")).hexdigest()