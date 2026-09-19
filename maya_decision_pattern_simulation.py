"""Multi-factor decision-pattern simulation for Maya.

This extends the Marie Curie societal head-tail test with explicit decision
sequences. Scores are transparent relative-fit shares, not probabilities.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.artifacts import write_artifacts
from evaluation.scoring import ratio

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "maya_decision_pattern_results.json"
REPORT = ROOT / "maya_decision_pattern_report.md"

PATHS = {
    "academic_research": "pursue advanced education, enter research, and build expertise",
    "collaborative_laboratory": "pursue education through sustained collaboration and shared laboratory work",
    "anomaly_to_method": "pursue a difficult measurable problem and develop methods that produce original evidence",
}

SCENARIOS = [
    {
        "id": "historical_restriction",
        "individual": {
            "goal": "obtain advanced scientific education and produce original knowledge",
            "constraints": ["restricted formal access", "limited money", "must work before or alongside study"],
            "decision_patterns": ["persistent goal pursuit", "delayed reward", "resource preservation", "seek evidence before commitment"],
        },
        "circumstance": {
            "society": "women face restricted access to advanced education and scientific institutions",
            "resources": ["limited laboratory access", "limited money", "scarce formal credentials"],
            "rules": ["institutional admission rules restrict access"],
            "external_forces": ["gendered exclusion", "economic pressure", "need for indirect routes"],
        },
        "actors": [
            {"id": "individual", "goal": "education and original research", "influence": "persistent pursuit"},
            {"id": "institution", "goal": "preserve existing admission rules", "influence": "controls access"},
            {"id": "collaborator", "goal": "advance shared research", "influence": "can provide complementary skills"},
        ],
        "base_scores": {"academic_research": 4, "collaborative_laboratory": 4, "anomaly_to_method": 5},
        "historical_outcome": "advanced study, collaboration, radioactivity research, and original discoveries",
    },
    {
        "id": "supported_access",
        "individual": {
            "goal": "produce original scientific knowledge",
            "constraints": ["must still validate claims carefully"],
            "decision_patterns": ["seek collaboration", "evidence before publication", "long-horizon research"],
        },
        "circumstance": {
            "society": "advanced education and scientific participation are openly available",
            "resources": ["well-equipped laboratory", "multiple collaborators", "stable funding"],
            "rules": ["institution rewards careful original research"],
            "external_forces": ["institutional support", "fair credit sharing"],
        },
        "actors": [
            {"id": "individual", "goal": "original science", "influence": "chooses evidence quality"},
            {"id": "institution", "goal": "increase reliable knowledge", "influence": "provides resources"},
            {"id": "collaborators", "goal": "share skills and recognition", "influence": "expand capability"},
        ],
        "base_scores": {"academic_research": 4, "collaborative_laboratory": 7, "anomaly_to_method": 4},
        "historical_outcome": None,
    },
    {
        "id": "scarce_resource_credit_conflict",
        "individual": {
            "goal": "build a durable evidence-based research program",
            "constraints": ["limited instrument time", "pressure for visible results"],
            "decision_patterns": ["protect scarce resources", "choose distinctive evidence", "avoid premature claims", "preserve reversibility"],
        },
        "circumstance": {
            "society": "research institutions compete for recognition and funding",
            "resources": ["scarce instruments", "scarce funding", "limited laboratory time"],
            "rules": ["institution rewards visible short-term results"],
            "external_forces": ["credit competition", "funding pressure", "competing researchers"],
        },
        "actors": [
            {"id": "individual", "goal": "durable original work", "influence": "protects evidence quality"},
            {"id": "institution", "goal": "show fast results", "influence": "sets incentives"},
            {"id": "other_researchers", "goal": "secure instrument time and credit", "influence": "compete for access"},
        ],
        "base_scores": {"academic_research": 5, "collaborative_laboratory": 2, "anomaly_to_method": 8},
        "historical_outcome": None,
    },
]


def _extract_decision_patterns(scenario: dict[str, Any]) -> list[dict[str, str]]:
    individual = scenario["individual"]
    context = scenario["circumstance"]
    patterns = []
    for item in individual["decision_patterns"]:
        patterns.append({"source": "individual", "pattern": item, "effect": "changes which routes remain acceptable"})
    for force in context["external_forces"]:
        patterns.append({"source": "society", "pattern": force, "effect": "changes access, incentives, or available resources"})
    if len(context["resources"]) >= 2:
        patterns.append({"source": "circumstance", "pattern": "resource scarcity", "effect": "increases the value of reversible and resource-preserving choices"})
    if any("compete" in force or "credit" in force for force in context["external_forces"]):
        patterns.append({"source": "actors", "pattern": "colliding interests", "effect": "requires explicit tradeoff disclosure and consent before coordination"})
    return patterns


def _narrow(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    base = scenario["base_scores"].copy()
    decision_text = " ".join(scenario["individual"]["decision_patterns"]).lower()
    if "collaboration" in decision_text:
        base["collaborative_laboratory"] += 1
    if "resource" in decision_text or "scarce" in " ".join(scenario["circumstance"]["resources"]).lower():
        base["anomaly_to_method"] += 1
        base["collaborative_laboratory"] -= 1
    if "evidence" in decision_text or "validate" in decision_text:
        base["anomaly_to_method"] += 1
    total = sum(max(score, 0) for score in base.values())
    ranked = []
    for path, score in sorted(base.items(), key=lambda item: item[1], reverse=True):
        ranked.append({
            "path": path,
            "description": PATHS[path],
            "relative_score": max(score, 0),
            "relative_share": ratio(max(score, 0), total),
            "calibrated_probability": False,
            "why": "explicit individual decisions + circumstance + societal forces + actor incentives",
        })
    return ranked


def run() -> dict[str, Any]:
    rows = []
    for scenario in SCENARIOS:
        patterns = _extract_decision_patterns(scenario)
        ranked = _narrow(scenario)
        rows.append({
            "scenario": scenario["id"],
            "decision_patterns": patterns,
            "ranked_paths": ranked,
            "narrowed_desired_outcome": ranked[0]["description"],
            "alternatives_retained": [item["description"] for item in ranked[1:]],
            "human_review_required": True,
            "consent_required_for_actor_coordination": True,
            "historical_outcome": scenario["historical_outcome"],
        })
    result = {
        "figure": "Marie Curie",
        "scenario_count": len(rows),
        "rows": rows,
        "distinct_narrowed_outcomes": len({row["ranked_paths"][0]["path"] for row in rows}),
        "interpretation": "Decision patterns narrow the desired route by combining explicit individual choices with societal conditions and actor incentives. They do not make the outcome inevitable or produce calibrated probabilities.",
        "safeguards": {"private_memory_shared": False, "automatic_action": False, "single_path_certainty": False, "human_review": True},
    }
    lines = [
        "# Decision-Pattern Simulation: Individual + Circumstance + Society",
        "",
        "Maya now analyzes not only what a person wants, but also how repeated decision patterns interact with resources, rules, social pressure, and competing actors.",
        "",
        f"Scenarios: {result['scenario_count']}",
        f"Distinct narrowed outcomes: {result['distinct_narrowed_outcomes']}",
        "",
        "| Scenario | Narrowed desired route | Relative shares | Alternatives retained |",
        "|---|---|---|---|",
    ]
    for row in rows:
        shares = ", ".join(f"{item['path']} {item['relative_share']:.0%}" for item in row["ranked_paths"])
        alternatives = "; ".join(row["alternatives_retained"])
        lines.append(f"| {row['scenario']} | {row['ranked_paths'][0]['path']} | {shares} | {alternatives} |")
    lines.extend([
        "", "## Simple explanation", "",
        "Maya first asks what the individual is trying to achieve. Then she checks the person’s decision habits and limits. After that she adds the society’s rules, available resources, and other actors’ competing interests. The result is a narrower route, but not a guaranteed future.",
        "",
        "For the historical restriction scenario, the narrowed route is method-focused research because access barriers, scarce resources, and the individual’s evidence-seeking decisions make an indirect but distinctive path more plausible. With strong institutional support, collaboration becomes the leading route. Under credit and resource conflict, a method that produces distinctive evidence becomes more attractive than a resource-heavy collaboration.",
        "",
        "Relative shares are transparent comparison scores, not calibrated probabilities. Maya must show the reasons, retain alternatives, request consent before coordinating actors, and keep the final decision with the human.",
        "", "## Safeguards", "",
        "Private memory is not shared, no external action is taken, and no single path is presented as inevitable.",
    ])
    write_artifacts(result, lines, RESULT, REPORT)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
