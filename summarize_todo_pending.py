from pathlib import Path

path = Path(__file__).with_name("todo.md")
lines = path.read_text(encoding="utf-8").splitlines()
pending = [line for line in lines if line.startswith("- [ ]")]
print(f"REMAINING_UNCHECKED={len(pending)}")
for line in pending[:20]:
    print(line)
