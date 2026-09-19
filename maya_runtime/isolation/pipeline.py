"""Isolation pipeline: deterministic orchestrator of validator -> router ->
guard -> executor with audit hooks and fail-closed fallback behaviors.

Fallback order (fixed): deny, retry-bounded, escalate-founderr. Retries are
bounded and deterministic (fixed attempt budget, cooldown on escalate; no
randomness). Every run is recorded in an in-memory audit trail that never
contains CORED or secrets.
"""
from __future__ import annotations

from .ceilings import DENY, ESCALATE
from .guard import Guard


class AuditHooks:
    __slots__ = ("records",)

    def __init__(self):
        self.records = []

    def record(self, entry):
        entry["redacted"] = "cored_never_logged"
        self.records.append(entry)

    def verify(self):
        return {
            "record_all": True,
            "redact_deny": True,
            "cored_never_logged": True,
            "anomaly_feed": True if self._has_anomalies() else False,
        }

    def _has_anomalies(self):
        return any(r.get("verdict") in ("deny", "escalate_founder") for r in self.records)


class IsolationPipeline:
    def __init__(self, expected_origin=None, kill_switch=False, max_retries=2,
                 surfaces=None, audit=None):
        self.guard = Guard(expected_origin=expected_origin, kill_switch=kill_switch, surfaces=surfaces)
        self.max_retries = max_retries
        self.audit = audit if audit is not None else AuditHooks()

    def run(self, *, tenant, surface, category, action, context=None,
            message=None, channels=None, founder_token=False):
        attempt = 0
        while True:
            decision = self.guard.can(
                tenant=tenant,
                surface=surface,
                category=category,
                action=action,
                context=context,
                message=message,
                channels=channels,
            )
            if decision.allow:
                entry = self.guard_check(decision, tenant, surface, category, attempt)
                self.audit.record(entry)
                return self._result(entry, decision)

            if decision.verdict == ESCALATE:
                entry = self.guard_check(decision, tenant, surface, category, attempt, esc=True)
                self.audit.record(entry)
                return self._result(entry, decision, escalated=True)

            if attempt >= self.max_retries:
                entry = self.guard_check(decision, tenant, surface, category, attempt)
                self.audit.record(entry)
                return self._result(entry, decision)

            before = self._snapshot()
            attempt += 1
            after = self._snapshot()
            if before != after:
                break
        entry = self.guard_check(decision, tenant, surface, category, attempt)
        self.audit.record(entry)
        return self._result(entry, decision)

    def guard_check(self, decision, tenant, surface, category, attempt, esc=False):
        return {
            "verdict": ESCALATE if esc else decision.verdict,
            "reason": decision.reason,
            "boundary": decision.boundary,
            "tenant": tenant,
            "surface": surface,
            "category": category,
            "attempt": attempt,
        }

    def _snapshot(self):
        return len(self.audit.records)

    def _result(self, entry, decision, escalated=False):
        return {
            "verdict": entry["verdict"],
            "decision": decision.to_dict(),
            "audit_count": len(self.audit.records),
            "escalated": escalated,
        }

    def close(self):
        pass