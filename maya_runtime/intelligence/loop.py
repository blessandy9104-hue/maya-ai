"""The 7-stage intelligence loop, in the architect's prescribed order:

    SENSE -> INTERPRET -> STABILIZE -> DECIDE -> EXPRESS -> LOG -> REFLECT

Ordering is enforced, not assumed: the state engine always runs before
persona fusion, world-model alignment, or language; safety always runs
before meaning and language; meaning is computed only after state,
fusion, alignment, and safety; and language is derived only from meaning.
A stage cannot be skipped: each stage verifies its predecessor exists.
"""
from __future__ import annotations

from .encoder import FeatureEncoder
from .state import StateEngine
from .fusion import PersonaFusion
from .confidence import ConfidenceScorer
from .relevance import Relevance
from .safety import SafetyEnforcer
from .meaning import MeaningComputer
from .language import LanguageEngine
from .reports import (
    build_decision_report,
    build_evidence_report,
    build_stability_report,
)
from .evolution import EvolutionLog
from .locks import LOCKED_SURFACES
from .profiles import DeploymentProfiles

STAGES = ("sense", "interpret", "stabilize", "decide", "express", "log",
          "reflect")


class IntelligenceLoop:
    """Deterministic execution of the full intelligence pipeline."""

    def __init__(self, encoder=None, state=None, fusion=None,
                 confidence=None, relevance=None, safety=None,
                 meaning=None, language=None, evolution=None,
                 profiles=None):
        self.encoder = encoder or FeatureEncoder()
        self.state = state or StateEngine()
        self.fusion = fusion or PersonaFusion()
        self.confidence = confidence or ConfidenceScorer()
        self.relevance = relevance or Relevance()
        self.safety = safety or SafetyEnforcer()
        self.meaning = meaning or MeaningComputer()
        self.language = language or LanguageEngine()
        self.evolution = evolution or EvolutionLog()
        self.profiles = profiles or DeploymentProfiles()

    def run(self, semantic=None, emotional=None, contextual=None,
            historical=None, render=None, reference=None, world_series=None,
            metrics=None, context_vector=None, evidence_ok=True,
            now=None, sequence=None, architect_instruction=None,
            environment="local"):
        ctx = {"inputs": self._inputs(semantic, emotional, contextual,
                                      historical, render, reference,
                                      world_series, metrics, context_vector,
                                      evidence_ok, now, sequence,
                                      architect_instruction)}
        ctx["profile"] = self.profiles.select(environment)
        for stage in STAGES:
            self.step(stage, ctx)
        ctx["trace"] = {stage: ctx[stage] for stage in STAGES}
        ctx["result"] = self.result(ctx)
        return ctx

    def step(self, stage, ctx):
        if stage not in STAGES:
            raise ValueError("unknown loop stage %r" % stage)
        ordering = self._ordering(stage, ctx)
        if ordering is not None:
            self.require(ctx, ordering)
        if stage == "sense":
            ctx["sense"] = ctx["inputs"]
        elif stage == "interpret":
            ctx["interpret"] = self._interpret(ctx)
        elif stage == "stabilize":
            ctx["stabilize"] = self._stabilize(ctx)
        elif stage == "decide":
            ctx["decide"] = self._decide(ctx)
        elif stage == "express":
            ctx["express"] = self._express(ctx)
        elif stage == "log":
            ctx["log"] = self._log(ctx)
        elif stage == "reflect":
            ctx["reflect"] = self._reflect(ctx)
        return ctx

    def result(self, ctx):
        return {
            "ok": bool(ctx["express"].get("meaning", {}).get("ok", False)),
            "meaning": ctx["express"]["meaning"],
            "language": ctx["express"]["language"],
            "state": ctx["stabilize"],
            "fusion": ctx["decide"]["fusion"],
            "confidence": ctx["decide"]["confidence"],
            "safety": ctx["decide"]["safety"],
            "reports": ctx["log"],
            "stages": list(STAGES),
        }

    def require(self, ctx, stage):
        if stage not in ctx:
            raise RuntimeError(
                "loop stage %r skipped; cannot continue before it runs"
                % stage)

    def _ordering(self, stage, ctx):
        prior = ()
        if stage == "interpret":
            prior = ("sense",)
        elif stage == "stabilize":
            prior = ("interpret",)
        elif stage == "decide":
            prior = ("stabilize",)
        elif stage == "express":
            prior = ("decide",)
        elif stage == "log":
            prior = ("express",)
        elif stage == "reflect":
            prior = ("log",)
        for item in prior:
            if item not in ctx:
                return item
        return None

    def _inputs(self, semantic, emotional, contextual, historical, render,
                reference, world_series, metrics, context_vector, evidence_ok,
                now, sequence, architect_instruction):
        return {
            "semantic": semantic or {},
            "emotional": emotional or {},
            "contextual": contextual or {},
            "historical": historical or {},
            "render": render or {},
            "reference": reference,
            "world_series": world_series,
            "metrics": metrics,
            "context_vector": context_vector,
            "evidence_ok": bool(evidence_ok),
            "now": now,
            "sequence": sequence,
            "architect_instruction": architect_instruction,
        }

    def _interpret(self, ctx):
        inputs = ctx["sense"]
        encoded = self.encoder.encode(
            semantic=inputs["semantic"],
            emotional=inputs["emotional"],
            contextual=inputs["contextual"],
            historical=inputs["historical"],
            render=inputs["render"],
            reference=inputs["reference"],
        )
        return {"encoded": encoded}

    def _stabilize(self, ctx):
        inputs = ctx["sense"]
        encoded = ctx["interpret"]["encoded"]
        series = inputs["world_series"] or first_series(inputs["historical"])
        state = self.state.compute(
            encoded,
            world_series=series,
            reference=inputs["reference"],
            metrics=inputs["metrics"],
        )
        if inputs["world_series"] is not None:
            state = dict(state) if isinstance(state, dict) else state
            state["world_structure"] = world_structure_digest(series)
        return state

    def _decide(self, ctx):
        inputs = ctx["sense"]
        encoded = ctx["interpret"]["encoded"]
        state = ctx["stabilize"]
        profile = ctx["profile"]
        fusion = self.fusion.compute(
            encoded, state=state, context_vector=inputs["context_vector"])
        confidence = self.confidence.score(
            state=state,
            evidence_ok=inputs["evidence_ok"],
            reference=inputs["reference"],
        )
        relevance = self.relevance.evaluate(
            fused_channels=fusion.get("channels"),
            state=state,
            reference=inputs["reference"],
        )
        safety = self.safety.enforce(
            encoded=encoded, state=state, fusion=fusion,
            series=inputs["world_series"],
        )
        return {
            "fusion": fusion,
            "confidence": confidence,
            "relevance": relevance,
            "safety": safety,
            "profile": profile["environment"],
        }

    def _express(self, ctx):
        state = ctx["stabilize"]
        decide = ctx["decide"]
        alignment = decide["relevance"]
        safety = decide["safety"]
        meaning = self.meaning.compute(
            state=state,
            fusion=decide["fusion"],
            alignment=alignment,
            safety=safety,
            reference=ctx["sense"].get("reference"),
        )
        language = self.language.generate(meaning)
        return {"meaning": meaning, "language": language}

    def _log(self, ctx):
        encoded = ctx["interpret"]["encoded"]
        decision = build_decision_report(ctx, encoded=encoded)
        evidence = build_evidence_report(ctx, encoded=encoded)
        stability = build_stability_report(ctx)
        return {
            "decision": decision,
            "evidence": evidence,
            "stability": stability,
        }

    def _reflect(self, ctx):
        proposal = self.evolution.propose(
            "identity", {"anchors": "static"})
        instruction = ctx["sense"].get("architect_instruction")
        changes = []
        if instruction and str(instruction).strip():
            for surface in LOCKED_SURFACES:
                entry = self.evolution.record(
                    surface, {"note": "reflection"},
                    architect_instruction=instruction,
                    now=ctx["sense"].get("now"),
                    sequence=ctx["sense"].get("sequence"),
                )
                changes.append(entry)
        return {
            "proposal": proposal,
            "changes": changes,
            "architect_applied": [c for c in changes if c.get("allowed")],
            "evolved": bool(any(c.get("allowed") for c in changes)),
        }


def first_series(historical=None):
    """First list-valued feature in a historical mapping, if any."""
    for value in (historical or {}).values():
        if isinstance(value, (list, tuple)) and len(value) > 1:
            return value
    return None


def world_structure_digest(series):
    """Runtime/evidence bridge: fold an explicit world-observation series
    against the stored, review-only world ledger.

    Called from ``_stabilize`` only when the caller supplied a live
    ``world_series`` (a derived historical series never triggers it, keeping
    the loop's frame deterministic for fixed inputs). The substrate is
    imported lazily and every failure degrades to None, so the portable
    runtime stays free of project-root coupling and never writes.
    """
    try:
        from maya_world_model import world_structure_summary
    except Exception:
        return None
    try:
        return world_structure_summary(world_series=series)
    except Exception:
        return None


INTELLIGENCE = IntelligenceLoop()


def run(*args, **kwargs):
    return INTELLIGENCE.run(*args, **kwargs)


def step(*args, **kwargs):
    return INTELLIGENCE.step(*args, **kwargs)