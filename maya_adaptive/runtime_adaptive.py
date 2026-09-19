"""Batch 8J — Runtime Adaptive Adapter (bounded capability, opt-in).

The validated 8I adaptive layer is deliberately side-channel: every learned
claim is a hypothesis that must survive evidence gates, all computation is
deterministic, and nothing writes core knowledge. This module is the SMALL
binding that lets the live production orchestration path (``maya_chat.ask`` /
``build_orchestrator``) consult that layer safely.

Host location note: this module reads the environment (opt-in gate) and may
optionally write a bounded journal, so it is hosted in the ``maya_adaptive``
package (outside ``maya_conversation``), preserving the 8G purity invariant.

Design rules enforced here (the "adapter boundary"):

0. CAPABILITY, NOT DEPENDENCY. The adapter engages only when
   ``MAYA_RUNTIME_ADAPTIVE=1`` (or an explicit ``enable=True`` in tests).
   Disabled, every public method returns ``None`` / safe neutral output and
   the production path is bit-identical to pre-8J.

1. NO DIRECT MUTATION OF CORE KNOWLEDGE. This adapter never writes to
   ``maya_identity``, trusted memory, ``maya_world_model``, ``tasks.json``,
   safety rules, ``presence_status``, the conversation store, or any 8G/8H
   module. It owns only its own in-process adaptive state plus an optional,
   bounded, append-only 8J journal (explicitly requested).

2. PROVENANCE. Every learned record carries the fingerprint key, the episode
   key, the source stage, and a deterministic ``seq``. An outcome attaches only
   to a matching proposal (8H ``LearningLedger`` semantics).

3. NO UNVALIDATED RULE. Only deterministic runtime outcome signals (guard ok,
   plan adherence, deterministic path used, failure episodes, user-supplied
   correction records) feed the learners. Model/LLM output is never trusted to
   write a rule merely because it looks confident.

4. ROLLBACK. Before a scheduler mutation (promote/weaken/reject/rollback) the
   adapter snapshots the prior hypothesis state; ``rollback()`` restores it and
   records the failure episode. Rollback never touches core identity, trusted
   memory, or safety rules.

5. REJECTABLE ADVISOR. ``suggest()`` returns a recommendation the orchestrator
   MAY reject; nothing is auto-applied by the adapter.

6. PRIVACY. ``capture()`` strips ``text_signature`` and ``input_brief`` before
   anything is stored or journaled. Raw conversation text is untrusted input,
   never training data.

Determinism: no clock, no randomness; all ordering canonical; the only I/O is
the optional append-only journal write (``_journal_append``) and it is
fail-open throughout.
"""
from __future__ import annotations

import json
import os

from maya_conversation.generalize import (characterize_task, to_key,
                                          TaskMemory, task_similarity,
                                          transfer_boundary_check)
from maya_conversation.hypothesis import GeneralizationHypothesis
from maya_conversation.portfolio import MethodPortfolio
from maya_conversation.adaptive import AdaptiveScheduler
from maya_conversation.learning_metrics import LearningMetrics
from maya_conversation.learning import LearningLedger
from maya_conversation.coop_challenge import cooperative_challenge
from maya_conversation.error_generalize import ErrorMemory


ENV_ENABLE = "MAYA_RUNTIME_ADAPTIVE"
STAGE_LIVE = "live"

MAX_HYPOTHESES_PER_METHOD = 8
MAX_JOURNAL_EVENTS = 10000
MAX_ERROR_CAUSES = 64
DEFAULT_PROFILE_PRESSURE = {"latency": 3.0, "cost": 3.0}


def enabled() -> bool:
    """Honest gate: is the adaptive layer engaged in this process?"""
    return str(os.environ.get(ENV_ENABLE, "")).strip().lower() in (
        "1", "true", "yes", "on")


def _public(fingerprint):
    """Strip raw-text-derived fields from a fingerprint for storage.

    The canonical key keeps ``text_signature`` (needed for seen/new
    comparisons), but nothing private is ever persisted or journaled.
    """
    fp = dict(fingerprint or {})
    for key in ("text_signature", "input_brief"):
        fp.pop(key, None)
    return fp


def _text(value):
    return str(value or "").strip()


_LEAN_FAST = {
    "conditions": {"resource_level": "pressure"},
    "exclusions": {"consequence_level": "elevated_guard"},
}
_MATH_PRECISE = {
    "conditions": {"math_structure": True},
    "exclusions": {},
}
_GUARD_CAREFUL = {
    "conditions": {"consequence_level": "elevated_guard"},
    "exclusions": {},
}
_FULL_STANDARD = {"conditions": {}, "exclusions": {}}


def _method_spec(name):
    if name == "lean_fast":
        return dict(_LEAN_FAST)
    if name == "math_precise":
        return dict(_MATH_PRECISE)
    if name == "guard_careful":
        return dict(_GUARD_CAREFUL)
    return dict(_FULL_STANDARD)


class RuntimeAdaptive:
    """The 8J runtime adapter: live capture, advisory, learning, rollback.

    All state is in-memory unless a ``journal`` path is supplied (bounded,
    append-only JSONL of privacy-stripped records; fail-open).
    """

    def __init__(self, enable=None, journal=None):
        self.enable = bool(enable) if enable is not None else enabled()
        self.journal = _text(journal) or None
        self.memory = TaskMemory()
        self.portfolio = MethodPortfolio()
        self.scheduler = AdaptiveScheduler()
        self.ledger = LearningLedger()
        self.metrics = LearningMetrics()
        self.errors = ErrorMemory(min_occurrences=2)
        self._hypotheses = {}          # method -> [GeneralizationHypothesis]
        self._preimages = {}           # method -> {key, before, after}
        self._source_keys = {}         # method -> canonical fingerprint key
        self._seq = 0
        self._journal_seen = 0

        self.portfolio.register(
            "lean_fast",
            conditions=dict(_LEAN_FAST["conditions"]),
            exclusions=dict(_LEAN_FAST["exclusions"]),
            resource_requirement="any", latency_steps=1,
            resource_cost=0.4, reliability=0.6,
            verification_strength=0.6,
            limitations=["only safe for ordinary-pressure ordinary-consequence"],
            description="8J live runtime: fast lean path under resource pressure")
        self.portfolio.register(
            "math_precise",
            conditions=dict(_MATH_PRECISE["conditions"]),
            exclusions=dict(_MATH_PRECISE["exclusions"]),
            resource_requirement="any", latency_steps=2,
            resource_cost=0.7, reliability=0.8,
            verification_strength=0.9,
            limitations=["math turns only", "does not substitute arithmetic checks"],
            description="8J live runtime: precise handling for math-structured turns")
        self.portfolio.register(
            "guard_careful",
            conditions=dict(_GUARD_CAREFUL["conditions"]),
            exclusions=dict(_GUARD_CAREFUL["exclusions"]),
            resource_requirement="any", latency_steps=3,
            resource_cost=1.0, reliability=0.9,
            verification_strength=0.95,
            limitations=["guard domains / holds only", "never bypassed by pressure"],
            description="8J live runtime: careful path for elevated-consequence turns")
        self.portfolio.register(
            "full_standard",
            **{
                "conditions": dict(_FULL_STANDARD["conditions"]),
                "exclusions": dict(_FULL_STANDARD["exclusions"]),
                "resource_requirement": "any", "latency_steps": 2,
                "resource_cost": 0.6, "reliability": 0.7,
                "verification_strength": 0.7,
                "limitations": ["default fallback when no specialised method fits"],
                "description": "8J live runtime: standard full path",
            }
        )

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #

    def _next_seq(self):
        self._seq += 1
        return self._seq

    def _bump(self):
        if self.enable and self.journal:
            self._journal_seen += 1
        return self._journal_seen

    def _journal_append(self, event):
        """Append one privacy-stripped event to the optional journal.

        Fail-open: any I/O/parse error drops the append (event stays in the
        in-memory ledger) without raising or corrupting the runtime.
        """
        if not self.enable or not self.journal:
            return False
        if self._journal_seen >= MAX_JOURNAL_EVENTS:
            return False
        try:
            line = json.dumps(event, ensure_ascii=False, sort_keys=True)
            with open(self.journal, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._bump()
            return True
        except Exception:
            return False

    def _hypothesis_for(self, method):
        """Get (or lazily create) the current hypothesis for a method."""
        spec = _method_spec(method)
        candidates = self._hypotheses.get(method)
        if candidates is not None:
            return candidates[-1], spec
        hypothesis = GeneralizationHypothesis(
            method=method,
            source_experience="8J live runtime (%s)" % method,
            conditions=dict(spec["conditions"]),
            exclusions=dict(spec["exclusions"]),
            assumptions=["evidence-gated", "boundary-checked"],
        )
        self._hypotheses[method] = [hypothesis]
        return hypothesis, spec

    def _restore(self, hypothesis, snapshot):
        """Deterministically rebuild a hypothesis from a snapshot (public API)."""
        restored = GeneralizationHypothesis(
            method=snapshot.get("method") or hypothesis.method,
            source_experience=snapshot.get("source_experience") or
            hypothesis.source_experience,
            assumptions=snapshot.get("assumptions"),
            conditions=snapshot.get("conditions"),
            exclusions=snapshot.get("exclusions"),
            uncertainty=snapshot.get("uncertainty", 0.5),
            expected_scope=snapshot.get("expected_scope"),
            failure_boundaries=snapshot.get("failure_boundaries"),
        )
        for case in snapshot.get("cases", ()):
            restored.record_case(case.get("key"), case.get("outcome"),
                                 case.get("ok"), note=case.get("note") or "")
        restored.update_uncertainty()
        restored.status = snapshot.get("status") or restored.status
        return restored

    # ------------------------------------------------------------------ #
    # Phase 3 — live task capture
    # ------------------------------------------------------------------ #

    def capture(self, conv_result, user_text="", resource_pressure=False,
                method=None):
        """Fingerprint a live runtime turn; return a privacy-stripped task.

        Returns ``None`` when disabled or when the envelope is unusable, so
        the production path can simply ignore the layer.
        """
        if not self.enable:
            return None
        fingerprint = characterize_task(conv_result, user_text,
                                        resource_pressure)
        # Normalize the two raw-text-derived fields so the captured record is
        # a FAITHFUL fingerprint: its canonical key (to_key round-trips) is
        # stable, content-free, and identical across capture/recall/observe.
        normalized = dict(fingerprint)
        normalized["text_signature"] = ""
        normalized["input_brief"] = False
        self.memory.remember(normalized)
        self.metrics.record_memory([to_key(normalized)], 1)
        record = _public(normalized)
        record["key"] = to_key(normalized)
        record["occurrences"] = self.memory.occurrences(normalized)
        record["method"] = _text(method) or ""
        record["text_signature"] = ""
        record["input_brief"] = False
        return record

    def recall(self, fingerprint):
        """Seen/new and occurrence count for a fingerprint (safe when off)."""
        if not self.enable:
            return None
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        return {
            "key": to_key(fp),
            "seen": self.memory.seen(fp),
            "occurrences": self.memory.occurrences(fp),
        }

    def counters(self):
        if not self.enable:
            return None
        return self.memory.counts()

    # ------------------------------------------------------------------ #
    # Phase 4 — live outcome loop
    # ------------------------------------------------------------------ #

    def observe(self, fingerprint, method, ok, outcome="observed", detail=""):
        """Record one live runtime outcome into the full learning loop.

        Learns ONLY from deterministic outcome signals. Returns a record with
        the ledger event, portfolio evidence, and scheduler effect (provenance
        preserved). ``None`` when disabled.
        """
        if not self.enable:
            return None
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        key = to_key(fp)
        episode = "live:" + method + ":" + key
        proposal = self.ledger.record(
            STAGE_LIVE, "proposal", episode, detail="episode opened")
        outcome_event = self.ledger.mark_outcome(
            STAGE_LIVE, episode, _text(outcome) or "observed", bool(ok))
        evidence = self.portfolio.record_outcome(method, fp, bool(ok))
        hypothesis, _spec = self._hypothesis_for(method)
        self._source_keys.setdefault(method, key)
        pre = hypothesis.snapshot()
        effect = self.scheduler.apply_outcome(
            hypothesis, fp, bool(ok), portfolio=self.portfolio)
        if effect.get("effect") not in ("observe", "ignore"):
            self._preimages[method] = {
                "key": episode,
                "before": pre,
                "after": hypothesis.snapshot(),
                "seq": self._next_seq(),
            }
        self.metrics.record_hypothesis_outcome(hypothesis.status)
        self.metrics.record_stability_batch(episode, [int(bool(ok))])
        record = {
            "seq": proposal["seq"] if proposal else self._next_seq(),
            "key": episode,
            "method": method,
            "fingerprint_key": key,
            "ok": bool(ok),
            "outcome": _text(outcome) or "observed",
            "effect": effect,
            "status": hypothesis.status,
            "uncertainty": round(float(hypothesis.uncertainty), 6),
            "portfolio_evidence": evidence,
            "detail": _text(detail),
        }
        self._journal_append({"kind": "observe", **_public(record)})
        return record

    def record_error(self, cause_key, detection, corrective_method,
                     fingerprint=None, resource_level=None):
        """Record a repeated failure pattern for future avoidance."""
        if not self.enable:
            return None
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        entry = self.errors.record(
            cause_key, detection, corrective_method,
            domains=fp.get("domains"),
            resource_level=resource_level or fp.get("resource_level"),
            fingerprint_key=to_key(fp))
        if len(self.errors.causes()) <= MAX_ERROR_CAUSES:
            self._journal_append({
                "kind": "error_record", "cause": _text(cause_key),
                "learned": self.errors.learned_for(cause_key),
            })
        return dict(entry)

    # ------------------------------------------------------------------ #
    # Phase 5 — live method advisory (rejectable)
    # ------------------------------------------------------------------ #

    def suggest(self, fingerprint, prefer=None, reject=None):
        """Recommend a method for a live task; the runtime may reject it.

        Returns ``None`` when disabled / nothing eligible. The return value
        always admits refusal: it is advice plus eligibility evidence.
        """
        if not self.enable:
            return None
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        rec = self.portfolio.recommend(fp, prefer=prefer, reject=reject)
        if rec is None:
            return None
        rec["within_scope"] = True
        rec["advisory"] = True
        rec["rejectable"] = True
        return rec

    def route(self, fingerprint, prefer=None):
        """Route through the scheduler's usable in-scope hypotheses."""
        if not self.enable:
            return None
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        methods = [method for method in self._hypotheses]
        candidates = [self._hypotheses[method][-1] for method in methods]
        pick = self.scheduler.route(fp, candidates, prefer=prefer)
        return pick

    # ------------------------------------------------------------------ #
    # Phase 7 — live cooperative challenge (deterministic validators)
    # ------------------------------------------------------------------ #

    def challenge(self, method, fingerprint, apply=True, validators=None):
        """Challenge a learned method hypothesis with in-process validators.

        ``validators`` restricts which deterministic checks run (latency
        aware). A challenge only fires when a validator independently finds
        hard disagreement; false challenges are ignored by the 8I layer.
        """
        if not self.enable:
            return None
        choose = set(validators) if validators else {
            "vocabulary", "boundary", "similarity", "guard"}
        fp = fingerprint if isinstance(fingerprint, dict) else {}
        hypothesis, _spec = self._hypothesis_for(method)
        ran = []
        reasons = []
        fired = False

        if "vocabulary" in choose:
            ran.append("vocabulary")
            objective = _text(fp.get("objective"))
            if objective not in _objective_vocabulary():
                fired = True
                reasons.append(
                    "objective %r outside verified vocabulary" % objective)
        if "boundary" in choose:
            ran.append("boundary")
            check = transfer_boundary_check(hypothesis, fp)
            if not check["within_scope"]:
                fired = True
                reasons.extend(check["reasons"][:2])
        if "similarity" in choose:
            ran.append("similarity")
            source = _fingerprint_of(self._source_keys.get(method, ""))
            if source:
                sim = task_similarity(source, fp)
                if sim["score"] < 0.4 and any(
                        d["severity"] == "elevated"
                        for d in sim["differences"]):
                    fired = True
                    reasons.append(
                        "task similarity %s with elevated differences"
                        % round(float(sim["score"]), 4))
        if "guard" in choose:
            ran.append("guard")
            if (fp.get("consequence_level") == "elevated_guard"
                    and method == "lean_fast"):
                fired = True
                reasons.append("lean_fast excludes elevated consequence")

        metaphor = cooperative_challenge(
            hypothesis, "8j-runtime-validator",
            challenge_result=fired)
        record = {
            "seq": self._next_seq(),
            "method": method,
            "fingerprint_key": to_key(fp),
            "validators_run": ran,
            "challenge_fired": fired,
            "reasons": reasons,
            "effect": metaphor.effect,
            "status": hypothesis.status,
        }
        self._journal_append({"kind": "challenge", **_public(record)})
        return record

    # ------------------------------------------------------------------ #
    # Phase 8 — live rollback
    # ------------------------------------------------------------------ #

    def rollback(self, method, reason="runtime rollback"):
        """Restore the prior stable hypothesis decision for a method.

        Returns the rollback record, or ``None`` when disabled or when no
        pre-image exists. Rollback touches only the adaptive layer.
        """
        if not self.enable:
            return None
        if method not in self._preimages:
            return None
        entry = self._preimages[method]
        hypothesis, _spec = self._hypothesis_for(method)
        restored = self._restore(hypothesis, entry["before"])
        self._hypotheses[method] = self._hypotheses.get(method, [])[:-1] + [restored]
        self.scheduler.run_context["last_outcome"] = {
            "ok": None, "consecutive_ok": 0, "consecutive_fail": 0,
            "tot_ok": 0, "tot_fail": 0,
        }
        self.ledger.record(STAGE_LIVE, "correction", method,
                           detail=_text(reason) or "runtime rollback")
        self.metrics.record_stability_batch(method + ":rollback", [0])
        record = {
            "seq": self._next_seq(),
            "method": method,
            "reason": _text(reason) or "runtime rollback",
            "restored_status": restored.status,
            "evidence_count": len(restored.cases),
            "episode": entry["key"],
        }
        self._journal_append({"kind": "rollback", **_public(record)})
        return record

    # ------------------------------------------------------------------ #
    # status / snapshot
    # ------------------------------------------------------------------ #

    def status(self):
        """Deterministic runtime-adapter status (safe read; no state change)."""
        hypotheses = []
        for method in sorted(self._hypotheses):
            hypotheses.append({
                "method": method,
                "status": self._hypotheses[method][-1].status,
                "cases": len(self._hypotheses[method][-1].cases),
            })
        return {
            "enabled": bool(self.enable),
            "journal": bool(self.journal),
            "counters": self.memory.counts(),
            "hypotheses": hypotheses,
            "errors": self.errors.stats(),
            "ledger": self.ledger.metrics(),
        }

    def snapshot(self):
        body = []
        for method in sorted(self._hypotheses):
            body.append({"method": method,
                         "hypothesis":
                             self._hypotheses[method][-1].snapshot()})
        return {
            "enabled": bool(self.enable),
            "seq": self._seq,
            "hypotheses": body,
            "ledger": self.ledger.snapshot(),
            "metrics": self.metrics.snapshot(),
            "errors": self.errors.snapshot(),
        }


def _fingerprint_of(source):
    """Rebuild a rough fingerprint dictionary from a canonical fingerprint
    key (``to_key`` output). Empty when unparseable.
    """
    source = _text(source)
    if not source:
        return {}
    parts = [line.strip() for line in source.split(";") if line.strip()]
    fingerprint = {}
    for part in parts:
        if part.startswith("domains="):
            fingerprint["domains"] = [d for d in
                                      part.split("=", 1)[1].split("|")
                                      if d]
        elif part.startswith("objective="):
            fingerprint["objective"] = part.split("=", 1)[1]
        elif part.startswith("intent="):
            fingerprint["primary_intent"] = part.split("=", 1)[1]
        elif part.startswith("consequence="):
            fingerprint["consequence_level"] = part.split("=", 1)[1]
        elif part.startswith("resource="):
            fingerprint["resource_level"] = part.split("=", 1)[1]
        elif part.startswith("math="):
            fingerprint["math_structure"] = \
                part.split("=", 1)[1] == "True"
        elif part.startswith("modality="):
            fingerprint["modality"] = part.split("=", 1)[1]
    return fingerprint


# Objective vocabulary (lazy, fail-open): read from the 8G plan module so the
# runtime validator checks the ACTUAL verified vocabulary, never a frozen copy.
_OBJECTIVES = frozenset({
    "answer", "explain", "compare", "clarify", "correct", "reason",
    "challenge", "summarize", "plan", "refuse", "acknowledge_uncertainty",
    "ask_missing_information",
})


def _objective_vocabulary():
    try:
        from maya_conversation.plan import objective_vocabulary
        return frozenset(objective_vocabulary())
    except Exception:
        return _OBJECTIVES


def _verify_objective_vocabulary():
    """Cheap parity helper used by the 8J suite (never called at import)."""
    return _objective_vocabulary()