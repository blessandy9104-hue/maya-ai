"""Batch 8I phase 8: error generalization.

Records repeated failure patterns and derives avoidance rules that apply
to genuinely similar unseen cases.  A single failure never becomes a rule;
only repeated, consistent failures with overlapping conditions yield a
learned avoidance.

Purity:
- No clock, no randomness, no file writes, no network.
- Deterministic occurrence counting and domain overlap.
- Never raises; malformed inputs are ignored (fail-open).

Avoidance is expressed as a dict of conditions that, when matched by a
NEW task, trigger a ``should_avoid`` warning.  Adoption of avoidance is
always the caller's responsibility — this module never mutates orchestration.
"""
from __future__ import annotations

from .generalize import _set, to_key


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


class ErrorMemory:
    """Per-cause failure journal with avoidance derivation."""

    def __init__(self, min_occurrences=2):
        self.min_occurrences = max(1, int(min_occurrences))
        self._causes = {}   # cause_key -> [failure entries]
        self._order = []    # deterministic cause insertion order

    def _ensure(self, cause_key):
        if cause_key not in self._causes:
            self._causes[cause_key] = []
            self._order.append(cause_key)
        return self._causes[cause_key]

    def record(self, cause_key, detection, corrective_method,
               domains=None, resource_level=None, fingerprint_key=""):
        """Record one failure attributed to a root cause.

        Returns the recorded entry dict.
        """
        cause_key = str(cause_key or "unknown_cause").strip()
        entry = {
            "cause_key": cause_key,
            "detection": str(detection or ""),
            "corrective_method": str(corrective_method or ""),
            "domains": sorted(set(str(d) for d in (domains or ()))),
            "resource_level": str(resource_level or "safe"),
            "fingerprint_key": str(fingerprint_key),
        }
        self._ensure(cause_key).append(entry)
        return dict(entry)

    def occurrences(self, cause_key):
        return len(self._causes.get(str(cause_key or ""), []))

    def learned_for(self, cause_key):
        """True only when evidence threshold is reached for this cause."""
        return self.occurrences(cause_key) >= self.min_occurrences

    def avoid(self, fingerprint, cause_key):
        """Deterministic domain-overlap avoidance check.

        Returns True when:
          (a) the cause has been learned (enough occurrences), AND
          (b) the fingerprint's domains overlap with the recorded failures'
              domains for that cause.
        """
        if not self.learned_for(cause_key):
            return False
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        fp_domains = _set(fp.get("domains"))
        if not fp_domains:
            return False
        for entry in self._causes.get(str(cause_key), []):
            entry_domains = _set(entry.get("domains"))
            if entry_domains and fp_domains & entry_domains:
                return True
        return False

    def causes(self):
        return list(self._order)

    def stats(self):
        return {
            "cause_count": len(self._order),
            "total_failures": sum(
                len(entries) for entries in self._causes.values()),
            "learned_causes": sum(
                1 for c in self._order if self.learned_for(c)),
        }

    def snapshot(self):
        return {
            "min_occurrences": self.min_occurrences,
            "causes": [
                {"cause_key": c, "occurrences": self.occurrences(c),
                 "learned": self.learned_for(c),
                 "entries": [dict(e) for e in self._causes[c]]}
                for c in self._order
            ],
            "stats": self.stats(),
        }