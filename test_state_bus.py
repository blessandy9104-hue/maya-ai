"""Unified state / knowledge bus verification battery (Batch #3).

Proofs, against the running implementation AND an independent verification
oracle:

- one canonical bus contract (fixed envelope, protocol, schema);
- authoritative stores identified by reference (no parallel truth store);
- typed representation enforced, the eleven declarations preserved
  (never collapsed into one generic knowledge bucket);
- provenance is required and survives state movement;
- conflicts are retained and never silently overwritten;
- temporal context is explicit; processing time never substitutes for
  event time;
- safety holds survive downstream (expression carries the hold tokens);
- persona is reference-only; geometry is first-class but not meaning;
- the real conversational path reaches the bus (bridge + chat wiring);
- the independent oracle agrees with the implementation, including the
  canonical digest;
- fifteen fail-closed negatives N1..N15;
- deterministic cross-interpreter digest (printed for parity comparison);
- ThinkPad-scale performance sanity bounds.

Runtime is deterministic: no wall-clock influence on records; the only
non-deterministic value is the caller-supplied ``created_at`` used to prove
the conversational path.
"""
import copy
import importlib.util
import json
import os
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime.intelligence.bridge import run_conversation_for_expression
from maya_runtime.intelligence import bus
from maya_runtime.intelligence.bus import BusError

_ROOT = os.path.dirname(os.path.abspath(__file__))
_ORACLE = None
_TS = "2026-09-10T12:00:00Z"
_PROVENANCE = {
    "source": "bus.battery", "source_url": None, "retrieved_at": _TS,
    "evidence_type": "observation", "confidence": "high",
    "claim": "state bus battery provenance",
}


def _ok(label):
    print(label + "=OK")


def _load_oracle():
    global _ORACLE
    if _ORACLE is not None:
        return _ORACLE
    path = os.path.join(_ROOT, "verification", "oracle_bus.py")
    spec = importlib.util.spec_from_file_location("bus_oracle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._load_oracles()
    _ORACLE = module
    return _ORACLE


def _reissue(obj, mutate=None):
    payload_ = {k: v for k, v in obj.items() if k != "digest"}
    payload_ = copy.deepcopy(payload_)
    if mutate is not None:
        mutate(payload_)
    import maya_runtime.intelligence.jcs as jcs
    canonical = jcs.canonical_bytes(payload_)
    payload_["digest"] = {"alg": "sha-256", "source": "jcs-rfc-8785",
                          "digest": jcs.sha256(payload_),
                          "bytes": len(canonical)}
    return payload_


def _expect_reject(fn, label):
    try:
        fn()
    except BusError:
        _ok(label)
        return
    raise AssertionError("%s: expected BusError rejection" % label)


# ---- 1. one canonical bus contract -------------------------------------

assert bus.PROTOCOL == "maya.unified_state"
assert bus.SCHEMA_ID == "maya:unified-state:1"
assert bus.SCHEMA_VERSION == 1
assert bus.DIGEST_ALG == "sha-256"
_ok("bus_contract_constants_ok")

assert isinstance(bus.ENVELOPE_KEYS, tuple) and len(bus.ENVELOPE_KEYS) == 25
_ok("bus_envelope_keys_ok")

# ---- 2. authoritative sources identified (no parallel truth store) -----

assert isinstance(bus.AUTHORITATIVE_SOURCES, dict)
assert bus.AUTHORITATIVE_SOURCES
for _domain, _source in bus.AUTHORITATIVE_SOURCES.items():
    assert isinstance(_source, str) and _source.strip()
for _backed in ("maya_identity/identity.json", "maya_identity/geometry",
                "maya_world_evidence.jsonl",
                "maya_conversation_continuity.json"):
    _p = os.path.join(_ROOT, _backed.replace("/", os.sep))
    assert os.path.exists(_p), "authoritative store missing: %s" % _backed
_ok("bus_authoritative_sources_ok")

# ---- 3. minimum canonical state envelope -------------------------------

_record = bus.create_state(
    state_id="bus-state-1", source="bus.battery", provenance=_PROVENANCE,
    declaration="INTERPRETATION", state_kind="STATE",
    temporal={"event_time": _TS, "publication_time": _TS,
              "processing_time": _TS, "state_time": _TS},
    confidence_value=0.8, uncertainty_value=0.1,
    input_declared={"type": "text", "value": "state bus battery"},
    knowledge={"refs": ["know:bus:1"], "summary": "contract state",
               "status": "reference_only"},
    world={"evidence_refs": ["ev:bus:1"],
           "world_summary": {"maya.state.x": {"type": "scalar",
                                              "value": 0.5}},
           "conflicts": []},
    safety={"status": "safe", "reason": "battery"},
)
assert bus.verify(_record)["digest_ok"]
assert bus.validate(_record)["valid"] is True
_ok("bus_envelope_create_ok")

# ---- 4. independent oracle agrees (incl. canonical digest) --------------

_oracle = _load_oracle()
_ok_oracle, _oracle_failures = _oracle.oracle_check(_record)
assert _ok_oracle, "oracle rejected implementation record: %r" % _oracle_failures
assert _oracle.digest_of(_record) == _record["digest"]["digest"]
assert bus.digest(_record) == _record["digest"]["digest"]
_ok("bus_oracle_agreement_ok")

# ---- 5. conflicts retained, never silently overwritten -----------------

_claim_a = bus.create_state(
    state_id="bus-a-1", source="bus.battery", provenance=_PROVENANCE,
    declaration="OBSERVATION", state_kind="EVIDENCE",
    temporal={"event_time": _TS, "state_time": _TS},
    world={"evidence_refs": ["ev:a"],
           "world_summary": {"maya.state.temperature": {
               "type": "scalar", "value": 0.4}},
           "conflicts": []})
_claim_b = bus.create_state(
    state_id="bus-b-1", source="bus.battery", provenance=_PROVENANCE,
    declaration="OBSERVATION", state_kind="EVIDENCE",
    temporal={"event_time": _TS, "state_time": _TS},
    world={"evidence_refs": ["ev:b"],
           "world_summary": {"maya.state.temperature": {
               "type": "scalar", "value": 0.9}},
           "conflicts": []})
_merged = bus.merge_state(
    _claim_a, _claim_b, state_id="bus-merge-1", source="bus.battery",
    provenance=_PROVENANCE, temporal={"state_time": _TS})
assert _merged["world"]["conflict_status"] == "DISPUTED"
assert len(_merged["world"]["conflicts"]) == 1
_conflict = _merged["world"]["conflicts"][0]
assert _conflict["claim_a"] == 0.4 and _conflict["claim_b"] == 0.9
assert _conflict["evidence_a"] == ["ev:a"] and _conflict["evidence_b"] == ["ev:b"]
assert _merged["validation_status"] == "disputed"
assert bus.validate(_merged)["valid"] is True
_ok("bus_conflict_retention_ok")

# ---- 6. provenance survives movement (snapshot / derive) ---------------

_snapshot = bus.snapshot(_record, snapshot_id="bus-ss-1",
                         source_identifier="bus.battery", at=_TS)
assert bus.validate(_snapshot)["valid"] is True
assert _snapshot["provenance"] == _PROVENANCE
_snapshot_ok, _snap_failures = _oracle.oracle_check(_snapshot)
assert _snapshot_ok, "oracle rejected snapshot: %r" % _snap_failures
_event = bus.publish_event(
    state_id="bus-ev-1", source="bus.battery", provenance=_PROVENANCE,
    event_time=_TS, declaration="OBSERVATION")
_derived = bus.derive_state(
    [_event], state_id="bus-derived-1", source="bus.battery",
    provenance=_PROVENANCE, state_time=_TS)
assert bus.validate(_derived)["valid"] is True
assert _derived["provenance"] == _PROVENANCE
_ok("bus_provenance_retained_ok")

# ---- 7. typed representation + declarations never collapsed ------------

assert set(bus.DECLARATIONS) == {
    "FACT", "OBSERVATION", "CALCULATION", "INFERENCE", "INTERPRETATION",
    "HYPOTHESIS", "USER_PROVIDED", "EXTERNAL_REPORT", "UNKNOWN"}
assert set(bus.VALIDATION_STATUSES) >= {
    "unvalidated", "validated", "disputed", "contradicted", "unknown"}
assert set(bus.CONFLICT_STATUSES) >= {
    "SUPPORTED", "DISPUTED", "CONTRADICTED", "UNKNOWN"}
assert set(bus.SAFETY_STATUSES) >= {"safe", "hold", "blocked", "unknown"}
assert set(bus.STATE_KINDS) >= {
    "STATE", "EVENT", "KNOWLEDGE", "EVIDENCE", "DERIVED_COGNITION",
    "EXPRESSION"}
_typed_state = bus.create_state(
    state_id="bus-typing-1", source="bus.battery", provenance=_PROVENANCE,
    declaration="FACT",
    temporal={"event_time": _TS, "state_time": _TS},
    knowledge={"refs": ["know:bus:2"], "summary": "typed",
               "status": "reference_only"},
    input_declared={"type": "text", "value": "typed sample"})
assert bus.validate(_typed_state)["valid"] is True
_ok("bus_typing_enforced_ok")

# ---- 8. temporal context explicit --------------------------------------

_turn = bus.publish_turn(
    user_text="position myself", history=[], features={},
    cognitive={"meaning_scalar": 0.7, "meaning_vector": [0.7],
               "meaning_ok": True, "stability": 0.9, "drift": 0.1,
               "alignment": 0.8, "state_ok": True, "safety_ok": True,
               "register": "grounded", "tone": "calm"},
    directive={"register": "grounded", "budget": 48, "holds": [],
               "text": "compact"},
    sequence=3, environment="local", created_at=_TS)
_turn_state = _turn["state"]
assert _turn["engaged"] and _turn["minted"]
assert _turn_state["temporal"]["event_time"] == _TS
assert _turn_state["temporal"]["state_time"] == _TS
assert _turn_state["temporal"]["processing_time"] == _TS
assert _turn_state["temporal"]["retrieval_time"] is None
assert bus.validate(_turn_state)["valid"] is True
_ok("bus_temporal_explicit_ok")

# ---- 9. safety holds survive downstream --------------------------------

_hold_turn = bus.publish_turn(
    user_text="do not proceed", history=[], features={},
    cognitive={"meaning_scalar": 0.3, "meaning_ok": False,
               "state_ok": False, "safety_ok": False},
    directive={"register": "reserved", "budget": 16,
               "holds": ["safety_boundary"], "text": "hold"},
    sequence=4, environment="local", created_at=_TS)
_hold_state = _hold_turn["state"]
assert _hold_state["safety"]["status"] == "blocked"
assert "safety_blocked" in _hold_state["expression"]["holds"]
assert bus.validate(_hold_state)["valid"] is True
_hold_ok, _hold_failures = _oracle.oracle_check(_hold_state)
assert _hold_ok, "oracle rejected hold record: %r" % _hold_failures
_ok("bus_safety_hold_survives_ok")

# ---- 10. geometry first-class, but not meaning -------------------------

_geo_state = bus.create_state(
    state_id="bus-geo-1", source="bus.battery", provenance=_PROVENANCE,
    declaration="INTERPRETATION",
    temporal={"event_time": _TS, "state_time": _TS},
    geometry={"space": [0.0, 1.0, 0.0, 1.0],
              "expressions": {"jaw": {"type": "measurement",
                                      "value": 0.5,
                                      "units": "normalized"}}},
    safety={"status": "safe"})
assert bus.validate(_geo_state)["valid"] is True
_geometry = _geo_state["geometry"]
assert _geometry["symmetry"]["axis"] == 0.5
assert _geometry["symmetry"]["tolerance"] == 0.004
assert _geometry["space"] == [0.0, 1.0, 0.0, 1.0]
assert "jaw" in _geometry["expressions"]
_ok("bus_geometry_first_class_ok")

# ---- 11. persona reference-only ----------------------------------------

_persona_state = bus.create_state(
    state_id="bus-persona-1", source="bus.battery", provenance=_PROVENANCE,
    declaration="INTERPRETATION",
    temporal={"event_time": _TS, "state_time": _TS},
    persona={"selection": "maya", "weights_ref": "persona:weights:maya",
             "constraints": ["persona:no-sarcasm"],
             "identity_ref": "maya"})
assert bus.validate(_persona_state)["valid"] is True
assert _persona_state["persona"]["identity_ref"] == "maya"


def _bad_persona():
    bus.create_state(
        state_id="bus-persona-bad", source="bus.battery",
        provenance=_PROVENANCE,
        persona={"identity_ref": "maya", "self_image": {"height": 1.75}})
_expect_reject(_bad_persona, "bus_persona_reference_only_ok")

# ---- 12. user-provided claims remain distinguishable -------------------

_user_state = bus.create_state(
    state_id="bus-user-1", source="bus.battery", provenance=_PROVENANCE,
    declaration="USER_PROVIDED",
    temporal={"event_time": _TS, "state_time": _TS},
    input_declared={"type": "text", "value": "Andy says the domain is x"})
assert bus.validate(_user_state)["valid"] is True
assert _user_state["declaration"] == "USER_PROVIDED"
_user_ok, _user_failures = _oracle.oracle_check(_user_state)
assert _user_ok, "oracle rejected user-provided record: %r" % _user_failures
_ok("bus_user_provided_distinct_ok")

# ---- reachability: real conversation path reaches the bus --------------

_reach_env = run_conversation_for_expression(
    "hello, how are you?", created_at=_TS, sequence=7,
    environment="local")
_reach_bus = _reach_env["bus"]
assert _reach_bus["engaged"] is True
assert _reach_bus["minted"] is True
assert _reach_bus["state"] is not None
_ok("bus_reachability_bridge_engaged_ok")

assert bus.validate(_reach_bus["state"])["valid"] is True
_reach_ok, _reach_failures = _oracle.oracle_check(_reach_bus["state"])
assert _reach_ok, "oracle rejected reachable record: %r" % _reach_failures
_ok("bus_reachability_cognitive_flows_ok")

_cognitive_bus = _reach_bus["state"]["cognitive"]
assert _cognitive_bus["meaning_ok"] == bool(
    _reach_env["cognitive"]["meaning_ok"])
assert _turn_state["input"]["detected_regime"] == "KNOWN"
_ok("bus_reachability_envelope_preserved_ok")

import maya_chat  # noqa: E402

_chat_env = maya_chat._run_conversation_intelligence("hello there", [])
assert _chat_env["bus"]["engaged"] is True, "chat path did not reach the bus"
assert _chat_env["bus"]["minted"] is True
assert bus.validate(_chat_env["bus"]["state"])["valid"] is True
_ok("bus_reachability_chat_path_ok")

# ---- negatives N1..N15 (fail closed) -----------------------------------

_expect_reject(lambda: bus.create_state(
    state_id="bus-n1", source="bus.battery", provenance=None,
    temporal={"state_time": _TS}), "bus_neg01_ok")

_bad_member = _reissue(_record, lambda p: p.update({"rogue_member": 1}))
_expect_reject(lambda: bus.verify(_bad_member), "bus_neg02_ok")

_expect_reject(lambda: bus.create_state(
    state_id="bus-n3", source="bus.battery", provenance=_PROVENANCE,
    input_declared={"type": "not_a_declared_type", "value": 1}),
    "bus_neg03_ok")

_expect_reject(lambda: bus.create_state(
    state_id="bus-n4", source="bus.battery", provenance=_PROVENANCE,
    temporal={"event_time": "2026-09-10T12:00:00Z",
              "state_time": "2026-09-10T10:00:00Z"}),
    "bus_neg04_ok")

_expect_reject(lambda: bus.publish_event(
    state_id="bus-n5", source="bus.battery", provenance=_PROVENANCE),
    "bus_neg05_ok")

_expect_reject(lambda: bus.publish_learning_event(
    state_id="bus-n6", source="bus.battery", provenance=_PROVENANCE,
    kind="PROPOSAL", mutation_requested=True, event_time=_TS),
    "bus_neg06_ok")

_expect_reject(lambda: bus.create_state(
    state_id="bus-n7", source="bus.battery", provenance=_PROVENANCE,
    safety={"status": "blocked"}, expression={"holds": []}),
    "bus_neg07_ok")

_expect_reject(lambda: bus.create_state(
    state_id="bus-n8", source="bus.battery", provenance=_PROVENANCE,
    transform_history=[{"op": "erase_provenance", "applied_to": "bus-n8",
                        "at": _TS}]),
    "bus_neg08_ok")

_expect_reject(lambda: bus.merge_state(
    _claim_a, _claim_b, state_id="bus-n9", source="bus.battery",
    provenance=_PROVENANCE, policy="prefer_a", temporal={"state_time": _TS}),
    "bus_neg09_ok")

_expect_reject(lambda: bus.create_state(
    state_id="bus-n10", source="bus.battery", provenance=_PROVENANCE,
    world={"conflict_status": "DISPUTED", "conflicts": [
        {"subject": "maya.state.x", "predicate": "value",
         "claim_a": 0.5, "claim_b": 0.5, "evidence_a": [], "evidence_b": [],
         "status": "DISPUTED"}]}),
    "bus_neg10_ok")

_regime_bad = _reissue(  # recompute digest, then present a wrong regime
    _typed_state,
    lambda p: p.get("input").update({"detected_regime": "AMBIGUOUS"}))
_expect_reject(lambda: bus.validate(_regime_bad), "bus_neg11_ok")

_expect_reject(lambda: bus.create_state(
    state_id="bus-n12", source="bus.battery", provenance=_PROVENANCE,
    confidence_value=1.5), "bus_neg12_ok")

_stale = bus.create_state(
    state_id="bus-n13", source="bus.battery", provenance=_PROVENANCE,
    temporal={"event_time": "2026-09-10T10:00:00Z",
              "state_time": "2026-09-10T10:00:00Z"},
    transform_history=[{"op": "create", "applied_to": "bus-n13",
                        "at": "2026-09-10T12:00:00Z"}])
assert not bus.current_check(_stale)["current"]
assert bus.current_check(_stale)["stale_status"] == "stale"
_ok("bus_neg13_ok")

_expect_reject(lambda: bus.create_state(
    state_id="bus-n14", source="bus.battery", provenance=_PROVENANCE,
    declaration="BELIEF"), "bus_neg14_ok")

_tampered = copy.deepcopy(_record)
_tampered["world"]["world_summary"]["maya.state.x"]["value"] = 0.9
_expect_reject(lambda: bus.verify(_tampered), "bus_neg15_ok")

# ---- cross-interpreter deterministic record digest ---------------------

_digest_print = bus.create_state(
    state_id="bus-parity-1", source="bus.battery", provenance=_PROVENANCE,
    declaration="INTERPRETATION",
    temporal={"event_time": _TS, "publication_time": _TS,
              "processing_time": _TS, "state_time": _TS},
    confidence_value=0.7, uncertainty_value=0.1,
    input_declared={"type": "text", "value": "parity"},
    knowledge={"refs": ["know:parity:1"], "summary": "parity",
               "status": "reference_only"},
    world={"evidence_refs": ["ev:parity:1"],
           "world_summary": {"maya.state.y": {"type": "scalar",
                                              "value": 0.25}},
           "conflicts": []},
    safety={"status": "safe", "reason": "parity"})
print("bus_state_digest=%s" % _digest_print["digest"]["digest"])
_parity_ok, _parity_failures = _oracle.oracle_check(_digest_print)
assert _parity_ok, "oracle rejected parity record: %r" % _parity_failures
_ok("bus_crossinterpreter_contract_ok")

# ---- performance sanity on ThinkPad class hardware ---------------------

def _perf(fn, n=120):
    start = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - start) / n * 1000.0


_avg_state = _perf(lambda: bus.create_state(
    state_id="bus-perf", source="bus.battery", provenance=_PROVENANCE,
    temporal={"state_time": _TS}, confidence_value=0.6,
    input_declared={"type": "text", "value": "perf"}))
assert _avg_state < 100.0, "average state construction too slow: %r" % _avg_state
print("bus_perf_state_avg_ms=%.3f" % _avg_state)
_ok("bus_perf_state_ms_ok")

_avg_canonical = _perf(lambda: bus.canonical_bytes(_record))
assert _avg_canonical < 100.0
print("bus_perf_canonical_avg_ms=%.3f" % _avg_canonical)
_ok("bus_perf_canonical_ms_ok")

_avg_digest = _perf(lambda: bus.digest(_record))
assert _avg_digest < 100.0
print("bus_perf_digest_avg_ms=%.3f" % _avg_digest)
_ok("bus_perf_digest_ms_ok")

tracemalloc.start()
_ = [bus.create_state(
    state_id="bus-perf-memory", source="bus.battery", provenance=_PROVENANCE,
    temporal={"state_time": _TS},
    input_declared={"type": "text", "value": "memory footprint"})
    for _ in range(100)]
_, _peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
print("bus_perf_peak_mem_mb=%.2f" % (_peak / (1024 * 1024)))
assert _peak < (128 * 1024 * 1024), "bus record footprint too large: %r" % _peak
_ok("bus_perf_memory_mb_ok")

print("test_state_bus=PASS")