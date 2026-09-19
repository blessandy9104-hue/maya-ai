"""Validator architecture for Founder Origin records (8N-E).

Four independent validators (schema, provenance, philosophy isolation,
integrity) composed into a transactional pipeline. The pipeline is pure:
it never mutates persistent state, never registers digests, never stores
partial results, and aborts at the first failing stage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import integrity

STAGES = ("schema", "provenance", "isolation", "integrity")
PHILOSOPHY_FIELDS = ("founding_intent", "founding_purpose", "founder_philosophy")
P2B_TARGET_KINDS = (
    "behavior_rule",
    "capability_requirement",
    "autonomous_directive",
    "capability_permission",
    "runtime_directive",
    "execution_instruction",
)
VISION_HOLDER_ROLE = "Vision Holder"


def default_schema_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent / "metadata" / "origin" / "origin.schema.json"


def default_schema() -> dict:
    with open(default_schema_path(), "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


@dataclass(frozen=True)
class Check:
    ok: bool
    errors: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class StageResult:
    ok: bool
    stage: Optional[str]
    errors: tuple


def _fail(errors) -> Check:
    return Check(False, tuple(errors))


def _ok() -> Check:
    return Check(True, ())


def _iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_dicts(value)


def _collect_keys(node: Any, forbidden: set) -> set:
    found = set()
    for obj in _iter_dicts(node):
        found.update(set(obj.keys()) & forbidden)
    return found


def _collect_kinds(node: Any, forbidden: set) -> set:
    found = set()
    for obj in _iter_dicts(node):
        kind = obj.get("kind")
        if kind in forbidden:
            found.add(kind)
    return found


def schema_validator(record: dict, schema: Optional[dict] = None, ledger_rows: Optional[list] = None, approvals: Optional[list] = None) -> Check:
    schema = schema or default_schema()
    fields = schema.get("fields", {})
    problems = []
    known = set(fields)
    unknown = set(record) - known
    if unknown:
        problems.append(f"unknown top-level fields: {sorted(unknown)}")
    for name, spec in fields.items():
        if spec.get("required") and name not in record:
            problems.append(f"required field missing: {name}")
            continue
        value = record.get(name)
        value_type = spec.get("type")
        if value is None:
            continue
        if value_type == "object" and not isinstance(value, dict):
            problems.append(f"{name} must be an object")
            continue
        if value_type == "array" and not isinstance(value, list):
            problems.append(f"{name} must be an array")
            continue
        if value_type == "string" and not isinstance(value, str):
            problems.append(f"{name} must be a string")
            continue
        bounded = spec.get("bounded", {})
        pattern = bounded.get("pattern")
        if isinstance(value, str) and pattern and not re.fullmatch(pattern, value):
            problems.append(f"{name} violates bounded pattern")
        for subkey in spec.get("required_subkeys", []):
            if value_type == "object" and subkey not in value:
                problems.append(f"{name}.{subkey} missing")
        if value_type == "object" and spec.get("forbidden_subkeys"):
            present = sorted(set(value) & set(spec["forbidden_subkeys"]))
            if present:
                problems.append(f"{name} contains forbidden subkeys: {present}")
        if value_type == "object" and spec.get("kind"):
            if value.get("kind") != spec["kind"]:
                problems.append(f"{name}.kind must be {spec['kind']}")
        if value_type == "array" and spec.get("item_kind"):
            for item in value:
                if not isinstance(item, dict) or item.get("kind") != spec["item_kind"]:
                    problems.append(f"{name} items must have kind {spec['item_kind']}")
    enums = schema.get("enums", {})
    for field_path, allowed in enums.items():
        key_path = field_path.split(".")
        node = record
        for part in key_path:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if node is not None and node not in allowed:
            problems.append(f"{field_path} must be one of {allowed}")
    runtime_forbidden = set(schema.get("runtime_fields_forbidden_everywhere", []))
    found_runtime = _collect_keys(record, runtime_forbidden)
    if found_runtime:
        problems.append(f"runtime execution fields present: {sorted(found_runtime)}")
    kind_allowlist = set(schema.get("allowed_kinds", []))
    for obj in _iter_dicts(record):
        if "kind" in obj and obj["kind"] not in kind_allowlist:
            problems.append(f"unallowed kind: {obj['kind']}")
    return _fail(problems) if problems else _ok()


def provenance_validator(
    record: dict,
    schema: Optional[dict] = None,
    ledger_rows: Optional[list] = None,
    approvals: Optional[list] = None,
) -> Check:
    schema = schema or default_schema()
    problems = []
    confirmation = record.get("founder_confirmation", {})
    creation = record.get("creation_provenance", {})
    for key in ("statement", "identity", "timestamp", "schema_version", "digest"):
        if key not in confirmation or confirmation.get(key) in (None, ""):
            problems.append(f"founder_confirmation.{key} missing")
    if confirmation.get("schema_version") != record.get("schema_version"):
        problems.append("founder_confirmation.schema_version does not match record")
    if confirmation.get("identity") != creation.get("founder"):
        problems.append("founder_confirmation.identity differs from creation_provenance.founder")
    if creation.get("role") != VISION_HOLDER_ROLE:
        problems.append("creation_provenance.role must be Vision Holder")
    if confirmation.get("digest") and confirmation["digest"] != integrity.compute_confirmation_digest(record):
        problems.append("founder_confirmation.digest does not match record content")
    state = record.get("integrity_metadata", {}).get("state")
    if state in ("INTEGRITY_REGISTERED", "ACTIVATED") and not ledger_rows:
        problems.append("activation prerequisite: ledger record required")
    if state == "ACTIVATED" and not approvals:
        problems.append("activation prerequisite: approval policy record required")
    activation_status = record.get("integrity_metadata", {}).get("state")
    if activation_status and activation_status not in schema.get(
        "enums", {}
    ).get("integrity_metadata.state", []):
        problems.append(f"activation status is not a valid lifecycle state: {activation_status}")
    return _fail(problems) if problems else _ok()


def philosophy_isolation_validator(
    record: dict,
    schema: Optional[dict] = None,
    ledger_rows: Optional[list] = None,
    approvals: Optional[list] = None,
) -> Check:
    schema = schema or default_schema()
    forbidden = set(schema.get("philosophy_forbidden_keys", []))
    problems = []
    for field_name in PHILOSOPHY_FIELDS:
        obj = record.get(field_name)
        if not isinstance(obj, dict):
            problems.append(f"{field_name} must be an object")
            continue
        if obj.get("kind") != "philosophical_inspiration":
            problems.append(f"{field_name}.kind must be philosophical_inspiration")
        if obj.get("classification") not in schema.get(
            "enums", {}
        ).get("philosophy.classification", []):
            problems.append(f"{field_name}.classification is not an allowed philosophy classification")
        found = _collect_keys(obj, forbidden)
        if found:
            problems.append(f"{field_name} contains forbidden philosophy keys: {sorted(found)}")
        p2b = _collect_kinds(obj, set(P2B_TARGET_KINDS))
        if p2b:
            problems.append(f"{field_name} attempts philosophy-to-directive transform: {sorted(p2b)}")
    return _fail(problems) if problems else _ok()


def integrity_validator(
    record: dict,
    schema: Optional[dict] = None,
    ledger_rows: Optional[list] = None,
    approvals: Optional[list] = None,
) -> Check:
    problems = []
    ok, record_problems = integrity.verify_record_digest(record)
    if not ok:
        problems.extend(record_problems)
    ok, chain_problems = integrity.verify_record_against_chain(record, ledger_rows or [])
    if not ok:
        problems.extend(chain_problems)
    return _fail(problems) if problems else _ok()


_STAGE_VALIDATORS: dict = {
    "schema": schema_validator,
    "provenance": provenance_validator,
    "isolation": philosophy_isolation_validator,
    "integrity": integrity_validator,
}


def validate(
    record: dict,
    schema: Optional[dict] = None,
    ledger_rows: Optional[list] = None,
    approvals: Optional[list] = None,
    on_stage: Optional[Callable[[str], None]] = None,
) -> StageResult:
    schema = schema or default_schema()
    for stage in STAGES:
        if on_stage is not None:
            on_stage(stage)
        check = _STAGE_VALIDATORS[stage](
            record, schema=schema, ledger_rows=ledger_rows, approvals=approvals
        )
        if not check.ok:
            return StageResult(ok=False, stage=stage, errors=check.errors)
    return StageResult(ok=True, stage=None, errors=())


def validate_all_checks(
    record: dict,
    schema: Optional[dict] = None,
    ledger_rows: Optional[list] = None,
    approvals: Optional[list] = None,
) -> dict:
    schema = schema or default_schema()
    results = {}
    for stage in STAGES:
        check = _STAGE_VALIDATORS[stage](
            record, schema=schema, ledger_rows=ledger_rows, approvals=approvals
        )
        results[stage] = {"ok": check.ok, "errors": list(check.errors)}
    return results