import json,sys,re
from pathlib import Path
from datetime import datetime
ROOT = Path(__file__).resolve().parent
F=ROOT/"tasks.json"
q=json.loads(F.read_text(encoding="utf-8")) if F.exists() else []
text=" ".join(sys.argv[1:])
due=""
for word in ("today","tomorrow","monday","tuesday","wednesday","thursday","friday","saturday","sunday"):
    if word in text.lower(): due=word; break
q.append({"text":text,"done":False,"due":due,"created":datetime.now().strftime("%Y-%m-%d %H:%M")})
F.write_text(json.dumps(q,indent=2)+"\n", encoding="utf-8")
print("Added:",text,"Due:",due or "not set")