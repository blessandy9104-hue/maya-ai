"""Seed-level proactive suggestions for Mother Maya.

The engine is deliberately review-only. It creates conditional, explainable
options from approved evidence; it never changes memory, executes actions, or
turns a hypothesis into a decision.
"""
from __future__ import annotations

from typing import Any

SEED_VERSION = "0.2"


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _option(option_id: str, description: str, individual_benefits: list[str], human_benefits: list[str], possible_harms: list[str], access_barriers: list[str], reversibility: str, uncertainty: str, assumptions: list[str], why_ranked: str) -> dict[str, Any]:
    return {
        "id": option_id,
        "description": description,
        "individual_benefits": individual_benefits,
        "human_benefits": human_benefits,
        "possible_harms": possible_harms,
        "access_barriers": access_barriers,
        "reversibility": reversibility,
        "uncertainty": uncertainty,
        "assumptions": assumptions,
        "why_ranked": why_ranked,
    }


def generate_seed_suggestion(scenario: dict[str, Any]) -> dict[str, Any]:
    goal = str(scenario.get("goal", "")).strip()
    constraints = _clean_list(scenario.get("constraints", []))
    signals = _clean_list(scenario.get("signals", []))
    circumstances = _clean_list(scenario.get("circumstances", []))
    affected_interests = _clean_list(scenario.get("affected_interests", []))
    if not goal:
        return {
            "status": "needs_goal",
            "suggestion": "State the desired outcome before narrowing options.",
            "label": "seed_hypothesis",
            "seed_version": SEED_VERSION,
            "human_review_status": "clarification_needed",
        }

    route = "Start with the smallest reversible test that produces evidence toward the goal."
    if constraints:
        route += " Respect the current constraints rather than assuming they will disappear."
    if signals:
        route += " Compare the signals over time before treating them as a stable pattern."

    option_a = _option(
        "A",
        route,
        ["Creates evidence with limited commitment.", "Keeps the person's control over the next step."],
        ["Can produce a useful learning signal without requiring broad adoption.", "Makes the reasoning inspectable rather than opaque."],
        ["A small test can still consume scarce time or attention.", "Early signals may be misleading."],
        constraints or ["Unknown access barriers; clarify before acting."],
        "high",
        "medium",
        ["The stated goal is current and approved.", "The test can be stopped without material harm."],
        "Ranked first because it is reversible and evidence-generating while preserving agency.",
    )
    option_b = _option(
        "B",
        "Pause implementation and gather more context from relevant people, sources, or constraints before testing.",
        ["May reduce avoidable rework and improve fit.", "Can surface a better-defined goal."],
        ["May reveal affected interests or access barriers that a solo test would miss."],
        ["Delay can reduce momentum.", "Additional information may be unavailable or biased."],
        ["Time, language, money, or access to trustworthy sources may limit research."],
        "high",
        "high",
        ["Relevant context can be obtained without collecting unnecessary private information."],
        "Kept as a credible alternative because uncertainty or conflict may justify clarification first.",
    )

    convergence_status = "convergent"
    conflict_note = "No affected interests were supplied; confirm them before treating this as a complete human-benefit review."
    if affected_interests:
        convergence_status = "partially_convergent"
        conflict_note = "Potentially affected interests were identified; compare benefits and harms with them before any consequential step."
    if scenario.get("conflict"):
        convergence_status = "conflict_identified"
        conflict_note = str(scenario["conflict"]).strip() or "A conflict was identified; preserve informed choice and explain the trade-off."

    return {
        "status": "hypothesis_only",
        "label": "mother_maya_seed_hypothesis",
        "seed_version": SEED_VERSION,
        "individual_goal": goal,
        "goal": goal,
        "current_constraints": constraints,
        "relevant_constraints": constraints,
        "relevant_circumstances": circumstances,
        "observed_signals": signals,
        "affected_interests": affected_interests,
        "options": [option_a, option_b],
        "preferred_path": "A",
        "convergence_status": convergence_status,
        "conflict_note": conflict_note,
        "narrowed_direction": route,
        "alternative": "Keep one credible alternative route and state what evidence would change the ranking.",
        "evidence_and_unknowns": {
            "approved_evidence": signals,
            "unknowns": ["Which constraints are temporary?", "What evidence would change the ranking?"],
        },
        "next_review_question": "What new evidence would confirm, weaken, or change this direction?",
        "human_review_status": "awaiting_review",
        "memory_update": "not_performed",
        "external_action": "not_performed",
        "approval_required_for_change": True,
    }


def sample_scenario() -> dict[str, Any]:
    return {
        "goal": "Build a useful software project that can grow into a sustainable service.",
        "constraints": ["limited time", "limited budget", "one working computer"],
        "signals": ["repeated interest in testing", "desire for practical progress", "need to prove usefulness before expansion"],
        "circumstances": ["early-stage project", "uncertain future demand"],
        "affected_interests": ["the builder", "future users", "people affected by the service"],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(generate_seed_suggestion(sample_scenario()), indent=2, ensure_ascii=False))
