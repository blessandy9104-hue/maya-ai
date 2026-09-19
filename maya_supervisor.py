import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
candidate_number = sys.argv[1] if len(sys.argv) > 1 else "2"
candidate = BASE / "evolution" / "candidates" / f"v{candidate_number}" / "assistant.py"

if not candidate.exists():
    print(f"Candidate not found: {candidate}")
    raise SystemExit(1)

checks = [
    ("syntax", [sys.executable, "-m", "py_compile", str(candidate)], ""),
    ("task list", [sys.executable, str(candidate), "task", "list"], "Total:"),
    ("task stats", [sys.executable, str(candidate), "task", "stats"], "Total:"),
]

failed = False
for name, command, required in checks:
    result = subprocess.run(command, capture_output=True, text=True)
    passed = result.returncode == 0 and (not required or required in result.stdout)
    print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not passed:
        failed = True
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())

if failed:
    print(f"Candidate {candidate_number} rejected by supervisor")
    raise SystemExit(1)

print(f"Candidate {candidate_number} passed supervisor checks")
