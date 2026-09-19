import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE / "evolution" / "candidates"
POLICY = json.loads((BASE / "evolution" / "activation_policy.json").read_text())
MAX_ATTEMPTS = int(POLICY.get("max_retry_attempts", 5))
REQUEST = " ".join(sys.argv[1:]).strip()

if not REQUEST:
    print("Usage: python3 maya_experiment_loop.py FEATURE_REQUEST")
    raise SystemExit(1)

feedback = "No previous attempt. Propose a genuinely creative solution."

for attempt in range(1, MAX_ATTEMPTS + 1):
    prompt = f"""Attempt {attempt} of {MAX_ATTEMPTS}.
Feature request: {REQUEST}
Previous evaluation feedback: {feedback}
You may invent a new design. Return a reviewable proposal with an exact implementation, tests, risks, and rollback steps. Do not assume nonexistent project APIs. Do not activate anything."""

    before = {p for p in ROOT.glob("generated-*")}
    result = subprocess.run(
        [sys.executable, str(BASE / "maya_generate_candidate.py"), prompt],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        feedback = result.stderr.strip() or "proposal generator failed"
        print(f"Attempt {attempt}: generator failed")
        continue

    after = sorted({p for p in ROOT.glob("generated-*")} - before)
    if not after:
        feedback = "No candidate directory was created."
        print(f"Attempt {attempt}: no candidate created")
        continue

    candidate_dir = after[-1]
    proposal = candidate_dir / "proposal.md"
    text = proposal.read_text(encoding="utf-8") if proposal.exists() else ""
    code_blocks = text.split("```python")[1:]

    if not code_blocks:
        feedback = "The proposal contained no executable Python implementation block."
        print(f"Attempt {attempt}: proposal only; retrying")
        continue

    code = code_blocks[0].split("```")[0].strip() + "\n"
    sandbox_file = candidate_dir / "candidate_impl.py"
    sandbox_file.write_text(code, encoding="utf-8")
    check = subprocess.run(
        [sys.executable, "-m", "py_compile", str(sandbox_file)],
        capture_output=True,
        text=True,
    )

    if check.returncode == 0:
        print(f"Attempt {attempt}: syntax passed")
        print(f"Review candidate: {candidate_dir}")
        print("No activation performed; human approval is still required.")
        raise SystemExit(0)

    feedback = check.stderr.strip() or "syntax test failed"
    print(f"Attempt {attempt}: syntax failed; retrying")

print("No candidate passed the bounded experiment loop.")
print("Maya remains unchanged.")
raise SystemExit(1)
