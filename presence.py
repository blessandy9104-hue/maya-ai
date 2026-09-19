import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
STATUS = ROOT / "presence_status.json"
MEMORY = ROOT / "presence_preferences.jsonl"
STOP = ROOT / "PRESENCE_STOP"


def now():
    return datetime.now(timezone.utc).isoformat()


def write_status(mode, reason=""):
    data = {
        "assistant": "Maya",
        "mode": mode,
        "updated_at": now(),
        "observation": "disabled",
        "local_only": True,
        "approval_required": True,
        "reason": reason,
    }
    STATUS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))


def read_status():
    if not STATUS.exists():
        write_status("off", "not initialized")
    return json.loads(STATUS.read_text(encoding="utf-8"))


def memory():
    if not MEMORY.exists():
        return []
    return [json.loads(line) for line in MEMORY.read_text(encoding="utf-8").splitlines() if line.strip()]


command = sys.argv[1].lower() if len(sys.argv) > 1 else "status"

if command == "on":
    if STOP.exists():
        print("Presence Mode is blocked by the emergency stop. Run: python3 presence.py reset-stop")
        raise SystemExit(1)
    write_status("on", "explicitly enabled by user")
elif command == "off":
    write_status("off", "explicitly disabled by user")
elif command == "stop":
    STOP.write_text("Emergency stop activated at " + now() + "\n", encoding="utf-8")
    write_status("emergency_stop", "manual emergency stop")
elif command == "reset-stop":
    STOP.unlink(missing_ok=True)
    write_status("off", "emergency stop cleared; observation remains disabled")
elif command == "status":
    print(json.dumps(read_status(), indent=2))
elif command == "memory":
    print(json.dumps(memory(), indent=2))
elif command == "propose" and len(sys.argv) >= 3:
    proposal = {
        "id": len(memory()) + 1,
        "created_at": now(),
        "status": "pending",
        "proposal": " ".join(sys.argv[2:]),
        "source": "local_presence_observation",
    }
    with MEMORY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(proposal) + "\n")
    print("Preference proposal recorded for approval:")
    print(json.dumps(proposal, indent=2))
elif command == "approve" and len(sys.argv) == 3:
    target = int(sys.argv[2])
    items = memory()
    changed = False
    for item in items:
        if item.get("id") == target:
            item["status"] = "approved"
            item["approved_at"] = now()
            changed = True
    MEMORY.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")
    print("Preference approved" if changed else "Preference ID not found")
elif command == "forget" and len(sys.argv) >= 3:
    term = " ".join(sys.argv[2:]).lower()
    items = memory()
    kept = [item for item in items if term not in item.get("proposal", "").lower()]
    removed = len(items) - len(kept)
    MEMORY.write_text("".join(json.dumps(item) + "\n" for item in kept), encoding="utf-8")
    print(f"Removed matching preference proposals: {removed}")
else:
    print("Usage: python3 presence.py [on|off|status|stop|reset-stop|memory|propose TEXT|forget TEXT]")
    raise SystemExit(2)
