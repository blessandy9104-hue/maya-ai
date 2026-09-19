import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
o=json.loads((ROOT / "evolution/opportunities.json").read_text(encoding="utf-8"))
t=json.loads((ROOT / "evolution/templates.json").read_text(encoding="utf-8"))["templates"]
p=[]
for x in o:
    for y in t:
        if y["trigger"] in x["theme"]:
            p.append({"opportunity":x["theme"],"template":y["id"],"description":y["description"],"status":"candidate"})
(ROOT / "evolution/template_candidates.json").write_text(json.dumps(p,indent=2), encoding="utf-8")
print("Template candidates:",len(p))
for x in p: print(x["template"],x["status"])