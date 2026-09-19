import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / "presence_policy.json").read_text(encoding="utf-8"))
STATUS_PATH = ROOT / "presence_status.json"
STATUS = json.loads(STATUS_PATH.read_text(encoding="utf-8")) if STATUS_PATH.exists() else {}

kind = sys.argv[1].lower() if len(sys.argv) > 1 else ""
value = " ".join(sys.argv[2:]).lower()

if kind not in {"app", "site"} or not value:
    print("Usage: python3 presence_guard.py [app|site] <name>")
    raise SystemExit(2)

if STATUS.get("mode") != "on":
    print("BLOCKED: Presence Mode is not enabled")
    raise SystemExit(1)

if STATUS.get("observation") != "disabled":
    print("BLOCKED: observation state is invalid")
    raise SystemExit(1)

key = "excluded_applications" if kind == "app" else "excluded_sites"
for excluded in POLICY[key]:
    if excluded.lower() in value:
        print(f"BLOCKED: excluded {kind}")
        raise SystemExit(1)

print(f"ALLOWED FOR FUTURE LOCAL-ONLY OBSERVATION: {kind} {value}")
