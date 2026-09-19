import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
STATUS = ROOT / "presence_status.json"
STOP = ROOT / "PRESENCE_STOP"
POWERSHELL = "powershell.exe"


def blocked(message):
    print("BLOCKED: " + message)
    raise SystemExit(1)


if not STATUS.exists():
    blocked("Presence Mode has not been initialized")
status = json.loads(STATUS.read_text(encoding="utf-8"))
if status.get("mode") != "on":
    blocked("Presence Mode is not explicitly enabled")
if STOP.exists():
    blocked("emergency stop is active")

context = " ".join(sys.argv[1:]).strip() or "editor"
subprocess.run([sys.executable, str(ROOT / "presence_guard.py"), "app", context], check=True)

if "--capture" not in sys.argv:
    print("DRY RUN: permission and privacy checks passed; no screenshot captured")
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix="maya_presence_") as temp:
    output = Path(temp) / "screen.png"
    subprocess.run([
        POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(ROOT / "capture_screen.ps1"),
        "-OutputPath", str(output),
    ], check=True)
    if not output.exists() or output.stat().st_size == 0:
        blocked("capture did not produce a valid image")
    print(f"LOCAL CAPTURE CREATED: {output.stat().st_size} bytes")
    print("The temporary screenshot will be deleted immediately.")

print("LOCAL CAPTURE DELETED")
