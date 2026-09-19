import json
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent

STATE = ROOT / "maya_service_state.json"
RUNNING = True


def now():
    return datetime.now(timezone.utc).isoformat()


def write_state(status):
    data = {
        "status": status,
        "updated_at": now(),
        "pid": __import__("os").getpid()
    }
    STATE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def stop_handler(signum, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGTERM, stop_handler)
signal.signal(signal.SIGINT, stop_handler)
write_state("awake")

while RUNNING:
    write_state("awake")
    time.sleep(5)

write_state("sleeping")


