"""Batch 8H learning orchestration: deterministic outcome ledger.

Connects learning events (proposals, observations, corrections) to measured
outcomes so the approval-gated learning flow gains an end-to-end loop without
changing who approves what. Permanent memory still requires the existing
review/approval layer; this ledger only *records and aggregates*.

Purity:
- In-memory only; no file writes, no network, no clock.
- Events carry a deterministic ``seq`` counter instead of a timestamp.
- ``metrics()`` / ``snapshot()`` are pure aggregations over recorded events.
- Never mutates learning status or proposes anything on its own.

Fail-open: malformed inputs are ignored without raising.
"""
from __future__ import annotations


EVENT_PROPOSAL = "proposal"        # a learning candidate was recorded
EVENT_OUTCOME = "outcome"          # a measurable result was observed
EVENT_CORRECTION = "correction"    # an earlier proposal was revised

STAGE_ANY = "*"


class LearningLedger:
    """Deterministic in-memory journal connecting events to outcomes."""

    def __init__(self):
        self._events = []
        self._proposals = {}   # key -> event dict
        self._next_seq = 0

    def _bump(self):
        seq = self._next_seq
        self._next_seq += 1
        return seq

    def record(self, stage, kind, key, detail="", ok=None):
        """Record a learning event. Returns the entry (or None if invalid)."""
        stage = str(stage or "")
        kind = str(kind or "")
        key = str(key or "")
        if not stage or not kind or not key:
            return None
        if kind not in (EVENT_PROPOSAL, EVENT_OUTCOME, EVENT_CORRECTION):
            return None
        entry = {
            "seq": self._bump(),
            "stage": stage,
            "kind": kind,
            "key": key,
            "detail": str(detail or ""),
            "ok": ok,
        }
        self._events.append(entry)
        if kind == EVENT_PROPOSAL:
            self._proposals[key] = entry
        return entry

    def mark_outcome(self, stage, key, outcome, ok):
        """Attach a measured outcome to a previously recorded proposal.

        Returns the outcome entry, or None when no proposal exists for the
        key on the stage, or when the latest proposal already received an
        outcome (stale outcomes from earlier episodes never block a new one).
        """
        proposal = self._proposals.get(str(key or ""))
        if proposal is None or proposal.get("stage") != str(stage or ""):
            return None
        after = any(
            e.get("kind") == EVENT_OUTCOME
            and e.get("seq") > proposal.get("seq", -1)
            for e in self._events)
        if after:
            return None
        return self.record(stage, EVENT_OUTCOME, key,
                           detail=str(outcome or ""), ok=bool(ok))

    def _outcome_pairs(self):
        outcomes = [e for e in self._events if e.get("kind") == EVENT_OUTCOME]
        pairs = {}
        for event in outcomes:
            key = event.get("key")
            if key not in pairs:
                pairs[key] = event
        return pairs

    def metrics(self):
        """Deterministic aggregate measures per stage (and overall)."""
        stages = {}
        for event in self._events:
            stage = event.get("stage", "")
            bucket = stages.setdefault(stage, {
                "proposals": 0, "outcomes": 0, "ok_outcomes": 0,
                "corrections": 0, "events": 0,
            })
            bucket["events"] += 1
            kind = event.get("kind")
            if kind == EVENT_PROPOSAL:
                bucket["proposals"] += 1
            elif kind == EVENT_OUTCOME:
                bucket["outcomes"] += 1
                if event.get("ok"):
                    bucket["ok_outcomes"] += 1
            elif kind == EVENT_CORRECTION:
                bucket["corrections"] += 1
        overall = {
            "proposals": 0, "outcomes": 0, "ok_outcomes": 0,
            "corrections": 0, "events": len(self._events),
        }
        for stage, bucket in stages.items():
            for field in ("proposals", "outcomes", "ok_outcomes",
                          "corrections"):
                overall[field] += bucket[field]
        result = {"stages": dict(sorted(stages.items()))}
        result["overall"] = overall
        result["outcome_rate"] = (overall["ok_outcomes"] / overall["outcomes"]
                                  if overall["outcomes"] else 0.0)
        result["pledged_outcomes"] = (overall["proposals"]
                                      - len(self._outcome_pairs()))
        return result

    def snapshot(self):
        """Deterministic stable dump of all events + metrics."""
        return {
            "events": list(self._events),
            "metrics": self.metrics(),
        }