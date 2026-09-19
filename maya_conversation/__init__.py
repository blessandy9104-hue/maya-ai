"""Maya conversational intelligence — Batch 8G.

A deterministic, additive conversational layer for Maya:

    text/voice input
      -> interpretation (intent, candidates, references, corrections,
                         epistemic-claim labels)
      -> relevance-driven routing (mathematics | psychology | philosophy |
                                   evidence | planning | none)
      -> domain pathways (psychology hypotheses, philosophy argument
                          structure, math notes, evidence statusing)
      -> response planning (objective, evidence language, register, holds)
      -> conversational-state update (topic, mode, unresolved questions,
                                      corrections, constraints)

Honesty invariants are enforced structurally across every module here:

- facts/inferences/hypotheses/interpretations/philosophical positions always
  keep distinct labels; nothing is silently upgraded.
- psychology never diagnoses; philosophy never asserts a final truth; math is
  engaged (via 8F) only when its entropy/probability actually informs the
  answer.
- voice is interface-only; there is no fake STT/TTS.
- all modules are deterministic: no clock, no randomness, no file writes.

Integration contract (:func:`orchestrate_turn`) is fail-open: every step is
defensive, and a raised exception from any pathway inside
:func:`orchestrate_turn` is caught and reported as ``ok=False`` so the chat
layer always preserves its pre-8G behavior.
"""
from __future__ import annotations

from . import state as state_module
from .state import ConversationState
from .interpret import (interpret_input, EPISTEMIC_STATUSES,
                        EPISTEMIC_STATUSES_ORDERED)
from .orchestrate import route
from . import psychology as psychology_module
from . import philosophy as philosophy_module
from . import plan as plan_module
from . import voice as voice_module
from .update import apply_turn
from .cooperate import cooperate, AGREEMENT, AGREEMENT_WITH_CAVEAT, \
    DISAGREEMENT, SINGLE_SOURCE, FALLBACK_USED, NO_ENGAGEMENT
from .adaptivity import assess_complexity, DEPTH_FAST, DEPTH_STANDARD, \
    DEPTH_DEEP
from .learning import LearningLedger, EVENT_PROPOSAL, EVENT_OUTCOME, \
    EVENT_CORRECTION
from .method_selection import MethodRegistry, plan_improvement, \
    select_method, APPROVED
from .profile import CapabilityProfile, DEFAULT_USER, SCOPE_ANY
from .generalize import characterize_task, to_key, TaskMemory, task_similarity, \
    transfer_boundary_check
from .hypothesis import GeneralizationHypothesis, hypothesis_from_experience
from .unseen_testing import classify_unseen, run_unseen_trial, \
    trial_measures, accuracy_vs_baseline
from .error_generalize import ErrorMemory
from .portfolio import MethodPortfolio
from .adaptive import AdaptiveScheduler
from .learning_metrics import LearningMetrics
from .self_improve import ControlledImprovement
from .coop_challenge import cooperative_challenge, ChallengeMetaphor
from .resource_profiles import ResourceProfile, ResourcePolicy

__all__ = [
    "ConversationState",
    "interpret_input",
    "route",
    "plan_response",
    "apply_turn",
    "orchestrate_turn",
    "build_orchestrator",
    "psychology_pathway",
    "philosophy_pathway",
    "catalog_topics",
    "voice",
    "state_module",
    "EPISTEMIC_STATUSES",
    "EPISTEMIC_STATUSES_ORDERED",
    "cooperate",
    "AGREEMENT",
    "AGREEMENT_WITH_CAVEAT",
    "DISAGREEMENT",
    "SINGLE_SOURCE",
    "FALLBACK_USED",
    "NO_ENGAGEMENT",
    "assess_complexity",
    "DEPTH_FAST",
    "DEPTH_STANDARD",
    "DEPTH_DEEP",
    "LearningLedger",
    "EVENT_PROPOSAL",
    "EVENT_OUTCOME",
    "EVENT_CORRECTION",
    "MethodRegistry",
    "plan_improvement",
    "select_method",
    "APPROVED",
    "CapabilityProfile",
    "DEFAULT_USER",
    "SCOPE_ANY",
    "characterize_task",
    "to_key",
    "TaskMemory",
    "task_similarity",
    "transfer_boundary_check",
    "GeneralizationHypothesis",
    "hypothesis_from_experience",
    "classify_unseen",
    "run_unseen_trial",
    "trial_measures",
    "accuracy_vs_baseline",
    "ErrorMemory",
    "MethodPortfolio",
    "AdaptiveScheduler",
    "LearningMetrics",
    "ControlledImprovement",
    "cooperative_challenge",
    "ChallengeMetaphor",
    "ResourceProfile",
    "ResourcePolicy",
]


def psychology_pathway(*args, **kwargs):
    return psychology_module.psychology_pathway(*args, **kwargs)


def philosophy_pathway(*args, **kwargs):
    return philosophy_module.philosophy_pathway(*args, **kwargs)


def plan_response(interpretation, state=None, routes=None, domain_results=None):
    return plan_module.plan_response(interpretation, state=state, routes=routes,
                                     domain_results=domain_results)


def catalog_topics():
    return philosophy_module.catalog_topics()


def orchestrate_turn(text, session_id=None, history=None,
                     state=None, *, modality="text"):
    """Run one turn through the full conversational layer (fail-open).

    Returns a dict always; never raises. The chat integration consumes
    ``result["plan"]`` and ``result["ok"]``; when ``ok`` is False (any
    pathway raised or inputs were unusable), the chat layer falls back to its
    pre-8G behavior unchanged.

    ``state`` may be supplied to keep continuity across turns; otherwise a
    fresh state (session_id or default) is created.
    """
    from .state import ConversationState as _CS

    try:
        if not isinstance(text, str) or not text.strip():
            return {
                "ok": False, "reason": "empty_input", "plan": None,
                "interpretation": None, "state": state, "routes": None,
                "domain_results": None,
            }
        current = state
        if current is None:
            current = _CS(session_id=str(session_id or "session1"))
        current = current.start_turn(modality=modality)

        interpretation = interpret_input(text, state=current, history=history)
        routes = route(interpretation, state=current)
        domains = routes.get("domains", []) or []

        domain_results = {}
        for domain in domains:
            if domain == "psychology":
                domain_results["psychology"] = psychology_module.psychology_pathway(
                    text, state=current, route=routes)
            elif domain == "philosophy":
                domain_results["philosophy"] = philosophy_module.philosophy_pathway(
                    text, state=current, route=routes)

        response_plan = plan_module.plan_response(
            interpretation, state=current, routes=routes,
            domain_results=domain_results)

        updated = apply_turn(current, interpretation, response_plan)
        return {
            "ok": True,
            "reason": "",
            "plan": response_plan,
            "interpretation": interpretation,
            "state": updated,
            "routes": routes,
            "domain_results": domain_results,
        }
    except Exception as error:  # fail-open: preserve pre-8G chat behavior
        return {
            "ok": False,
            "reason": "%s: %s" % (type(error).__name__, error),
            "plan": None,
            "interpretation": None,
            "state": state,
            "routes": None,
            "domain_results": None,
        }


def build_orchestrator(session_id="session1"):
    """Factory returning a callable bound to one session's state.

    ``orchestrator(text, *, history=None, modality="text")`` keeps continuity
    internally across calls and returns the same shape as
    :func:`orchestrate_turn` while carrying the current state.
    """
    current_state = {"state": ConversationState(session_id=session_id)}

    def orchestrator(text, *, history=None, modality="text"):
        result = orchestrate_turn(
            text, session_id=session_id, history=history,
            state=current_state["state"], modality=modality)
        if result.get("ok") and isinstance(result.get("state"), ConversationState):
            current_state["state"] = result["state"]
        return result

    return orchestrator


def render_deterministic(result) -> str:
    """Render a *narrow* deterministic reply from structured domain output.

    Used only when ``plan.deterministic_allowed`` is True (psychology
    hypothesis presentation or philosophy argument sketch — both fully
    covered by validated structure with no need for an LLM). Everything else
    keeps the LLM path. Returns None when nothing deterministic is renderable.
    """
    if not result or not isinstance(result, dict):
        return None
    plan = result.get("plan") or {}
    domains = plan.get("domains") or []
    domain_results = result.get("domain_results") or {}
    interpretation = result.get("interpretation") or {}

    lines = []

    if plan.get("objective") == "correct":
        lines.append("Understood — corrected. Here is the adjusted reading:")

    psychology = domain_results.get("psychology") or {}
    if "psychology" in domains and psychology.get("engaged"):
        lines.append("I hear a pattern in what you described — I can offer "
                     "possible readings, but I won't turn them into a label "
                     "or diagnosis.")
        for hypothesis in (psychology.get("hypotheses") or []):
            lines.append("- Possible: %s (heuristic confidence %s)" % (
                hypothesis["label"], hypothesis["confidence"]))
        if psychology.get("clinical_claim_present"):
            lines.append("I can't confirm or rule out a clinical condition — "
                         "that needs a qualified professional.")
        entropy = psychology.get("entropy") or {}
        if entropy.get("computed"):
            lines.append("Among the readings above, uncertainty is %s (0-1, "
                         "normalized entropy over hypothesis confidences)." %
                         round(float(entropy.get("entropy", 0.0)), 3))
        ask_q = (psychology.get("strategy") or {}).get("ask_question")
        if not psychology.get("clinical_claim_present") and ask_q:
            lines.append(ask_q)

    philosophy = domain_results.get("philosophy") or {}
    if "philosophy" in domains and philosophy.get("engaged"):
        if philosophy.get("representation_kind") == "scaffold_fallback":
            lines.append(philosophy.get("framer") or "")
            lines.append("Could you give me a more specific framing so I can "
                         "engage the arguments seriously?")
        else:
            title = philosophy.get("title") or "the question"
            lines.append("On %s, the philosophical positions differ — here "
                         "are the main ones." % title)
            for position in (philosophy.get("positions") or []):
                lines.append("- %s (%s): \u2014 %s" % (
                    position["name"], position["tradition"],
                    position["argument"]))
            disagreement = philosophy.get("disagreement") or {}
            if disagreement:
                lines.append(disagreement.get("note") or "")
            lines.append("None of these is 'the fact' here — philosophy "
                         "keeps these contested.")

    if not lines:
        return None
    return " ".join(line.strip() for line in lines if line.strip())