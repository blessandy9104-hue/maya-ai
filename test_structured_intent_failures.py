import json
from maya_intent_cues import classify_opening
from pathlib import Path
results=json.loads(Path(__file__).resolve().with_name("benchmark_results_ml.json").read_text(encoding="utf-8-sig"))
failures=results["adjusted_misclassifications"]
print("FAILURES",len(failures))
for item in failures:
    value=classify_opening(item["sentence"])
    print(json.dumps({"sentence":item["sentence"],"expected":item["expected"],"primary":value["primary_intent"],"secondary":value["secondary_intents"],"negated":value["negated_intents"],"confidence":value["confidence"],"ambiguous":value["ambiguous"]},ensure_ascii=False))
