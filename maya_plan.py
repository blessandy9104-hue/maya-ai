import json, sys
from datetime import datetime, timezone
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit("Usage: python3 maya_plan.py <goal>")

goal = " ".join(sys.argv[1:])
ROOT = Path(__file__).resolve().parent
plan = {
    "plan_id": datetime.now(timezone.utc).strftime("plan-%Y%m%dT%H%M%SZ"),
    "creator": "Andy",
    "goal": goal,
    "steps": [
        "Clarify the goal and constraints",
        "Use approved local context",
        "Identify assumptions and risks",
        "Prepare an isolated proposal",
        "Test the proposal",
        "Ask Andy for approval before action",
        "Keep backup and rollback available"
    ],
    "status": "draft",
    "approval_required": True
}
out = ROOT / "evolution" / "plans"
out.mkdir(parents=True, exist_ok=True)
path = out / (plan["plan_id"] + ".json")
path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
print(json.dumps(plan, indent=2))
print("Saved:", path)
