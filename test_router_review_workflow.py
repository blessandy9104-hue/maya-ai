"""Router-level review-workflow walkthrough.

Isolated from the real suggestion-review state so running this test
doesn't leave the checked-in maya_suggestion_reviews.json / audit log dirty.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import maya_suggestion_review as review_module
from maya_chat import maya_local_command

_tmp_dir = tempfile.TemporaryDirectory()
_patches = [
    patch.object(review_module, "REVIEW_FILE", Path(_tmp_dir.name) / "maya_suggestion_reviews.json"),
    patch.object(review_module, "AUDIT_FILE", Path(_tmp_dir.name) / "maya_suggestion_review_audit.jsonl"),
]
for _p in _patches:
    _p.start()

world = json.loads(maya_local_command(":world summary"))
assert world["status"] == "neutral_world_model"
assert world["private_memory_access"] is False
assert world["automatic_external_action"] is False

seed = json.loads(maya_local_command(":seed demo"))
assert seed["review_status"] in {"pending_review", "approved_pending_sandbox_and_regression", "rejected_by_user"}
assert seed["suggestion_id"]

queue = maya_local_command(":suggestion review")
assert seed["suggestion_id"] in queue

blocked = maya_local_command(f":suggestion approve {seed['suggestion_id']}")
assert "Explicit confirmation required" in blocked

inspection = json.loads(maya_local_command(f":suggestion inspect {seed['suggestion_id']}"))
assert inspection["status"] == "ok"
assert inspection["suggestion"]["review_status"] == seed["review_status"]

print("world_summary_route=OK")
print("seed_registration_route=OK")
print("pending_review_route=OK")
print("inspect_route=OK")
print("explicit_confirmation_gate=OK")