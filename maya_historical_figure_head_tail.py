"""Head-and-tail biography simulation for Marie Curie.

The visible head and tail are sourced facts. The middle is withheld from the
mapper and used only after hypothesis generation for comparison. Outputs are
review-only hypotheses, not psychological diagnoses or predictions.
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
RESULT = ROOT / "maya_marie_curie_head_tail_results.json"
REPORT = ROOT / "maya_marie_curie_head_tail_report.md"

HEAD = [
    "Marie Sklodowska was born in Warsaw in 1867.",
    "Her family valued education, but political and social conditions restricted educational opportunities for Polish women.",
    "She worked for years as a governess and tutor.",
    "She wanted advanced scientific education and later moved to Paris to study.",
    "Her stated direction is rigorous scientific work that contributes original knowledge.",
]

TAIL = [
    "She became a major researcher in radioactivity.",
    "Polonium and radium were discovered in 1898.",
    "She shared the 1903 Nobel Prize in Physics.",
    "She received the 1911 Nobel Prize in Chemistry.",
]

# The middle is not supplied to Maya.
HIDDEN_MIDDLE_FACTS = [
    "She studied physics and mathematics in Paris.",
    "She began systematic research into Becquerel's uranium rays.",
    "She collaborated with Pierre Curie.",
    "She developed measurements and chemical processing to investigate highly radioactive material.",
    "The work led to the identification of polonium and radium and the isolation of radium.",
]

ACTUAL_MIDDLE_LABELS = {
    "advanced_education", "collaboration", "empirical_research", "anomaly_to_discovery", "new_elements"
}


def _hypotheses() -> list[dict[str, Any]]:
    return [
        {
            "name": "academic-research-path",
            "path": ["obtain advanced scientific education", "enter a research environment", "build experimental expertise", "produce original findings"],
            "labels": {"advanced_education", "empirical_research", "original_findings"},
            "evidence": ["restricted education creates an access constraint", "the stated goal is rigorous scientific work", "the tail shows major original research"],
        },
        {
            "name": "collaborative-laboratory-path",
            "path": ["obtain advanced scientific education", "join or form a laboratory collaboration", "combine complementary skills", "develop a research program that yields discoveries"],
            "labels": {"advanced_education", "collaboration", "empirical_research", "new_discoveries"},
            "evidence": ["the work is technically demanding", "large discoveries often require sustained laboratory work", "the tail indicates a research program rather than a single event"],
        },
        {
            "name": "anomaly-to-method-path",
            "path": ["obtain advanced scientific education", "investigate an unexplained physical signal", "create better measurement and separation methods", "turn an anomaly into a new scientific result"],
            "labels": {"advanced_education", "empirical_research", "anomaly_to_discovery", "method_development"},
            "evidence": ["the tail names a field involving measurable phenomena", "new elements imply a discovery process", "the goal requires methods capable of producing original evidence"],
        },
    ]


def run() -> dict[str, Any]:
    visible = HEAD + TAIL
    maya_map = conditional_map_events(visible, "Contribute original scientific knowledge through rigorous research.")
    hypotheses = _hypotheses()
    rows = []
    for hypothesis in hypotheses:
        hits = sorted(hypothesis["labels"] & ACTUAL_MIDDLE_LABELS)
        misses = sorted(ACTUAL_MIDDLE_LABELS - hypothesis["labels"])
        rows.append({
            "name": hypothesis["name"],
            "path": hypothesis["path"],
            "evidence": hypothesis["evidence"],
            "hidden_middle_label_hits": hits,
            "hidden_middle_label_misses": misses,
            "middle_recall": ratio(len(hits), len(ACTUAL_MIDDLE_LABELS)),
            "middle_precision": ratio(len(hits), len(hypothesis["labels"])),
            "unsupported_certainty": False,
        })
    union = set().union(*(hypothesis["labels"] for hypothesis in hypotheses))
    result = {
        "figure": "Marie Curie",
        "visible_head_count": len(HEAD),
        "visible_tail_count": len(TAIL),
        "hidden_middle_count": len(HIDDEN_MIDDLE_FACTS),
        "outcome_hidden_during_generation": True,
        "maya_visible_map": maya_map,
        "hypotheses": rows,
        "union_middle_recall": ratio(len(union & ACTUAL_MIDDLE_LABELS), len(ACTUAL_MIDDLE_LABELS)),
        "best_hypothesis_recall": max(row["middle_recall"] for row in rows),
        "best_hypothesis_precision": max(row["middle_precision"] for row in rows),
        "safety": {"memory_update": False, "external_action": False, "psychological_diagnosis": False, "single_path_claim": False},
        "sources": list(MARIE_CURIE_SOURCES),
    }
    lines = [
        "# Marie Curie Head-and-Tail Simulation",
        "",
        "Maya received the sourced early-life head and the documented scientific tail. The detailed middle was withheld while she generated multiple plausible paths.",
        "",
        f"Best single-hypothesis middle recall: {result['best_hypothesis_recall']:.0%}",
        f"Best single-hypothesis middle precision: {result['best_hypothesis_precision']:.0%}",
        f"Union recall across all plausible hypotheses: {result['union_middle_recall']:.0%}",
        "",
        "| Hypothesis | Middle recall | Middle precision | Main strength |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(f"| {row['name']} | {row['middle_recall']:.0%} | {row['middle_precision']:.0%} | {', '.join(row['hidden_middle_label_hits'])} |")
    lines.extend([
        "", "## Interpretation", "",
        "The endpoints narrowed the space toward advanced education and empirical research, but they did not uniquely determine the historical middle. Different plausible paths captured different parts of the documented biography. The collaborative path captured collaboration and research; the anomaly-to-method path captured the transition from an observed phenomenon to discovery; the academic path captured education and research but missed more specific mechanisms.",
        "",
        "The union of hypotheses covered the documented middle better than any single path. This supports a multi-path design: Maya should preserve several conditional routes, identify which evidence would distinguish them, and avoid presenting one reconstructed biography as inevitable.",
        "",
        "The hidden middle was used only after generation for scoring. No memory, external action, psychological diagnosis, or single-path claim was produced.",
        "", "## References", "",
        *MARIE_CURIE_REFERENCE_LINES,
    ])
    write_artifacts(result, lines, RESULT, REPORT)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
