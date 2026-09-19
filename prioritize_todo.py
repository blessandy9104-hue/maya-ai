from pathlib import Path

lines = Path(__file__).with_name("todo.md").read_text(encoding="utf-8").splitlines()
current = "Uncategorized"
groups = {}
for line in lines:
    if line.startswith("## "):
        current = line[3:].strip()
        groups.setdefault(current, [])
    elif line.startswith("- [ ]"):
        groups.setdefault(current, []).append(line[6:].strip())

for heading, items in groups.items():
    if not items:
        continue
    text = " ".join(items).lower()
    if any(word in text for word in ("install", "network", "voice", "microphone", "external", "cross-user", "desktop application", "power", "brightness", "cooling")):
        tier = "APPROVAL / DEFER"
    elif any(word in text for word in ("benchmark", "test", "report", "document", "source", "simulate", "score", "calibrate", "class")):
        tier = "SAFE LOCAL"
    else:
        tier = "SAFE WITH REVIEW"
    print(f"[{tier}] {heading} ({len(items)})")
    for item in items[:4]:
        print(f"  - {item}")
