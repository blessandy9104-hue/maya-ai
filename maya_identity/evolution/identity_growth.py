"""Controlled identity evolution system.

Maya may improve presentation quality without randomly changing appearance.
Every recorded change requires a version, reason, timestamp and validation
state, and is stored in metadata/identity_versions.jsonl.

This system never writes geometry/ or identity.json on its own — evolution is
controlled and reviewed, never automatic.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .. import identity as _identity


def _load_rules(rules_path=None) -> dict:
    if rules_path is not None:
        try:
            return json.loads(Path(rules_path).read_text(encoding="utf-8"))
        except Exception:
            return {}
    return _identity.load_engine_config("evolution")


def _clean(value) -> str:
    return "" if value is None else str(value)


def _log_has_version(path: Path, version: str) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("version") == str(version):
            return True
    return False


class IdentityGrowth:
    def __init__(self, rules=None, log_path=None):
        self.rules = rules if rules is not None else _load_rules()
        self.log_path = Path(log_path) if log_path else _identity.VERSIONS_LOG

    def allowed_kinds(self):
        return set(self.rules.get("allowed", []))

    def forbidden_kinds(self):
        return set(self.rules.get("forbidden", []))

    def evaluate(self, kind: str, reason: str = "", version: str = "",
                 validation: str = "") -> dict:
        kind = _clean(kind).strip()
        reason = _clean(reason).strip()
        version = _clean(version).strip()
        validation = _clean(validation).strip()
        allowed = kind in self.allowed_kinds()
        forbidden = kind in self.forbidden_kinds()
        violations = []
        if forbidden:
            violations.append("forbidden_change_kind")
        if not allowed and not forbidden:
            violations.append("kind_not_in_allowed_list")
        if not reason:
            violations.append("missing_reason")
        if not version:
            violations.append("missing_version")
        if not validation:
            violations.append("missing_validation")
        requirements = {
            "version": bool(version),
            "reason": bool(reason),
            "timestamp": True,
            "validation": bool(validation),
        }
        return {
            "kind": kind,
            "allowed": allowed and not forbidden,
            "blocked": bool(forbidden),
            "violations": violations,
            "requirements": requirements,
            "complete": all(requirements.values()) and not violations,
        }

    def suggest_version(self) -> str:
        identity = _identity.load_identity()
        iver = identity.get("identity_version", "1.0.0")
        count = 0
        try:
            for line in self.log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("event") == "identity_evolution":
                    count += 1
        except FileNotFoundError:
            count = 0
        return f"{iver}·evolution#{count + 1}"

    def record(self, kind: str, reason: str, version: str = "",
               validation: str = "validated", created_by: str = "identity-evolution",
               detail: dict = None, log_path=None) -> dict:
        evaluation = self.evaluate(kind, reason, version, validation)
        if not evaluation["allowed"] or not evaluation["complete"]:
            return {"status": "blocked", "evaluation": evaluation}
        target = Path(log_path) if log_path else self.log_path
        effective_version = _clean(version).strip() or self.suggest_version()
        if _log_has_version(target, effective_version):
            blocked = dict(evaluation)
            blocked["violations"] = list(evaluation["violations"]) + ["duplicate_version"]
            blocked["complete"] = False
            return {"status": "blocked", "evaluation": blocked}
        identity = _identity.load_identity()
        entry = {
            "event": "identity_evolution",
            "identity_version": identity.get("identity_version", ""),
            "face_version": identity.get("face_version", ""),
            "geometry_version": identity.get("geometry_version", ""),
            "change_kind": kind,
            "version": effective_version,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation": validation,
            "created_by": created_by,
            "allowed_kinds": sorted(self.allowed_kinds()),
            "protected_paths": self.rules.get("protected_paths", []),
            "detail": detail or {},
        }
        _identity._append_jsonl(target, entry)
        return {
            "status": "recorded",
            "version": effective_version,
            "event": entry["event"],
            "evaluation": evaluation,
        }


if __name__ == "__main__":
    growth = IdentityGrowth()
    print(growth.evaluate("better_expressions", reason="smoother curvature blending",
                          version="1.0.0", validation="validated"))
    print(growth.evaluate("changing_canonical_geometry", reason="try a new face",
                          version="2.0.0", validation="validated"))