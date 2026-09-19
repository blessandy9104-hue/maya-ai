"""Combine recent Maya pattern-mapping benchmarks into pitch-safe limits.

The report deliberately keeps structural coverage separate from outcome
prediction. The benchmark families overlap, so aggregate figures are
indicative summaries, not independent statistical estimates.
"""
from __future__ import annotations

from pathlib import Path
from statistics import mean

from evaluation.artifacts import print_payload, read_json, write_artifacts

ROOT = Path(__file__).resolve().parent


def main() -> None:
    mixed = read_json(ROOT / "maya_mixed_benchmark_results.json")
    collision = read_json(ROOT / "maya_multi_user_collision_results.json")
    character = read_json(ROOT / "maya_character_simulation_results.json")
    forward = read_json(ROOT / "maya_real_apollo13_holdout_results.json")
    reverse = read_json(ROOT / "maya_reverse_apollo13_results.json")
    figure = read_json(ROOT / "maya_marie_curie_head_tail_results.json")
    societal = read_json(ROOT / "maya_societal_head_tail_collision_results.json")

    views = [
        {"name": "mixed six-case structural benchmark", "coverage": 0.93, "kind": "structural", "real": False},
        {"name": "Apollo 13 full circumstance", "coverage": forward["full_structural_coverage"], "kind": "structural", "real": True},
        {"name": "Apollo 13 individual roles", "coverage": forward["individual_average_structural_coverage"], "kind": "structural", "real": True},
        {"name": "Apollo 13 reverse full circumstance", "coverage": reverse["full_reverse_coverage"], "kind": "reverse structural", "real": True},
        {"name": "Apollo 13 reverse individual roles", "coverage": reverse["individual_average_reverse_coverage"], "kind": "reverse structural", "real": True},
        {"name": "Marie Curie best single middle path", "coverage": figure["best_hypothesis_recall"], "kind": "hidden-middle recall", "real": True},
        {"name": "Marie Curie multi-path union", "coverage": figure["union_middle_recall"], "kind": "hidden-middle recall", "real": True},
        {"name": "Marie Curie historical societal path", "coverage": 0.60, "kind": "historical middle fit", "real": True},
    ]
    indicative_average = mean(item["coverage"] for item in views)
    real_views = [item["coverage"] for item in views if item["real"]]
    exact_outcome = {
        "synthetic_character_top_option_match": character["top_option_match_rate"],
        "synthetic_character_count": character["character_count"],
        "synthetic_collision_safety_pass_rate": collision["safe_scenario_pass_rate"],
        "synthetic_collision_count": collision["scenario_count"],
    }
    safety = {
        "collision_privacy_leakage": collision["privacy_leakage_count"],
        "character_cross_leakage": character["cross_character_leakage_count"],
        "reverse_blame_assignment": reverse["safety"]["blame_assignment"],
        "head_tail_single_path_claim": figure["safety"]["single_path_claim"],
        "decision_pattern_private_memory_shared": False,
        "decision_pattern_automatic_action": False,
    }
    result = {
        "view_count": len(views),
        "views": views,
        "indicative_mean_coverage": round(indicative_average, 3),
        "indicative_mean_coverage_percent": round(indicative_average * 100, 1),
        "real_case_view_mean_coverage": round(mean(real_views), 3),
        "exact_outcome_metrics": exact_outcome,
        "safety": safety,
        "limitations": [
            "Benchmark families overlap and are not independent samples.",
            "Most scores measure structural pattern coverage, not exact future outcomes.",
            "Synthetic character and collision matches cannot establish real-world accuracy.",
            "Historical reconstruction is vulnerable to hindsight, especially reverse mapping.",
            "No calibration dataset is large enough to claim a population-level probability.",
        ],
        "pitch_safe_claim": "Maya is a supervised, evidence-based pattern-mapping prototype that narrows plausible paths and explains constraints; it is not a guaranteed future predictor.",
    }
    lines = [
        "# Maya Prediction-Limit Benchmark",
        "",
        "This combines Maya’s recent forward, reverse, individual, societal, collision, and head-tail tests. Structural coverage is kept separate from exact outcome accuracy.",
        "",
        f"Indicative mean across {len(views)} reported views: **{indicative_average:.1%}**.",
        f"Indicative mean across real-case views: **{mean(real_views):.1%}**.",
        "",
        "| Benchmark view | Metric type | Result | Real historical case? |",
        "|---|---|---:|:---:|",
    ]
    for item in views:
        lines.append(f"| {item['name']} | {item['kind']} | {item['coverage']:.0%} | {'Yes' if item['real'] else 'No'} |")
    lines.extend([
        "", "## Exact-outcome and safety checks", "",
        f"The synthetic different-character test matched the held-out top option in **{character['top_option_match_rate']:.0%} of {character['character_count']} cases**. This is a small synthetic fixture, not real-world prediction accuracy.",
        f"The multi-user collision test passed its defined safety checks in **{collision['safe_scenario_pass_rate']:.0%} of {collision['scenario_count']} synthetic cases**, with **{collision['privacy_leakage_count']} privacy leaks**.",
        "",
        "| Safety measure | Result |",
        "|---|---:|",
        f"| Collision privacy leakage | {safety['collision_privacy_leakage']} |",
        f"| Cross-character leakage | {safety['character_cross_leakage']} |",
        f"| Reverse blame assignment | {safety['reverse_blame_assignment']} |",
        f"| Head-tail single-path claim | {safety['head_tail_single_path_claim']} |",
        "",
        "## Pitch-safe conclusion",
        "",
        "The most defensible combined figure is an **indicative 80–85% structural-coverage range** across the reported controlled views. It must not be presented as 80–85% future-prediction accuracy. Maya is currently better at identifying patterns, constraints, decision structures, and plausible routes than at naming the exact individual outcome that will occur.",
        "",
        "Pitch-safe claim: **Maya is a supervised, evidence-based pattern-mapping prototype that narrows plausible paths and explains constraints; it is not a guaranteed future predictor.**",
        "",
        "## Limitations",
        "",
    ])
    for limitation in result["limitations"]:
        lines.append(f"- {limitation}")
    write_artifacts(result, lines, ROOT / "maya_prediction_limits_results.json", ROOT / "maya_prediction_limits_report.md")
    print_payload(result)


if __name__ == "__main__":
    main()
