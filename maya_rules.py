import json
from pathlib import Path
ROOT = Path(__file__).parent

def fast_answer(text, history):
    lower = text.lower().strip()
    if any(marker in lower for marker in ("opportunit", "ways to earn", "map three", "income")):
        from maya_pattern_mapping import render_pattern_map
        return render_pattern_map(text)

    if lower in {"say that again", "repeat that", "repeat yourself"}:
        for item in reversed(history):
            if item.get("role") == "assistant": return item.get("content", "I do not have a previous answer.")
        return "I do not have a previous answer to repeat."
    if lower in {"what can you do", "maya capabilities", "hello maya, what can you do"}:
        return "I can report status, perform public read-only research, manage activation, review observations, and learn approved patterns. I do not change permissions or trusted memory without approval."
    if lower in {"hello maya", "how are you", "are you okay", "are you awake"}:
        return "I am running locally. Use Status for service state; Presence Mode remains off unless explicitly implemented and enabled."
    if lower in {"can maya self-evolve", "can you self-evolve", "can maya self evolve", "can you self evolve"}:
        return "I can improve through supervised research, reviewed patterns, corrections, and approved proposals. I cannot rewrite my permissions or core behavior without approval."
    if any(word in lower for word in ("status", "running", "awake", "sleeping", "watching", "observing")) and lower.startswith(("what is maya", "is maya", "maya status")):
        return "Use the Status command for the authoritative service and activation state. Presence Mode remains off."
    if "preference" in lower or "remember" in lower:
        path = ROOT / "presence_preferences.jsonl"
        approved = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    if item.get("status") == "approved": approved.append(item.get("proposal", ""))
        return "My approved preferences are: " + "; ".join(approved) if approved else "I have no approved personal preferences saved."
    return None


