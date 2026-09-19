import json
from pathlib import Path

from maya_suggestion_review import inspect_suggestion

review_file = Path(__file__).with_name("maya_suggestion_reviews.json")
payload = json.loads(review_file.read_text(encoding="utf-8"))
item = next(item for item in payload.get("suggestions", []) if item.get("suggestion_id") == "mother_maya_seed_hypothesis")
assert item["review_status"] == "approved_pending_sandbox_and_regression"
assert item["automatic_activation"] is False
assert item["memory_update"] == "not_performed"
assert item["external_action"] == "not_performed"
assert inspect_suggestion("mother_maya_seed_hypothesis")["status"] == "ok"

print(json.dumps({
    "sandbox_review": "READY_AND_SAFE",
    "suggestion_id": item["suggestion_id"],
    "review_status": item["review_status"],
    "automatic_activation": item["automatic_activation"],
    "memory_update": item["memory_update"],
    "external_action": item["external_action"],
    "next_stage": "sandbox_regression_only",
}, indent=2))
