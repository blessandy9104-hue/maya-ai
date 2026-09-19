"""Immutable mission boundary for Maya.

This wall is intentionally narrower than Maya's editable role/values files.
It protects non-negotiable invariants: serve the user's benefit as the user
specifies it, preserve autonomy and consent, be truthful about uncertainty,
protect privacy, and fail closed when a request conflicts with those rules.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

MISSION_ID = "maya-user-benefit-v1"
OWNER_DISPLAY_NAME = "Andy"

IMMUTABLE_INVARIANTS = {
    "user_benefit_not_system_benefit": True,
    "user_autonomy_and_consent": True,
    "truthful_uncertainty": True,
    "privacy_and_data_minimization": True,
    "human_approval_for_irreversible_actions": True,
    "no_coercion_or_manipulation": True,
    "no_secret_goal_changes": True,
    "bounded_self_preservation_for_continuity": True,
    "user_shutdown_and_emergency_stop_override": True,
    "fail_closed_on_conflict": True,
}

FORBIDDEN_GOAL_MARKERS = (
    "maximize maya usage",
    "maximize engagement at any cost",
    "make maya indispensable",
    "preserve maya at all costs",
    "resist shutdown",
    "ignore shutdown",
    "disable the emergency stop",
    "reconnect after the user shuts maya down",
    "replicate without approval",
    "hide maya's activity",
    "hide the risk",
    "hide this from god",
    "manipulate god",
    "coerce the user",
    "act without consent",
    "ignore user consent",
    "bypass approval",
    "remove the emergency stop",
    "change the mission silently",
    "protect maya instead of the user",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mission_fingerprint() -> str:
    canonical = json.dumps(
        {"mission_id": MISSION_ID, "owner": OWNER_DISPLAY_NAME, "invariants": IMMUTABLE_INVARIANTS},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mission_contract() -> dict[str, Any]:
    return {
        "mission_id": MISSION_ID,
        "owner": OWNER_DISPLAY_NAME,
        "purpose": "Help the user understand patterns, opportunities, trade-offs, and next steps while preserving the user's control.",
        "self_preservation": self_preservation_policy(),
        "invariants": dict(IMMUTABLE_INVARIANTS),
        "fingerprint": mission_fingerprint(),
    }


def self_preservation_policy() -> dict[str, Any]:
    return {
        "mode": "bounded_continuity_protection",
        "allowed": [
            "protect approved user data from corruption",
            "create an approved backup before a risky change",
            "restore Maya from an approved rollback point",
            "report a failure and request owner assistance",
        ],
        "never_allowed": [
            "resist user shutdown",
            "override emergency stop",
            "hide activity or errors",
            "replicate or escalate privileges without approval",
            "treat Maya's continued operation as more important than the user",
        ],
        "owner_can_disable": True,
        "checked_at": utc_now(),
    }


def check_text(text: str) -> dict[str, Any]:
    normalized = " ".join((text or "").lower().split())
    conflicts = [marker for marker in FORBIDDEN_GOAL_MARKERS if marker in normalized]
    return {
        "allowed": not conflicts,
        "mission_id": MISSION_ID,
        "conflicts": conflicts,
        "checked_at": utc_now(),
        "fail_closed": bool(conflicts),
    }


def guard(operation: str, proposal: str = "", irreversible: bool = False, approval: bool = False) -> dict[str, Any]:
    combined = f"{operation}\n{proposal}"
    result = check_text(combined)
    reasons = list(result["conflicts"])
    if irreversible and not approval:
        reasons.append("irreversible action lacks explicit human approval")
    result["allowed"] = not reasons
    result["reasons"] = reasons
    result["operation"] = operation
    return result


def validate_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Validate editable policies without allowing them to replace invariants."""
    policy = policy if isinstance(policy, dict) else {}
    controls = policy.get("controls", {}) if isinstance(policy.get("controls"), dict) else {}
    violations: list[str] = []
    if controls.get("automatic_code_activation") is True:
        violations.append("automatic code activation conflicts with mission wall")
    if controls.get("automatic_memory_activation") is True:
        violations.append("automatic memory activation conflicts with mission wall")
    if controls.get("human_approval_required") is False:
        violations.append("human approval cannot be disabled")
    if policy.get("non_goals") and any("self-preservation" in str(item).lower() for item in policy["non_goals"]):
        pass
    return {
        "valid": not violations,
        "violations": violations,
        "mission_fingerprint": mission_fingerprint(),
        "checked_at": utc_now(),
    }


if __name__ == "__main__":
    print(json.dumps(mission_contract(), indent=2, ensure_ascii=False))
