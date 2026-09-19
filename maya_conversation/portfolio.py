"""Batch 8I phase 9: method portfolio.

Extends 8H method selection into a portfolio of competing methods with
condition tables: where each method worked / failed, latency, resource
cost, reliability, verification strength, and limitations.  The orchestrator
chooses per task conditions — a previously successful method is rejected
when conditions change.

Purity:
- No clock, no randomness, no file writes, no network.
- Scores are deterministic functions of recorded evidence and static method
  profiles.

Fail-open:
- Unregistered methods, malformed fingerprints, and empty candidate sets
  degrade to safe ``None`` recommendations (never raise).
"""
from __future__ import annotations

from .generalize import transfer_boundary_check, _set


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


def _clip01(value):
    return min(1.0, max(0.0, _finite(value)))


class MethodPortfolio:
    """Competing methods with per-condition evidence and characteristics."""

    def __init__(self):
        self._methods = {}   # name -> method dict
        self._order = []     # registration order (default tiebreak)
        self._evidence = {}  # name -> [{domains, ok}]

    def register(self, name, conditions=None, exclusions=None,
                 resource_requirement="any", latency_steps=1,
                 resource_cost=1.0, reliability=0.5,
                 verification_strength=0.5, limitations=None,
                 description=""):
        """Register a method with its condition table and characteristics."""
        name = str(name or "").strip()
        if not name or name in self._methods:
            return None
        method = {
            "name": name,
            "conditions": dict(conditions or {}),
            "exclusions": dict(exclusions or {}),
            "resource_requirement": str(resource_requirement or "any"),
            "latency_steps": max(0, int(_finite(latency_steps))),
            "resource_cost": max(0.0, _finite(resource_cost)),
            "reliability": _clip01(reliability),
            "verification_strength": _clip01(verification_strength),
            "limitations": sorted(set(
                str(l) for l in (limitations or ()) if str(l).strip())),
            "description": str(description or ""),
        }
        self._methods[name] = method
        self._order.append(name)
        return dict(method)

    def record_outcome(self, name, fingerprint, ok):
        """Record one real outcome for a method on a task fingerprint."""
        name = str(name or "")
        if name not in self._methods:
            return None
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        entry = {"domains": sorted(_set(fp.get("domains"))), "ok": bool(ok),
                 "resource_level": str(fp.get("resource_level") or "safe")}
        self._evidence.setdefault(name, []).append(entry)
        return dict(entry)

    def _evidence_score(self, name, fingerprint):
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        fp_domains = _set(fp.get("domains"))
        entries = self._evidence.get(name, [])
        overlapping = [e for e in entries
                       if not fp_domains or (e["domains"] and
                                             set(e["domains"]) & fp_domains)]
        if not overlapping:
            return 0.5   # neutral prior: no evidence = not best and not worst
        ok_count = sum(1 for e in overlapping if e["ok"])
        return ok_count / len(overlapping)

    def _eligible(self, method, fingerprint):
        """Domain-condition eligibility via the transfer boundary check."""
        pseudo = method
        check = transfer_boundary_check(pseudo, fingerprint)
        if not check["within_scope"]:
            return False, check
        resource = method["resource_requirement"]
        fp_resource = str(fingerprint.get("resource_level") or "safe") \
            if isinstance(fingerprint, dict) else "safe"
        if resource != "any" and fp_resource != resource:
            return False, check
        return True, check

    def recommend(self, fingerprint, prefer=None, reject=None):
        """Choose a method for a task from eligible candidates.

        Prefers explicit ``prefer`` names first (when eligible); otherwise
        scores eligible candidates deterministically.  ``reject`` names are
        never recommended, even if previously successful.
        """
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        reject = set(str(r) for r in (reject or ()))
        prefer = [str(p) for p in (prefer or ()) if str(p)]

        candidates = []
        for name in self._order:
            if name in reject or name not in self._methods:
                continue
            method = self._methods[name]
            eligible, check = self._eligible(method, fp)
            if not eligible:
                continue
            candidates.append((name, method, check))

        for pref in prefer:
            for name, method, check in candidates:
                if name == pref:
                    return {
                        "method": name,
                        "score": 1.0,
                        "preferred": True,
                        "rejected_previous": [],
                        "scores": {"evidence": self._evidence_score(
                            name, fp)},
                    }

        best = None
        best_score = -1.0
        for name, method, check in candidates:
            evidence = self._evidence_score(name, fp)
            latency_norm = 1.0 / (1.0 + method["latency_steps"])
            resource_ok = 1.0 if (
                method["resource_requirement"] == "any"
                or fp.get("resource_level", "safe") ==
                method["resource_requirement"]) else 0.0
            score = (0.4 * evidence
                     + 0.2 * method["reliability"]
                     + 0.2 * method["verification_strength"]
                     + 0.1 * resource_ok
                     + 0.1 * latency_norm)
            pick = (round(score, 9), name)
            if best is None or pick > best_score:
                best = (name, method, score, evidence)
                best_score = pick

        if best is None:
            return None

        name, method, score, evidence = best
        return {
            "method": name,
            "score": _finite(score),
            "preferred": False,
            "rejected_previous": [],
            "scores": {"evidence": evidence,
                       "reliability": method["reliability"],
                       "verification_strength": method["verification_strength"],
                       "latency_norm": 1.0 / (1.0 + method["latency_steps"])},
            "limitations": list(method["limitations"]),
        }

    def history(self):
        return {
            "methods": [self._methods[n] for n in self._order],
            "evidence": {n: list(self._evidence.get(n, []))
                         for n in self._order},
        }