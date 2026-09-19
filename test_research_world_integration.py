"""Regression tests for world-baseline <-> research integration.

Covers:
- _world_baseline matches neutral world-evidence claims to a topic.
- research_summary renders a "Known world baseline" section.
- _persist_research_disagreements is gated by maya_service.running_pid()
  (no writes when the service is offline).
- maya_world_model.add_research_conflict persists a neutral, review-only
  disagreement note (never trusted memory).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_web_research as r
import maya_world_model as wm

RESULT = []


def case(name):
    def deco(fn):
        def wrapper(*args, **kwargs):
            try:
                fn(*args, **kwargs)
                RESULT.append(name + "=OK")
            except Exception as exc:
                RESULT.append(name + "=FAIL")
                raise
        return wrapper
    return deco


def _isolated_world(rows):
    """Point maya_world_model's store at a temp file containing rows."""
    tmp = Path(tempfile.mkdtemp()) / "world_evidence.jsonl"
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    wm.EVIDENCE_FILE = tmp
    return tmp


_BASE_ROW = {
    "evidence_id": "11111111-1111-1111-1111-111111111111",
    "claim": "Epistemology is the branch of philosophy that examines knowledge.",
    "source": "external_open_ref",
    "source_url": "https://external.example/epistemology",
    "retrieved_at": "2026-09-01T00:00:00Z",
    "confidence": "high",
    "evidence_type": "fact",
    "conflict_status": "no_conflict_detected",
    "conflicts_with": [],
    "visibility": "public_world_context",
    "memory_update": "not_performed",
}


@case("world_baseline_match")
def test_baseline_match():
    _isolated_world([_BASE_ROW])
    rows = r._world_baseline("philosophy")
    assert len(rows) == 1, rows
    assert rows[0]["evidence_id"] == _BASE_ROW["evidence_id"], rows
    assert r._world_baseline("gardening") == [], r._world_baseline("gardening")


@case("summary_renders_baseline")
def test_summary_renders_baseline():
    _isolated_world([_BASE_ROW])
    row = {"url": "https://en.wikipedia.org/wiki/Epistemology",
           "title": "Epistemology", "host": "en.wikipedia.org",
           "class": "encyclopedic", "relevance": 1.0,
           "tier": "high", "belief": 0.85,
           "snippet": "Epistemology is the study of knowledge and justified belief."}
    text = r.research_summary("philosophy", [row],
                              {"allowed_hosts": ["en.wikipedia.org"]})
    assert "Known world baseline (neutral stored evidence, review-only):" in text, text
    assert "Epistemology is the branch of philosophy" in text, text
    assert "No trusted memory update occurred." in text


@case("contradiction_persist_gated_offline")
def test_contradiction_persist_gated_offline():
    _isolated_world([])
    original = r.maya_service.running_pid
    r.maya_service.running_pid = lambda: None
    try:
        rows = [
            {"url": "https://en.wikipedia.org/wiki/A", "title": "A",
             "host": "en.wikipedia.org", "class": "encyclopedic",
             "relevance": 1.0, "tier": "high", "belief": 0.85,
             "snippet": "The red panda is not hibernating in winter."},
            {"url": "https://en.wikipedia.org/wiki/B", "title": "B",
             "host": "en.wikipedia.org", "class": "encyclopedic",
             "relevance": 1.0, "tier": "high", "belief": 0.85,
             "snippet": "The red panda is hibernating in winter."},
        ]
        pairs = r._detect_contradictions(rows)
        assert pairs, "expected a contradiction pair"
        count = r._persist_research_disagreements("topic", pairs, rows)
        assert count == 0, count
        assert wm.read_evidence() == [], wm.read_evidence()
    finally:
        r.maya_service.running_pid = original


@case("contradiction_persist_when_live")
def test_contradiction_persist_when_live():
    tmp = _isolated_world([])
    original = r.maya_service.running_pid
    r.maya_service.running_pid = lambda: 424242
    try:
        rows = [
            {"url": "https://en.wikipedia.org/wiki/A", "title": "A",
             "host": "en.wikipedia.org", "class": "encyclopedic",
             "relevance": 1.0, "tier": "high", "belief": 0.85,
             "snippet": "The red panda is not hibernating in winter."},
            {"url": "https://en.wikipedia.org/wiki/B", "title": "B",
             "host": "en.wikipedia.org", "class": "encyclopedic",
             "relevance": 1.0, "tier": "high", "belief": 0.85,
             "snippet": "The red panda is hibernating in winter."},
        ]
        pairs = r._detect_contradictions(rows)
        assert pairs
        count = r._persist_research_disagreements("topic", pairs, rows)
        assert count == 1, count
        stored = wm.read_evidence()
        assert len(stored) >= 1
        rec = stored[0]
        assert rec["memory_update"] == "not_performed", rec
        assert rec["external_action"] == "not_performed", rec
        assert rec["evidence_type"] == "observation", rec
        assert rec["confidence"] == "low", rec
        assert "disagree" in rec["claim"], rec
    finally:
        r.maya_service.running_pid = original
        r._world_baseline.__self__ if False else None


@case("research_conflict_note_schema")
def test_research_conflict_note_schema():
    tmp = _isolated_world([])
    result = wm.add_research_conflict(
        topic="sample topic",
        sentence_a="The network was restored.",
        url_a="https://docs.example/a",
        host_a="docs.example",
        sentence_b="The network was not restored.",
        url_b="https://docs.example/b",
        host_b="docs.example",
    )
    assert result["status"] == "recorded", result
    item = result["evidence"]
    assert item["source"] == "research_synthesis"
    assert item["perspective"] == "https://docs.example/b"
    assert item["memory_update"] == "not_performed"
    assert item["conflict_status"] in {"conflict_flagged", "no_conflict_detected"}
    assert "disagree" in item["claim"]
    assert wm.read_evidence()[0]["evidence_id"] == item["evidence_id"]


def main():
    for fn in (test_baseline_match, test_summary_renders_baseline,
               test_contradiction_persist_gated_offline,
               test_contradiction_persist_when_live,
               test_research_conflict_note_schema):
        fn()
    print("\n".join(RESULT))
    print("research_world_integration_suite=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())