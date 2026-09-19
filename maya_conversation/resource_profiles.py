"""Batch 8I phase 14: resource-aware generalization.

Methods that "work normally" remain available; cheaper methods are
preferred under time / memory / compute pressure.  Selection is based on
resource profiles: each profile carries latency, cost, pressure-viability,
and domain-exclusion constraints.  Orchestrator ranks by budget fit, then
pressure-success-probability.

Resource constraints are honest and deterministic — no clock, no
randomness, no probing of internal state.

Purity:
- No file I/O, no network, no runtime mutation of production code.
Fail-open:
- Unknown profiles / empty registries degrade to ``None`` / empty dicts.
"""
from __future__ import annotations

from .generalize import _set


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


class ResourceProfile:
    """One fixed resource-cost profile."""

    def __init__(self, name, latency=1.0, cost=0.2, pressure_ok=True,
                 pressure_success_prob=0.5, domains_excluded=None):
        self.name = str(name or "unknown")
        self.latency = max(0.0, _finite(latency))
        self.cost = max(0.0, _finite(cost))
        self.pressure_ok = bool(pressure_ok)
        self.pressure_success_prob = max(0.0, min(1.0,
                                                    _finite(pressure_success_prob)))
        self.domains_excluded = sorted(
            set(str(d) for d in (domains_excluded or ())))

    def within_budget(self, budget):
        budget = budget if isinstance(budget, dict) else {}
        _LARGE = 1e9
        max_latency = _finite(budget.get("latency", _LARGE))
        max_cost = _finite(budget.get("cost", _LARGE))
        return self.latency <= max_latency and self.cost <= max_cost

    def eligible_for_task(self, fingerprint, resource_pressure=False):
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        if resource_pressure and not self.pressure_ok:
            return False
        fp_domains = sorted(_set(fp.get("domains")))
        if fp_domains and self.domains_excluded:
            if set(fp_domains) & set(self.domains_excluded):
                return False
        return True

    def snapshot(self):
        return {
            "name": self.name,
            "latency": self.latency,
            "cost": self.cost,
            "pressure_ok": self.pressure_ok,
            "pressure_success_prob": self.pressure_success_prob,
            "domains_excluded": list(self.domains_excluded),
        }


class ResourcePolicy:
    """Registry of profiles with budget-constrained selection."""

    def __init__(self):
        self._profiles = {}
        self._order = []

    def register(self, profile):
        if profile is None or profile.name in self._profiles:
            return None
        self._profiles[profile.name] = profile
        self._order.append(profile.name)
        return profile.snapshot()

    def select_for_resource(self, fingerprint, budget=None,
                            resource_pressure=False):
        budget = budget if isinstance(budget, dict) else {}
        _LARGE = 1e9
        candidates = []
        for name in self._order:
            profile = self._profiles[name]
            max_latency = _finite(budget.get("latency", _LARGE))
            max_cost = _finite(budget.get("cost", _LARGE))
            if profile.latency > max_latency or profile.cost > max_cost:
                continue
            if not profile.eligible_for_task(fingerprint,
                                             resource_pressure=resource_pressure):
                continue
            candidates.append(profile)
        if not candidates:
            return None
        candidates.sort(
            key=lambda p: (-p.pressure_success_prob, p.name))
        best = candidates[0]
        return {
            "profile": best.name,
            "latency": best.latency,
            "cost": best.cost,
            "pressure_success_prob": best.pressure_success_prob,
        }

    def estimate_costs(self, fingerprint):
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        return {
            name: {
                "latency": profile.latency,
                "cost": profile.cost,
                "eligible": profile.eligible_for_task(fp),
            }
            for name, profile in self._profiles.items()
        }

    def profiles(self):
        return [self._profiles[n].snapshot() for n in self._order]