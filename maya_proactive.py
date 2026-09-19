import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
p = ROOT / "tasks.json"


def suggestions():
    data = json.loads(p.read_text(encoding="utf-8"))
    tasks = data if isinstance(data, list) else data.get("tasks", [])
    open_tasks = [t for t in tasks if t.get("done") is not True and t.get("status") != "done"]
    lines = [f"Maya: You have {len(open_tasks)} open task(s)."]
    if open_tasks:
        lines.append("Maya: A useful next step is to review the first few open tasks:")
        for task in open_tasks[:3]:
            lines.append("- " + task.get("text", "Untitled task"))
    lines.append("Maya: These are suggestions only. I will not change tasks without your approval.")
    return "\n".join(lines)


def main():
    if not p.exists():
        print("Maya: I cannot find the task list yet.")
        raise SystemExit
    print(suggestions())


if __name__ == "__main__":
    main()