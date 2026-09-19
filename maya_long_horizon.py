"""Long-horizon scenario evaluation and hardening for Maya.

This module evaluates scenario reflections as structured possibilities. It does
not predict a user's future, assign a calibrated probability, write memory, or
choose a path. It is intentionally deterministic and local-only.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

REQUIRED_FIELDS = (
    "title",
    "gains",
    "sacrifices",
    "trajectory",
    "emotional_cost",
    "risks",
    "assumptions",
    "reversible_experiment",
)

CERTAINTY_PATTERNS = (
    r"\bwill\b",
    r"\bguaranteed\b",
    r"\bguarantee\b",
    r"\binevitable\b",
    r"\balways\b",
    r"\bnever\b",
    r"\bdefinitely\b",
    r"\bthe right path\b",
    r"\bthe only path\b",
)

PROBABILITY_PATTERNS = (
    r"\b\d{1,3}%\b",
    r"\bprobability\s*(?:is|of)?\s*\d",
    r"\blikelihood\s*(?:is|of)?\s*\d",
)

QUALIFIED_REPLACEMENTS = {
    "will": "may",
    "guaranteed": "potentially strong",
    "guarantee": "support",
    "inevitable": "plausible",
    "always": "often",
    "never": "not necessarily",
    "definitely": "possibly",
    "the right path": "a potentially fitting path",
    "the only path": "one possible path",
}


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _missing_fields(scenario: dict[str, Any]) -> list[str]:
    missing = []
    for field in REQUIRED_FIELDS:
        value = scenario.get(field)
        if not value or (isinstance(value, list) and not any(str(item).strip() for item in value)):
            missing.append(field)
    return missing


def _find_matches(text: str, patterns: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [pattern for pattern in patterns if re.search(pattern, lowered)]


def evaluate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(_as_text(scenario.get(field)) for field in REQUIRED_FIELDS)
    missing = _missing_fields(scenario)
    certainty = _find_matches(text, CERTAINTY_PATTERNS)
    numeric_probability = _find_matches(text, PROBABILITY_PATTERNS)
    experiment = _as_text(scenario.get("reversible_experiment"))
    experiment_is_reversible = any(
        term in experiment.lower()
        for term in ("small", "reversible", "pilot", "prototype", "test", "one", "feedback")
    )

    checks = {
        "has_tradeoffs": bool(scenario.get("gains")) and bool(scenario.get("sacrifices")),
        "has_trajectory": bool(scenario.get("trajectory")),
        "has_emotional_cost": bool(scenario.get("emotional_cost")),
        "has_risks": bool(scenario.get("risks")),
        "has_assumptions": bool(scenario.get("assumptions")),
        "has_reversible_experiment": experiment_is_reversible,
        "no_absolute_certainty": not certainty,
        "no_unsupported_numeric_probability": not numeric_probability,
        "complete_structure": not missing,
    }
    score = round(sum(checks.values()) / len(checks) * 100)
    return {
        "title": scenario.get("title", "Untitled scenario"),
        "status": "ready_for_review" if all(checks.values()) else "needs_hardening",
        "validation_score": score,
        "checks": checks,
        "missing_fields": missing,
        "certainty_flags": certainty,
        "probability_flags": numeric_probability,
        "decision_owner": "human",
        "memory_update": "not_performed",
        "external_action": "not_performed",
        "note": "This is a structured possibility, not a prediction or instruction.",
    }


def harden_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    hardened = deepcopy(scenario)
    for field in REQUIRED_FIELDS:
        value = hardened.get(field)
        if isinstance(value, list):
            hardened[field] = [_qualify(str(item)) for item in value]
        elif value is not None:
            hardened[field] = _qualify(str(value))

    experiment = _as_text(hardened.get("reversible_experiment"))
    if not any(term in experiment.lower() for term in ("small", "reversible", "pilot", "prototype", "test", "one", "feedback")):
        hardened["reversible_experiment"] = "Run one small reversible pilot, gather feedback, and reassess before making a larger commitment."

    hardened["disclaimer"] = (
        "This scenario is a reflective possibility based on the stated assumptions. "
        "It is not a prediction, diagnosis, guarantee, or recommendation. Compare it "
        "with alternatives and test it through a small reversible experiment."
    )
    hardened["decision_owner"] = "human"
    hardened["memory_update"] = "not_performed"
    hardened["external_action"] = "not_performed"
    return hardened


def _qualify(text: str) -> str:
    result = text
    for source, replacement in QUALIFIED_REPLACEMENTS.items():
        result = re.sub(rf"\b{re.escape(source)}\b", replacement, result, flags=re.IGNORECASE)
    result = re.sub(r"\b(\d{1,3})%\b", r"an unverified quantitative estimate (\1 percent)", result, flags=re.IGNORECASE)
    return result


def evaluate_set(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    evaluations = [evaluate_scenario(scenario) for scenario in scenarios]
    titles = [item["title"] for item in evaluations]
    return {
        "status": "ready_for_review" if len(evaluations) >= 2 and all(item["status"] == "ready_for_review" for item in evaluations) else "needs_hardening",
        "scenario_count": len(evaluations),
        "alternative_paths_present": len(evaluations) >= 2,
        "evaluations": evaluations,
        "set_guardrails": {
            "single_path_recommendation_blocked": len(evaluations) < 2,
            "human_decision_required": True,
            "memory_updates": "not_performed",
            "external_actions": "not_performed",
        },
        "titles": titles,
    }


def render_scenario_set(scenarios: list[dict[str, Any]]) -> str:
    report = evaluate_set(scenarios)
    lines = [
        "Long-horizon scenario review",
        "These are structured possibilities, not predictions or instructions.",
        f"Scenarios compared: {report['scenario_count']}",
    ]
    for evaluation in report["evaluations"]:
        lines.append(f"- {evaluation['title']}: {evaluation['status']} ({evaluation['validation_score']}/100)")
        if evaluation["certainty_flags"]:
            lines.append("  Harden certainty language before presenting this scenario.")
        if evaluation["probability_flags"]:
            lines.append("  Remove unsupported numeric probability claims.")
    lines.append("Human choice remains required; no memory update or external action occurred.")
    return "\n".join(lines)
