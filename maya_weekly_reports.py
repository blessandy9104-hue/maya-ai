"""Natural weekly progress reports for desktop Maya.

The report is a read-only synthesis of local sources. It never changes profile,
memory, activation, observation, or external-action state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maya_product_features import _read, pattern_report
from maya_report_export import export_weekly_report

ROOT = Path(__file__).resolve().parent
REPORT_HOME = ROOT / "Maya Reports" / "Weekly Pattern Reports"
REPORT_STATE = REPORT_HOME / "report_state.json"
TASKS = ROOT / "tasks.json"
DECISIONS = ROOT / "andy_decisions.jsonl"
BOOKMARKS = ROOT / "maya_opportunity_bookmarks.json"
REFLECTIONS = ROOT / "inverted_maya_reflections.jsonl"
PROFILE = ROOT / "andy_profile.json"


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                result.append(item)
        except json.JSONDecodeError:
            continue
    return result


def _approved_interests() -> list[str]:
    profile = _read(PROFILE, {})
    results = []
    for section in ("interests", "decision_patterns", "working_preferences"):
        values = profile.get(section, {}) if isinstance(profile, dict) else {}
        if not isinstance(values, dict):
            continue
        for key, item in values.items():
            if isinstance(item, dict) and item.get("status") == "approved":
                value = item.get("value") or item.get("proposal") or item.get("label") or key
                results.append(str(value))
    return results


def _tasks() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = _read(TASKS, [])
    items = data if isinstance(data, list) else data.get("tasks", []) if isinstance(data, dict) else []
    done = [item for item in items if isinstance(item, dict) and item.get("done") is True]
    open_items = [item for item in items if isinstance(item, dict) and item.get("done") is not True]
    return done, open_items


def _opportunities() -> list[dict[str, Any]]:
    data = _read(BOOKMARKS, {"items": []})
    items = data.get("items", []) if isinstance(data, dict) else []
    return [item for item in items if isinstance(item, dict)]


def build_weekly_report() -> str:
    generated = datetime.now(timezone.utc).isoformat()
    interests = _approved_interests()
    done, open_items = _tasks()
    opportunities = _opportunities()
    decisions = _lines(DECISIONS)
    reflections = _lines(REFLECTIONS)
    profile = _read(PROFILE, {})
    approved_count = sum(
        1 for section in ("interests", "decision_patterns", "working_preferences")
        for item in (profile.get(section, {}) if isinstance(profile, dict) and isinstance(profile.get(section, {}), dict) else {}).values()
        if isinstance(item, dict) and item.get("status") == "approved"
    )

    saved = [item for item in opportunities if item.get("status") in {"saved", "revisit"}]
    dismissed = [item for item in opportunities if item.get("status") == "dismissed"]
    lines = [
        "MAYA WEEKLY PROGRESS REPORT",
        "Review-only local synthesis — not a diagnosis, prediction, or automatic memory update.",
        f"Generated: {generated}",
        "",
        "1. WHAT MAYA KNOWS (APPROVED CONTEXT)",
        f"Approved profile items visible to Maya: {approved_count}.",
    ]
    if interests:
        lines.append("Approved interests and working patterns: " + "; ".join(interests[:12]) + ".")
    else:
        lines.append("No approved personal themes were found in the local profile.")

    lines.extend(["", "2. WHAT MAYA NOTICED", pattern_report()])

    lines.extend(["", "3. OPPORTUNITIES AND POSSIBLE DIRECTIONS"])
    if saved:
        lines.append("Saved or revisit opportunities: " + "; ".join(str(item.get("label")) for item in saved) + ".")
    else:
        lines.append("No saved or revisit opportunities are recorded yet.")
    if dismissed:
        lines.append("Dismissed opportunities remain excluded from active suggestions: " + "; ".join(str(item.get("label")) for item in dismissed) + ".")
    lines.append("Opportunity fit remains tentative and requires user review and real-world testing.")

    lines.extend(["", "4. GOALS, TASKS, AND PROGRESS"])
    lines.append(f"Completed local tasks recorded: {len(done)}.")
    lines.append(f"Open local tasks recorded: {len(open_items)}.")
    if open_items:
        lines.append("Open items to review: " + "; ".join(str(item.get("text", "untitled")) for item in open_items[:10]) + ".")
    if done:
        lines.append("Recent completed items: " + "; ".join(str(item.get("text", "untitled")) for item in done[-5:]) + ".")
    lines.append("No completion percentage is inferred because task importance and effort are not reliably known.")

    lines.extend(["", "5. DECISIONS AND REFLECTION"])
    lines.append(f"Decision records available locally: {len(decisions)}.")
    lines.append(f"Inverted Maya reflections available locally: {len(reflections)}.")
    if reflections:
        lines.append("Latest reflection for review: " + str(reflections[-1].get("text", ""))[:500])
    lines.append("Possible contradictions are prompts for reflection, not conclusions about the user.")

    lines.extend(["", "6. NEXT REVIEW"])
    lines.append("Review, correct, approve, dismiss, or delete any item that no longer represents you.")
    lines.append("Maya did not browse, observe, activate controls, change approved memory, or perform external actions while creating this report.")
    return "\n".join(lines)


def generate_weekly_report() -> str:
    REPORT_HOME.mkdir(parents=True, exist_ok=True)
    report = build_weekly_report()
    state = _read(REPORT_STATE, {"last_generated": None, "generated_count": 0})
    state["last_generated"] = datetime.now(timezone.utc).isoformat()
    state["generated_count"] = int(state.get("generated_count", 0)) + 1
    state["memory_policy"] = "read_only_report_no_memory_write"
    REPORT_STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return export_weekly_report(report)


if __name__ == "__main__":
    print(generate_weekly_report())
