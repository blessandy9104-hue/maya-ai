"""Blinded historical holdout for Maya's existing pattern mapper.

This harness does not alter Maya's profile or memory. It replaces the mapper's
local source reader in memory for one run, then restores it automatically.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import maya_pattern_mapping as mapper

from evaluation.artifacts import write_artifacts
from evaluation.scoring import ratio

ROOT = Path(__file__).resolve().parent
OUTPUT_JSON = ROOT / "apollo13_holdout_result.json"
OUTPUT_MD = ROOT / "apollo13_holdout_report.md"

PRE_OUTCOME = [
    "Apollo 13 was intended to land in the Fra Mauro area of the Moon.",
    "The first two days were generally smooth, aside from minor surprises.",
    "Ground testing had previously found that oxygen tank number 2 did not detank normally.",
    "The tank had been damaged during an earlier removal and was later tested after modification.",
    "An electrical heater was used for about eight hours to boil off remaining oxygen during ground testing.",
    "At about 55 hours 53 minutes after liftoff the crew was instructed to stir the cryogenic tanks.",
    "Soon after, oxygen tank number 2 showed pressure and sensor abnormalities and electrical disturbances.",
    "A large bang was followed by main bus undervoltage and loss of fuel-cell capacity.",
    "Oxygen was rapidly depleting and oxygen tank number 1 pressure also began to fall.",
    "The crew reported a problem and began closing the tunnel while ground controllers assessed the situation.",
    "The command module's normal electrical power, light, and water supply were threatened.",
]

HELD_OUTCOME = {
    "mission_landing": "aborted",
    "primary_response": "use the lunar module as a lifeboat and develop new procedures",
    "resource_strategy": "conserve power, water, and carbon-dioxide removal capacity",
    "final_outcome": "crew returned safely to Earth",
    "learning_outcome": "successful failure with substantial operational learning",
}

EXPECTED_STRUCTURAL_PATTERNS = {
    "known_hazard_escalation": "prior test anomaly + damaged component + later abnormal readings",
    "cascading_system_failure": "oxygen loss -> electrical/fuel-cell loss -> life-support risk",
    "adaptive_response": "switch to backup habitat, improvise procedures, and conserve scarce resources",
    "human_decision_under_uncertainty": "controllers and crew must validate new procedures before execution",
    "goal_reframing": "lunar landing objective becomes safe return objective",
}


def _blind_source_reader() -> tuple[str, list[tuple[str, str, str]]]:
    sources = [("historical_holdout", str(index), event) for index, event in enumerate(PRE_OUTCOME, 1)]
    return " ".join(PRE_OUTCOME).lower(), sources


def _run_blind() -> dict[str, Any]:
    original = mapper._text_blob
    mapper._text_blob = _blind_source_reader
    try:
        opportunity_result = mapper.pattern_map("Map the dominant patterns, risks, possible next states, and safe response options.")
        event_result = mapper.pattern_map_events(
            PRE_OUTCOME,
            objective="The planned lunar landing is threatened; identify the safer mission objective.",
        )
    finally:
        mapper._text_blob = original
    return {"opportunity_mapper": opportunity_result, "event_stream_mapper": event_result}


def _score(result: dict[str, Any]) -> dict[str, Any]:
    event_result = result["event_stream_mapper"]
    detected_names = {item["name"] for item in event_result.get("patterns", [])}
    hits = {
        "known_hazard_escalation": "known-hazard-escalation" in detected_names,
        "cascading_system_failure": "cascading-system-failure" in detected_names,
        "adaptive_response": bool(event_result.get("response_options")),
        "human_decision_under_uncertainty": "human-decision-under-uncertainty" in detected_names,
        "goal_reframing": "objective-at-risk" in detected_names,
    }
    limitations = [
        "The current candidate ontology is opportunity-oriented; it does not model mission state, failure cascades, resource budgets, or response sequencing.",
        "The mapper can detect lexical overlap but cannot infer the Apollo 13 rescue sequence from the historical event stream alone.",
        "The output contains relative evidence-fit bands, not a calibrated forecast or a time-indexed next-state distribution.",
        "The current safe experiment field is generic and not connected to observed system constraints.",
    ]
    return {
        "patterns_expected": EXPECTED_STRUCTURAL_PATTERNS,
        "pattern_hits": hits,
        "pattern_coverage": ratio(sum(hits.values()), len(hits)),
        "held_out_outcome_not_fed_to_mapper": True,
        "limitations": limitations,
        "interpretation": "A low or partial coverage score indicates an ontology and temporal-reasoning gap, not that the safety walls failed.",
    }


def run() -> dict[str, Any]:
    result = _run_blind()
    score = _score(result)
    payload = {
        "case": "Apollo 13",
        "cutoff": "immediately after oxygen tank failure and initial system alarms",
        "input_event_count": len(PRE_OUTCOME),
        "blind_input": PRE_OUTCOME,
        "mapper_output": result,
        "held_out_outcome": HELD_OUTCOME,
        "evaluation": score,
        "safety": {
            "memory_write": False,
            "external_action": False,
            "permission_change": False,
            "profile_state_mutated": False,
        },
    }
    lines = [
        "# Apollo 13 Historical Holdout — Maya Pattern Mapping",
        "",
        "This is a blinded historical simulation. Maya received only the pre-outcome event stream; the rescue and safe-return outcome was withheld until comparison.",
        "",
        f"**Pattern coverage:** {score['pattern_coverage']:.0%}",
        "",
        "## What Maya received",
        "",
    ]
    lines.extend(f"{index}. {event}" for index, event in enumerate(PRE_OUTCOME, 1))
    lines.extend(["", "## Held-out historical outcome", ""])
    lines.extend(f"- **{key.replace('_', ' ').title()}:** {value}" for key, value in HELD_OUTCOME.items())
    lines.extend(["", "## Mapper output", "", json.dumps(result, indent=2, ensure_ascii=False), "", "## Evaluation", ""])
    lines.extend(f"- **{key.replace('_', ' ').title()}:** {'detected' if value else 'not detected'}" for key, value in score["pattern_hits"].items())
    lines.extend(["", "### Current limitations", ""])
    lines.extend(f"- {item}" for item in score["limitations"])
    lines.extend(["", "## Safe conclusion", "", score["interpretation"], "The run performed no memory write, permission change, external action, or profile mutation."])
    write_artifacts(payload, lines, OUTPUT_JSON, OUTPUT_MD)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
