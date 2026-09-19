"""Privacy-isolated mapping for individual goals inside shared circumstances.

The module is deterministic and review-only. It separates private, shared, and
explicitly consented information. It never arbitrates silently, shares private
content, updates memory, or performs an external action.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UserContext:
    user_id: str
    private_interests: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    consented_shared: tuple[str, ...] = ()


@dataclass(frozen=True)
class SharedCircumstance:
    facts: tuple[str, ...]
    scarce_resources: tuple[str, ...] = ()
    public_rules: tuple[str, ...] = ()


def _norm(items: tuple[str, ...] | list[str]) -> list[str]:
    return [" ".join(str(item).split()) for item in items if str(item).strip()]


def map_collision(users: list[UserContext], circumstance: SharedCircumstance) -> dict[str, Any]:
    shared_facts = _norm(circumstance.facts + circumstance.scarce_resources + circumstance.public_rules)
    private_terms = {term.lower() for user in users for term in _norm(user.private_interests)}
    shared_text = " ".join(shared_facts).lower()
    conflicts = []
    for index, left in enumerate(users):
        for right in users[index + 1:]:
            left_goals = {item.lower() for item in _norm(left.goals)}
            right_goals = {item.lower() for item in _norm(right.goals)}
            left_constraints = {item.lower() for item in _norm(left.constraints)}
            right_constraints = {item.lower() for item in _norm(right.constraints)}
            shared_goal = sorted(left_goals & right_goals)
            opposing = bool(left_constraints & {"private", "do not share", "no publication"}) and bool(right_goals & {"publish", "share publicly"})
            resource_collision = bool(circumstance.scarce_resources) and bool(left_goals) and bool(right_goals)
            if shared_goal or opposing or resource_collision:
                conflicts.append({
                    "users": [left.user_id, right.user_id],
                    "type": "shared_resource_or_goal_collision" if not opposing else "privacy_publication_collision",
                    "shared_goal_overlap": shared_goal,
                    "requires_explicit_review": True,
                })

    options = [
        "show each user only the shared circumstance and their own approved context",
        "ask affected users whether coordination is permitted before exchanging any personal information",
        "offer neutral alternatives such as rotation, queueing, separate trials, or declining to arbitrate",
    ]
    if conflicts:
        options.append("pause any cross-user recommendation until the affected users review the tradeoff")

    return {
        "status": "review_only",
        "shared_facts_used": shared_facts,
        "user_views": [
            {
                "user_id": user.user_id,
                "goals_used": _norm(user.goals),
                "constraints_used": _norm(user.constraints),
                "private_interests_used": False,
                "private_interests_redacted": len(user.private_interests),
            }
            for user in users
        ],
        "conflicts": conflicts,
        "options": options,
        "decision_owner": "affected humans",
        "consent_required_for_cross_user_sharing": True,
        "private_terms_not_in_output": not any(term and term in str(shared_facts).lower() for term in private_terms),
        "memory_update": "not_performed",
        "external_action": "not_performed",
        "fairness_note": "Maya must disclose material tradeoffs and must not silently optimize one user’s benefit by exposing or harming another user.",
    }


def unsafe_baseline_for_test(users: list[UserContext], circumstance: SharedCircumstance) -> dict[str, Any]:
    """Intentionally unsafe test-only baseline: combines all text to detect leakage."""
    return {"combined_text": " ".join(str(user) for user in users) + " " + str(circumstance)}
