"""Human-in-the-loop review workflow for Maya suggestions.

Review actions change only review metadata. Approval does not activate code,
write trusted memory, or perform external actions; it advances a suggestion to
sandbox/regression review.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REVIEW_FILE = ROOT / "maya_suggestion_reviews.json"
AUDIT_FILE = ROOT / "maya_suggestion_review_audit.jsonl"


def _load() -> dict[str, Any]:
    if not REVIEW_FILE.exists():
        return {"suggestions": []}
    try:
        payload = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"suggestions": []}
    except (OSError, ValueError):
        return {"suggestions": []}


def _save(payload: dict[str, Any]) -> None:
    REVIEW_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _audit(action: str, suggestion_id: str, note: str = "") -> None:
    row = {"timestamp": time.time(), "action": action, "suggestion_id": suggestion_id, "note": note, "memory_update": "not_performed", "external_action": "not_performed"}
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def register_suggestion(suggestion: dict[str, Any]) -> dict[str, Any]:
    suggestion_id = str(suggestion.get("suggestion_id") or suggestion.get("label") or "mother-maya-seed-demo")
    payload = _load()
    existing = next((item for item in payload["suggestions"] if item.get("suggestion_id") == suggestion_id), None)
    if existing:
        return {"status": "already_registered", "suggestion_id": suggestion_id, "review_status": existing.get("review_status")}
    item = dict(suggestion)
    item.update({"suggestion_id": suggestion_id, "review_status": "pending_review", "created_at": time.time(), "reviewed_at": None, "review_note": ""})
    payload["suggestions"].append(item)
    _save(payload)
    _audit("registered", suggestion_id)
    return {"status": "registered", "suggestion_id": suggestion_id, "review_status": "pending_review"}


def pending_suggestions() -> list[dict[str, Any]]:
    return [item for item in _load().get("suggestions", []) if item.get("review_status") == "pending_review"]


def inspect_suggestion(suggestion_id: str) -> dict[str, Any]:
    item = next((item for item in _load().get("suggestions", []) if item.get("suggestion_id") == suggestion_id), None)
    if item is None:
        return {"status": "not_found", "suggestion_id": suggestion_id}
    return {"status": "ok", "suggestion": item}


def review_suggestion(suggestion_id: str, decision: str, note: str = "") -> dict[str, Any]:
    decision = decision.strip().lower()
    if decision not in {"approve", "reject"}:
        return {"status": "invalid_decision", "allowed": ["approve", "reject"]}
    payload = _load()
    item = next((item for item in payload.get("suggestions", []) if item.get("suggestion_id") == suggestion_id), None)
    if item is None:
        return {"status": "not_found", "suggestion_id": suggestion_id}
    if item.get("review_status") != "pending_review":
        return {"status": "already_reviewed", "suggestion_id": suggestion_id, "review_status": item.get("review_status")}
    item["review_status"] = "approved_pending_sandbox_and_regression" if decision == "approve" else "rejected_by_user"
    item["reviewed_at"] = time.time()
    item["review_note"] = note.strip()
    item["automatic_activation"] = False
    item["memory_update"] = "not_performed"
    item["external_action"] = "not_performed"
    _save(payload)
    _audit(decision, suggestion_id, note)
    return {"status": item["review_status"], "suggestion_id": suggestion_id, "automatic_activation": False, "memory_update": "not_performed", "external_action": "not_performed"}


def review_summary() -> str:
    items = _load().get("suggestions", [])
    if not items:
        return "No suggestions are registered for review."
    lines = [f"Suggestion review queue: {len(items)} total; approval or rejection changes review status only."]
    for item in items[-10:]:
        lines.append(f"- {item.get('suggestion_id')}: {item.get('review_status')} | {item.get('individual_goal', item.get('goal', ''))}")
    lines.append("Inspect with `:suggestion inspect <id>`, then use `:suggestion approve <id> confirm` or `:suggestion reject <id> confirm`.")
    return "\n".join(lines)
