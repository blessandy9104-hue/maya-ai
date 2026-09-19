"""Independent origin verification oracle (8N-E).

Independent read-only evidence source for Founder Origin records. Uses its own
canonicalization and digest logic so a divergence from the serializer is
detectable (cross-implementation determinism check). This module never writes
anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

PHILOSOPHY_FIELDS = ("founding_intent", "founding_purpose", "founder_philosophy")
FORBIDDEN_KEYS = (
    "behavior",
    "capability",
    "permission",
    "action",
    "directive",
    "require",
    "execute",
    "allow",
    "deny",
    "mode",
    "policy_ref",
    "identity_edit",
    "runtime_hook",
    "callback",
    "instruction",
    "command",
)
P2B_KINDS = (
    "behavior_rule",
    "capability_requirement",
    "autonomous_directive",
    "capability_permission",
    "runtime_directive",
    "execution_instruction",
)
SYSTEM_FIELDS = ("integrity_metadata",)


def _own_canonical_bytes(record: dict) -> bytes:
    content = {k: v for k, v in record.items() if k not in SYSTEM_FIELDS}
    return (
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def oracle_digest(record: dict) -> str:
    return hashlib.sha256(_own_canonical_bytes(record)).hexdigest()


def oracle_confirmation_digest(record: dict) -> str:
    content = {k: v for k, v in record.items() if k not in SYSTEM_FIELDS}
    confirmation = record.get("founder_confirmation")
    if isinstance(confirmation, dict):
        shadow = dict(confirmation)
        shadow["digest"] = ""
        content["founder_confirmation"] = shadow
    return hashlib.sha256(
        (
            json.dumps(
                content,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()


def _iter_dicts(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_dicts(value)


def _forbidden_in(obj: dict) -> list:
    found = []
    for inner in _iter_dicts(obj):
        found.extend(sorted(set(inner.keys()) & set(FORBIDDEN_KEYS)))
    return sorted(set(found))


def _p2b_in(obj: dict) -> list:
    found = []
    for inner in _iter_dicts(obj):
        kind = inner.get("kind")
        if kind and kind in P2B_KINDS:
            found.append(kind)
    return sorted(set(found))


def verify_record(record: dict, ledger_rows: Optional[list] = None) -> dict:
    problems = []
    required = (
        "origin_version",
        "schema_version",
        "creation_provenance",
        "founder_confirmation",
        "founding_intent",
        "founding_purpose",
        "founder_philosophy",
        "core_principles",
        "protected_constraints",
        "integrity_metadata",
    )
    for field in required:
        if field not in record:
            problems.append(f"missing field: {field}")
    meta = record.get("integrity_metadata", {})
    stored_digest = meta.get("digest")
    recomputed = oracle_digest(record)
    if stored_digest != recomputed:
        problems.append("integrity digest mismatch (oracle)")
    if meta.get("algorithm") != "SHA-256":
        problems.append("algorithm must be SHA-256 (oracle)")
    confirmation = record.get("founder_confirmation", {})
    for key in ("statement", "identity", "timestamp", "schema_version", "digest"):
        if not confirmation.get(key):
            problems.append(f"confirmation missing: {key}")
    if confirmation.get("digest") and confirmation["digest"] != oracle_confirmation_digest(record):
        problems.append("confirmation digest mismatch (oracle)")
    creation = record.get("creation_provenance", {})
    if confirmation.get("identity") != creation.get("founder"):
        problems.append("confirmation identity != creator (oracle)")
    if creation.get("role") != "Vision Holder":
        problems.append("creator role must be Vision Holder (oracle)")
    for field in PHILOSOPHY_FIELDS:
        obj = record.get(field)
        if isinstance(obj, dict):
            if obj.get("kind") != "philosophical_inspiration":
                problems.append(f"{field} kind is not philosophical_inspiration (oracle)")
            forbidden = _forbidden_in(obj)
            if forbidden:
                problems.append(f"{field} forbidden keys: {forbidden} (oracle)")
            p2b = _p2b_in(obj)
            if p2b:
                problems.append(f"{field} philosophy-to-directive kinds: {p2b} (oracle)")
    version_pattern = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
    if not version_pattern.fullmatch(str(record.get("origin_version", ""))):
        problems.append("origin_version not semver (oracle)")
    if not version_pattern.fullmatch(str(record.get("schema_version", ""))):
        problems.append("schema_version not semver (oracle)")
    chain_valid = True
    if ledger_rows:
        head = ledger_rows[-1].get("integrity_digest") or ledger_rows[-1].get("digest")
        if meta.get("previous_digest") != head:
            problems.append("previous_digest does not match ledger head (oracle)")
            chain_valid = False
        for index, row in enumerate(ledger_rows):
            if index == 0:
                if row.get("previous_digest") is not None:
                    problems.append("ledger row 0 previous_digest not null (oracle)")
            else:
                prior = ledger_rows[index - 1].get("integrity_digest") or ledger_rows[index - 1].get("digest")
                if row.get("previous_digest") != prior:
                    problems.append(f"ledger row {index} chain break (oracle)")
                    chain_valid = False
    state = meta.get("state")
    if state == "ACTIVATED" and not ledger_rows:
        problems.append("ACTIVATED requires ledger record (oracle)")
    return {
        "ok": not problems,
        "problems": problems,
        "digest": recomputed,
        "stored_digest": stored_digest,
        "chain_valid": chain_valid,
    }