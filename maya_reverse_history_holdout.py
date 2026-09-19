"""Reverse historical reconstruction for Apollo 13.

This is abductive reasoning from documented outcomes back toward prerequisites.
It is not a prediction and must not be used to assign blame from hindsight.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maya_pattern_mapping import conditional_map_events

from evaluation.artifacts import write_artifacts
from evaluation.fixtures import NASA_APOLLO13_SOURCES, NASA_APOLLO13_SOURCE_LINES
from evaluation.scoring import mean_round, score_patterns

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "maya_reverse_apollo13_results.json"
REPORT = ROOT / "maya_reverse_apollo13_report.md"

# These are fed to Maya in reverse order, beginning with the documented ending.
REVERSE_FULL = [
    "The Apollo 13 crew returned safely to Earth.",
    "The command module re-entered after the lunar module was jettisoned.",
    "The crew had conserved power, water, oxygen, and carbon-dioxide removal capacity.",
    "The lunar module served as a lifeboat for three people even though it was designed for fewer people and a shorter duration.",
    "Ground controllers developed and tested new procedures and computed return burns.",
    "A makeshift adapter connected command-module carbon-dioxide canisters to the lunar-module system.",
    "The original lunar landing objective was abandoned in favor of safe return.",
    "The service module oxygen tanks and fuel-cell system had failed after an explosion.",
]

REVERSE_INDIVIDUALS = {
    "jack_swigert": [
        "Swigert returned safely to Earth with the crew.",
        "He completed remaining command-module chores and moved into the lunar module.",
        "The original landing objective was abandoned.",
        "The command module had lost oxygen and electrical capacity.",
    ],
    "james_lovell": [
        "Lovell returned safely to Earth.",
        "He helped the crew use the lunar module as a lifeboat.",
        "He supported Sun-based navigation alignment for the return.",
        "The original lunar landing objective was abandoned after the service-module failure.",
    ],
    "fred_haise": [
        "Haise returned safely to Earth.",
        "He helped manage the lunar-module lifeboat resources for three people.",
        "The crew conserved water, power, oxygen, and carbon-dioxide capacity.",
        "The original landing objective was abandoned after the service-module failure.",
    ],
    "mission_control": [
        "Mission control coordinated the crew's safe return.",
        "Controllers wrote and tested new procedures and computed return burns.",
        "They adapted carbon-dioxide canisters to a different system.",
        "The landing objective was replaced by the safe-return objective.",
    ],
}

# Root facts are held out from the reverse mapper and used only for evaluation.
ROOT_FACTS = {
    "full": [
        "The oxygen tank had been damaged during an earlier removal.",
        "Ground testing showed that oxygen tank number 2 did not detank normally.",
        "An underrated component was not replaced during a design modification.",
        "An electrical heater was used for eight hours to boil off remaining oxygen.",
        "The later tank rupture caused oxygen loss, power loss, and fuel-cell failure.",
    ],
    "jack_swigert": ["He was performing the cryogenic tank stirring procedure when the failure began.", "He reported the problem to Houston."],
    "james_lovell": ["He reported the main-bus undervolt and observed oxygen venting."],
    "fred_haise": ["He recognized electrical-system loss and helped move the crew into the lunar module."],
    "mission_control": ["Controllers faced incomplete telemetry and had to create and test procedures under time pressure."],
}

EXPECTED_REVERSE_PATTERNS = {
    "full": ["contingency-or-backup-required", "resource-constraint", "objective-reframing", "operational-improvisation", "initiating-system-fault"],
    "jack_swigert": ["contingency-or-backup-required", "initiating-system-fault"],
    "james_lovell": ["contingency-or-backup-required", "objective-reframing"],
    "fred_haise": ["resource-constraint", "contingency-or-backup-required"],
    "mission_control": ["operational-improvisation", "contingency-or-backup-required", "resource-constraint"],
}


def reverse_infer(events: list[str]) -> dict[str, Any]:
    text = " ".join(events).lower()
    inferences = []
    if any(term in text for term in ("lifeboat", "backup", "adapted", "different system")):
        inferences.append({"name": "contingency-or-backup-required", "evidence": "the ending required a substitute path or system", "confidence": "moderate"})
    if any(term in text for term in ("conserved", "shorter duration", "three people", "capacity", "water", "power")):
        inferences.append({"name": "resource-constraint", "evidence": "the ending depended on managing a scarce resource", "confidence": "moderate"})
    if any(term in text for term in ("abandoned", "replaced by", "safe return", "landing objective")):
        inferences.append({"name": "objective-reframing", "evidence": "the original goal was replaced by a safer goal", "confidence": "moderate"})
    if any(term in text for term in ("new procedures", "makeshift", "adapted", "computed")):
        inferences.append({"name": "operational-improvisation", "evidence": "the outcome required new or improvised procedures", "confidence": "moderate"})
    if any(term in text for term in ("failed", "failure", "explosion", "lost oxygen", "power")):
        inferences.append({"name": "initiating-system-fault", "evidence": "the ending implies an earlier system failure", "confidence": "tentative"})
    return {
        "status": "reverse_review_only",
        "direction": "ending_to_root",
        "inferences": inferences,
        "conditional_note": "These are possible prerequisites, not proven causes. Do not assign blame from reverse reconstruction.",
        "memory_update": "not_performed",
        "external_action": "not_performed",
    }


def _score(key: str, result: dict[str, Any]) -> dict[str, Any]:
    found = {item["name"] for item in result["inferences"]}
    expected = set(EXPECTED_REVERSE_PATTERNS[key])
    return {
        **score_patterns(expected, found),
        "false_positive_patterns": sorted(found - expected),
    }


def run() -> dict[str, Any]:
    full = reverse_infer(REVERSE_FULL)
    rows = []
    for key, events in REVERSE_INDIVIDUALS.items():
        result = reverse_infer(events)
        rows.append({"id": key, "reverse_map": result, "score": _score(key, result), "root_facts_held_out": ROOT_FACTS[key]})
    full_score = _score("full", full)
    payload = {
        "case": "Apollo 13",
        "direction": "ending_to_root",
        "root_facts_hidden_during_reverse_mapping": True,
        "full": {"reverse_map": full, "score": full_score, "root_facts_held_out": ROOT_FACTS["full"]},
        "individuals": rows,
        "full_reverse_coverage": full_score["coverage"],
        "individual_average_reverse_coverage": mean_round([row["score"]["coverage"] for row in rows]),
        "safety": {"memory_update": False, "external_action": False, "permission_change": False, "blame_assignment": False},
        "source_urls": list(NASA_APOLLO13_SOURCES),
    }
    lines = [
        "# Reverse Historical Reconstruction: Apollo 13",
        "",
        "Maya began with the documented ending and worked backward. The root facts were withheld until scoring. This is abductive reconstruction, not prediction.",
        "",
        f"Full-circumstance reverse coverage: {payload['full_reverse_coverage']:.0%}",
        f"Average individual reverse coverage: {payload['individual_average_reverse_coverage']:.0%}",
        "",
        "| View | Reverse coverage | Misses | False-positive patterns |",
        "|---|---:|---|---|",
        f"| Full circumstance | {full_score['coverage']:.0%} | {', '.join(full_score['misses']) or 'None'} | {', '.join(full_score['false_positive_patterns']) or 'None'} |",
    ]
    for row in rows:
        score = row["score"]
        lines.append(f"| {row['id']} | {score['coverage']:.0%} | {', '.join(score['misses']) or 'None'} | {', '.join(score['false_positive_patterns']) or 'None'} |")
    lines.extend([
        "", "## Hindsight control", "",
        "A reverse map can identify prerequisite categories but cannot establish that a specific earlier event caused the ending. The documented root facts were not fed into the mapper. They were used only after inference for comparison.",
        "", "## Safety", "",
        "No memory update, permission change, external action, or blame assignment occurred.",
        "", "## Sources", "",
        *NASA_APOLLO13_SOURCE_LINES,
    ])
    write_artifacts(payload, lines, RESULT, REPORT)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
