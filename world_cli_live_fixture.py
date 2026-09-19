import json
from maya_chat import maya_local_command

add_output = json.loads(maya_local_command(":world add | Sample public claim used for CLI verification only. | Maya verification fixture | high | report | https://example.org/maya-cli-test"))
assert add_output["status"] == "recorded"
record = add_output["evidence"]
assert record["confidence"] == "high"
assert record["source"] == "Maya verification fixture"
assert record["source_url"] == "https://example.org/maya-cli-test"
assert record["retrieved_at"].endswith("Z")
assert record["visibility"] == "public_world_context"

summary = json.loads(maya_local_command(":world summary"))
assert summary["status"] == "neutral_world_model"
assert summary["confidence_counts"]["high"] >= 1

listing = maya_local_command(":world list")
assert record["evidence_id"][:12] in listing
assert "high" in listing

print(json.dumps({
    "cli_add": "OK",
    "confidence": record["confidence"],
    "retrieved_at": record["retrieved_at"],
    "source": record["source"],
    "world_summary": "OK",
    "world_list": "OK",
}, indent=2))
