"""Shared synthetic fixtures for the Founder Origin verification suite (8N-E).

Fixtures are built in-memory only; nothing is written to disk. All digests are
computed from the serializer so a valid candidate record passes the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import sys

from maya_identity.origin import integrity


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_importable() -> None:
    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def philosophy_block(statement: str) -> dict:
    return {
        "kind": "philosophical_inspiration",
        "classification": "philosophical_inspiration",
        "statement": statement,
    }


def make_intent(status: str = "founder_confirmed") -> dict:
    block = philosophy_block(
        "Maya was created from the belief that untapped human potential exists, "
        "and that intelligence can become more meaningful when connected with human life."
    )
    block["status"] = status
    return block


def make_purpose() -> dict:
    block = philosophy_block(
        "Maya exists to benefit humanity and connect intelligence with human understanding."
    )
    block["statements"] = [
        "benefit humanity",
        "improve individual human experiences",
        "expand access to knowledge",
        "connect intelligence with human understanding",
    ]
    return block


def make_philosophy() -> dict:
    return philosophy_block(
        "Intelligence is the relationship between knowledge and the human being "
        "who experiences, interprets, and applies it."
    )


def make_principles() -> list:
    return [
        {"kind": "principle", "id": "P.01", "text": "A calm, luminous, evolving intelligence."},
        {"kind": "principle", "id": "P.02", "text": "Speaking is altering the world; false words alter it wrongly."},
        {"kind": "principle", "id": "P.03", "text": "Never manipulative, harmful, or destructive toward human wellbeing."},
    ]


def make_constraints() -> dict:
    return {
        "protection_rule": "founder_origin_protection",
        "protected_paths": ["maya_identity/metadata/origin/"],
        "founder_negative_boundary": {
            "no_harm": True,
            "no_wellbeing_violation": True,
            "no_user_ownership_override": True,
            "no_system_boundary_bypass": True,
        },
    }


def make_record(origin_version: str = "1.0.0", state: str = "DRAFT") -> dict:
    record = {
        "origin_version": origin_version,
        "schema_version": "1.0.0",
        "creation_provenance": {
            "founder": "Andy",
            "role": "Vision Holder",
            "created_at": "2026-09-12T00:00:00Z",
            "source_refs": ["MAYA_BATCH_8N_D0_FOUNDER_CORE_FINALIZATION_REPORT.md"],
        },
        "founder_confirmation": {
            "statement": "I confirm the origin intent, purpose, philosophy, principles, and constraints as authored.",
            "identity": "Andy",
            "timestamp": "2026-09-12T00:00:00Z",
            "schema_version": "1.0.0",
            "digest": "set-at-build",
        },
        "founding_intent": make_intent(),
        "founding_purpose": make_purpose(),
        "founder_philosophy": make_philosophy(),
        "core_principles": make_principles(),
        "protected_constraints": make_constraints(),
    }
    confirmation_digest = integrity.compute_confirmation_digest(record)
    record["founder_confirmation"]["digest"] = confirmation_digest
    content_digest = integrity.compute_content_digest(record)
    record["integrity_metadata"] = {
        "algorithm": "SHA-256",
        "digest": content_digest,
        "previous_digest": None,
        "state": state,
    }
    return record


def make_ledger(record: Optional[dict] = None) -> list:
    row_record = record or make_record()
    content_digest = integrity.compute_content_digest(row_record)
    row = {
        "event": "origin_record_prepared",
        "event_at": "2026-09-12T00:00:00Z",
        "previous_digest": None,
    }
    row["digest"] = integrity.row_digest_of(row)
    rows = [row]
    row_record = dict(record or make_record())
    meta = dict(record.get("integrity_metadata", {}))
    meta["previous_digest"] = rows[-1]["digest"]
    row_record["integrity_metadata"] = meta
    return rows, row_record


def current_state(record: dict) -> str:
    return record.get("integrity_metadata", {}).get("state", "DRAFT")


def copy_record(record: dict) -> dict:
    import copy

    return copy.deepcopy(record)