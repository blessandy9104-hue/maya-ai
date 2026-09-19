"""Harness parity suite for the shared evaluation package.

Pins the shared artifact/scoring/fixture mechanics and the wiring of the
converted benchmark scripts, without regenerating their root artifacts.
"""
from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path

from evaluation.artifacts import read_json, render_json, render_markdown, write_artifacts
from evaluation.fixtures import (
    MARIE_CURIE_REFERENCE_LINES,
    MARIE_CURIE_SOURCES,
    NASA_APOLLO13_SOURCE_LINES,
    NASA_APOLLO13_SOURCES,
)
from evaluation.scoring import mean_round, ratio, score_patterns

ROOT = Path(__file__).resolve().parent

CONVERTED_WRITERS = [
    "maya_historical_holdout.py",
    "maya_real_history_holdout.py",
    "maya_reverse_history_holdout.py",
    "maya_historical_figure_head_tail.py",
    "maya_societal_head_tail_collision.py",
    "maya_character_simulation.py",
    "maya_decision_pattern_simulation.py",
    "maya_mixed_scenario_benchmark.py",
    "maya_prediction_limits.py",
]


def _ok(label: str) -> None:
    print(label + " =OK")


def check_render_json() -> None:
    payload = {"b": 1, "a": "é"}
    text = render_json(payload)
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert json.loads(text) == payload
    assert '"a": "é"' in text  # ensure_ascii=False survives rendering
    _ok("render_json canonical")


def check_render_markdown() -> None:
    text = render_markdown(["# Title", "", "body"])
    assert text == "# Title\n\nbody\n"
    _ok("render_markdown joins")


def check_write_artifacts() -> None:
    payload = {"coverage": 0.67}
    lines = ["# Report", "", "row"]
    with tempfile.TemporaryDirectory() as tmp:
        json_path = Path(tmp) / "result.json"
        md_path = Path(tmp) / "report.md"
        write_artifacts(payload, lines, json_path, md_path)
        assert json.loads(json_path.read_text(encoding="utf-8")) == payload
        assert read_json(json_path) == payload
        assert md_path.read_text(encoding="utf-8") == render_markdown(lines)
    _ok("write_artifacts writes both files")


def check_score_patterns() -> None:
    score = score_patterns(["a", "b", "c"], {"b", "c", "d"})
    assert score["hits"] == ["b", "c"]
    assert score["misses"] == ["a"]
    assert score["coverage"] == 0.67
    empty = score_patterns([], [])
    assert empty["hits"] == [] and empty["misses"] == [] and empty["coverage"] == 1.0
    _ok("score_patterns hits misses coverage")


def check_ratio() -> None:
    assert ratio(1, 2) == 0.5
    assert ratio(1, 3) == 0.33
    assert ratio(0, 0) == 1.0
    assert ratio(1, 0) == 1.0
    assert ratio(5, 7, ndigits=3) == 0.714
    _ok("ratio guards zero totals")


def check_mean_round() -> None:
    assert mean_round([]) == 0.0
    assert mean_round([0.5, 1.0]) == 0.75
    assert mean_round([1, 2, 2]) == 1.67
    _ok("mean_round guards empty input")


def check_fixtures_pinned() -> None:
    assert MARIE_CURIE_SOURCES == [
        "https://www.nobelprize.org/prizes/physics/1903/marie-curie/biographical/",
        "https://www.nobelprize.org/stories/women-who-changed-science/marie-curie/",
        "https://institut-curie.org/legacy-marie-curie-perpetuating-spirit-pioneer",
        "https://www.britannica.com/biography/Marie-Curie",
    ]
    assert MARIE_CURIE_REFERENCE_LINES == [
        "[1] Nobel Prize, Marie Curie — Biographical: https://www.nobelprize.org/prizes/physics/1903/marie-curie/biographical/",
        "[2] Nobel Prize, Women Who Changed Science: Marie Curie: https://www.nobelprize.org/stories/women-who-changed-science/marie-curie/",
        "[3] Institut Curie, The legacy of Marie Curie: https://institut-curie.org/legacy-marie-curie-perpetuating-spirit-pioneer",
        "[4] Encyclopaedia Britannica, Marie Curie: https://www.britannica.com/biography/Marie-Curie",
    ]
    assert NASA_APOLLO13_SOURCES == [
        "https://www.nasa.gov/missions/apollo/apollo-13-mission-details/",
        "https://www.nasa.gov/history/detailed-chronology-of-events-surrounding-the-apollo-13-accident/",
    ]
    assert NASA_APOLLO13_SOURCE_LINES == [
        "[1] NASA, Apollo 13: Mission Details — https://www.nasa.gov/missions/apollo/apollo-13-mission-details/",
        "[2] NASA History Office, Detailed Chronology of Events Surrounding the Apollo 13 Accident — https://www.nasa.gov/history/detailed-chronology-of-events-surrounding-the-apollo-13-accident/",
    ]
    _ok("fixtures pinned verbatim")


def check_converted_scripts_entrypoints() -> None:
    run_modules = [
        "maya_historical_holdout",
        "maya_real_history_holdout",
        "maya_reverse_history_holdout",
        "maya_historical_figure_head_tail",
        "maya_societal_head_tail_collision",
        "maya_character_simulation",
        "maya_decision_pattern_simulation",
        "maya_mixed_scenario_benchmark",
    ]
    for name in run_modules:
        module = importlib.import_module(name)
        assert callable(getattr(module, "run"))
    aggregator = importlib.import_module("maya_prediction_limits")
    assert callable(getattr(aggregator, "main"))
    _ok("converted scripts import and expose entrypoints")


def check_scripts_delegate_to_harness() -> None:
    for name in CONVERTED_WRITERS:
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "from evaluation.artifacts import" in source, name
    _ok("converted writers delegate artifact output to harness")


def check_harness_purity() -> None:
    forbidden = ("import random", "from random", "import datetime", "from datetime", "time.time")
    harness_dir = ROOT / "evaluation"
    for module_path in sorted(harness_dir.glob("*.py")):
        text = module_path.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), module_path.name
    _ok("harness modules contain no randomness or clock dependency")


def main() -> int:
    check_render_json()
    check_render_markdown()
    check_write_artifacts()
    check_score_patterns()
    check_ratio()
    check_mean_round()
    check_fixtures_pinned()
    check_converted_scripts_entrypoints()
    check_scripts_delegate_to_harness()
    check_harness_purity()
    print("test_evaluation_harness=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
