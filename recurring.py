import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
F = ROOT / "tasks.json"


def load():
    if not F.exists():
        return []
    data = json.loads(F.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("tasks", [])


def save(q):
    tmp = F.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(q, indent=2) + "\n", encoding="utf-8")
    tmp.replace(F)


def add(text):
    q = load()
    q.append({
        "text": text,
        "done": False,
        "repeat": "weekly",
        "next_due": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
    })
    save(q)
    print(f"Added weekly task: {text}")


def list_weekly():
    q = load()
    rows = [t for t in q if t.get("repeat") == "weekly"]
    for i, t in enumerate(rows, 1):
        print(f"{i}. {t.get('text', 'Untitled')} (next {t.get('next_due', '')})")


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "add":
        add(" ".join(a[1:]))
    elif a[:1] == ["list"]:
        list_weekly()
    else:
        print("Usage: python recurring.py add TASK | list")


if __name__ == "__main__":
    main()