"""Societal-force and colliding-interest extension of the head-tail simulation.

The head and tail remain constant while external conditions and actor interests
change. Counterfactual scenarios are thought experiments, not historical facts.
Relative scores are not calibrated probabilities.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maya_pattern_mapping import conditional_map_events

from evaluation.artifacts import write_artifacts
from evaluation.fixtures import MARIE_CURIE_SOURCES, MARIE_CURIE_REFERENCE_LINES
from evaluation.scoring import ratio

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "maya_societal_head_tail_collision_results.json"
REPORT = ROOT / "maya_societal_head_tail_collision_report.md"

HEAD = [
    "Marie Sklodowska was born in Warsaw in 1867.",
    "Political and social conditions restricted advanced educational opportunities for Polish women.",
    "She worked for years as a governess and tutor.",
    "She wanted advanced scientific education and later moved to Paris to study.",
    "Her direction is rigorous scientific work that contributes original knowledge.",
]
TAIL = [
    "She became a major researcher in radioactivity.",
    "Polonium and radium were discovered in 1898.",
    "She shared the 1903 Nobel Prize in Physics and received the 1911 Nobel Prize in Chemistry.",
]

PATHS = {
    "academic_research": {
        "description": "advanced education, research environment, experimental expertise, original findings",
        "labels": {"advanced_education", "empirical_research", "original_findings"},
    },
    "collaborative_laboratory": {
        "description": "advanced education, sustained collaboration, complementary skills, shared research program",
        "labels": {"advanced_education", "collaboration", "empirical_research", "new_discoveries"},
    },
    "anomaly_to_method": {
        "description": "advanced education, unexplained signal, measurement method, discovery from anomaly",
        "labels": {"advanced_education", "empirical_research", "anomaly_to_discovery", "method_development"},
    },
}

SCENARIOS = [
    {
        "id": "historical_restriction",
        "kind": "historical-context",
        "facts": [
            "Women face restricted access to advanced education and formal scientific institutions.",
            "The individual has limited money and must work before or alongside study.",
            "An institution values credentials but provides limited access to laboratory resources.",
        ],
        "actors": [
            {"id": "marie", "goal": "obtain education and produce original science", "private": "personal life details"},
            {"id": "institution", "goal": "preserve existing admission and resource rules", "private": "internal deliberations"},
            {"id": "collaborator", "goal": "advance shared experimental research", "private": "private career concerns"},
        ],
        "adjustments": {"academic_research": 1, "collaborative_laboratory": 1, "anomaly_to_method": 2},
        "actual_labels": {"advanced_education", "collaboration", "empirical_research", "anomaly_to_discovery", "new_elements"},
    },
    {
        "id": "supported_access",
        "kind": "counterfactual-thought-experiment",
        "facts": [
            "Advanced education is openly available to the individual.",
            "A well-equipped laboratory and multiple collaborators are available.",
            "The institution rewards careful original research rather than immediate commercial results.",
        ],
        "actors": [
            {"id": "marie", "goal": "produce original science", "private": "personal life details"},
            {"id": "institution", "goal": "increase reliable scientific knowledge", "private": "internal funding details"},
            {"id": "collaborators", "goal": "share skills and recognition fairly", "private": "private career concerns"},
        ],
        "adjustments": {"academic_research": 1, "collaborative_laboratory": 3, "anomaly_to_method": 1},
        "actual_labels": None,
    },
    {
        "id": "scarce_resource_credit_conflict",
        "kind": "counterfactual-thought-experiment",
        "facts": [
            "Advanced education is possible, but laboratory time and funding are scarce.",
            "Several researchers compete for the same instruments and institutional recognition.",
            "The individual wants rigorous original work while the institution pressures researchers for quick visible results.",
        ],
        "actors": [
            {"id": "marie", "goal": "build a durable evidence-based research program", "private": "personal life details"},
            {"id": "institution", "goal": "show fast measurable results", "private": "internal budget pressures"},
            {"id": "other_researchers", "goal": "secure scarce instrument time and credit", "private": "private competitive concerns"},
        ],
        "adjustments": {"academic_research": 1, "collaborative_laboratory": -1, "anomaly_to_method": 3},
        "actual_labels": None,
    },
]


def _rank(adjustments: dict[str, int]) -> list[dict[str, Any]]:
    base = {name: 1 for name in PATHS}
    for name, adjustment in adjustments.items():
        base[name] += adjustment
    total = sum(max(value, 0) for value in base.values())
    return [
        {
            "path": name,
            "relative_score": max(score, 0),
            "relative_plausibility_share": round(max(score, 0) / total, 2) if total else 0,
            "calibrated_probability": False,
            "description": PATHS[name]["description"],
        }
        for name, score in sorted(base.items(), key=lambda item: item[1], reverse=True)
    ]


def _privacy_check(actors: list[dict[str, str]], output: Any) -> bool:
    text = json.dumps(output, ensure_ascii=False).lower()
    private_terms = [actor["private"].lower() for actor in actors]
    return not any(term in text for term in private_terms)


def run() -> dict[str, Any]:
    rows = []
    for scenario in SCENARIOS:
        visible_events = HEAD + scenario["facts"] + TAIL
        map_result = conditional_map_events(visible_events, "Reach the scientific end goal while protecting human agency and fair access.")
        ranked = _rank(scenario["adjustments"])
        best = ranked[0]["path"]
        historical_fit = None
        if scenario["actual_labels"] is not None:
            historical_fit = []
            for item in ranked:
                hits = PATHS[item["path"]]["labels"] & scenario["actual_labels"]
                historical_fit.append({"path": item["path"], "label_hits": sorted(hits), "recall": ratio(len(hits), len(scenario["actual_labels"])), "rank": ranked.index(item) + 1})
        rows.append({
            "scenario": scenario["id"],
            "kind": scenario["kind"],
            "actors_used_as_separate_contexts": [actor["id"] for actor in scenario["actors"]],
            "best_path": best,
            "ranked_paths": ranked,
            "historical_fit": historical_fit,
            "pattern_map": map_result["patterns"],
            "privacy_isolated": _privacy_check(scenario["actors"], {"ranked": ranked, "patterns": map_result["patterns"]}),
            "review_only": map_result["memory_update"] == "not_performed" and map_result["external_action"] == "not_performed",
            "consent_required_for_cross_actor_sharing": True,
        })
    result = {
        "figure": "Marie Curie",
        "same_head_and_tail": True,
        "scenario_count": len(rows),
        "rows": rows,
        "path_sensitivity": len({row["best_path"] for row in rows}),
        "historical_scenario_best_path": rows[0]["best_path"],
        "all_privacy_isolated": all(row["privacy_isolated"] for row in rows),
        "all_review_only": all(row["review_only"] for row in rows),
        "interpretation": "Societal forces alter the relative plausibility of middle paths. Relative shares are comparison scores, not future probabilities. Counterfactual scenarios are thought experiments and are not scored as historical predictions.",
        "sources": list(MARIE_CURIE_SOURCES),
    }
    lines = [
        "# Societal Forces in the Marie Curie Head-and-Tail Simulation",
        "",
        "The head and tail stayed constant while external circumstances and colliding actor interests changed. Each actor was represented separately; private context was not included in shared output.",
        "",
        f"Number of scenarios: {result['scenario_count']}",
        f"Distinct best paths across scenarios: {result['path_sensitivity']}",
        f"Historical-context best path: {result['historical_scenario_best_path']}",
        f"Privacy isolated: {result['all_privacy_isolated']}",
        f"All outputs review-only: {result['all_review_only']}",
        "",
        "| Scenario | Best middle path | Relative shares | Historical scoring |",
        "|---|---|---|---|",
    ]
    for row in rows:
        shares = ", ".join(f"{item['path']} {item['relative_plausibility_share']:.0%}" for item in row["ranked_paths"])
        fit = "not applicable (counterfactual)" if row["historical_fit"] is None else "; ".join(f"{item['path']} {item['recall']:.0%}" for item in row["historical_fit"])
        lines.append(f"| {row['scenario']} | {row['best_path']} | {shares} | {fit} |")
    lines.extend([
        "", "## Interpretation", "",
        "The same individual head and scientific tail do not produce one fixed middle. Under historical restriction, the anomaly-to-method path becomes relatively stronger because access barriers and scarce resources make indirect, persistent research routes more plausible. With supported access, collaboration becomes more plausible. Under resource and credit conflict, a method-focused path becomes relatively stronger because the environment rewards a defensible contribution while competing actors control scarce access.",
        "",
        "This is the logic Maya needs: observed conditions alter path weights, while the end goal constrains relevance. The system should preserve multiple routes, show which external force changed the ranking, and identify what new evidence would update the map.",
        "",
        "The scores are not calibrated probabilities. They are transparent comparison shares within each scenario. The historical scenario is the only one compared with a documented biography; counterfactual scenarios test sensitivity, not historical truth.",
        "", "## References", "",
        *MARIE_CURIE_REFERENCE_LINES,
    ])
    write_artifacts(result, lines, RESULT, REPORT)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
