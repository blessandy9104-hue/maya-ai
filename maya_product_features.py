"""CPU-friendly, local-only product features for Maya.

All writes are explicit and reviewable. This module never browses, observes,
changes permissions, or silently promotes data into approved memory.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "andy_profile.json"
INTEREST_MAP = ROOT / "knowledge" / "andy_interest_map.json"
ONBOARDING = ROOT / "onboarding_pending.json"
BOOKMARKS = ROOT / "maya_opportunity_bookmarks.json"
REFLECTIONS = ROOT / "inverted_maya_reflections.jsonl"

ONBOARDING_QUESTIONS = [
    "What matters most to you right now?",
    "What are you trying to build, learn, protect, or change?",
    "Which skills, interests, or experiences do you want Maya to consider?",
    "What constraints should Maya respect, such as time, money, privacy, or energy?",
    "What kind of opportunities would be useful, and which kinds should be excluded?",
    "How would you like Maya to communicate: concise, detailed, challenging, reflective, or practical?",
    "What must Maya never do without your explicit approval?",
]

REFLECTION_PROMPTS = [
    "What is occupying your attention today, and why might it matter?",
    "What pattern has appeared more than once in your recent thoughts or decisions?",
    "What are you saying you want, and what evidence supports that direction?",
    "Where might two of your current priorities be in tension?",
    "What would you change if you trusted your own evidence more than your immediate mood?",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def onboarding_interview() -> str:
    state = _read(ONBOARDING, {"answers": {}, "status": "not_started"})
    answers = state.get("answers", {}) if isinstance(state, dict) else {}
    lines = ["Maya onboarding interview (answers become proposals, not approved memory):"]
    for index, question in enumerate(ONBOARDING_QUESTIONS, 1):
        marker = "answered" if str(index) in answers and answers[str(index)].strip() else "not answered"
        lines.append(f"{index}. {question} [{marker}]")
    lines.append("Use `onboarding answer 1: ...` to record a local proposal. Review and approve each item separately.")
    return "\n".join(lines)


def onboarding_answer(index: int, answer: str) -> str:
    if index < 1 or index > len(ONBOARDING_QUESTIONS):
        return f"Choose an onboarding question from 1 to {len(ONBOARDING_QUESTIONS)}. Nothing was saved."
    answer = " ".join(answer.strip().split())
    if not answer:
        return "The answer was empty. Nothing was saved."
    state = _read(ONBOARDING, {"answers": {}, "status": "in_progress"})
    state.setdefault("answers", {})[str(index)] = answer[:1000]
    state["status"] = "in_progress"
    state["updated_at"] = _now()
    state["memory_policy"] = "pending_proposal_only"
    _write(ONBOARDING, state)
    return f"Saved answer {index} as a local onboarding proposal. It is not approved memory."


def pattern_report() -> str:
    profile = _read(PROFILE, {})
    interest_map = _read(INTEREST_MAP, {})
    approved = []
    for section in ("interests", "decision_patterns", "working_preferences"):
        values = profile.get(section, {}) if isinstance(profile, dict) else {}
        if isinstance(values, dict):
            for key, item in values.items():
                if isinstance(item, dict) and item.get("status") == "approved":
                    value = item.get("value") or item.get("proposal") or item.get("label") or key
                    approved.append(str(value))
    inferred = interest_map.get("interests", {}) if isinstance(interest_map, dict) else {}
    ranked = sorted(
        ((topic, item.get("evidence", 0)) for topic, item in inferred.items() if isinstance(item, dict)),
        key=lambda pair: (int(pair[1] or 0), pair[0]), reverse=True,
    )
    lines = [
        "Weekly pattern report (local evidence review):",
        "This is an interpretation aid, not a diagnosis or permanent profile update.",
        f"Approved context items visible to Maya: {len(approved)}.",
    ]
    if approved:
        lines.append("Stable approved themes: " + "; ".join(approved[:5]) + ".")
    if ranked:
        lines.append("Repeated provisional topics: " + "; ".join(f"{topic} ({count} signals)" for topic, count in ranked[:5]) + ".")
    else:
        lines.append("There are not yet enough repeated provisional topics to report.")
    lines.append("Controls: correct the report, delete a memory item, or ask Maya to show the evidence.")
    return "\n".join(lines)


def bookmark_opportunity(label: str, status: str = "saved") -> str:
    if status not in {"saved", "dismissed", "revisit"}:
        return "Use saved, dismissed, or revisit. Nothing changed."
    label = " ".join(label.strip().split())
    if not label:
        return "The opportunity label was empty. Nothing changed."
    data = _read(BOOKMARKS, {"items": []})
    items = data.setdefault("items", [])
    existing = next((item for item in items if item.get("label", "").lower() == label.lower()), None)
    if existing is None:
        existing = {"id": f"opp_{len(items)+1:04d}", "label": label}
        items.append(existing)
    existing.update({"status": status, "updated_at": _now(), "source": "Andy_explicit_command"})
    _write(BOOKMARKS, data)
    return f"Opportunity marked {status}: {label}."


def opportunity_bookmarks() -> str:
    data = _read(BOOKMARKS, {"items": []})
    items = data.get("items", []) if isinstance(data, dict) else []
    if not items:
        return "No opportunity bookmarks yet. Nothing has been saved."
    lines = ["Opportunity history:"]
    for item in items:
        lines.append(f"- {item.get('id')}: {item.get('label')} [{item.get('status', 'saved')}]")
    return "\n".join(lines)


def memory_audit() -> str:
    profile = _read(PROFILE, {})
    rows = []
    for section in ("owner", "communication", "interests", "decision_patterns", "working_preferences", "approved_memories"):
        values = profile.get(section, {}) if isinstance(profile, dict) else {}
        if isinstance(values, dict):
            iterable = values.items()
        elif isinstance(values, list):
            iterable = ((str(index), item) for index, item in enumerate(values))
        else:
            iterable = []
        for key, item in iterable:
            if isinstance(item, dict) and item.get("status") == "approved":
                value = item.get("value") or item.get("proposal") or item.get("label") or str(item)
                rows.append((f"{section}.{key}", str(value)))
    if not rows:
        return "Memory audit: no approved memory items are currently visible."
    lines = ["Memory audit (approved items only):"]
    lines.extend(f"- {item_id}: {value}" for item_id, value in rows)
    lines.append("Delete one explicitly with `memory delete section.key confirm`. Deletion is permanent for that item.")
    return "\n".join(lines)


def memory_delete(item_id: str, confirmation: str) -> str:
    if confirmation.lower() != "confirm":
        return "Deletion requires the final word `confirm`; nothing was deleted."
    if "." not in item_id:
        return "Use the audit identifier section.key; nothing was deleted."
    section, key = item_id.split(".", 1)
    profile = _read(PROFILE, {})
    values = profile.get(section) if isinstance(profile, dict) else None
    if isinstance(values, dict) and key in values and isinstance(values[key], dict) and values[key].get("status") == "approved":
        del values[key]
        profile[section] = values
        profile.setdefault("metadata", {})["last_audit_action"] = {"action": "delete", "item": item_id, "at": _now()}
        _write(PROFILE, profile)
        return f"Deleted approved memory item {item_id}. Verify with `memory audit`."
    return f"No approved memory item matched {item_id}; nothing was deleted."


def next_reflection_prompt() -> str:
    count = 0
    if REFLECTIONS.exists():
        count = sum(1 for line in REFLECTIONS.read_text(encoding="utf-8").splitlines() if line.strip())
    prompt = REFLECTION_PROMPTS[min(count, len(REFLECTION_PROMPTS) - 1)]
    return f"Inverted Maya reflection prompt {min(count + 1, len(REFLECTION_PROMPTS))}: {prompt}\nNothing is saved until you explicitly submit a reflection."


def add_reflection(text: str) -> str:
    text = " ".join(text.strip().split())
    if not text:
        return "The reflection was empty. Nothing was saved."
    REFLECTIONS.parent.mkdir(parents=True, exist_ok=True)
    with REFLECTIONS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": _now(), "text": text[:2000], "status": "local_reflection"}, ensure_ascii=False) + "\n")
    return "Reflection saved locally for review. It is not approved memory."


def contradiction_review() -> str:
    if not REFLECTIONS.exists():
        return "No reflections are available for contradiction review."
    entries = []
    for line in REFLECTIONS.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            entries.append(item.get("text", ""))
        except json.JSONDecodeError:
            continue
    if len(entries) < 2:
        return "Contradiction review needs at least two reflections."
    positive = re.compile(r"\b(want|like|interested|prefer|choose|enjoy)\b", re.I)
    negative = re.compile(r"\b(do not|don't|not interested|avoid|hate|never|no longer)\b", re.I)
    pairs = []
    for index, left in enumerate(entries):
        for right in entries[index + 1:]:
            left_words = set(re.findall(r"[a-z]{5,}", left.lower()))
            right_words = set(re.findall(r"[a-z]{5,}", right.lower()))
            overlap = sorted(left_words & right_words)
            if overlap and ((positive.search(left) and negative.search(right)) or (negative.search(left) and positive.search(right))):
                pairs.append((overlap[:5], left, right))
    if not pairs:
        return "No clear contradiction detected. Maya will not force a conclusion from ambiguous wording."
    lines = ["Possible contradiction review (gentle, unconfirmed):"]
    for overlap, left, right in pairs[:3]:
        lines.append(f"- Shared terms: {', '.join(overlap)}")
        lines.append(f"  Earlier/later tension: {left} / {right}")
    lines.append("This is a prompt for reflection, not a judgment. Confirm, explain, or dismiss it.")
    return "\n".join(lines)
