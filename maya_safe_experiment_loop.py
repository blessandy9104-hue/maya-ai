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
    print("Usage: python3 maya_safe_experiment_loop.py FEATURE_REQUEST")
    raise SystemExit(1)

feedback = "No previous attempt. Propose a creative but testable design."

for attempt in range(1, MAX_ATTEMPTS + 1):
    prompt = f"""Attempt {attempt} of {MAX_ATTEMPTS}.
Feature request: {REQUEST}
Previous supervisor feedback: {feedback}
You may invent a new architecture, but provide executable Python code and tests. Do not modify or activate active Maya files."""

    before = set(ROOT.glob("generated-*"))
    generated = subprocess.run(
        [sys.executable, str(BASE / "maya_generate_candidate.py"), prompt],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if generated.returncode != 0:
        feedback = generated.stderr.strip() or "candidate generation failed"
        print(f"Attempt {attempt}: generation failed")
        continue

    created = sorted(set(ROOT.glob("generated-*")) - before)
    if not created:
        feedback = "No candidate directory was created."
        print(f"Attempt {attempt}: no candidate created")
        continue

    candidate_dir = created[-1]
    proposal = candidate_dir / "proposal.md"
    text = proposal.read_text(encoding="utf-8") if proposal.exists() else ""
    blocks = text.split("```python")[1:]

    if not blocks:
        feedback = "No executable Python implementation block was provided."
        print(f"Attempt {attempt}: no code block; retrying")
        continue

    code = blocks[0].split("```")[0].strip() + "\n"
    candidate_file = candidate_dir / "candidate_impl.py"
    candidate_file.write_text(code, encoding="utf-8")

    checked = subprocess.run(
        [sys.executable, str(BASE / "maya_runtime_supervisor.py"), str(candidate_file)],
        capture_output=True,
        text=True,
        timeout=15,
    )

    if checked.returncode == 0:
        print(f"Attempt {attempt}: runtime supervisor passed")
        print(f"Review candidate: {candidate_dir}")
        print("No activation performed; human approval is still required.")
        raise SystemExit(0)

    feedback = (checked.stdout + "\n" + checked.stderr).strip()
    print(f"Attempt {attempt}: supervisor rejected candidate; retrying")
    print(feedback)

print("No candidate passed the bounded runtime loop.")
print("Maya remains unchanged.")
raise SystemExit(1)
