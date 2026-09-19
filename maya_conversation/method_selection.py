"""Batch 8H phase 9: deterministic method selection and gated improvement.

Selects among alternative calculation methods for a target without
randomness or floating nondeterminism, and provides a controlled-improvement
plan that engages only under explicit approval.

Purity:
- No clock, no randomness, no file writes, no network.
- Selection is a pure function of the registered methods and their scores.
- ``plan_improvement`` never mutates or executes anything: it only reports
  when approval is granted, and returns ``requires_approval`` otherwise.

Fail-open:
- Empty method sets, unknown targets, malformed scores, and unapproved gates
  all return safe no-op results instead of raising.
"""
from __future__ import annotations


APPROVED = "approved"
GATE_ANY = "any"


class MethodRegistry:
    """Ordered set of named methods for a target.

    Registration order is preserved and used as the deterministic tiebreak;
    methods can be added at leisure but availability never depends on order.
    """

    def __init__(self):
        self._methods = {}   # target -> [method dicts in registration order]

    def register(self, target, name, fn, description=""):
        target = str(target or "")
        name = str(name or "")
        if not target or not name or fn is None:
            return None
        methods = self._methods.setdefault(target, [])
        if any(m["name"] == name for m in methods):
            return None
        methods.append({
            "target": target,
            "name": name,
            "fn": fn,
            "description": str(description or ""),
        })
        return methods[-1]

    def available(self, target):
        """Deterministic list of registered method names for a target."""
        return [m["name"] for m in self._methods.get(str(target or ""), [])]

    def select(self, target, preference=None):
        """Pick the highest-scored method for ``target``.

        Deterministic ordering: score descending, then registration order,
        then name. Returns a dict copy, or None when the target has no
        methods (fail-open). ``preference`` is accepted for interface
        symmetry but does not override scoring here.
        """
        methods = self._methods.get(str(target or ""))
        if not methods:
            return None
        best = None
        best_key = None
        for method in methods:
            method_score = _finite(method.get("score"))
            key = (method_score,)
            if best is None or key > best_key:
                best = method
                best_key = key
        return dict(best)

    def set_score(self, target, name, score):
        """Attach/update the deterministic score a method wants to use.

        Returns the updated method dict, or None when the method is unknown.
        """
        methods = self._methods.get(str(target or "")) or []
        for method in methods:
            if method["name"] == str(name or ""):
                method["score"] = _finite(score)
                return dict(method)
        return None


def _finite(value):
    """Coerce to float, fail-open to 0.0 on non-numeric or non-finite."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


def select_method(registry, target, preference=None):
    """Convenience wrapper: registry.select(target, preference)."""
    return registry.select(target, preference)


def plan_improvement(target, baseline, candidate, gate):
    """Controlled-improvement plan.

    Returns:
    - ``None`` when baseline/candidate are unusable (fail-open).
    - ``{"plan": "requires_approval", ...}`` when ``gate`` is not approved.
    - a deterministic comparison dict when ``gate == APPROVED``.
    """
    target = str(target or "")
    try:
        baseline = float(baseline)
        candidate = float(candidate)
    except (TypeError, ValueError):
        return None
    if target == "":
        return None
    if str(gate or "") != APPROVED:
        return {
            "target": target,
            "plan": "requires_approval",
            "gate": str(gate or ""),
            "improvement": 0.0,
        }
    baseline_number = _finite(baseline)
    candidate_number = _finite(candidate)
    if baseline != baseline or baseline in (float("inf"), float("-inf")):
        plan = "keep_baseline"
        improvement = 0.0
    else:
        delta = candidate_number - baseline_number
        plan = "adopt_candidate" if delta > 0 else "keep_baseline"
        improvement = max(delta, 0.0)
    return {
        "target": target,
        "plan": plan,
        "gate": APPROVED,
        "baseline": baseline_number,
        "candidate": candidate_number,
        "improvement": improvement,
    }