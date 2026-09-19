import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
opportunities_path = ROOT / "evolution" / "opportunities.json"
knowledge_root = ROOT / "knowledge"
report_dir = ROOT / "evolution" / "reports"
report_dir.mkdir(parents=True, exist_ok=True)

opportunities = json.loads(opportunities_path.read_text(encoding="utf-8"))
implemented = {"recurring": True, "stats": True, "improve": False, "reminder": False}


def knowledge_matches(query):
    terms = [word.lower() for word in query.split() if word.strip()]
    matches = []
    if not knowledge_root.exists():
        return matches
    for path in sorted(knowledge_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        score = sum(text.lower().count(term) for term in terms)
        if score:
            matches.append({"path": str(path), "match_count": score})
    return sorted(matches, key=lambda item: (-item["match_count"], item["path"]))[:5]


for item in opportunities:
    theme = item["theme"]
    item["status"] = "implemented" if implemented.get(theme, False) else "pending"
    item["knowledge_sources"] = knowledge_matches(theme + " " + item.get("request", ""))

report = {
    "cycle": 1,
    "opportunities": opportunities,
    "live_version": "v4",
    "activation_required": True,
    "knowledge_policy": "read_only_approved_sources"
}

(ROOT / "evolution" / "reports" / "cycle_1.json").write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
print("Cycle report created with knowledge sources")
for item in opportunities:
    print(item["theme"], item["status"], len(item["knowledge_sources"]), "source(s)")
