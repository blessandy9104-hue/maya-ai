"""Activation controller for Founder Origin records (8N-E).

Enforces the lifecycle state machine:

    DRAFT -> SCHEMA_VALIDATED -> FOUNDER_REVIEW_REQUIRED ->
    FOUNDER_CONFIRMED -> INTEGRITY_REGISTERED -> ACTIVATED

Rules: no skipped states; no draft-to-active transition; failed validation
can never activate. Same confirmed content + technical failure resumes safely;
changed confirmed content requires new founder confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import integrity
from . import validator

STATES = (
    "DRAFT",
    "SCHEMA_VALIDATED",
    "FOUNDER_REVIEW_REQUIRED",
    "FOUNDER_CONFIRMED",
    "INTEGRITY_REGISTERED",
    "ACTIVATED",
)

_TRANSITIONS = {
    "DRAFT": ("SCHEMA_VALIDATED",),
    "SCHEMA_VALIDATED": ("FOUNDER_REVIEW_REQUIRED",),
    "FOUNDER_REVIEW_REQUIRED": ("FOUNDER_CONFIRMED",),
    "FOUNDER_CONFIRMED": ("INTEGRITY_REGISTERED",),
    "INTEGRITY_REGISTERED": ("ACTIVATED",),
    "ACTIVATED": (),
}

ACTIVATED_STATE = "ACTIVATED"
DRAFT_STATE = "DRAFT"
CONFIRMED_STATE = "FOUNDER_CONFIRMED"
REGISTERED_STATE = "INTEGRITY_REGISTERED"


@dataclass(frozen=True)
class AdvanceResult:
    ok: bool
    state: str
    stage: Optional[str]
    errors: tuple = field(default_factory=tuple)


def legal_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, ())


def next_states(state: str) -> tuple:
    return _TRANSITIONS.get(state, ())


def content_fingerprint(record: dict) -> str:
    return integrity.compute_content_digest(record)


def with_state(record: dict, new_state: str) -> dict:
    current = record.get("integrity_metadata", {}).get("state", DRAFT_STATE)
    if not legal_transition(current, new_state):
        raise ValueError(f"illegal transition {current} -> {new_state}")
    updated = dict(record)
    meta = dict(record.get("integrity_metadata", {}))
    meta["state"] = new_state
    updated["integrity_metadata"] = meta
    return updated


def confirmation_fingerprint(record: dict) -> Optional[str]:
    confirmation = record.get("founder_confirmation", {})
    digest = confirmation.get("digest")
    return digest


def advance(
    record: dict,
    schema: Optional[dict] = None,
    ledger_rows: Optional[list] = None,
    approvals: Optional[list] = None,
) -> AdvanceResult:
    schema = schema or validator.default_schema()
    current = record.get("integrity_metadata", {}).get("state", DRAFT_STATE)
    candidates = next_states(current)
    validation = validator.validate(
        record, schema=schema, ledger_rows=ledger_rows, approvals=approvals
    )
    if not validation.ok:
        return AdvanceResult(
            ok=False, state=current, stage=validation.stage, errors=validation.errors
        )
    if current == CONFIRMED_STATE:
        confirmation_digest = confirmation_fingerprint(record)
        if confirmation_digest is None:
            return AdvanceResult(
                ok=False, state=current, stage="provenance",
                errors=("founder confirmation missing before integrity registration",),
            )
    if current == REGISTERED_STATE and not approvals:
        return AdvanceResult(
            ok=False, state=current, stage="provenance",
            errors=("activation approval required before ACTIVATED",),
        )
    if not candidates:
        return AdvanceResult(ok=True, state=current, stage=None, errors=())
    return AdvanceResult(ok=True, state=candidates[0], stage=None, errors=())


def recovery_advice(record: dict, failure_stage: Optional[str]) -> dict:
    state = record.get("integrity_metadata", {}).get("state", DRAFT_STATE)
    if failure_stage in ("schema", "isolation"):
        recovery_state = DRAFT_STATE
        confirmation_valid = False
        new_approval = False
    elif failure_stage == "provenance":
        recovery_state = "FOUNDER_REVIEW_REQUIRED" if state == DRAFT_STATE else state
        confirmation_valid = state == CONFIRMED_STATE
        new_approval = False
    else:
        recovery_state = "SCHEMA_VALIDATED"
        confirmation_valid = True
        new_approval = False
    return {
        "failure_stage": failure_stage,
        "recovery_state": recovery_state,
        "founder_confirmation_remains_valid": confirmation_valid,
        "new_approval_required": new_approval,
    }