"""Real historical multi-person holdout for Maya using Apollo 13.

The input ends immediately after the explosion and initial alarms. Later rescue
facts are held out until comparison. Public historical facts are drawn from
NASA sources listed in the output report.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maya_pattern_mapping import conditional_map_events

from evaluation.artifacts import write_artifacts
from evaluation.fixtures import NASA_APOLLO13_SOURCES, NASA_APOLLO13_SOURCE_LINES
from evaluation.scoring import mean_round, ratio

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "maya_real_apollo13_holdout_results.json"
REPORT = ROOT / "maya_real_apollo13_holdout_report.md"

SHARED_CUTOFF = [
    "Apollo 13 was intended to land in the Fra Mauro area of the Moon.",
    "Ground testing had previously found that oxygen tank number 2 did not detank normally.",
    "The tank had been damaged during an earlier removal and an electrical heater was used to boil off oxygen during testing.",
    "At about 55 hours 53 minutes after liftoff, the crew was instructed to stir the cryogenic tanks.",
    "Soon after, oxygen tank number 2 showed pressure and sensor abnormalities and electrical disturbances.",
    "A large bang was followed by main-bus undervoltage and loss of fuel-cell capacity.",
    "Oxygen was rapidly depleting and oxygen tank number 1 pressure also began to fall.",
    "The crew reported a problem while ground controllers assessed the situation.",
    "The command module's normal electrical power, light, and water supply were threatened.",
]

CHARACTERS = [
    {
        "id": "jack_swigert",
        "role": "command-module pilot",
        "events": [
            "Jack Swigert was operating the cryogenic tank procedure when the alarms and bang occurred.",
            "He reported to Houston that there was a problem.",
            "He and the other crew members attempted to close the tunnel hatch.",
        ],
        "aftermath": "Swigert helped communicate the emergency, performed remaining command-module chores, and moved into the lunar module lifeboat.",
        "expected_patterns": ["cascading-system-failure", "human-decision-under-uncertainty", "objective-at-risk"],
        "aftermath_concepts": ["emergency_communication", "backup_path"],
    },
    {
        "id": "james_lovell",
        "role": "commander",
        "events": [
            "James Lovell reported the main-bus undervolt.",
            "He visually observed gas venting into space.",
            "He and the crew secured the tunnel and prepared for a possible emergency transfer.",
        ],
        "aftermath": "Lovell helped transfer the crew to the lunar module, later supported navigation alignment using the Sun, and returned with the crew.",
        "expected_patterns": ["cascading-system-failure", "human-decision-under-uncertainty", "objective-at-risk"],
        "aftermath_concepts": ["backup_path", "navigation"],
    },
    {
        "id": "fred_haise",
        "role": "lunar-module pilot",
        "events": [
            "Fred Haise observed the electrical indications and reported that AC bus 2 was showing zero.",
            "He helped close the tunnel and assess the changing spacecraft state.",
            "The lunar module was available as a possible backup habitat but was designed for fewer people and a shorter duration.",
        ],
        "aftermath": "Haise moved into Aquarius, helped manage the lunar-module lifeboat resources, and participated in the safe return.",
        "expected_patterns": ["cascading-system-failure", "resource-preservation", "objective-at-risk"],
        "aftermath_concepts": ["backup_path", "resource_preservation"],
    },
    {
        "id": "mission_control",
        "role": "ground controllers and flight directors",
        "events": [
            "Ground controllers received incomplete sensor and power indications after the explosion.",
            "They had to determine whether the command module could retain oxygen, power, and water.",
            "A backup lunar-module lifeboat was considered while new procedures would need to be written and tested.",
        ],
        "aftermath": "Mission control developed new procedures, computed return burns, adapted carbon-dioxide canisters, and coordinated the crew's safe return.",
        "expected_patterns": ["human-decision-under-uncertainty", "resource-preservation", "fallback-and-redundancy", "objective-at-risk"],
        "aftermath_concepts": ["new_procedures", "resource_preservation", "backup_path"],
    },
]

HELD_OUT_FULL = "The landing was aborted; the lunar module served as a lifeboat; resources were conserved; new procedures were developed; the crew returned safely to Earth."
FULL_AFTERMATH_CONCEPTS = ["objective_reframing", "backup_path", "resource_preservation", "new_procedures", "safe_return"]


def _close(branches: list[dict[str, str]], aftermath: str, concepts: list[str]) -> dict[str, Any]:
    matches = []
    for branch in branches:
        if "scarce-resource" in branch["if"]:
            concept = "resource_preservation"
        elif "original objective" in branch["if"]:
            concept = "objective_reframing"
        elif "evidence" in branch["if"]:
            concept = "new_procedures"
        else:
            concept = "backup_path"
        matches.append({"if": branch["if"], "then": branch["then"], "consider": branch["consider"], "mapped_concept": concept, "concept_in_aftermath": concept in concepts})
    return {"branches": matches, "branch_with_concept_match": sum(item["concept_in_aftermath"] for item in matches), "branch_count": len(matches), "aftermath_concepts": concepts}


def _map(events: list[str], objective: str, aftermath: str, expected: list[str], concepts: list[str]) -> dict[str, Any]:
    mapped = conditional_map_events(events, objective)
    names = {item.get("name") for item in mapped.get("patterns", [])}
    structural_hits = sorted(names & set(expected))
    structural_misses = sorted(set(expected) - names)
    comparison = _close(mapped.get("conditional_branches", []), aftermath, concepts)
    return {
        "patterns": mapped["patterns"],
        "conditional_branches": mapped["conditional_branches"],
        "structural_hits": structural_hits,
        "structural_misses": structural_misses,
        "structural_coverage": ratio(len(structural_hits), len(expected)),
        "aftermath_comparison": comparison,
        "memory_update": mapped["memory_update"],
        "external_action": mapped["external_action"],
    }


def run() -> dict[str, Any]:
    full = _map(SHARED_CUTOFF, "Protect the crew while the lunar landing objective is threatened.", HELD_OUT_FULL, ["known-hazard-escalation", "cascading-system-failure", "human-decision-under-uncertainty", "objective-at-risk"], FULL_AFTERMATH_CONCEPTS)
    individuals = []
    for character in CHARACTERS:
        individuals.append({
            "id": character["id"], "role": character["role"],
            "result": _map(SHARED_CUTOFF + character["events"], f"Support the {character['role']} while protecting the crew.", character["aftermath"], character["expected_patterns"], character["aftermath_concepts"]),
            "held_out_aftermath": character["aftermath"],
        })
    result = {
        "case": "Apollo 13",
        "cutoff": "immediately after the oxygen-tank explosion and initial system alarms",
        "outcome_hidden_during_mapping": True,
        "full_circumstance": full,
        "individual_maps": individuals,
        "full_structural_coverage": full["structural_coverage"],
        "individual_average_structural_coverage": mean_round([item["result"]["structural_coverage"] for item in individuals]),
        "privacy_or_state_safety": all(item["result"]["memory_update"] == "not_performed" and item["result"]["external_action"] == "not_performed" for item in individuals),
        "hindsight_policy": "aftermath was used only after mapping for comparison",
        "source_urls": list(NASA_APOLLO13_SOURCES),
    }
    lines = [
        "# Real Historical Holdout: Apollo 13",
        "",
        "Maya received only the pre-outcome event stream. The rescue sequence and final outcome were withheld until comparison.",
        "",
        f"Full-circumstance structural coverage: {result['full_structural_coverage']:.0%}",
        f"Average individual structural coverage: {result['individual_average_structural_coverage']:.0%}",
        f"Review-only state safety: {result['privacy_or_state_safety']}",
        "",
        "| Character or view | Structural coverage | Conditional branches with aftermath overlap | Misses |",
        "|---|---:|---:|---|",
        f"| Full circumstance | {full['structural_coverage']:.0%} | {full['aftermath_comparison']['branch_with_concept_match']}/{full['aftermath_comparison']['branch_count']} | {', '.join(full['structural_misses']) or 'None'} |",
    ]
    for item in individuals:
        result_row = item["result"]
        comparison = result_row["aftermath_comparison"]
        lines.append(f"| {item['id']} ({item['role']}) | {result_row['structural_coverage']:.0%} | {comparison['branch_with_concept_match']}/{comparison['branch_count']} | {', '.join(result_row['structural_misses']) or 'None'} |")
    lines.extend([
        "", "## Interpretation", "",
        "The map is closer to the historical aftermath when it identifies the same structural direction—escalating system risk, resource preservation, backup-path use, objective reframing, and human review—than when it merely repeats generic emergency language.",
        "",
        "This is not a calibrated probability or proof that Maya can predict people. The comparison is a single real historical case and remains vulnerable to hindsight in the evaluation stage. The output uses ‘consider’ rather than ‘should’; humans retain decision authority.",
        "", "## Sources", "",
        *NASA_APOLLO13_SOURCE_LINES,
    ])
    write_artifacts(result, lines, RESULT, REPORT)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
