"""Restoration verification: math re-integration, knowledge-network runtime,
and orchestration (model registry + capability unification).

Covers, against real (read-only) stores:
  - the cooperative orchestrator now carries a substrate-derived
    ``cooperation_math`` frame (``maya_math.cooperation``) without changing
    verdicts, contract confidence, or epistemic status;
  - ``:world analyze`` reaches ``maya_world_model.mathematical_analysis``
    from the runtime command path and is advertised by the registry;
  - ``knowledge_search`` is promoted into ``:knowledge search`` and a first
    persisted claim/source/contradiction graph is derived and (service-live
    gated) written by ``:knowledge graph``;
  - orchestration: the model name comes from one registry, and the dormant
    ``capabilities.py`` inventory is now derived from the live registry.

Discipline: the graph write path is verified hermetic (tempedge file +
patched service pid); the real ``knowledge/graph_edges.jsonl`` is never
written by this test. Tests are deterministic (no clock, no network).
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_conversation import orchestrate_turn
from maya_conversation.cooperate import cooperate
from maya_math.cooperation import agreement_weighted_combine, label_similarity

import maya_world_model
import maya_capabilities
import knowledge_graph
import knowledge_search
import maya_model_registry
import capabilities as legacy_capabilities

from maya_chat import maya_local_command, MODEL as CHAT_MODEL

FAILURES = []
_OK_COUNT = {"n": 0}


def _ok(label):
    _OK_COUNT["n"] += 1
    print(label + "=OK")


def _assert(cond, label):
    if cond:
        _ok(label)
    else:
        FAILURES.append(label)
        print(label + "=FAIL")


# ---- 1. cooperation now reports a substrate math frame --------------------
r = cooperate(orchestrate_turn("hello"), {"register": "measured", "budget": 48,
                                          "holds": [], "text": "test"}, None)
_assert(r["verdict"] in ("agreement", "agreement_with_caveat"),
        "restore_coop_agreement_preserved")
_assert("cooperation_math" in r, "restore_coop_math_key")
frame = r["cooperation_math"]
want = label_similarity(r["epistemic"].get("supporting_sources") or [],
                        r["epistemic"].get("disputing_sources") or [])
_assert(frame.get("support_concordance") == want,
        "restore_coop_math_uses_substrate")

r2 = cooperate({"ok": True, "interpretation": {"classifier_confidence": 0.5,
               "ambiguous": False}}, None, {"confidence": 0.95})
frame2 = r2["cooperation_math"]
_assert(frame2.get("engine_concordance") is not None,
        "restore_coop_math_concordance_present")
want2 = agreement_weighted_combine(0.5, 0.95)
_assert(math.isclose(frame2.get("combined_confidence", -1.0), want2,
                     rel_tol=1e-12),
        "restore_coop_math_combine_present")
_assert(frame2.get("engine_concordance") == 0.55,
        "restore_coop_math_concordance_value")

r_ne = cooperate(None, None, None)
_assert(r_ne["verdict"] == "no_engagement", "restore_coop_no_engagement_kept")
_assert(r_ne["confidence"] == 0.0, "restore_coop_no_engagement_conf_kept")
_assert(r_ne["cooperation_math"] == {}, "restore_coop_no_engagement_math_empty")

# ---- 2. mathematical_analysis reachable from the runtime command path -----
resp = maya_local_command(":world analyze")
_assert(resp is not None, "restore_world_analyze_dispatch")
if resp is not None:
    payload = json.loads(resp)
    _assert(payload.get("status") == "mathematical_analysis",
            "restore_world_analyze_status")
    _assert(payload.get("additive_only") is True,
            "restore_world_analyze_additive")
resp_nl = maya_local_command("world model analysis")
_assert(resp_nl is not None and resp is not None and resp_nl == resp,
        "restore_world_analyze_nl_parity")
_world_cmds = [c for _, _, cmds in maya_capabilities.CAPABILITY_REGISTRY
               for c in cmds]
_assert(":world analyze" in _world_cmds, "restore_world_analyze_advertised")

# ---- 3. knowledge search promoted to the runtime --------------------------
_corpus_terms = []
for _path in knowledge_search.documents():
    for _token in _path[0].read_text(encoding="utf-8").split():
        _clean = "".join(ch for ch in _token if ch.isalnum())
        if _clean:
            _corpus_terms.append(_clean)
_known_term = _corpus_terms[0] if _corpus_terms else "maya"
hits = knowledge_search.render_search(_known_term)
_assert(hits is not None and "Read-only search" in hits,
        "restore_kn_search_renders")
_assert(knowledge_search.render_search("") .startswith("Use :knowledge"),
        "restore_kn_search_empty_refusal")
ks_resp = maya_local_command(":knowledge search %s" % _known_term)
_assert(ks_resp is not None, "restore_kn_search_dispatch")
_assert(maya_local_command(":knowledge search  ") is not None,
        "restore_kn_search_dispatch_empty")

# ---- 4. first persisted knowledge graph (hermetic write gate) -------------
edges = knowledge_graph.build_edges()
_assert(edges == knowledge_graph.build_edges(), "restore_graph_deterministic")
kinds = set(e.get("kind") for e in edges)
_assert("source_claim" in kinds, "restore_graph_source_claim_edges")
_assert(all(e.get("review_only") is True for e in edges),
        "restore_graph_all_review_only")
_assert(all(e.get("provenance") for e in edges),
        "restore_graph_all_provenance")

tmp_dir = Path(tempfile.mkdtemp())
tmp_edges = tmp_dir / "graph_edges.jsonl"

import maya_service
_orig_edge = knowledge_graph.EDGE_FILE
_orig_pid = maya_service.running_pid
try:
    knowledge_graph.EDGE_FILE = tmp_edges
    maya_service.running_pid = lambda: None
    result = knowledge_graph.persist_edges()
    _assert(result == {"written": 0, "reason": "service_offline"},
            "restore_graph_gate_offline")
    _assert(not tmp_edges.exists(), "restore_graph_gate_no_file_when_offline")

    maya_service.running_pid = lambda: 12345
    result = knowledge_graph.persist_edges(edges)
    _assert(result["written"] == len(edges)
            and result["reason"] == "service_live",
            "restore_graph_gate_live_writes")
    written = [line for line in tmp_edges.read_text(encoding="utf-8")
               .splitlines() if line.strip()]
    _assert(len(written) == len(edges),
            "restore_graph_gate_file_line_count")
finally:
    knowledge_graph.EDGE_FILE = _orig_edge
    maya_service.running_pid = _orig_pid

_blank_render = knowledge_graph.render_graph("never-a-real-term-xyz")
_assert("none - nothing" in _blank_render or "no edges" in _blank_render,
        "restore_graph_render_no_term_honest")
_known_claim = edges[0].get("claim")
if _known_claim:
    _term_probe = " ".join(_known_claim.split()[:2])
    _connected = knowledge_graph.render_graph(_term_probe)
    _assert("Connected edges for" in _connected,
            "restore_graph_render_term_connects")
kg_resp = maya_local_command(":knowledge graph probe-term")
_assert(kg_resp is not None and "Knowledge network" in kg_resp,
        "restore_graph_dispatch")
kn_cmds = [c for _, _, cmds in maya_capabilities.CAPABILITY_REGISTRY
           for c in cmds]
for advertised in (":knowledge", ":knowledge search <terms>",
                   ":knowledge graph [term]"):
    _assert(advertised in kn_cmds, "restore_kn_advertised_" + advertised)
_assert(maya_local_command(":knowledge") is not None,
        "restore_kn_status_dispatch")
_assert(maya_capabilities.offline_registry_audit() == [
    "offline_registry_audit_ok"], "restore_offline_registry_audit_ok")

# ---- 5. orchestration: one model registry ---------------------------------
_assert(maya_model_registry.default_model() == "qwen2.5-coder:3b",
        "restore_model_default_value")
_assert(CHAT_MODEL == maya_model_registry.default_model(),
        "restore_model_chat_uses_registry")
models = maya_model_registry.describe_models()
_assert(any(m.get("key") == "local_default" for m in models),
        "restore_model_registry_listed")

# ---- 6. orchestration: dormant capabilities.py now derives from registry --
registered = [name for name, _, _ in maya_capabilities.CAPABILITY_REGISTRY]
derived_names = {c["name"] for c in legacy_capabilities.CAPABILITIES
                 if c["available"]}
_assert(derived_names == {name.title() for name in registered},
        "restore_cap_alias_names_match_registry")
_assert(len(legacy_capabilities.CAPABILITIES)
        == len(maya_capabilities.CAPABILITY_REGISTRY) + 3,
        "restore_cap_alias_total_count")
prompt = legacy_capabilities.capabilities_prompt_text()
for name, description, _ in maya_capabilities.CAPABILITY_REGISTRY:
    _assert(description in prompt,
            "restore_cap_alias_prompt_covers_" + name.replace(" ", "_"))
summary = legacy_capabilities.capabilities_summary_text()
_assert(any(description in summary
            for name, description, _ in maya_capabilities.CAPABILITY_REGISTRY),
        "restore_cap_alias_summary_derived")

print("restoration_ok=%d" % _OK_COUNT["n"])
if FAILURES:
    print("restoration_integration=FAIL")
    print("failures=" + ", ".join(FAILURES))
    sys.exit(1)
print("restoration_integration=PASS")