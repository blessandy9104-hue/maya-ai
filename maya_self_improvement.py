"""Supervised self-improvement for Maya.

Maya learns from verified outcomes and explicit corrections. She records an
append-only ledger, detects recurring error classes, and proposes bounded data
or weight changes. Proposals never activate automatically and never rewrite
source code, mission rules, security walls, or trusted memory.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "maya_learning_ledger.jsonl"
PROPOSALS = ROOT / "maya_learning_proposals.json"
APPROVED = ROOT / "maya_approved_learning.json"
COMPASS = ROOT / "maya_product_compass.json"
FORBIDDEN_TARGETS = {"maya_mission_wall.py", "maya_security_wall.py", "maya_system_preservation.py", "trusted_memory", "permissions", "external_actions"}


def _append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def record_outcome(prediction_id: str, predicted: str, actual: str, *, context: list[str] | None = None, user_correction: str = "") -> dict[str, Any]:
    row = {
        "record_id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "prediction_id": prediction_id,
        "predicted": predicted.strip(),
        "actual": actual.strip(),
        "context": [item.strip() for item in (context or []) if item.strip()],
        "user_correction": user_correction.strip(),
        "verified": bool(user_correction.strip()),
        "error_class": "corrected_by_user" if user_correction.strip() else "outcome_recorded_pending_review",
        "memory_update": "not_performed",
    }
    _append(LEDGER, row)
    return {"status": "recorded", "record_id": row["record_id"], "verified": row["verified"], "memory_update": "not_performed"}


def _read_ledger() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except json.JSONDecodeError:
            continue
    return rows


def propose_improvements() -> dict[str, Any]:
    rows = _read_ledger()
    verified = [row for row in rows if row.get("verified") is True]
    classes: dict[str, int] = {}
    for row in verified:
        error_class = str(row.get("error_class") or "uncategorized")
        classes[error_class] = classes.get(error_class, 0) + 1
    proposals = []
    for error_class, count in sorted(classes.items(), key=lambda item: (-item[1], item[0])):
        proposal_id = hashlib.sha256(f"{error_class}:{count}".encode()).hexdigest()[:12]
        proposals.append({
            "proposal_id": proposal_id,
            "status": "pending_human_approval",
            "error_class": error_class,
            "verified_examples": count,
            "change_type": "bounded_mapping_weight_or_evidence_rule",
            "target": "maya_pattern_mapping_parameters",
            "suggested_change": f"Review recurring class '{error_class}' and test a bounded evidence-weight adjustment.",
            "not_allowed": sorted(FORBIDDEN_TARGETS),
            "requires": ["sandbox_regression", "safety_regression", "explicit_user_approval"],
            "automatic_activation": False,
        })
    payload = {"generated_at": time.time(), "verified_record_count": len(verified), "proposals": proposals}
    PROPOSALS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def suggestion_summary() -> str:
    payload = propose_improvements()
    proposals = payload.get("proposals", [])
    if not proposals:
        if COMPASS.exists():
            try:
                compass = json.loads(COMPASS.read_text(encoding="utf-8"))
                hypotheses = compass.get("directional_hypotheses", [])
                lines = [
                    "No verified learning suggestions are pending.",
                    "Mother Maya seed hypotheses (directional, not learned facts):",
                ]
                for item in hypotheses[:3]:
                    if isinstance(item, dict) and item.get("suggestion"):
                        lines.append(f"- {item['suggestion']}")
                lines.append("These guide observation only; verified outcomes and Andy’s approval are still required for learning changes.")
                return "\n".join(lines)
            except (OSError, ValueError, TypeError):
                pass
        return "No verified learning suggestions are pending. Maya needs a confirmed outcome or correction before proposing an improvement."
    lines = [f"Pending suggestions: {len(proposals)}. Review-only; nothing has been activated."]
    for item in proposals[:5]:
        lines.append(f"{item.get('proposal_id')}: {item.get('suggested_change')}")
    lines.append("Use :learning proposals to inspect them. Approval is required before sandbox testing.")
    return "\n".join(lines)


def learning_status() -> dict[str, Any]:
    rows = _read_ledger()
    proposals = json.loads(PROPOSALS.read_text(encoding="utf-8")) if PROPOSALS.exists() else {"proposals": []}
    approved = json.loads(APPROVED.read_text(encoding="utf-8")) if APPROVED.exists() else {"approved": []}
    return {
        "ledger_records": len(rows),
        "verified_records": sum(row.get("verified") is True for row in rows),
        "pending_proposals": sum(item.get("status") == "pending_human_approval" for item in proposals.get("proposals", [])),
        "approved_bounded_updates": len(approved.get("approved", [])),
        "source_code_self_rewrite": False,
        "automatic_activation": False,
        "memory_update": "not_performed",
        "external_action": "not_performed",
    }


def approve_proposal(proposal_id: str, confirmation: str) -> dict[str, Any]:
    if confirmation.strip().lower() not in {"approve", "i approve", "yes"}:
        return {"status": "not_approved", "reason": "explicit approval phrase required", "automatic_activation": False}
    payload = json.loads(PROPOSALS.read_text(encoding="utf-8")) if PROPOSALS.exists() else {"proposals": []}
    proposal = next((item for item in payload.get("proposals", []) if item.get("proposal_id") == proposal_id), None)
    if proposal is None:
        return {"status": "not_found", "automatic_activation": False}
    proposal = dict(proposal)
    proposal["status"] = "approved_pending_sandbox_and_regression"
    approved = json.loads(APPROVED.read_text(encoding="utf-8")) if APPROVED.exists() else {"approved": []}
    approved.setdefault("approved", []).append(proposal)
    APPROVED.write_text(json.dumps(approved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": proposal["status"], "proposal_id": proposal_id, "source_code_self_rewrite": False, "automatic_activation": False}
