"""Identity evolution rollback DESIGN SUPPORT (MAYA BATCH 8J-A).

Read-only planning only. This module NEVER writes, deletes, or activates an
identity change; autonomous rollback is explicitly NOT implemented. Activation
of any rollback requires operator approval plus the canonical validations of
the identity protection rule.

Mechanism (identity change lifecycle):
    identity change
        -> version record (append-only metadata/identity_versions.jsonl)
        -> validation      (run_canonical_checks / consistency rules)
        -> approval        (operator identity review; protection_rule)
        -> activation      (bounded evolution / finalize_canonical_face)
        -> rollback capability   (THIS MODULE: prepare a rollback PLAN only)

Contract
    - ``available_rollback_targets()`` -- past, non-current version records
      from the identity evolution journal (sorted oldest -> newest).
    - ``plan_identity_rollback()`` -- a deterministic, read-only rollback
      PLAN. The plan states exactly what a future, operator-initiated
      rollback WOULD do; nothing here executes it. Every plan carries
      ``autonomous=False``, ``approval_required=True`` and the protected
      paths that a rollback must never bypass.

Determinism: no randomness, no wall-clock, no network, no writes.
"""
from __future__ import annotations

from . import identity as _identity

ROLLBACK_PROTOCOL = "maya.identity_rollback.plan.v1"
PLAN_VERSION = 1

PROTECTED_PATHS = ("geometry/", "identity.json", "avatar/")

_VALIDATION_REQUIRED = (
    "run_canonical_checks",
    "identity_consistency",
    "consistency_rules",
)

_ACTIVATION_STEPS = (
    "operator issues rollback request for the target version record",
    "validation: run_canonical_checks() and identity consistency against the"
    " target version",
    "approval: operator identity review (protection_rule); no autonomous"
    " rollback is permitted",
    "restore the materialized assets recorded for the target face_version in"
    " avatar/ (a placeholder version has no materialized assets)",
    "write an append-only event=identity_rollback record into"
    " metadata/identity_versions.jsonl (the previous activation is preserved,"
    " never overwritten)",
    "re-run canonical checks and activate the restored version with a version"
    " increment",
)


def _load_journal():
    import json

    lines = []
    if _identity.VERSIONS_LOG.exists():
        lines = _identity.VERSIONS_LOG.read_text(encoding="utf-8").splitlines()
    records = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except Exception:
            continue
    return records


def _snapshot(record):
    keys = (
        "event", "identity_version", "face_version", "geometry_version",
        "date", "timestamp", "created_by", "canonical", "validation",
        "reason", "change", "change_kind",
    )
    return {key: record.get(key) for key in keys if key in record}


def available_rollback_targets():
    """Past, non-current identity version records (read-only).

    The current identity version is excluded, so only versions that could
    actually be rolled back to are returned.
    """
    current_face = _identity.identity_version()[1]
    records = _load_journal()
    targets = [r for r in records
               if r.get("face_version") != current_face]
    return [_snapshot(r) for r in targets]


def plan_identity_rollback(target_record):
    """Deterministic, read-only rollback PLAN for a prior version record.

    ``target_record`` must be one of the snapshots returned by
    ``available_rollback_targets()``. Passing the current identity version (or
    an unknown record) raises ``ValueError``. This function performs no writes.
    """
    targets = available_rollback_targets()
    if target_record not in targets:
        raise ValueError(
            "target is not a prior identity version record "
            "(current versions cannot be rolled back to themselves)")
    current_versions = {
        "identity_version": _identity.identity_version()[0],
        "face_version": _identity.identity_version()[1],
    }
    target = dict(target_record)
    affected = [
        key for key in ("identity_version", "face_version", "geometry_version")
        if key in target
    ]
    affected += ["avatar/", "configuration/appearance.json",
                 "metadata/identity_versions.jsonl"]
    return {
        "state": "prepared",
        "executed": False,
        "autonomous": False,
        "approval_required": True,
        "approval_role": "operator identity review",
        "protocol": ROLLBACK_PROTOCOL,
        "plan_version": PLAN_VERSION,
        "current_versions": current_versions,
        "target_record": target,
        "affected_fields": affected,
        "validation_required": list(_VALIDATION_REQUIRED),
        "protected_paths": list(PROTECTED_PATHS),
        "version_increment_required": True,
        "activation_steps": list(_ACTIVATION_STEPS),
        "note": (
            "Design support only: this plan describes an operator-initiated "
            "rollback. No autonomous rollback is implemented or permitted."
        ),
    }


__all__ = (
    "ROLLBACK_PROTOCOL",
    "PLAN_VERSION",
    "PROTECTED_PATHS",
    "available_rollback_targets",
    "plan_identity_rollback",
)