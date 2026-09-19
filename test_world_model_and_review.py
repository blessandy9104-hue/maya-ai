import json
import tempfile
from pathlib import Path

import maya_world_model as world
import maya_suggestion_review as review
from maya_proactive_suggestions import generate_seed_suggestion, sample_scenario

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    world.EVIDENCE_FILE = root / "evidence.jsonl"
    result = world.add_evidence(
        claim="A public report describes a measurable change.",
        source="Public test report",
        source_url="https://example.org/report",
        confidence="high",
        evidence_type="report",
        published_at="2026-08-01",
    )
    assert result["status"] == "recorded"
    evidence = result["evidence"]
    assert evidence["retrieved_at"].endswith("Z")
    assert evidence["published_at"] == "2026-08-01"
    assert evidence["confidence"] == "high"
    assert evidence["visibility"] == "public_world_context"
    assert world.add_evidence(claim="token password secret", source="bad", confidence="high", evidence_type="fact")["status"] == "rejected"
    assert world.evidence_summary()["record_count"] == 1

    review.REVIEW_FILE = root / "reviews.json"
    review.AUDIT_FILE = root / "audit.jsonl"
    suggestion = generate_seed_suggestion(sample_scenario())
    registered = review.register_suggestion(suggestion)
    assert registered["review_status"] == "pending_review"
    suggestion_id = registered["suggestion_id"]
    assert review.inspect_suggestion(suggestion_id)["status"] == "ok"
    assert review.review_suggestion(suggestion_id, "approve")["status"] == "approved_pending_sandbox_and_regression"
    assert review.review_suggestion(suggestion_id, "approve")["status"] == "already_reviewed"

print("world_provenance=OK")
print("world_privacy_rejection=OK")
print("suggestion_pending_review=OK")
print("suggestion_approval_gate=OK")
print("no_automatic_activation=OK")
