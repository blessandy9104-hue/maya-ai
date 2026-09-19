"""Shared artifact output for Maya evaluation and benchmark scripts.

Single owner of the JSON + Markdown write idiom that every benchmark and
holdout script previously duplicated. Writers stay review-only: they touch
only their own result files, never identity, memory, or runtime state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def render_json(payload: Any) -> str:
    """Canonical result-file rendering: indent 2, UTF-8 text, trailing newline."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_markdown(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def write_artifacts(payload: dict[str, Any], md_lines: list[str], json_path: Path, md_path: Path) -> None:
    json_path.write_text(render_json(payload), encoding="utf-8")
    md_path.write_text(render_markdown(md_lines), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def print_payload(payload: Any) -> None:
    """Console dump identical to the former ``print(json.dumps(...))`` idiom."""
    sys.stdout.write(render_json(payload))
