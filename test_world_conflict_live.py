"""Verify conflict flags without adding fixtures to Maya's real evidence ledger."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import maya_world_model as world


with tempfile.TemporaryDirectory() as directory:
    original_file = world.EVIDENCE_FILE
    try:
        world.EVIDENCE_FILE = Path(directory) / "evidence.jsonl"
        positive = world.add_evidence(
            claim="Conflict test service is available to users.",
            source="Conflict simulation source A",
            source_url="https://example.org/conflict-a",
            confidence="medium",
            evidence_type="observation",
        )
        negative = world.add_evidence(
            claim="Conflict test service is not available to users.",
            source="Conflict simulation source B",
            source_url="https://example.org/conflict-b",
            confidence="low",
            evidence_type="observation",
        )
        record = negative["evidence"]
        assert positive["status"] == "recorded"
        assert negative["status"] == "recorded"
        assert record["conflict_status"] == "conflict_flagged"
        assert positive["evidence"]["evidence_id"] in record["conflicts_with"]
        assert world.evidence_summary()["conflict_flagged_records"] == 1
    finally:
        world.EVIDENCE_FILE = original_file

print(json.dumps({
    "conflict_simulation": "OK",
    "conflict_status": record["conflict_status"],
    "truth_auto_resolved": False,
    "memory_update": "not_performed",
    "external_action": "not_performed",
}, indent=2))
