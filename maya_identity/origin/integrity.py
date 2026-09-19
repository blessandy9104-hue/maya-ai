"""Integrity layer for Founder Origin records (8N-E).

Digest and lineage helpers. The record digest covers the record's content
fields (everything except ``integrity_metadata``) so the digest is not
self-referential. Ledger row digests likewise cover row content minus the
row's own ``digest`` key.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from .serializer import canonical_bytes

DIGEST_ALGORITHM = "SHA-256"


def digest_of_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def content_bytes(record: dict) -> bytes:
    content = {k: v for k, v in record.items() if k != "integrity_metadata"}
    return canonical_bytes(content)


def compute_content_digest(record: dict) -> str:
    return digest_of_bytes(content_bytes(record))


def compute_confirmation_digest(record: dict) -> str:
    content = {k: v for k, v in record.items() if k != "integrity_metadata"}
    confirmation = record.get("founder_confirmation")
    if isinstance(confirmation, dict):
        shadow = dict(confirmation)
        shadow["digest"] = ""
        content["founder_confirmation"] = shadow
    return digest_of_bytes(canonical_bytes(content))


def row_content_bytes(row: dict) -> bytes:
    content = {k: v for k, v in row.items() if k != "digest"}
    return canonical_bytes(content)


def row_digest_of(row: dict) -> str:
    return digest_of_bytes(row_content_bytes(row))


def previous_digest_from(ledger_rows: Optional[list]) -> Optional[str]:
    if not ledger_rows:
        return None
    last = ledger_rows[-1]
    return last.get("integrity_digest") or last.get("digest")


def verify_chain(ledger_rows: list) -> tuple:
    problems = []
    for index, row in enumerate(ledger_rows):
        expected = previous_digest_from(ledger_rows[:index])
        actual = row.get("previous_digest")
        if (expected is None) != (actual is None):
            problems.append(f"row {index}: previous_digest presence mismatch")
            continue
        if expected is not None and actual != expected:
            problems.append(f"row {index}: previous_digest chain break")
    return (not problems), problems


def verify_record_digest(record: dict) -> tuple:
    meta = record.get("integrity_metadata", {})
    problems = []
    if meta.get("algorithm") != DIGEST_ALGORITHM:
        problems.append("integrity_metadata.algorithm must be SHA-256")
    if meta.get("digest") != compute_content_digest(record):
        problems.append("integrity_metadata.digest does not match canonical content bytes")
    return (not problems), problems


def verify_record_against_chain(record: dict, ledger_rows: Optional[list]) -> tuple:
    problems = []
    ok, chain_problems = verify_chain(ledger_rows or [])
    if not ok:
        problems.extend(chain_problems)
    expected_previous = previous_digest_from(ledger_rows or [])
    actual_previous = record.get("integrity_metadata", {}).get("previous_digest")
    if actual_previous != expected_previous:
        problems.append("record previous_digest does not match ledger head")
    ok, digest_problems = verify_record_digest(record)
    if not ok:
        problems.extend(digest_problems)
    return (not problems), problems