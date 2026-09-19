import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
items=[json.loads(x) for x in (ROOT/"feedback.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
text=" ".join(x["text"].lower() for x in items)
rules={"recurring":"Add recurring-task support","reminder":"Add local reminder checking","improve":"Add controlled self-improvement workflow"}
found=[v for k,v in rules.items() if k in text]
props=[{"id":i+1,"request":x,"status":"proposed"} for i,x in enumerate(found)]
(ROOT/"improvement.json").write_text(json.dumps(props,indent=2), encoding="utf-8")
print("Proposals:",len(props))
for p in props: print(p["id"],p["request"],"[proposed]")