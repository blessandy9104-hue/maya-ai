"""Evidence drilldown verification suite.

Pins the provenance surface after the architecture pass: IDs and the
registry (with its single writer/reader) live in maya_evidence; answer
analysis and summary evidence extraction live in maya_web_research (the
module that produced the answer); the world store exposes its rows only
through read_evidence. The :evidence router branch loads persisted answers
via load_answers and hands them to pure renderers. Write-mode checks run
on injected temporary paths; the real registry and world store are only
read.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_chat
import maya_evidence as ev
import maya_web_research as research
from maya_world_model import list_evidence, read_evidence


def _ok(label: str) -> None:
    print(label + " =OK")


REAL_REGISTRY = ev.REGISTRY_FILE
WORLD_STORE = Path("maya_world_evidence.jsonl")


def _tmp_registry() -> Path:
    return Path(tempfile.mkdtemp()) / "evidence_registry.jsonl"


ROWS_AGREE = [
    {"url": "https://plato.stanford.edu/entries/probe/", "title": "Probe - Stanford",
     "host": "plato.stanford.edu", "class": "scholarly", "tier": "high", "belief": 0.85,
     "snippet": "The probe experiment confirmed the expected result.", "relevance": 0.9},
    {"url": "https://en.wikipedia.org/wiki/Probe", "title": "Probe - Wikipedia",
     "host": "en.wikipedia.org", "class": "encyclopedic", "tier": "medium", "belief": 0.6,
     "snippet": "Later reviews also describe the probe result as confirmed.", "relevance": 0.8},
]
ROWS_CONFLICT = [
    {"url": "https://a.org/x", "title": "A", "class": "scholarly", "tier": "high",
     "belief": 0.85, "snippet": "The mars surface probe confirmed water ice exists beneath the surface.",
     "relevance": 0.9},
    {"url": "https://b.org/y", "title": "B", "class": "encyclopedic", "tier": "medium",
     "belief": 0.6, "snippet": "The mars surface probe did not confirm water ice exists beneath the surface.",
     "relevance": 0.8},
]

# ---- 1. deterministic content-derived IDs --------------------------------

a = ev.evidence_id_for_row("https://a.org/x", "The probe result.")
b = ev.evidence_id_for_row("https://a.org/x", "The  probe   result. ")
c = ev.evidence_id_for_row("https://a.org/x", "Different excerpt entirely.")
assert a == b and a != c, (a, b, c)
assert a.startswith("ev-") and len(a) == 13, a
# ID is invariant to title presence: a cache row with title and a parsed
# row without one hash identically, so cross-session lookup works.
assert ev.evidence_id_for_row("https://a.org/x", "snippet one") == \
    ev.evidence_id_for_row(url="https://a.org/x", snippet="snippet one")
_ok("evidence_ids_deterministic")


# ---- 2. registry round-trip: idempotent, capped, honest on empty ----------

reg = _tmp_registry()
out = ev.register_answer("probe topic", ROWS_AGREE, {"retrieved_at": "2026-09-15T10:00:00Z"},
                         session_id="sess-A", registry_path=reg)
assert out["status"] == "registered" and len(out["evidence_ids"]) == 2, out
again = ev.register_answer("probe topic", ROWS_AGREE, {"retrieved_at": "2026-09-15T10:00:00Z"},
                           session_id="sess-A", registry_path=reg)
assert again["status"] == "already_registered", again
assert len(ev.load_answers(reg)) == 1  # idempotent: no duplicate row
empty = ev.register_answer("nothing", [], {}, registry_path=reg)
assert empty["status"] == "nothing_registered"
# Registry cap keeps only the most recent answers (own registry so the main
# fixture answer below is not evicted).
cap_reg = _tmp_registry()
for index in range(ev.REGISTRY_MAX_ANSWERS + 3):
    ev.register_answer("cap topic %d" % index, ROWS_AGREE[:1], {}, registry_path=cap_reg)
cap_rows = ev.load_answers(cap_reg)
assert len(cap_rows) == ev.REGISTRY_MAX_ANSWERS, len(cap_rows)
assert cap_rows[-1]["topic"] == "cap topic %d" % (ev.REGISTRY_MAX_ANSWERS + 2)
assert cap_rows[0]["topic"] == "cap topic 3"
# Analysis is delegated to the research owner and matches its verdict.
registered = ev.load_answers(reg)[0]
verdict = research.analyze_rows(ROWS_AGREE)
assert registered["answer_status"] == verdict["status"], (registered, verdict)
assert registered["answer_confidence"] == verdict["confidence"]
assert registered["answer_belief"] == verdict["belief"]
_ok("registry_roundtrip_idempotent_capped")


# ---- 3. research drilldown: full provenance fields ------------------------

answers = [row for row in ev.load_answers(reg) if row.get("topic", "").startswith("probe topic")]
assert answers, reg.read_text(encoding="utf-8")[:200]
source = answers[0]["sources"][0]
answer_id = source["evidence_id"]
detail = ev.drilldown(answer_id, answers=ev.load_answers(reg))
for field in ("Evidence %s (research)" % answer_id, "Topic: probe topic",
              "Supports: The probe experiment confirmed", "Source: https://plato.stanford.edu",
              "Type: scholarly | Confidence: high (belief 0.85)", "Retrieved:",
              "Freshness:", "Conflicts: no contradiction detected",
              "Answer context: status"):
    assert field in detail, (field, detail)
# The conflicting fixture flags the contradiction inside the answer context.
conf_reg = _tmp_registry()
ev.register_answer("mars ice", ROWS_CONFLICT, {}, registry_path=conf_reg)
conf_answer = ev.load_answers(conf_reg)[0]
conf_detail = ev.drilldown(conf_answer["sources"][0]["evidence_id"], answers=[conf_answer])
assert "flagged as contradicting" in conf_detail and "within the same answer" in conf_detail, conf_detail
# Conflict map is index-space and symmetric, from the research owner.
cmap = research._conflict_index_map(ROWS_CONFLICT)
assert cmap == {0: [1], 1: [0]}, cmap
_ok("research_drilldown_complete")


# ---- 4. world drilldown over the real store (read-only) -------------------

world_rows = list_evidence(1)
assert world_rows, "world model fixture row expected"
world_id = world_rows[0]["evidence_id"]
assert read_evidence(), "read_evidence must expose the store rows"
world_detail = ev.drilldown(world_id)
for field in ("Evidence %s (world model)" % world_id, "Claim:", "Source:",
              "Type: ", "Retrieved: ", "Freshness:", "Conflicts:", "Uncertainty:",
              "Visibility:"):
    assert field in world_detail, (field, world_detail)
# Unambiguous prefix lookup on both stores.
assert ev.drilldown(world_id[:8]).startswith("Evidence %s (world model)" % world_id)
assert ev.drilldown(answer_id[:8], answers=ev.load_answers(reg)).startswith(
    "Evidence %s (research)" % answer_id)
_ok("world_drilldown_complete")


# ---- 5. freshness is clock-injectable and honest --------------------------

stale = ev.drilldown(world_id, now=datetime(2027, 1, 1, tzinfo=timezone.utc))
assert "stale (" in stale, stale
fresh = ev.drilldown(world_id, now=datetime(2026, 9, 15, tzinfo=timezone.utc))
assert "fresh (" in fresh, fresh
row_no_time = dict(world_rows[0])
row_no_time["retrieved_at"] = ""
assert "Freshness: unknown" in ev._world_drilldown(row_no_time)
_ok("freshness_clock_injectable")


# ---- 6. miss, ambiguity, and help paths -----------------------------------

help_text = ev.drilldown("")
assert "Evidence drilldown" in help_text and ":evidence <id>" in help_text, help_text
miss = ev.drilldown("zzzzzzzzzz", answers=ev.load_answers(reg))
assert "No evidence record matches 'zzzzzzzzzz'" in miss, miss
# Two distinct answers sharing an 8-char prefix -> ambiguity, longer ID wins.
amb_reg = _tmp_registry()
ev.register_answer("amb one", [{"url": "https://x.org/1", "snippet": "one unique excerpt.",
                                "class": "general", "tier": "low"}], {}, registry_path=amb_reg)
ev.register_answer("amb two", [{"url": "https://x.org/2", "snippet": "two unique excerpt.",
                                "class": "general", "tier": "low"}], {}, registry_path=amb_reg)
amb_rows = ev.load_answers(amb_reg)
id1 = amb_rows[0]["sources"][0]["evidence_id"]
id2 = amb_rows[1]["sources"][0]["evidence_id"]
if id1[:8] == id2[:8]:
    ambiguous = ev.drilldown(id1[:8], answers=amb_rows)
    assert "ambiguous ID prefix" in ambiguous, ambiguous
    assert ev.drilldown(id1, answers=amb_rows).startswith("Evidence %s (research)" % id1)
_ok("miss_ambiguity_help")


# ---- 7. show_sources: newest first, capped, honest when empty -------------

listing = ev.show_sources(ev.load_answers(reg))
assert "newest first" in listing and "probe topic" in listing and answer_id in listing, listing
capped = ev.show_sources(list(ev.load_answers(reg))[-2:])
assert capped.count(". [research]") <= 2, capped
empty_listing = ev.show_sources([])
assert "No research answers are registered yet" in empty_listing, empty_listing
_ok("show_sources_listing")


# ---- 8. purity: renderers and queries never write -------------------------

before = reg.read_bytes()
world_before = WORLD_STORE.read_bytes()
ev.drilldown(answer_id, answers=ev.load_answers(reg))
ev.drilldown(world_id)
ev.show_sources(ev.load_answers(reg))
research.extract_summary_evidence("probe topic", "")
assert reg.read_bytes() == before
# The live service may append world evidence concurrently; appends are legal,
# rewrites are not.
assert WORLD_STORE.read_bytes().startswith(world_before)
_ok("query_paths_write_free")


# ---- 9. summary evidence extraction: dual capture path, owner-side --------

ANSWER_TEXT = (
    "Brief research summary: parsed topic\n"
    "Evidence retrieved: 2026-09-14T08:00:00 UTC\n"
    "\nEvidence:\n"
    "1. Source: https://plato.stanford.edu/entries/probe/\n"
    "   Type: scholarly\n"
    "   Confidence: high\n"
    "   Supports: The probe experiment confirmed the expected result.\n"
    "2. Source: https://en.wikipedia.org/wiki/Probe\n"
    "   Type: encyclopedic\n"
    "   Confidence: medium\n"
    "   Supports: Later reviews also describe the probe result as confirmed.\n"
    "\nDifferences:\nNo significant disagreement detected among the 2 retrieved source(s).\n"
)

original_cache_hit = research._cache_hit


def _fake_cache_hit(topic):
    if topic == "cache replay topic":
        return {
            "topic": topic, "retrieved_at": "2026-09-15T10:00:00Z",
            "meta": {"kind": "definition_or_information"},
            "sources": [dict(row, retrieved_at="2026-09-15T10:00:00Z") for row in ROWS_AGREE],
        }
    return original_cache_hit(topic)


research._cache_hit = _fake_cache_hit
try:
    rows, meta, analysis = research.extract_summary_evidence("cache replay topic", "unused")
finally:
    research._cache_hit = original_cache_hit
assert len(rows) == 2 and meta.get("retrieved_at") == "2026-09-15T10:00:00Z", meta
assert rows[0]["title"] == "Probe - Stanford" and rows[0]["retrieved_at"], rows[0]
parsed_rows, parsed_meta, parsed_analysis = research.extract_summary_evidence(
    "parsed topic", ANSWER_TEXT)
assert len(parsed_rows) == 2, parsed_rows
assert parsed_rows[0]["url"] == "https://plato.stanford.edu/entries/probe/", parsed_rows[0]
assert parsed_rows[0]["snippet"].startswith("The probe experiment confirmed"), parsed_rows[0]
assert parsed_meta.get("retrieved_at") == "2026-09-14T08:00:00Z", parsed_meta
# Same url+snippet -> same ID from either capture path.
assert ev.evidence_id_for_row(rows[0]["url"], rows[0]["snippet"]) == \
    ev.evidence_id_for_row(parsed_rows[0]["url"], parsed_rows[0]["snippet"])
assert research.extract_summary_evidence("none topic", "No focused public result matched") == ([], {}, None)
# Analysis matches what the rendered summary itself reports.
summary = research.research_summary("parsed topic", [dict(r) for r in parsed_rows],
                                    dict(parsed_meta))
assert ("Status: %s" % parsed_analysis["status"]) in summary, (parsed_analysis, summary[-200:])
_ok("source_extraction_dual_path")


# ---- 10. answer tagging end-to-end through maya_chat ----------------------

orig_research = maya_chat.research_topic
ev.REGISTRY_FILE = e2e_reg = _tmp_registry()
maya_chat.research_topic = lambda topic: ANSWER_TEXT
try:
    tagged = maya_chat.maya_topic_research("parsed topic")
finally:
    maya_chat.research_topic = orig_research
    ev.REGISTRY_FILE = REAL_REGISTRY
assert "Evidence IDs: " in tagged and ANSWER_TEXT.splitlines()[0] in tagged, tagged[-200:]
# The contextual capability tip rides on the same registration event.
assert 'Tip: say ":evidence <id>" (or "show sources")' in tagged, tagged[-250:]
stored = ev.load_answers(e2e_reg)
assert len(stored) == 1 and stored[0]["topic"] == "parsed topic", stored
ids = [s["evidence_id"] for s in stored[0]["sources"]]
for evidence_id in ids:
    assert evidence_id in tagged
# Empty answers register nothing and append no IDs.
ev.REGISTRY_FILE = empty_reg = _tmp_registry()
maya_chat.research_topic = lambda topic: (
    "No focused public result matched: none topic\nNo trusted memory update occurred.")
try:
    bare = maya_chat.maya_topic_research("none topic")
finally:
    maya_chat.research_topic = orig_research
    ev.REGISTRY_FILE = REAL_REGISTRY
assert "Evidence IDs:" not in bare and "Tip:" not in bare and not empty_reg.exists(), bare
_ok("answer_tagging_end_to_end")


# ---- 11. router surface ---------------------------------------------------

world_reply = maya_chat.maya_local_command(":evidence " + world_id)
assert "(world model)" in world_reply and world_id in world_reply, world_reply[:120]
ev.REGISTRY_FILE = reg
try:
    research_reply = maya_chat.maya_local_command(":evidence " + ids[0])
    listing_reply = maya_chat.maya_local_command("show sources")
    alias_reply = maya_chat.maya_local_command("evidence sources")
finally:
    ev.REGISTRY_FILE = REAL_REGISTRY
assert "(research)" in research_reply, research_reply[:120]
assert "newest first" in listing_reply and answer_id in listing_reply, listing_reply[:120]
assert "newest first" in alias_reply, alias_reply[:120]
ev.REGISTRY_FILE = _tmp_registry()
try:
    empty_router = maya_chat.maya_local_command("show sources")
finally:
    ev.REGISTRY_FILE = REAL_REGISTRY
assert "No research answers are registered" in empty_router, empty_router[:120]
world_list_reply = maya_chat.maya_local_command(":world list")
assert "Use :evidence <id>" in world_list_reply, world_list_reply[-120:]
cluster_reply = maya_chat.maya_local_command(":evidence")
import json as _json
_json.loads(cluster_reply)  # bare :evidence still serves the cluster report JSON
passthrough = maya_chat.maya_local_command(":evidenceX")
assert passthrough is None or "Evidence drilldown" not in str(passthrough)
_ok("router_surface_complete")


# ---- 12. real registry untouched by the suite (live appends are legal) ----

SUITE_TOPICS = ("probe topic", "parsed topic", "cache replay topic", "cap topic",
                "mars ice", "amb one", "amb two", "none topic")
real_registry_text = (REAL_REGISTRY.read_text(encoding="utf-8")
                      if REAL_REGISTRY.exists() else "")
for line in real_registry_text.splitlines():
    if line.strip():
        for topic in SUITE_TOPICS:
            assert topic not in line, "suite leaked a fixture into the real registry"
_ok("real_root_untouched")

print("test_evidence_drilldown=PASS")
