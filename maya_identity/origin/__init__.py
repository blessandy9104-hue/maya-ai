"""Founder Origin facade (8N-E).

Read-only interface exposing verification, status, and lineage information.
No write API. No runtime decision input. No philosophy content surface.
Runtime behavior modules must not import this package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .activation import STATES, AdvanceResult, advance, content_fingerprint, next_states
from .activation import DRAFT_STATE as _DRAFT
from .activation import ACTIVATED_STATE as _ACTIVATED
from .integrity import DIGEST_ALGORITHM, compute_content_digest, previous_digest_from, verify_chain, verify_record_digest
from .serializer import canonical_bytes, canonical_text
from .validator import STAGES, StageResult, default_schema, default_schema_path, validate, validate_all_checks

SCHEMA_PATH: Path = default_schema_path()


def verify(record: dict, ledger_rows: Optional[list] = None, approvals: Optional[list] = None) -> dict:
    schema = default_schema()
    stage_result = validate(record, schema=schema, ledger_rows=ledger_rows, approvals=approvals)
    digest_ok, digest_problems = verify_record_digest(record)
    chain_ok, chain_problems = verify_chain(ledger_rows or [])
    previous = previous_digest_from(ledger_rows or [])
    fingerprint = content_fingerprint(record)
    previous_match = record.get("integrity_metadata", {}).get("previous_digest") == previous
    return {
        "ok": stage_result.ok and digest_ok and chain_ok and previous_match,
        "state": record.get("integrity_metadata", {}).get("state", _DRAFT),
        "fingerprint": fingerprint,
        "stage_error": {"stage": stage_result.stage, "errors": list(stage_result.errors)} if not stage_result.ok else None,
        "digest_problems": digest_problems,
        "chain_problems": chain_problems,
        "previous_match": previous_match,
    }


def status_of(record: dict) -> dict:
    meta = record.get("integrity_metadata", {})
    state = meta.get("state", _DRAFT)
    return {
        "state": state,
        "activation_candidate": state == _ACTIVATED,
        "next_states": list(next_states(state)),
    }


def lineage_info(ledger_rows: list) -> dict:
    ok, problems = verify_chain(ledger_rows)
    return {
        "chain_valid": ok,
        "problems": problems,
        "row_count": len(ledger_rows),
        "head_digest": previous_digest_from(ledger_rows),
    }


__all__ = [
    "verify",
    "status_of",
    "lineage_info",
    "advance",
    "next_states",
    "STATES",
    "default_schema",
    "default_schema_path",
    "SCHEMA_PATH",
    "StageResult",
    "AdvanceResult",
    "content_fingerprint",
    "canonical_bytes",
    "canonical_text",
    "compute_content_digest",
    "DIGEST_ALGORITHM",
    "verify_record_digest",
    "verify_chain",
    "validate",
    "validate_all_checks",
]