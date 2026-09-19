import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
fb=ROOT/"feedback.jsonl"
items=[json.loads(x) for x in fb.read_text(encoding="utf-8").splitlines() if x.strip()] if fb.exists() else []
text=" ".join(x.get("text","").lower() for x in items)
rules={"recurring":"recurring task support","reminder":"local reminder checking","improve":"controlled self-improvement workflow","stats":"task statistics"}
hits=[{"theme":k,"request":v,"count":text.count(k)} for k,v in rules.items() if k in text]
(ROOT/"evolution/opportunities.json").write_text(json.dumps(hits,indent=2), encoding="utf-8")
print("Opportunities detected:",len(hits))
for x in hits: print(x["theme"],"count",x["count"])