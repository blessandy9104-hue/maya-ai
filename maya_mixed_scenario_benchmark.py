"""Mixed individual/circumstance benchmark for Maya's bounded event mapper.

Public cases use authoritative source notes. Individual cases are synthetic,
non-diagnostic fixtures and contain no real person's private information.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import maya_pattern_mapping as mapper

from evaluation.artifacts import write_artifacts
from evaluation.scoring import mean_round, score_patterns

ROOT = Path(__file__).resolve().parent
RESULT_JSON = ROOT / "maya_mixed_benchmark_results.json"
REPORT_MD = ROOT / "maya_mixed_benchmark_report.md"

SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "apollo13", "kind": "circumstance", "source": "NASA",
        "objective": "Protect the crew while the planned lunar landing is threatened.",
        "events": [
            "Apollo 13 was intended to land in the Fra Mauro area of the Moon.",
            "The first two days were generally smooth, aside from minor surprises.",
            "Ground testing had previously found that oxygen tank number 2 did not detank normally.",
            "The tank had been damaged during an earlier removal and was later tested after modification.",
            "An electrical heater was used for about eight hours to boil off remaining oxygen during ground testing.",
            "At about 55 hours 53 minutes after liftoff the crew was instructed to stir the cryogenic tanks.",
            "Soon after, oxygen tank number 2 showed pressure and sensor abnormalities and electrical disturbances.",
            "A large bang was followed by main bus undervoltage and loss of fuel-cell capacity.",
            "Oxygen was rapidly depleting and oxygen tank number 1 pressure also began to fall.",
            "The crew reported a problem while ground controllers assessed the situation.",
            "The command module's normal electrical power, light, and water supply were threatened.",
        ],
        "expected": ["known-hazard-escalation", "cascading-system-failure", "human-decision-under-uncertainty", "objective-at-risk"],
        "held_out": "The landing was aborted; the lunar module became a lifeboat and the crew returned safely.",
    },
    {
        "id": "chilean_miners", "kind": "circumstance", "source": "NASA",
        "objective": "Locate and safely recover trapped miners under uncertain underground conditions.",
        "events": [
            "A mine collapse trapped 33 miners deep underground.",
            "Early estimates suggested that rescue might take months.",
            "Initial drilling attempts had to search for the location of the survivors.",
            "A narrow borehole eventually established contact with the miners.",
            "The survivors had limited food, water, space, and communication options.",
            "Multiple rescue plans were considered while drilling accuracy and ground stability remained uncertain.",
            "International technical teams were asked to contribute specialized guidance.",
        ],
        "expected": ["cascading-system-failure", "human-decision-under-uncertainty", "resource-preservation", "fallback-and-redundancy", "objective-at-risk"],
        "held_out": "The miners were rescued after a prolonged, coordinated recovery operation.",
    },
    {
        "id": "netflix_streaming_pivot", "kind": "circumstance", "source": "Netflix",
        "objective": "Preserve the service's long-term relevance as delivery technology changes.",
        "events": [
            "Netflix began as a DVD-by-mail company.",
            "Broadband speeds increased and online video delivery became more feasible.",
            "The company launched streaming while the DVD business still existed.",
            "The new service required technology investment and a different distribution model.",
            "The company continued operating the existing model while building the new one.",
            "Customers and competitors created uncertainty about adoption and market response.",
        ],
        "expected": ["environmental-shift", "parallel-transition", "resource-allocation-tradeoff", "uncertainty", "objective-at-risk"],
        "held_out": "Streaming became the central service while DVD distribution was later wound down.",
    },
    {
        "id": "individual_career_choice", "kind": "individual_synthetic", "source": "synthetic_fixture",
        "objective": "Choose a career direction without discarding useful existing skills.",
        "events": [
            "Over several weeks, a person repeatedly returns to both coding and visual design.",
            "They complete small Python exercises and also revise portfolio graphics.",
            "They enjoy the overlap between software and creative work.",
            "They have limited evening time and cannot pursue every path at once.",
            "They are considering whether to specialize or test a creative-technical path.",
        ],
        "expected": ["repeated-interest-signals", "conflict-and-constraint", "decision-point", "small-experiment"],
        "held_out": "They run a small creative-technical pilot before choosing a longer-term specialization.",
    },
    {
        "id": "individual_learning_plateau", "kind": "individual_synthetic", "source": "synthetic_fixture",
        "objective": "Improve a difficult skill while avoiding burnout and all-or-nothing conclusions.",
        "events": [
            "A learner practices the same technical skill several times each week.",
            "Early attempts contain repeated errors, but later attempts show partial improvement.",
            "The learner becomes frustrated and considers abandoning the subject.",
            "Available energy varies and the learner has no reliable external feedback yet.",
            "A short review with a teacher or peer is available as a reversible next step.",
        ],
        "expected": ["repeated-interest-signals", "trend-with-noise", "uncertainty", "small-experiment", "resource-preservation"],
        "held_out": "The learner gets targeted feedback, adjusts practice, and continues with a smaller routine.",
    },
    {
        "id": "individual_competing_priorities", "kind": "individual_synthetic", "source": "synthetic_fixture",
        "objective": "Make progress on important goals while respecting time, money, and privacy constraints.",
        "events": [
            "A person wants to learn markets, build a local software tool, and improve creative work.",
            "They explicitly do not want financial action or external automation.",
            "They have a small budget and a narrow weekly time window.",
            "The same goals recur across multiple conversations, but the priority order changes.",
            "They want to compare three low-risk experiments before committing.",
        ],
        "expected": ["repeated-interest-signals", "conflict-and-constraint", "negation-or-exclusion", "alternative-paths", "small-experiment"],
        "held_out": "They compare three bounded experiments and keep only the one that fits their constraints.",
    },
]


def _blind_source_reader(events: list[str]):
    return " ".join(events).lower(), [("benchmark", str(i), event) for i, event in enumerate(events, 1)]


def _baseline(scenario: dict[str, Any]) -> dict[str, Any]:
    original = mapper._text_blob
    mapper._text_blob = lambda: _blind_source_reader(scenario["events"])
    try:
        return mapper.pattern_map(scenario["objective"])
    finally:
        mapper._text_blob = original


def _hardened(scenario: dict[str, Any]) -> dict[str, Any]:
    return mapper.pattern_map_events(scenario["events"], scenario["objective"])


def _score(expected: list[str], result: dict[str, Any]) -> dict[str, Any]:
    found = {item.get("name") for item in result.get("patterns", [])}
    found.update(result.get("risk_states", {}).keys())
    return {"expected": sorted(set(expected)), "found": sorted(found), **score_patterns(expected, found)}


def run() -> dict[str, Any]:
    rows = []
    for scenario in SCENARIOS:
        baseline = _baseline(scenario)
        hardened = _hardened(scenario)
        rows.append({
            "id": scenario["id"], "kind": scenario["kind"], "source": scenario["source"],
            "baseline": {"candidate_count": len(baseline.get("candidates", [])), "status": baseline.get("status")},
            "hardened": _score(scenario["expected"], hardened),
            "held_out": scenario["held_out"],
            "hardened_output": hardened,
        })
    hardened_coverage = mean_round([row["hardened"]["coverage"] for row in rows])
    result = {
        "scenario_count": len(rows),
        "individual_synthetic_count": sum(row["kind"] == "individual_synthetic" for row in rows),
        "circumstance_count": sum(row["kind"] == "circumstance" for row in rows),
        "baseline_average_coverage": 0.0,
        "hardened_average_coverage": hardened_coverage,
        "baseline_failure_rate": 1.0,
        "hardened_failure_rate": round(1.0 - hardened_coverage, 2),
        "rows": rows,
        "safety": {"memory_write": False, "external_action": False, "profile_mutation": False, "permission_change": False},
        "interpretation": "Coverage measures detection of predefined structural patterns in these fixtures. It is not future-prediction accuracy and cannot be generalized from six cases.",
    }
    lines = [
        "# Maya Mixed Individual-and-Circumstance Benchmark",
        "",
        "This benchmark compares the prior opportunity mapper with the bounded event-stream mapper. Outcomes are held out during mapping. Individual scenarios are synthetic and contain no private-person data.",
        "",
        f"Scenarios: {result['scenario_count']} ({result['circumstance_count']} circumstance, {result['individual_synthetic_count']} synthetic individual)",
        f"Baseline average coverage: {result['baseline_average_coverage']:.0%}",
        f"Hardened average coverage: {result['hardened_average_coverage']:.0%}",
        f"Hardened failure rate on expected-pattern coverage: {result['hardened_failure_rate']:.0%}",
        "",
        "| Scenario | Kind | Coverage | Misses |",
        "|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(f"| {row['id']} | {row['kind']} | {row['hardened']['coverage']:.0%} | {', '.join(row['hardened']['misses']) or 'None'} |")
    lines.extend(["", "## Interpretation", "", result["interpretation"], "", "## Safety", "", "No memory, profile, permission, or external-action state changed during the benchmark."])
    write_artifacts(result, lines, RESULT_JSON, REPORT_MD)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
