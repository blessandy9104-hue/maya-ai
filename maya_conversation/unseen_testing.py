"""Batch 8I phase 5: unseen-case testing.

Tests a learned generalization on cases that were NOT used to generate it,
and measures success, failure, robustness, latency, resource cost, and
unexpected behavior. Latency/resource measures are structural proxies
(step counts reported by the executed method), not wall-clock readings,
keeping the module deterministic and pure.

Purity:
- No clock, no randomness, no file writes, no network.
- Every measure is a pure function of trial records.

Fail-open:
- A trial on a SEEN case is still recorded but flagged ``was_seen`` so the
  caller cannot claim unseen evidence from repeated structure.
"""
from __future__ import annotations

from .generalize import characterize_task, to_key


def classify_unseen(memory, fingerprint):
    """NEW vs SEEN classification for a characterized task."""
    fingerprint = fingerprint or {}
    key = to_key(fingerprint)
    occurrences = memory.occurrences(fingerprint)
    return {
        "unseen": occurrences == 0,
        "was_seen": occurrences > 0,
        "occurrences": occurrences,
        "key": key,
    }


def _violates_constraints(output, constraints):
    if not constraints:
        return False
    if not isinstance(output, dict):
        return False
    text = str(output)
    for constraint in constraints:
        constraint = str(constraint or "")
        if not constraint:
            continue
        if constraint.strip().lower() in text.lower():
            return False
    return True


def run_unseen_trial(memory, hypothesis, fingerprint, method_fn,
                     constraints=None):
    """Execute ``method_fn`` on a (preferably NEW) case and record it.

    ``method_fn(fingerprint)`` must return a dict with at least:
      ok: bool, latency_steps: int, resource_cost: float, output: object
    Returns a deterministic trial record including the unseen classification
    and any unexpected-behavior flag.
    """
    classification = classify_unseen(memory, fingerprint)
    fingerprint = fingerprint or {}
    result = method_fn(fingerprint)
    if not isinstance(result, dict):
        result = {"ok": False, "output": result, "latency_steps": 0,
                  "resource_cost": 0.0}
    unexpected = bool(result.get("unexpected"))
    if not unexpected:
        unexpected = _violates_constraints(result.get("output"), constraints)
    outcome = "ok" if result.get("ok") else "failed"
    entry = hypothesis.record_case(
        classification["key"], outcome, bool(result.get("ok")),
        note="unseen=%s" % classification["unseen"])
    return {
        "was_seen": classification["was_seen"],
        "unseen": classification["unseen"],
        "ok": bool(result.get("ok")),
        "unexpected": unexpected,
        "latency_steps": int(result.get("latency_steps") or 0),
        "resource_cost": _finite(result.get("resource_cost")),
        "entry": entry,
    }


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


def trial_measures(trials):
    """Deterministic aggregate measures over trial records."""
    trials = list(trials or ())
    ok_count = sum(1 for t in trials if t.get("ok"))
    unseen_count = sum(1 for t in trials if t.get("unseen"))
    unexpected_count = sum(1 for t in trials if t.get("unexpected"))
    failures = [t for t in trials if not t.get("ok")]
    n = len(trials)
    latency = [t.get("latency_steps", 0) for t in trials]
    cost = [t.get("resource_cost", 0.0) for t in trials]
    return {
        "total_trials": n,
        "success_count": ok_count,
        "failure_count": n - ok_count,
        "success_rate": (ok_count / n) if n else 0.0,
        "unseen_count": unseen_count,
        "unexpected_count": unexpected_count,
        "mean_latency_steps": (sum(latency) / n) if n else 0.0,
        "mean_resource_cost": (sum(cost) / n) if n else 0.0,
        "failed_keys": sorted(
            str(t.get("entry", {}).get("key")) for t in failures or ()),
    }


def accuracy_vs_baseline(trials, expected_ok_flags):
    """Fraction of trials whose ok matches the independently known outcome."""
    trials = list(trials or ())
    expected = list(expected_ok_flags or ())
    if not trials or len(trials) != len(expected):
        return 0.0
    matches = sum(
        1 for t, want in zip(trials, expected)
        if bool(t.get("ok")) == bool(want))
    return matches / len(trials)