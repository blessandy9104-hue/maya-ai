"""Shared evaluation harness for Maya benchmark, holdout, and simulation scripts.

Mechanics only: artifact rendering/writing, deterministic scoring, and
byte-identical shared fixtures. Scenario data stays with the script that
owns it. All writers are review-only.
"""
from evaluation.artifacts import print_payload, read_json, render_json, render_markdown, write_artifacts
from evaluation.scoring import mean_round, ratio, score_patterns

__all__ = [
    "print_payload",
    "read_json",
    "render_json",
    "render_markdown",
    "write_artifacts",
    "mean_round",
    "ratio",
    "score_patterns",
]
