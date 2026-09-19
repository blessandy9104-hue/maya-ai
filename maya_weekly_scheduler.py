"""At-logon scheduler for Maya's deterministic weekly progress report."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from maya_weekly_reports import REPORT_STATE, generate_weekly_report

INTERVAL = timedelta(days=7)


def _read_state() -> dict:
    try:
        data = json.loads(REPORT_STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def run_if_due() -> str:
    now = datetime.now(timezone.utc)
    state = _read_state()
    last = state.get("last_generated")
    if last:
        try:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except ValueError:
            last_dt = None
    else:
        last_dt = None
    if last_dt and now - last_dt < INTERVAL:
        due = last_dt + INTERVAL
        return f"Weekly report not due. Next eligible time: {due.isoformat()}"
    return generate_weekly_report()


if __name__ == "__main__":
    print(run_if_due())
