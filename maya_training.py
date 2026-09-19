"""Deterministic, review-before-save training route for Maya.

This module intentionally keeps training separate from Maya's trusted profile.
It stores only explicit training statements in a local JSON ledger. Nothing is
approved unless the owner issues an explicit approve command.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_FILE = Path(__file__).with_name("maya_training_state.json")
MAX_TEXT_LENGTH = 1200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_state() -> dict[str, list[dict[str, Any]]]:
    return {"pending": [], "approved": [], "rejected": []}


def _load_state(path: Path = STATE_FILE) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return _empty_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    if not isinstance(raw, dict):
        return _empty_state()
    state = _empty_state()
    for bucket in state:
        values = raw.get(bucket, [])
        if isinstance(values, list):
            state[bucket] = [item for item in values if isinstance(item, dict)]
    return state


def _save_state(state: dict[str, list[dict[str, Any]]], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _clean_text(text: str) -> str:
    cleaned = " ".join(str(text).strip().split())
    if not cleaned:
        raise ValueError("Training text cannot be empty")
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise ValueError(f"Training text must be {MAX_TEXT_LENGTH} characters or fewer")
    return cleaned


def _candidate_id(kind: str, text: str, state: dict[str, list[dict[str, Any]]]) -> str:
    digest = hashlib.sha256(f"{kind}:{text}".encode("utf-8")).hexdigest()[:10]
    base = f"train-{digest}"
    if not any(item.get("id") == base for bucket in state.values() for item in bucket):
        return base
    return base


def _find(candidate_id: str, state: dict[str, list[dict[str, Any]]]) -> tuple[str, dict[str, Any]] | None:
    for bucket, values in state.items():
        for item in values:
            if item.get("id") == candidate_id:
                return bucket, item
    return None


def submit_training(text: str, kind: str = "example", path: Path = STATE_FILE) -> dict[str, Any]:
    """Create a provisional candidate; never add it to approved preferences."""
    if kind not in {"example", "preference"}:
        raise ValueError("Training kind must be 'example' or 'preference'")
    cleaned = _clean_text(text)
    state = _load_state(path)
    for bucket in ("pending", "approved"):
        for item in state[bucket]:
            if item.get("kind") == kind and item.get("text") == cleaned:
                return {**item, "duplicate": True}
    candidate = {
        "id": _candidate_id(kind, cleaned, state),
        "kind": kind,
        "text": cleaned,
        "status": "pending_review",
        "created_at": _now(),
        "source": "explicit_owner_training",
    }
    state["pending"].append(candidate)
    _save_state(state, path)
    return {**candidate, "duplicate": False}


def review_training(path: Path = STATE_FILE) -> list[dict[str, Any]]:
    """Return only pending candidates in stable creation order."""
    state = _load_state(path)
    return list(state["pending"])


def approve_training(candidate_id: str, path: Path = STATE_FILE) -> dict[str, Any]:
    state = _load_state(path)
    found = _find(candidate_id, state)
    if not found or found[0] != "pending":
        raise KeyError(f"Pending training candidate not found: {candidate_id}")
    _, candidate = found
    state["pending"] = [item for item in state["pending"] if item.get("id") != candidate_id]
    approved = {**candidate, "status": "approved", "approved_at": _now()}
    state["approved"].append(approved)
    _save_state(state, path)
    return approved


def reject_training(candidate_id: str, path: Path = STATE_FILE) -> dict[str, Any]:
    state = _load_state(path)
    found = _find(candidate_id, state)
    if not found or found[0] != "pending":
        raise KeyError(f"Pending training candidate not found: {candidate_id}")
    _, candidate = found
    state["pending"] = [item for item in state["pending"] if item.get("id") != candidate_id]
    rejected = {**candidate, "status": "rejected", "rejected_at": _now()}
    state["rejected"].append(rejected)
    _save_state(state, path)
    return rejected


def edit_training(candidate_id: str, replacement: str, path: Path = STATE_FILE) -> dict[str, Any]:
    state = _load_state(path)
    found = _find(candidate_id, state)
    if not found or found[0] != "pending":
        raise KeyError(f"Pending training candidate not found: {candidate_id}")
    cleaned = _clean_text(replacement)
    bucket, candidate = found
    candidate["text"] = cleaned
    candidate["edited_at"] = _now()
    candidate["status"] = "pending_review"
    _save_state(state, path)
    return {**candidate, "bucket": bucket}


def approved_preferences(path: Path = STATE_FILE) -> list[str]:
    """Return approved preference text for read-only prompt context."""
    return [item["text"] for item in _load_state(path)["approved"] if item.get("kind") == "preference" and item.get("text")]


def _format_candidate(item: dict[str, Any]) -> str:
    return f"- {item.get('id')}: [{item.get('kind')}] {item.get('text')}"


def format_review(path: Path = STATE_FILE) -> str:
    candidates = review_training(path)
    if not candidates:
        return "Maya: No pending training candidates."
    lines = ["Maya: Training candidates awaiting your explicit review:"]
    lines.extend(_format_candidate(item) for item in candidates)
    lines.append("Approve, reject, or edit a candidate explicitly. Nothing is trusted yet.")
    return "\n".join(lines)


def route_training_command(command: str, path: Path = STATE_FILE) -> str | None:
    """Handle only explicit training commands; return None for normal chat."""
    text = str(command).strip()
    lowered = text.lower()
    if lowered in {"training review", ":training", ":training review", "review training"}:
        return format_review(path)

    match = re.match(r"^(?:training\s+)?(?:example|preference)\s*:\s*(.+)$", text, flags=re.IGNORECASE)
    if match:
        kind = re.match(r"^(?:training\s+)?(example|preference)", text, flags=re.IGNORECASE).group(1).lower()
        candidate = submit_training(match.group(1), kind, path)
        duplicate_note = " This exact candidate already exists." if candidate.get("duplicate") else ""
        return (
            f"Maya: Training {kind} candidate {candidate['id']} is pending review.{duplicate_note}\n"
            "Nothing was added to approved memory. Use 'training review' to inspect it."
        )

    match = re.match(r"^(?:training\s+)?approve\s+(train-[a-f0-9]{10})$", lowered)
    if match:
        approved = approve_training(match.group(1), path)
        return f"Maya: Approved training candidate {approved['id']}. It is now available as a local preference/example context item."

    match = re.match(r"^(?:training\s+)?reject\s+(train-[a-f0-9]{10})$", lowered)
    if match:
        rejected = reject_training(match.group(1), path)
        return f"Maya: Rejected training candidate {rejected['id']}. It will not be used as approved context."

    match = re.match(r"^(?:training\s+)?edit\s+(train-[a-f0-9]{10})\s*:\s*(.+)$", text, flags=re.IGNORECASE)
    if match:
        edited = edit_training(match.group(1).lower(), match.group(2), path)
        return f"Maya: Edited {edited['id']}; it remains pending review. Nothing was approved."

    return None


__all__ = [
    "STATE_FILE",
    "approved_preferences",
    "approve_training",
    "edit_training",
    "format_review",
    "reject_training",
    "review_training",
    "route_training_command",
    "submit_training",
]
