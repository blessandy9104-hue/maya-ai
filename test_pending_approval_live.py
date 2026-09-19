"""Live approval-gate walkthrough.

Uses a temp-dir copy of the suggestion-review state so the test is
idempotent: the shipped ``maya_suggestion_reviews.json`` previously carried
review state across runs (a suggestion left "approved" from a prior run
would make a second run fail), which this isolation avoids.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import maya_suggestion_review as review_module
from maya_chat import maya_local_command

_tmp_dir = tempfile.TemporaryDirectory()
_review_file = Path(_tmp_dir.name) / "maya_suggestion_reviews.json"
_audit_file = Path(_tmp_dir.name) / "maya_suggestion_review_audit.jsonl"
_patches = [
    patch.object(review_module, "REVIEW_FILE", _review_file),
    patch.object(review_module, "AUDIT_FILE", _audit_file),
]
for _p in _patches:
    _p.start()

seed = json.loads(maya_local_command(":seed demo"))
suggestion_id = seed["suggestion_id"]
queue = maya_local_command(":suggestion review")
assert suggestion_id in queue
inspection = json.loads(maya_local_command(f":suggestion inspect {suggestion_id}"))
assert inspection["status"] == "ok"
assert inspection["suggestion"]["review_status"] == "pending_review"

blocked = maya_local_command(f":suggestion approve {suggestion_id}")
assert "Explicit confirmation required" in blocked

approved = json.loads(maya_local_command(f":suggestion approve {suggestion_id} confirm"))
assert approved["status"] == "approved_pending_sandbox_and_regression"
assert approved["automatic_activation"] is False
assert approved["memory_update"] == "not_performed"
assert approved["external_action"] == "not_performed"

print(json.dumps({
    "suggestion_id": suggestion_id,
    "queue_inspection": "OK",
    "confirmation_gate": "OK",
    "approval_status": approved["status"],
    "automatic_activation": approved["automatic_activation"],
    "memory_update": approved["memory_update"],
    "external_action": approved["external_action"],
}, indent=2))

for _p in _patches:
    _p.stop()
_tmp_dir.cleanup()