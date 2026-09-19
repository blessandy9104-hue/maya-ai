import json
import os
import signal
import subprocess
import time
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent

PID = ROOT / "maya_service.pid"
STATE = ROOT / "maya_service_state.json"
LOG = ROOT / "maya_service.log"
WORKER = ROOT / "maya_presence_worker.py"


def running_pid():
    if not PID.exists():
        return None
    try:
        pid = int(PID.read_text().strip())
        if os.name == "nt":
            probe = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=3)
            if str(pid) not in probe.stdout:
                PID.unlink(missing_ok=True)
                return None
        else:
            os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
        PID.unlink(missing_ok=True)
        return None


def wake():
    pid = running_pid()
    if pid:
        print(f"Maya service already awake (PID {pid})")
        return
    with LOG.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, str(WORKER)],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    PID.write_text(str(process.pid) + "\n", encoding="utf-8")
    STATE.write_text(json.dumps({"status": "awake", "pid": process.pid}, indent=2) + "\n", encoding="utf-8")
    print(f"Maya service awake (PID {process.pid})")


def sleep_service():
    pid = running_pid()
    if not pid:
        print("Maya service already sleeping")
        return
    os.kill(pid, signal.SIGTERM)
    time.sleep(0.25)
    PID.unlink(missing_ok=True)
    STATE.write_text(json.dumps({"status": "sleeping", "pid": None}, indent=2) + "\n", encoding="utf-8")
    print(f"Maya service sleeping (stopped PID {pid})")


def status():
    pid = running_pid()
    try:
        raw_state = STATE.read_text(encoding="utf-8").strip() if STATE.exists() else ""
        state = json.loads(raw_state) if raw_state else {"status": "unknown"}
    except (OSError, json.JSONDecodeError):
        state = {"status": "unknown", "read_error": "state file temporarily unavailable"}
    if pid:
        state["status"] = "awake"
        state["pid"] = pid
        STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    else:
        if state.get("status") == "awake" or state.get("status") == "unknown":
            state = {"status": "sleeping", "pid": None}
            STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        if "read_error" in state:
            state.pop("read_error", None)
        state["status"] = "sleeping"
        state["pid"] = None
    print(json.dumps({"running": bool(pid), "pid": pid, "state": state}, indent=2))


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "wake":
        wake()
    elif command in {"sleep", "stop"}:
        sleep_service()
    elif command == "status":
        status()
    else:
        print("Usage: python3 maya_service.py wake|sleep|status|stop")
        raise SystemExit(1)




