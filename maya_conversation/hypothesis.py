"""Batch 8I phase 4: generalization hypotheses.

A learned method that may apply to a new task class is represented as a
HYPOTHESIS, never as a trusted rule. A hypothesis carries its source
experience, assumptions, relevant conditions, supporting evidence,
uncertainty, expected scope, and failure boundaries, and starts UNTESTED.

Purity:
- No clock, no randomness, no file writes, no network.
- Evidence accumulates deterministically (per-case outcome records).
- Status transitions are explicit operations; nothing auto-promotes.

Fail-open:
- Malformed inputs degrade to a neutral untested hypothesis (never raises).
"""
from __future__ import annotations

ST_UNTESTED = "untested"
ST_TESTED = "tested"
ST_PROMOTED = "promoted"
ST_REJECTED = "rejected"
ST_ROLLED_BACK = "rolled_back"
ST_WEAKENED = "weakened"

MIN_EVIDENCE_FOR_TESTED = 1
MIN_UNCERTAINTY = 0.0
MAX_UNCERTAINTY = 1.0


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


def _text(value):
    return str(value or "").strip()


class GeneralizationHypothesis:
    """First-class representation of a proposed generalization."""

    def __init__(self, method, source_experience, assumptions=None,
                 conditions=None, exclusions=None, evidence=None,
                 uncertainty=0.5, expected_scope=None,
                 failure_boundaries=None):
        self.method = _text(method) or "unknown_method"
        self.source_experience = _text(source_experience)
        self.assumptions = sorted(set(_text(a) for a in (assumptions or ())))
        self.conditions = dict(conditions or {})
        self.exclusions = dict(exclusions or {})
        self.expected_scope = _text(expected_scope)
        self.failure_boundaries = sorted(
            set(_text(b) for b in (failure_boundaries or ())))
        self.uncertainty = min(MAX_UNCERTAINTY, max(MIN_UNCERTAINTY,
                                                    _finite(uncertainty)))
        self.status = ST_UNTESTED
        self.cases = []   # deterministic outcome log: {key, ok, note}
        self._case_keys = {}

    def _evidence_count(self):
        return len(self.cases)

    def record_case(self, case_key, outcome, ok, note=""):
        """Record one (ideally UNSEEN) case outcome.

        Deterministic: duplicate case keys update the existing record.
        Returns the recorded entry.
        """
        key = _text(case_key) or ("case_%d" % (len(self.cases) + 1))
        entry = self._case_keys.get(key)
        if entry is None:
            entry = {"key": key, "outcome": _text(outcome), "ok": bool(ok),
                     "note": _text(note)}
            self._case_keys[key] = entry
            self.cases.append(entry)
        else:
            entry["outcome"] = _text(outcome)
            entry["ok"] = bool(ok)
            entry["note"] = _text(note)
        if self.status == ST_UNTESTED and self._evidence_count() >= \
                MIN_EVIDENCE_FOR_TESTED:
            self.status = ST_TESTED
        return dict(entry)

    def update_uncertainty(self):
        """Bayes-free, deterministic uncertainty from outcome consistency."""
        if not self.cases:
            return self.uncertainty
        ok_count = sum(1 for c in self.cases if c.get("ok"))
        n = len(self.cases)
        consistency = ok_count / n
        sample_penalty = 1.0 / (1.0 + n)
        self.uncertainty = min(MAX_UNCERTAINTY, max(MIN_UNCERTAINTY,
                             1.0 - consistency * (1.0 - sample_penalty)))
        return self.uncertainty

    def promote(self):
        """Explicit promotion to trusted-rule candidate. Requires evidence."""
        if self._evidence_count() < MIN_EVIDENCE_FOR_TESTED:
            return False
        self.update_uncertainty()
        if self.uncertainty > 0.35:
            return False
        self.status = ST_PROMOTED
        return True

    def weaken(self, reason=""):
        self.status = ST_WEAKENED
        self.failure_boundaries = sorted(set(
            self.failure_boundaries + [_text(reason) or "unspecified"]))
        return self.status

    def reject(self, reason=""):
        self.status = ST_REJECTED
        self.failure_boundaries = sorted(set(
            self.failure_boundaries + [_text(reason) or "unspecified"]))
        return self.status

    def rollback(self, reason=""):
        self.status = ST_ROLLED_BACK
        self.failure_boundaries = sorted(set(
            self.failure_boundaries + [_text(reason) or "unspecified"]))
        return self.status

    def snapshot(self):
        return {
            "method": self.method,
            "source_experience": self.source_experience,
            "assumptions": list(self.assumptions),
            "conditions": dict(self.conditions),
            "exclusions": dict(self.exclusions),
            "uncertainty": _finite(self.uncertainty),
            "expected_scope": self.expected_scope,
            "failure_boundaries": list(self.failure_boundaries),
            "status": self.status,
            "evidence_count": self._evidence_count(),
            "cases": [dict(c) for c in self.cases],
        }


def hypothesis_from_experience(method, source_experience, assumptions=None,
                               conditions=None, exclusions=None):
    """Construct an UNTESTED hypothesis from a source experience."""
    return GeneralizationHypothesis(
        method=method,
        source_experience=source_experience,
        assumptions=assumptions,
        conditions=conditions,
        exclusions=exclusions,
        uncertainty=0.5,
    )