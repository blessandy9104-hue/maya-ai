import subprocess
import sys
from pathlib import Path

candidate_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if candidate_path is None or not candidate_path.exists():
    print("Usage: python3 maya_runtime_supervisor.py PATH_TO_CANDIDATE")
    raise SystemExit(1)

text = candidate_path.read_text(encoding="utf-8")
failed = False

if "import maya_chat" in text or "from maya_chat" in text:
    print("FAIL: candidate imports maya_chat.py, which starts the interactive loop at import time")
    failed = True

for name in ["MayaChat", "send_message"]:
    if name in text:
        print(f"NOTICE: candidate assumes interface name: {name}")

compile_result = subprocess.run(
    [sys.executable, "-m", "py_compile", str(candidate_path)],
    capture_output=True,
    text=True,
)
if compile_result.returncode != 0:
    print("FAIL: syntax check")
    print(compile_result.stderr.strip())
    failed = True
else:
    print("PASS: syntax check")

try:
    result = subprocess.run(
        [sys.executable, str(candidate_path)],
        input="exit\n",
        capture_output=True,
        text=True,
        timeout=3,
    )
    if "Maya is ready" in result.stdout:
        print("FAIL: candidate triggered Maya's interactive loop")
        failed = True
    else:
        print("PASS: no detected interactive side effect")
except subprocess.TimeoutExpired:
    print("FAIL: candidate did not terminate within 3 seconds")
    failed = True

if failed:
    print("CANDIDATE REJECTED BY RUNTIME SUPERVISOR")
    raise SystemExit(1)

print("CANDIDATE PASSED RUNTIME SUPERVISOR")
