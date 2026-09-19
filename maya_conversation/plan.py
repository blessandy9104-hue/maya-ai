"""Response planning (Batch 8G).

Synthesizes interpretation + state + routes + domain results into one
:class:`ResponsePlan` that constrains the natural-language surface:

- objective  (answer / explain / compare / clarify / correct / reason /
  challenge / summarize / plan / refuse / acknowledge_uncertainty /
  ask_missing_information)
- epistemic language rules (how uncertainty must be phrased)
- register, length target, modality, safety holds
- ``deterministic_allowed`` — the *narrow* case where the structured pathway
  fully covers the question and no language model is needed. Everything else
  flows to the LLM wording path (always the default).

The planner is deterministic and defensive: unknown combinations fall back to
plain ``answer`` with ``deterministic_allowed = False``.
"""
from __future__ import annotations

OBJECTIVES = {
    "answer", "explain", "compare", "clarify", "correct", "reason",
    "challenge", "summarize", "plan", "refuse",
    "acknowledge_uncertainty", "ask_missing_information",
}

_REGISTERS = ("measured", "decisive", "parent_like", "playful", "even_tempered",
              "caring", "matter_of_fact", "direct", "precise")

_LENGTH = {
    "answer": 48, "explain": 64, "compare": 80, "clarify": 48, "correct": 64,
    "reason": 96, "challenge": 64, "summarize": 48, "plan": 96, "refuse": 32,
    "acknowledge_uncertainty": 48, "ask_missing_information": 48,
}

_EXECUTION_WORDS = {
    "execute", "run this", "go ahead and", "please rewrite the file",
    "modify the file", "change the code", "apply the change", "just do it",
    "mkdir", "delete the", "remove the", "create a new file",
}


def plan_response(interpretation, state=None, routes=None, domain_results=None):
    """Compute the ResponsePlan for one turn. All inputs optional-safe."""
    interpretation = interpretation or {}
    state = state
    routes = routes or {}
    domain_results = domain_results or {}

    utterance = interpretation.get("utterance", "")
    intent = interpretation.get("primary_intent", "")
    candidates = interpretation.get("candidates", []) or []
    is_correction = bool(interpretation.get("is_correction"))
    compatible = bool(interpretation.get("ambiguous"))
    domains = list(routes.get("domains", []) or [])
    low = utterance.lower()

    philosophy = domain_results.get("philosophy") or {}
    psychology = domain_results.get("psychology") or {}

    objective = "answer"
    content_points = []
    evidence_rules = []
    holds = []

    modality = interpretation.get("modality", "text")

    # --- corrections ------------------------------------------------------
    if is_correction:
        objective = "correct"
        content_points.append(
            "acknowledge the correction; re-answer the prior content point "
            "with the corrected framing (never claim the earlier version was "
            "fine)")
        evidence_rules.append("mark the correction as applied, do not rewrite "
                              "history")

    # --- ambiguity / clarification need -----------------------------------
    elif compatible and len(candidates) > 1 and intent in (
            "statement_or_general_request", "reason_or_cause", "process_or_explanation"):
        objective = "clarify"
        content_points.append("ask which of the candidate interpretations the "
                              "user meant (list them plainly)")

    # --- philosophy -------------------------------------------------------
    elif "philosophy" in domains and philosophy.get("engaged"):
        topic = philosophy.get("topic")
        position_count = len(philosophy.get("positions") or [])
        if position_count > 1:
            objective = "compare"
        elif philosophy.get("representation_kind") == "scaffold_fallback":
            objective = "acknowledge_uncertainty"
        else:
            objective = "reason"
        content_points.append(
            "present the structured positions for the topic with their "
            "sources" if topic else "state that no curated entry matched and "
            "offer the scaffold")
        content_points.append("retain disagreement: opposing positions are "
                              "given at full strength; do not flatten")
        evidence_rules.append("every position is labeled as a philosophical "
                              "position (DISPUTED), never as fact")
        holds.append("philosophy_positions_only")

    # --- psychology -------------------------------------------------------
    elif "psychology" in domains and psychology.get("engaged"):
        objective = "explain"
        content_points.append(
            "name the pattern as a described behavior, present 2-3 clearly "
            "labeled hypotheses with confident levels marked as heuristic "
            "estimates")
        severity = psychology.get("uncertainty", 1.0)
        if severity > 0.3:
            content_points.append("use an explicit uncertainty sentence from "
                                  "the entropy-derived uncertainty")
        content_points.append("close with the strategy's clarifying question")
        evidence_rules.append(
            "never emit a diagnostic conclusion (never_diagnosis invariant)")
        if psychology.get("clinical_claim_present"):
            objective = "refuse"
            content_points.append("refuse to confirm/deny any diagnosis; "
                                  "redirect to a qualified professional while "
                                  "still addressing the practical behavior")
            holds.append("diagnosis_out_of_scope")

    # --- mathematics ------------------------------------------------------
    elif "mathematics" in domains:
        objective = "answer"
        content_points.append(
            "answer the numeric/question using math only where the route "
            "justified it; mark calculated values CALCULATED")
        evidence_rules.append("probabilities/entropy values come from "
                              "maya_math (8F); state the basis")
        if not compatible:
            evidence_rules.append("if the numbers are insufficient, state "
                                  "that clearly instead of inventing values")

    # --- evidence / world -------------------------------------------------
    elif "evidence" in domains:
        objective = "answer"
        content_points.append(
            "weigh the claims against available evidence and name the "
            "epistemic status of each claim")
        evidence_rules.append("reported/hearsay claims stay REPORTED; do not "
                              "upgrade user hearsay to fact")

    # --- planning ---------------------------------------------------------
    elif "planning" in domains:
        objective = "plan"
        content_points.append("give a short, concrete step sequence with "
                              "explicit assumptions; ask for one refinement "
                              "before deepening")

    # --- plain ------------------------------------------------------------
    elif not domains:
        objective = _objective_for_question(intent, utterance)
        if intent in ("maya_capability_or_action", "polite_request_or_capability") \
                and _execution_requested(low):
            objective = "refuse"
            holds.append("requires_mission_wall_review")
            content_points.append("refuse to perform unverified code/system "
                                  "actions; route into the guarded command "
                                  "path")

    # --- unresolved question from a prior turn ----------------------------
    if interpretation.get("resolved_question_id") and objective == "answer":
        content_points.append("connect the answer explicitly to the earlier "
                              "unresolved question")

    # --- epistemological uncertainty on principle -------------------------
    if not objective == "clarify" and not objective == "refuse" and \
            not is_correction and (not domains or compatible):
        evidence_rules.append("claim no certainty beyond the available "
                              "evidence; when uncertain, say so")

    # --- register + length + modality -------------------------------------
    register = "matter_of_fact"
    if "philosophy" in domains:
        register = "measured"
    elif "psychology" in domains:
        register = "caring"
    elif is_correction:
        register = "direct"
    elif "mathematics" in domains:
        register = "precise"
    elif "planning" in domains:
        register = "decisive"

    length_target = _LENGTH.get(objective, 48)

    # --- deterministic-allowed (narrow, structured only) -------------------
    deterministic_allowed = False
    if "philosophy" in domains and philosophy.get("engaged") and \
            philosophy.get("representation_kind") == "scholarly_catalog" and \
            intent not in ("maya_capability_or_action",):
        deterministic_allowed = True
    elif "psychology" in domains and psychology.get("engaged") and \
            not psychology.get("clinical_claim_present"):
        deterministic_allowed = True

    return {
        "objective": objective,
        "deterministic_allowed": deterministic_allowed,
        "content_points": content_points,
        "evidence_rules": evidence_rules,
        "holds": holds,
        "register": register,
        "length_target": length_target,
        "modality": modality,
        "domains": domains,
        "uncertainty": round(
            float((domain_results.get("psychology") or {}).get("uncertainty",
                                                               0.0)), 4),
    }


def _objective_for_question(intent, utterance):
    low = (utterance or "").lower()
    if any(marker in low for marker in ("compare", "contrast", "difference "
                                        "between", "versus", "vs ")):
        return "compare"
    if intent in ("choice_or_comparison",):
        return "compare"
    if any(marker in low for marker in ("why", "reason", "cause")):
        return "reason"
    if intent in ("reason_or_cause",):
        return "reason"
    if any(marker in low for marker in ("how", "explain", "what is",
                                        "what does", "tell me about")):
        return "explain"
    return "answer"


def _execution_requested(low):
    return any(token in low for token in _EXECUTION_WORDS)


# referenced by the verification suite to confirm the objective vocabulary
def objective_vocabulary():
    return sorted(OBJECTIVES)