import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CANDIDATES = BASE / "evolution" / "candidates"
MODEL = os.environ.get("MAYA_CANDIDATE_MODEL", "qwen2.5-coder:3b")
API_URL = os.environ.get("MAYA_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
TIMEOUT = 300
MAX_PROMPT = 4000
MAX_ATTEMPTS = 2

DRIFT_TERMS = ["maya.cmds", "maya.utils", "autodesk maya", "mayasandbox.py", "maya runner"]

SYSTEM_GUIDANCE = (
    "You generate self-contained feature proposals for a local personal assistant "
    "codebase. Constraints: everything stays local; never modify, generate, or activate "
    "any live project file; never target Autodesk Maya or unrelated cloud products; do "
    "not call Python APIs that may not exist in the codebase; do not import the "
    "interactive chat module and do not start an interactive loop. Format: a Markdown "
    "proposal with Overview, Implementation, Tests, Risks, and Rollback sections. Put "
    "the complete implementation in EXACTLY ONE python fenced code block. The code must "
    "run standalone and terminate quickly when executed with no arguments."
)


def ask_ollama(user: str) -> str:
    payload = {
        "model": MODEL,
        "stream": False,
        "options": {"num_predict": 4000, "temperature": 0.4},
        "messages": [
            {"role": "system", "content": SYSTEM_GUIDANCE},
            {"role": "user", "content": user},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            text = resp.read().decode("utf-8")
    except Exception as exc:
        print(f"Ollama request failed: {exc}", file=sys.stderr)
        return ""
    try:
        data = json.loads(text)
    except ValueError:
        return ""
    return (data.get("message") or {}).get("content", "").strip()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 maya_generate_candidate.py PROMPT", file=sys.stderr)
        return 1
    request = " ".join(sys.argv[1:]).strip()
    if not request:
        print("Empty prompt", file=sys.stderr)
        return 1
    if len(request) > MAX_PROMPT:
        print(f"Prompt too long (max {MAX_PROMPT} chars)", file=sys.stderr)
        return 1
    if not CANDIDATES.exists():
        print(f"Candidates directory missing: {CANDIDATES}", file=sys.stderr)
        return 1

    feedback = "No prior attempt."
    for attempt in range(1, MAX_ATTEMPTS + 1):
        content = ask_ollama(request + "\nPrevious feedback: " + feedback)
        if not content:
            feedback = "The model returned an empty proposal."
            print(f"Attempt {attempt}: empty model output", file=sys.stderr)
            continue

        lowered = content.lower()
        hits = [t for t in DRIFT_TERMS if t in lowered]
        if hits:
            feedback = (
                "Candidate drifted off-topic: " + ", ".join(hits)
                + ". Stay strictly local to the assistant codebase."
            )
            print(f"Attempt {attempt}: drift terms present; retrying", file=sys.stderr)
            continue

        if "```python" not in content:
            feedback = "No python fenced code block was provided. Always include exactly one ```python code fence."
            print(f"Attempt {attempt}: no code fence; retrying", file=sys.stderr)
            continue

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = CANDIDATES / ("generated-" + stamp)
        out.mkdir(parents=True, exist_ok=True)
        (out / "proposal.md").write_text(content, encoding="utf-8")
        print(out)
        return 0

    print("Candidate generation failed after retries.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Candidate generation crashed: {exc}", file=sys.stderr)
        raise SystemExit(1)