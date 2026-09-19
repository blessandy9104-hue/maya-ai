import json,sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent
text=" ".join(sys.argv[1:])
entry={"type":"feedback","text":text,"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
with (ROOT / "feedback.jsonl").open("a", encoding="utf-8") as f: f.write(json.dumps(entry, ensure_ascii=False)+chr(10))
print("Feedback recorded:",text)