"""Regression checks for local evidence freshness and source comparison."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import maya_world_model as world


with tempfile.TemporaryDirectory() as directory:
    original_file = world.EVIDENCE_FILE
    try:
        world.EVIDENCE_FILE = Path(directory) / "evidence.jsonl"
        first = world.add_evidence(
            claim="Transit use increased in the city.",
            source="Transport report",
            confidence="medium",
            evidence_type="report",
        )["evidence"]
        second = world.add_evidence(
            claim="Transit use did not increase in the city.",
            source="Independent survey",
            confidence="low",
            evidence_type="observation",
        )["evidence"]
        first["retrieved_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat().replace("+00:00", "Z")
        world.EVIDENCE_FILE.write_text("\n".join(json.dumps(row) for row in (first, second)) + "\n", encoding="utf-8")

        comparison = world.compare_sources("transit city")
        assert comparison["matching_records"] == 2
        assert comparison["distinct_sources"] == 2
        assert comparison["stale_records"] == 1
        assert comparison["conflict_flagged_records"] == 1
        summary = world.evidence_summary()
        assert summary["stale_records"] == 1
        assert summary["fresh_records"] == 1
    finally:
        world.EVIDENCE_FILE = original_file

print("world_freshness=OK")
print("world_source_comparison=OK")
print("world_conflict_visibility=OK")
