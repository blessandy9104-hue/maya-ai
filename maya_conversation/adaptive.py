"""Batch 8I phase 10: adaptive orchestration (side-channel).

AdaptiveScheduler observes externally-supplied outcomes and rewrites the
8I-owned learning records — never production run() internals.  The 8F/8G/8H
production+tests are untouched: no probing, no injection, no mutation.

Fixed learning rules (deterministic, hardcoded):
  - promote :   S consecutive successful transfers  (S = 2)
  - weaken  :   1+ failure with recorded evidence
  - reject  :   2+ failures in total for the hypothesis
  - rollback:   2+ CONSECUTIVE failures
  - replace :   portfolio comparison when a different portfolio method is
                strictly preferred for the same fingerprint

Statuses (from hypothesis.py): untested -> tested -> promoted ->
weakened|rejected|rolled_back.

Purity: no clock, no randomness, no IO, no network.
Fail-open: unknown fingerprints/hypotheses return safe ``None``/False.
"""
from __future__ import annotations

from .generalize import transfer_boundary_check


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


_USABLE = ("promoted", "tested", "weakened")
_DEAD = ("rejected", "rolled_back")
_ORDER = {"promoted": 0, "tested": 1, "weakened": 2}


class AdaptiveScheduler:
    """Side-channel promotion/weakening/rejection/rollback controller."""

    def __init__(self, promote_after=2, fail_to_weaken=1,
                 fail_to_reject=2, consecutive_fail_to_rollback=2,
                 run_context=None):
        self.promote_after = max(1, int(promote_after))
        self.fail_to_weaken = max(1, int(fail_to_weaken))
        self.fail_to_reject = max(2, int(fail_to_reject))
        self.rollback_after = max(2, int(consecutive_fail_to_rollback))
        self.run_context = dict(run_context or {})
        self._counters = {}   # hypothesis -> counter dict

    def _counter(self, hypothesis):
        return self._counters.setdefault(
            id(hypothesis),
            {"consecutive_ok": 0, "consecutive_fail": 0,
             "tot_ok": 0, "tot_fail": 0, "promoted": False,
             "weakened_steps": 0, "case_n": 0})

    def apply_outcome(self, hypothesis, fingerprint, outcome,
                      portfolio=None):
        """Record one real outcome and apply the fixed learning rules.

        Outcomes are recorded onto the hypothesis itself (evidence log),
        then status transitions follow the scheduler rules.  Returns an
        effect dict describing any status change.
        """
        if hypothesis is None:
            return {"effect": "ignore", "reason": "no hypothesis"}
        counter = self._counter(hypothesis)
        ok = bool(outcome)
        counter["case_n"] += 1
        hypothesis.record_case(
            case_key="scheduled_%d" % counter["case_n"],
            outcome="scheduler observation",
            ok=ok,
            note="8I adaptive orchestration side-channel")
        hypothesis.update_uncertainty()

        if ok:
            counter["consecutive_ok"] += 1
            counter["consecutive_fail"] = 0
            counter["tot_ok"] += 1
        else:
            counter["consecutive_fail"] += 1
            counter["consecutive_ok"] = 0
            counter["tot_fail"] += 1

        effect = {"effect": "observe", "status": hypothesis.status}

        if (hypothesis.status in ("untested", "tested", "weakened")
                and counter["consecutive_ok"] >= self.promote_after
                and not counter["promoted"]
                and hypothesis.promote()):
            counter["promoted"] = True
            effect = {"effect": "promote", "status": hypothesis.status}

        if not ok:
            if (counter["consecutive_fail"] >= self.rollback_after
                    and hypothesis.status == "promoted"):
                hypothesis.rollback(reason="2 consecutive failures")
                effect = {"effect": "rollback",
                          "status": hypothesis.status}
            elif counter["tot_fail"] >= self.fail_to_reject:
                hypothesis.reject(reason="2+ failures")
                effect = {"effect": "reject", "status": hypothesis.status}
            elif (counter["tot_fail"] >= self.fail_to_weaken
                  and hypothesis.status == "tested"):
                hypothesis.weaken(reason="failure evidence")
                counter["weakened_steps"] += 1
                effect = {"effect": "weaken", "status": hypothesis.status}

        if portfolio is not None:
            rec = portfolio.recommend(fingerprint)
            if (rec is not None and rec["method"] !=
                    getattr(hypothesis, "method",
                            getattr(hypothesis, "name", None))
                    and rec["score"] > 0.5):
                effect["replaced_by"] = rec["method"]

        self.run_context["last_outcome"] = {
            "ok": ok,
            "consecutive_ok": counter["consecutive_ok"],
            "consecutive_fail": counter["consecutive_fail"],
            "tot_ok": counter["tot_ok"],
            "tot_fail": counter["tot_fail"],
        }
        return effect

    def route(self, fingerprint, candidates, prefer=None):
        """Pick the strongest usable candidate that is within scope.

        ``candidates`` are hypotheses (or dict-likes with conditions).
        Only usable statuses are routable; rejected/rolled_back never route.
        """
        best_name = None
        best_hypothesis = None
        prefer = [str(p) for p in (prefer or ())]
        usable = []
        for h in candidates:
            if h is None:
                continue
            status = getattr(h, "status", None)
            if status is None and isinstance(h, dict):
                status = h.get("status", "untested")
            if status is None:
                status = "untested"
            if status in _DEAD:
                continue
            name = getattr(h, "method", None)
            if name is None and isinstance(h, dict):
                name = h.get("method")
            if name is None:
                name = str(h)
            check = transfer_boundary_check(h, fingerprint)
            if not check["within_scope"]:
                continue
            usable.append((name, status, h))
        for pref in prefer:
            for name, status, h in usable:
                if name == pref and status in _USABLE:
                    return {"name": name, "status": status,
                            "preferred": True}
        if not usable:
            return None
        usable.sort(key=lambda item: (_ORDER.get(item[1], 1), item[0]))
        name, status, h = usable[0]
        return {"name": name, "status": status, "preferred": False}

    def counters(self):
        return {
            "count": len(self._counters),
            "per_hypothesis": [
                {"id": key, **dict(value)}
                for key, value in sorted(
                    self._counters.items(),
                    key=lambda item: item[1]["tot_ok"]
                    + item[1]["tot_fail"])
            ],
        }