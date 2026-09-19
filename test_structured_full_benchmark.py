import json
from maya_intent_cues import classify_opening
from pathlib import Path
src=Path(__file__).resolve().with_name("test_intent_benchmark.py")
text=open(src,encoding="utf-8-sig").read()
ns={}
exec(text,ns)
cases=ns["cases"][:50]
rows=[]
primary=0
covered=0
for sentence,expected in cases:
    value=classify_opening(sentence)
    all_intents=[value["primary_intent"]]+value["secondary_intents"]
    primary += int(value["primary_intent"]==expected)
    covered += int(expected in all_intents)
    if expected not in all_intents: rows.append({"sentence":sentence,"expected":expected,"structured":value})
print(json.dumps({"cases":len(cases),"primary_correct":primary,"primary_accuracy":primary/len(cases),"covered_by_primary_or_secondary":covered,"coverage":covered/len(cases),"uncovered_failures":rows},indent=2,ensure_ascii=False))
