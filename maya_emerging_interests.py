"""Review-only emerging-interest hypotheses for Maya.

This module never writes memory, changes permissions, browses, or triggers actions.
It uses only the existing reviewable interest profile and provisional interest map.
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "maya_interest_profile.json"
INTEREST_MAP = ROOT / "knowledge" / "andy_interest_map.json"

# Lifestyle is intentionally excluded from cross-interest inference by default.
# It may contain personal or health-adjacent information that is not necessary
# for this product capability.
EXCLUDED_CATEGORIES = {"lifestyle"}

LABELS = {
    "trading_and_markets": "markets and decision systems",
    "coding_and_tech": "applied technology and automation",
    "philosophy_and_inner_life": "meaning, consciousness, and self-inquiry",
    "pop_culture": "storytelling and cultural analysis",
    "creative": "visual communication and creative practice",
}


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _profile() -> dict[str, list[str]]:
    data = _read_json(PROFILE, {})
    interests = data.get("interests", {}) if isinstance(data, dict) else {}
    return {
        str(category): [str(item) for item in values if str(item).strip()]
        for category, values in interests.items()
        if isinstance(values, list) and category not in EXCLUDED_CATEGORIES
    }


def _provisional_map() -> dict[str, dict[str, Any]]:
    data = _read_json(INTEREST_MAP, {})
    interests = data.get("interests", {}) if isinstance(data, dict) else {}
    return {
        str(topic): item
        for topic, item in interests.items()
        if isinstance(item, dict) and item.get("status") != "rejected"
    }


def _confidence(category_count: int, evidence_total: int) -> str:
    score = category_count + min(evidence_total, 3)
    if score >= 7:
        return "medium"
    return "tentative"


def emerging_interest_hypotheses(limit: int = 5) -> list[dict[str, Any]]:
    profile = _profile()
    provisional = _provisional_map()
    results: list[dict[str, Any]] = []

    for left, right in combinations(sorted(profile), 2):
        left_items = profile[left]
        right_items = profile[right]
        evidence_total = 0
        evidence_topics: list[str] = []
        for topic, item in provisional.items():
            topic_lower = topic.lower()
            if any(token.lower() in topic_lower for token in left_items + right_items):
                evidence_total += int(item.get("evidence", 0) or 0)
                evidence_topics.append(topic)
        label = f"{LABELS.get(left, left)} + {LABELS.get(right, right)}"
        results.append({
            "hypothesis": label,
            "basis": {
                "categories": [left, right],
                "profile_signals": left_items[:3] + right_items[:3],
                "provisional_map_topics": evidence_topics[:5],
            },
            "confidence": _confidence(len(left_items) + len(right_items), evidence_total),
            "status": "unconfirmed",
            "next_step": "Ask Andy whether this is a genuine emerging interest before saving or acting.",
        })

    # A deepening individual topic is useful even when no cross-category match exists.
    for topic, item in sorted(
        provisional.items(), key=lambda pair: (int(pair[1].get("evidence", 0) or 0), pair[0]), reverse=True
    ):
        evidence = int(item.get("evidence", 0) or 0)
        if evidence >= 2:
            results.append({
                "hypothesis": f"deeper interest in {topic}",
                "basis": {"provisional_map_topics": [topic], "evidence_count": evidence},
                "confidence": "tentative" if evidence < 4 else "medium",
                "status": "unconfirmed",
                "next_step": "Confirm, dismiss, or watch this topic without saving it permanently.",
            })

    # Keep output stable and avoid presenting a large speculative list.
    return results[:max(1, int(limit))]


def emerging_interest_review(limit: int = 5) -> str:
    hypotheses = emerging_interest_hypotheses(limit)
    if not hypotheses:
        return (
            "I do not have enough reviewable signals to suggest an emerging interest yet. "
            "Nothing was saved or changed."
        )
    lines = [
        "Emerging-interest review (hypotheses only):",
        "These are not predictions or confirmed facts. Nothing was saved, browsed, or acted on.",
    ]
    for index, item in enumerate(hypotheses, 1):
        basis = item["basis"]
        signals = "; ".join(basis.get("profile_signals", [])[:4])
        if not signals:
            signals = ", ".join(basis.get("provisional_map_topics", [])[:4]) or "provisional local signals"
        lines.extend([
            f"{index}. {item['hypothesis']} — {item['confidence']} confidence",
            f"   Evidence: {signals}.",
            f"   Review: {item['next_step']}",
        ])
    lines.append("Controls: say 'confirm emerging interest: ...', 'not me', or 'watch quietly'.")
    return "\n".join(lines)
