import sys
from pathlib import Path

candidate = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if candidate is None or not candidate.exists():
    print("Usage: python3 maya_relevance_supervisor.py PATH_TO_CANDIDATE")
    raise SystemExit(1)

text = candidate.read_text(encoding="utf-8").lower()
proposal = candidate.with_name("proposal.md")
if proposal.exists():
    text += "\n" + proposal.read_text(encoding="utf-8").lower()

forbidden = [
    "maya.cmds",
    "maya.utils",
    "autodesk maya",
    "mayasandbox.py",
    "maya runner",
]

found = [term for term in forbidden if term in text]
if found:
    print("RELEVANCE CHECK: FAIL")
    print("Candidate appears to target Autodesk Maya or an unrelated runtime:")
    for term in found:
        print(f"- {term}")
    raise SystemExit(1)

print("RELEVANCE CHECK: PASS — no known Autodesk Maya drift detected")
