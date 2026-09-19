"""World mapping (Representation -> World-Model) verification battery
(Batch #5).

Proofs, against the running implementation AND a clean-room oracle that
never imports ``maya_runtime``:

- the mapping contract (statuses, world kinds, result keys, provenance,
  validation, epistemic, losses) and that every mapping result validates;
- the full representation-class matrix (§2): measurement, scalar, vector,
  matrix, equation, symbol, category, relation, event, temporal_interval,
  text, geometric_point, geometric_vector, geometric_transform,
  geometric_object, graph, probability, confidence, uncertainty, identifier,
  language, structured_canonical_object — each mapped only as far as
  structure supports;
- the minimal world-kind vocabulary (entity/event/measurement/relation/
  location/temporal interval/geometric object/process/state/claim/unknown)
  plus the reserved cryptographic kinds (extensible, never classified);
- a bare number / bare proportion is never auto-assigned a meaning (N1);
- CLAIM vs WORLD STATE: free text and cultural statements are preserved as
  claims with provenance; representation validity never implies a world
  reference; world state is never mutated by the mapping layer (N11-N14,
  N20);
- geometry is first-class: identity and declared spaces are preserved with
  source, coordinate system and y-axis; vectors are never reinterpreted as
  points/locations/velocities; out-of-space geometry fails closed (N6/N7);
- temporal is conservative: timestamp = temporal reference with unresolved
  role; duration = interval/duration candidate with unresolved bounds; the
  bus temporal contract remains authoritative (N4);
- cryptographic extensibility: reserved crypto kinds exist but this batch
  never labels identifier/hex-like input as hash/key/signature (§10);
- fail-closed negatives N1..N20, including corrupted envelopes, corrupted
  mapping results, malformed provenance, contradictory relations, and an
  attempted fabricated world reference;
- clean-room oracle agreement on the shared corpus (positives, temporals,
  geometry and ambiguity);
- the real conversational path (detector -> bridge -> publish_turn) carries
  the mapping into ``context.world_mapping``, authenticated by the digest;
- deterministic, smart-scan-clean runtime (no randomness, no clock, no
  eval/exec of untrusted text);
- ThinkPad-scale performance sanity bounds.

Runtime is deterministic: no wall-clock influence on mapping results.
"""
import copy
import importlib.util
import json
import math
import os
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime.intelligence import bus
from maya_runtime.intelligence import decipher
from maya_runtime.intelligence import detector
from maya_runtime.intelligence import epistemic
from maya_runtime.intelligence import representation
from maya_runtime.intelligence import world_mapping

from maya_runtime.intelligence.bridge import run_conversation_for_expression

_ROOT = os.path.dirname(os.path.abspath(__file__))
_ORACLE = None
_TS = "2026-09-10T12:00:00Z"
_PROW = {"source": "worldmapping.battery", "source_url": None,
         "retrieved_at": _TS, "evidence_type": "observation",
         "confidence": "medium"}


def _ok(label):
    print(label + "=OK")


def _load_oracle():
    global _ORACLE
    if _ORACLE is not None:
        return _ORACLE
    path = os.path.join(_ROOT, "verification", "oracle_world_mapping.py")
    spec = importlib.util.spec_from_file_location("world_mapping_oracle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _ORACLE = module
    return _ORACLE


def _map(value, declared=None, original=None, **kwargs):
    detection = detector.detect(value, declared=declared)
    return world_mapping.map_to_world(detection, original=original
                                      if original is not None else
                                      (value if isinstance(value, str)
                                       else None),
                                      provenance=kwargs.get("provenance"),
                                      epistemic_status=kwargs.get(
                                          "epistemic_status"),
                                      empirical_status=kwargs.get(
                                          "empirical_status"),
                                      domain=kwargs.get("domain"))


# ---- 1. mapping contract ---------------------------------------------------

assert world_mapping.WORLD_MAPPING_STATUSES == \
    ("KNOWN", "AMBIGUOUS", "UNRESOLVED", "INVALID")
assert world_mapping.MAP_RESULT_KEYS == (
    "status", "detected_type", "world_kind", "candidate_reference",
    "normalized_fields", "mapping_evidence", "unresolved_fields",
    "provenance", "validation", "epistemic", "losses")
for _kind in ("entity", "event", "measurement", "relation", "location",
              "temporal_interval", "geometric_object", "process_state",
              "claim_assertion", "unknown_reference"):
    assert _kind in world_mapping.WORLD_KIND_SET, _kind
_ok("wm_contract_constants_ok")

_m_measurement = _map({"type": "measurement", "value": 42, "units": "kg"})
assert _m_measurement["status"] == "KNOWN"
assert _m_measurement["world_kind"] == "measurement"
assert _m_measurement["candidate_reference"]["kind"] == "measurement"
assert _m_measurement["candidate_reference"]["units"] == "kg"
assert _m_measurement["normalized_fields"] == {"value": 42, "units": "kg"}
assert _m_measurement["validation"]["world_reference_resolved"] is True
assert _m_measurement["validation"]["representation_valid"] is True
assert _m_measurement["mapping_evidence"]["world_state_mutation"] == "none"
assert _m_measurement["unresolved_fields"] == []
_ok("wm_contract_measurement_ok")

assert world_mapping.validate_mapping(_m_measurement)["valid"] is True
assert world_mapping.validate_mapping(_m_measurement)["reason"] is None
_ok("wm_contract_shape_valid_ok")

# ---- 2. representation-class matrix ---------------------------------------

_CLASS_CASES = [
    ("measurement", {"type": "measurement", "value": 42, "units": "kg"},
     "KNOWN", "measurement"),
    ("scalar", {"type": "scalar", "value": 7}, "UNRESOLVED",
     "unknown_reference"),
    ("vector", {"type": "vector", "value": [1.0, 0.0, 0.0], "dim": 3},
     "UNRESOLVED",
     "unknown_reference"),
    ("matrix", {"type": "matrix", "value": [[1.0, 0.0], [0.0, 1.0]],
                "rows": 2, "cols": 2}, "UNRESOLVED",
     "unknown_reference"),
    ("equation", {"type": "equation",
                  "value": "x = 2*t + 1", "language": "maya.symbolic.v1"},
     "KNOWN", "claim_assertion"),
    ("symbol", {"type": "symbol", "value": "cos",
                "language": "maya.symbolic.v1"}, "UNRESOLVED",
     "unknown_reference"),
    ("category", {"type": "category", "value": "A1",
                  "code_set": ["A1"]}, "UNRESOLVED",
     "unknown_reference"),
    ("relation", {"type": "relation",
                  "value": {"source_id": "src", "target_id": "dst",
                            "predicate": "links"}, "predicates": ["links"]},
     "KNOWN", "relation"),
    ("event", {"type": "event", "value": {"kind": "meeting", "at": _TS},
               "event_types": ["meeting"]}, "KNOWN", "event"),
    ("temporal_interval", {"start": _TS, "end": "2026-09-10T13:00:00Z"},
     "KNOWN", "temporal_interval"),
    ("text", "hello there", "UNRESOLVED", "unknown_reference"),
    ("geometric_point", {"type": "geometric_point", "value": [0.2, 0.4]},
     "KNOWN", "geometric_point"),
    ("geometric_vector", {"type": "geometric_vector", "value": [0.2, 0.4],
                          "dim": 2},
     "KNOWN", "geometric_vector"),
    ("geometric_transform",
     {"type": "geometric_transform",
      "value": {"kind": "scale",
                "parameters": {"factors": [2.0, 2.0], "dim": 2}}},
     "KNOWN", "geometric_transform"),
    ("geometric_object",
     {"type": "geometric_object",
      "value": {"geometry_kind": "curve",
                "data": [[0.1, 0.1], [0.2, 0.1], [0.3, 0.1]]}},
     "KNOWN", "geometric_object"),
    ("graph", {"type": "graph", "value": {"nodes": ["a", "b"],
                                          "edges": [["a", "b"]]}},
     "KNOWN", "graph"),
    ("probability", {"type": "probability", "value": 0.7}, "KNOWN",
     "claim_assertion"),
    ("confidence", {"type": "confidence", "value": 0.9}, "KNOWN",
     "claim_assertion"),
    ("uncertainty", {"type": "uncertainty", "value": 0.1}, "KNOWN",
     "claim_assertion"),
    ("identifier", {"type": "identifier", "value": "abc-123"}, "UNRESOLVED",
     "unknown_reference"),
]
for _name, _candidate, _want_status, _want_kind in _CLASS_CASES:
    _result = _map(_candidate)
    assert _result["status"] == _want_status, \
        "%s status %s != %s (%r)" \
        % (_name, _result["status"], _want_status, _result)
    assert _result["world_kind"] == _want_kind, \
        "%s kind %s != %s" % (_name, _result["world_kind"], _want_kind)
    assert world_mapping.validate_mapping(_result)["valid"] is True, _name
    _ok("wm_classes_%s_ok" % _name)

_lang = _map({"language_tag": "en-US"})
assert _lang["status"] == "UNRESOLVED"
assert _lang["world_kind"] == "unknown_reference"
assert _lang["normalized_fields"].get("language_tag") == "en-US"
_ok("wm_classes_language_ok")

_env_record = bus.create_state(
    state_id="wm-env", source="worldmapping.battery", provenance=_PROW,
    input_declared={"type": "text", "value": "envelope"})
_env_map = _map(_env_record)
assert _env_map["status"] == "UNRESOLVED"
assert _env_map["world_kind"] == "unknown_reference"
_ok("wm_classes_envelope_ok")

# ---- 3. world-kind vocabulary + conservative bare values ------------------

assert world_mapping.RESERVED_CRYPTO_KINDS == frozenset({
    "encoded_data", "encrypted_data", "hash", "signature", "key",
    "certificate", "cryptographic_claim"})
assert world_mapping.TIMESTAMP_ROLE_CANDIDATES == (
    "event_time", "publication_time", "retrieval_time", "processing_time")
_ok("wm_world_kinds_minimal_ok")

_bare = _map("42")
assert _bare["status"] != "KNOWN"
assert _bare["world_kind"] is None or _bare["world_kind"] == "unknown_reference"
assert _bare["validation"]["world_reference_resolved"] is False
assert world_mapping.validate_mapping(_bare)["valid"] is True
_ok("wm_bare_number_conservative_ok")

_prop = _map("0.7")
assert _prop["status"] != "KNOWN"
assert _prop["world_kind"] is None or _prop["world_kind"] == "unknown_reference"
_ok("wm_bare_proportion_conservative_ok")

# ---- 4. CLAIM vs WORLD STATE ----------------------------------------------

_sky = _map("The sky is blue.")
assert _sky["status"] == "UNRESOLVED"
assert _sky["world_kind"] == "unknown_reference"
assert _sky["validation"]["world_reference_resolved"] is False
assert _sky["validation"]["claim_factual"] is False
assert _sky["mapping_evidence"]["world_state_mutation"] == "none"
assert isinstance(_sky["epistemic"], dict)
assert _sky["mapping_evidence"]["claim_status"] == "non-factual-claim"
_ok("wm_claim_vs_world_state_ok")

_measured = _map({"type": "measurement", "value": 42, "units": "kg"},
                 provenance=_PROW, epistemic_status="MEASURED",
                 empirical_status="EMPIRICALLY_TESTED")
assert _measured["status"] == "KNOWN"
assert _measured["validation"]["claim_factual"] is True
assert _measured["validation"]["external_validation"] == "unvalidated"
assert _measured["mapping_evidence"]["claim_status"] == \
    "factual-claim-candidate"
assert _measured["mapping_evidence"]["world_state_mutation"] == "none"
_ok("wm_measurable_claim_never_world_state_ok")

_trad = _map("The festival begins with a cleansing ritual.",
             domain="RELIGIOUS_TRADITION")
assert _trad["status"] == "UNRESOLVED"
assert _trad["mapping_evidence"]["claim_status"] == "non-factual-claim"
assert _trad["validation"]["claim_factual"] is False
assert _trad["epistemic"]["claims_nothing_factual"] is True
_ok("wm_cultural_claim_nonfactual_ok")

_astro = _map("Tomorrow's horoscope favors action.",
              domain="ASTROLOGY")
assert _astro["mapping_evidence"]["claim_status"] == "non-factual-claim"
assert _astro["validation"]["claim_factual"] is False
_ok("wm_astrology_claim_nonfactual_ok")

_phil = _map("Being precedes essence.", domain="PHILOSOPHICAL_SCHOOL")
assert _phil["mapping_evidence"]["claim_status"] == "non-factual-claim"
assert _phil["validation"]["claim_factual"] is False
_ok("wm_philosophy_claim_nonfactual_ok")

# ---- 5. geometry first-class ----------------------------------------------

_gp = _map({"type": "geometric_point", "value": [0.2, 0.4]})
assert _gp["status"] == "KNOWN" and _gp["world_kind"] == "geometric_point"
_normalized_space = _gp["normalized_fields"]["space"]
assert _normalized_space == [0.0, 1.0, 0.0, 1.0]
assert _gp["normalized_fields"]["coordinate_system"] == "identity_maya_2d"
assert _gp["normalized_fields"]["y_down"] is True
assert _gp["normalized_fields"]["space_source"] == \
    "maya_identity/geometry/maya_geometry.json"
assert _gp["candidate_reference"]["space"] == [0.0, 1.0, 0.0, 1.0]
_ok("wm_geometry_identity_space_ok")

_gp_declared = _map({"type": "geometric_point", "value": [2.0, 3.0],
                     "space": [0.0, 5.0, 0.0, 5.0]})
assert _gp_declared["status"] == "KNOWN"
assert _gp_declared["normalized_fields"]["space"] == [0.0, 5.0, 0.0, 5.0]
assert _gp_declared["normalized_fields"]["coordinate_system"] == \
    "declared_space"
assert _gp_declared["normalized_fields"]["space_source"] == "input_declared"
assert _gp_declared["normalized_fields"]["y_down"] is None
_ok("wm_geometry_declared_space_ok")

_gv = _map({"type": "geometric_vector", "value": [0.2, 0.4], "dim": 2})
assert _gv["status"] == "KNOWN" and _gv["world_kind"] == "geometric_vector"
assert _gv["normalized_fields"]["geometry_kind"] == "vector"
assert _gv["normalized_fields"]["dimensions"] == 2
assert any("vector" in loss for loss in
           _gv["mapping_evidence"]["conservatism"])
_ok("wm_geometry_vector_not_point_ok")

# ---- 6. temporal conservative ---------------------------------------------

_ts_raw = _map("2026-09-10T12:00:00Z", original="2026-09-10T12:00:00Z")
assert _ts_raw["status"] == "AMBIGUOUS"
assert _ts_raw["world_kind"] == "temporal_reference"
assert _ts_raw["candidate_reference"]["kind"] == "temporal_reference"
assert "temporal_role" in _ts_raw["unresolved_fields"]
assert _ts_raw["candidate_reference"]["role_candidates"] == list(
    world_mapping.TIMESTAMP_ROLE_CANDIDATES)
_ok("wm_temporal_timestamp_role_ok")

_dur = _map("2h", original="2h")
assert _dur["status"] == "AMBIGUOUS"
assert _dur["world_kind"] == "temporal_interval"
assert _dur["normalized_fields"]["duration_seconds"] == 7200.0
assert _dur["normalized_fields"]["start"] is None
assert _dur["normalized_fields"]["end"] is None
assert {"start", "end"} <= set(_dur["unresolved_fields"])
_ok("wm_temporal_duration_ok")

_event_notime = _map({"kind": "meeting", "at": None})
assert _event_notime["status"] in ("AMBIGUOUS", "INVALID")
_ok("wm_temporal_missing_time_ok")

# ---- 7. cryptographic extensibility (reserved, never classified) ----------

_hexish = _map({"type": "identifier", "value": "a" * 64})
assert _hexish["world_kind"] == "unknown_reference"
assert _hexish["mapping_evidence"]["crypto_class"] == "not_classified"
assert _hexish["world_kind"] not in world_mapping.RESERVED_CRYPTO_KINDS
_ok("wm_crypto_reserved_not_classified_ok")

# ---- 8. fail-closed negatives N1..N20 -------------------------------------

_neg01 = _map("42")
assert _neg01["status"] != "KNOWN"
assert _neg01["world_kind"] is None or _neg01["world_kind"] == \
    "unknown_reference"
_ok("wm_neg01_ok")

_neg02 = _map("42 kgs")
assert _neg02["status"] != "KNOWN"
_ok("wm_neg02_ok")

_neg03 = _map("64 quarks")
assert _neg03["status"] != "KNOWN"
_ok("wm_neg03_ok")

_neg04 = _map("2024-13-45T99:00:00Z")
assert _neg04["status"] == "INVALID"
_ok("wm_neg04_ok")

_neg05 = _map("abc-123")
assert _neg05["status"] != "KNOWN"
_ok("wm_neg05_ok")

_neg06 = _map({"type": "geometric_point", "value": [1.5, 0.4],
               "space": [0.0, 1.0, 0.0, 1.0]})
assert _neg06["status"] == "INVALID"
_ok("wm_neg06_ok")

_neg07 = _map({"geometry_kind": "point", "data": [0.2, 0.4, 0.1, 0.9]})
assert _neg07["status"] == "INVALID"
_ok("wm_neg07_ok")

_neg08 = _map({"source_id": "a", "target_id": "b", "predicate": "links"})
assert _neg08["status"] != "KNOWN"
_ok("wm_neg08_ok")

_neg09 = _map({"source_id": "a", "target_id": "a", "predicate": "opposes",
               "predicates": ["links", "opposes"]})
assert _neg09["status"] == "INVALID"
_ok("wm_neg09_ok")

_neg10 = _map({"type": "identifier", "value": "entity-7"})
assert _neg10["status"] == "UNRESOLVED"
assert _neg10["world_kind"] == "unknown_reference"
assert "world_reference" in _neg10["unresolved_fields"]
_ok("wm_neg10_ok")

_neg11 = _map("The object is red.")
assert _neg11["status"] == "UNRESOLVED"
assert _neg11["validation"]["claim_factual"] is False
assert _neg11["mapping_evidence"]["world_state_mutation"] == "none"
_ok("wm_neg11_ok")

_neg12 = _map("Ganesha protects this house.", domain="RELIGIOUS_TRADITION")
assert _neg12["mapping_evidence"]["claim_status"] == "non-factual-claim"
assert _neg12["validation"]["world_reference_resolved"] is False
_ok("wm_neg12_ok")

_neg13 = _map("Mars is in retrograde and favors logic.", domain="ASTROLOGY")
assert _neg13["mapping_evidence"]["claim_status"] == "non-factual-claim"
_ok("wm_neg13_ok")

_neg14 = _map("Truth is conformity to the world.", domain="PHILOSOPHICAL_SCHOOL")
assert _neg14["mapping_evidence"]["claim_status"] == "non-factual-claim"
_ok("wm_neg14_ok")

_neg15 = _map({"type": "symbol", "value": "∇", "language": "not-a-language"})
assert _neg15["status"] == "INVALID"
_ok("wm_neg15_ok")

_corrupted_env = dict(_env_record)
_corrupted_env["metadata"] = {"maya.meta": {"note": "tampered"}}
_corrupted_detection = detector.detect(_corrupted_env)
assert _corrupted_detection["status"] == "INVALID"
_neg16 = world_mapping.map_to_world(_corrupted_detection)
assert _neg16["status"] == "INVALID"
_ok("wm_neg16_ok")

_neg17 = world_mapping.validate_mapping({"status": "KNOWN"})
assert _neg17["valid"] is False
assert world_mapping.validate_mapping({"status": "MADE_UP",
                                       "world_kind": "moon"})["valid"] is False
_ok("wm_neg17_ok")

_neg18 = _map("42 kg", provenance={"source": "s", "retrieved_at": "bad-date",
                                   "evidence_type": "observation",
                                   "confidence": "high"})
assert _neg18["status"] == "INVALID"
_ok("wm_neg18_ok")

_neg19 = _map("42 kg", provenance=_PROW, epistemic_status="INVALID_STATUS")
assert _neg19["status"] in ("KNOWN", "UNRESOLVED")
assert _neg19["epistemic"] is None
assert _neg19["validation"]["external_validation"] == "unvalidated"
_ok("wm_neg19_ok")

_neg20 = _map("ambient 21.5 degC", original="ambient 21.5 degC")
assert _neg20["status"] == "UNRESOLVED"
assert _neg20["world_kind"] == "unknown_reference"
assert _neg20["validation"]["world_reference_resolved"] is False
assert _neg20["mapping_evidence"]["world_state_mutation"] == "none"
assert _neg20["mapping_evidence"]["claim_status"] == "non-factual-claim"
_fabricate = _map("ambient 21.5 degC", original="ambient 21.5 degC",
                  epistemic_status="MEASURED", empirical_status="EMPIRICALLY_TESTED")
assert _fabricate["status"] == "UNRESOLVED"
assert _fabricate["validation"]["world_reference_resolved"] is False
assert _fabricate["world_kind"] == "unknown_reference"
_ok("wm_neg20_ok")

# ---- 9. clean-room oracle agreement ---------------------------------------

_oracle = _load_oracle()
assert _oracle.ORACLE_WORLD_KINDS == world_mapping.WORLD_KIND_SET
assert _oracle.ORACLE_STATUSES == set(world_mapping.WORLD_MAPPING_STATUSES)
assert _oracle.RESERVED_CRYPTO_KINDS == world_mapping.RESERVED_CRYPTO_KINDS
assert _oracle.IDENTITY_SPACE["space"] == [0.0, 1.0, 0.0, 1.0]

_CORPUS = _CLASS_CASES + [
    ("language", {"language_tag": "en-US"}, "UNRESOLVED",
     "unknown_reference"),
    ("temporal_raw", "2026-09-10T12:00:00Z", "known-timestamp", "temporal"),
    ("duration_raw", "2h", "known-duration", "temporal"),
    ("bare_number", "42", "bare", None),
    ("bare_proportion", "0.7", "bare", None),
    ("bare_bool", True, "bare", None),
    ("out_of_space", {"type": "geometric_point", "value": [5.0, 5.0]},
     "known", "geometry"),
]
for _name, _candidate, _kind, _note in _CORPUS:
    _det = detector.detect(_candidate)
    if _kind == "known-timestamp":
        _expected = ("AMBIGUOUS", "temporal_reference")
    elif _kind == "known-duration":
        _expected = ("AMBIGUOUS", "temporal_interval")
    elif _kind == "bare":
        det_status = _det["status"]
        expected_status = "AMBIGUOUS" if det_status == "AMBIGUOUS" \
            else "UNRESOLVED" if det_status == "UNKNOWN" else "INVALID"
        _expected = (expected_status, None)
    else:
        _expected = _det["status"], None
    _mapped = world_mapping.map_to_world(
        _det, original=_candidate if isinstance(_candidate, str) else None)
    _oracle_status, _oracle_kind, _oracle_resolved, _oracle_unresolved, \
        _oracle_claim, _oracle_crypto = _oracle.oracle_map(
            _det["status"], _mapped["detected_type"],
            _mapped["normalized_fields"], original=_candidate
            if isinstance(_candidate, str) else None)
    assert _mapped["status"] == _oracle_status, \
        "%s status: impl=%s oracle=%s" % (_name, _mapped["status"],
                                          _oracle_status)
    if _kind in ("known",):
        assert _mapped["status"] == _oracle_status
    assert _mapped["world_kind"] == _oracle_kind, \
        "%s kind: impl=%s oracle=%s" % (_name, _mapped["world_kind"],
                                        _oracle_kind)
    assert _mapped["validation"]["world_reference_resolved"] == \
        _oracle_resolved, "%s resolved" % (_name,)
    assert _mapped["mapping_evidence"]["crypto_class"] == _oracle_crypto
_ok("wm_oracle_cleanroom_verified_ok")

# ---- 10. real conversational path carries the mapping ---------------------

_env42 = run_conversation_for_expression("42 kg", created_at=_TS)
assert _env42["detection"]["status"] == "KNOWN"
assert _env42["detection"]["detected_type"] == "measurement"
assert _env42["bus"]["minted"] is True
_mapping_in_record = _env42["bus"]["state"]["context"]["world_mapping"]
assert _mapping_in_record["status"] == "KNOWN"
assert _mapping_in_record["world_kind"] == "measurement"
assert _mapping_in_record["candidate_reference"]["units"] == "kg"
assert bus.validate(_env42["bus"]["state"])["valid"] is True
_ok("wm_reachability_measurement_ok")

_env_txt = run_conversation_for_expression("hello, how are you?", created_at=_TS)
assert _env_txt["bus"]["minted"] is True
_txt_mapping = _env_txt["bus"]["state"]["context"]["world_mapping"]
assert _txt_mapping["status"] == "UNRESOLVED"
assert _txt_mapping["world_kind"] == "unknown_reference"
assert bus.validate(_env_txt["bus"]["state"])["valid"] is True
assert _txt_mapping not in ({}, None)
_ok("wm_reachability_text_ok")

_bad_mapping = {"status": "KNOWN"}
assert bus.validate_mapping_for_handoff(_bad_mapping) is None
assert bus.validate_mapping_for_handoff(_mapping_in_record) == \
    _mapping_in_record
_ok("wm_reachability_handoff_guard_ok")

_env42b = run_conversation_for_expression("42 kg", created_at=_TS)
assert _env42b["bus"]["digest"] == _env42["bus"]["digest"]
_ok("wm_reachability_deterministic_ok")

# no world-mapping turn keeps the exact Batch #3/#4 context shape
_record_plain = bus.create_state(
    state_id="wm-plain", source="worldmapping.battery", provenance=_PROW,
    input_declared={"type": "text", "value": "plain"})
assert sorted(_record_plain["context"].keys()) == \
    ["active_context", "semantic_summary"]
_ok("wm_reachability_context_shape_preserved_ok")

# ---- 11. smart-scan cleanliness and determinism ---------------------------

with open(os.path.join(_ROOT, "maya_runtime", "intelligence",
                       "world_mapping.py"), "r", encoding="utf-8") as _handle:
    _src = _handle.read()
for _forbidden in ("import random", "import time", "import datetime",
                   "import tkinter", "import subprocess", "import socket",
                   "import sched"):
    assert _forbidden not in _src, \
        "world_mapping.py must stay clean of %s" % _forbidden
assert "eval(" not in _src and "exec(" not in _src
_ok("wm_smart_scan_clean_ok")

_m1 = _map("42 kg")
_m2 = _map("42 kg")
assert json.dumps(_m1, sort_keys=True) == json.dumps(_m2, sort_keys=True)
assert json.dumps(_map("2026-09-10T12:00:00Z",
                       original="2026-09-10T12:00:00Z"),
                  sort_keys=True) == json.dumps(_map("2026-09-10T12:00:00Z",
                                                     original="2026-09-10T"
                                                              "12:00:00Z"),
                                                sort_keys=True)
_ok("wm_determinism_ok")

# ---- 12. ThinkPad-scale performance sanity --------------------------------

_loop_maps = [{"type": "measurement", "value": 1.0 + i, "units": "kg"}
              for i in range(200)]
tracemalloc.start()
_t0 = time.perf_counter()
for _item in _loop_maps:
    world_mapping.map_to_world(detector.detect(_item))
_elapsed = time.perf_counter() - _t0
_current, _peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
assert _elapsed < 10.0, "mapping too slow: %.3fs" % _elapsed
assert _peak < 32 * 1024 * 1024, "mapping peak memory %.1fMB" \
    % (_peak / (1024 * 1024))
print("wm_perf_mapping_200_avg_ms=%.3f" % (_elapsed / 200 * 1000.0))
print("wm_perf_peak_mem_mb=%.2f" % (_peak / (1024 * 1024)))
_ok("wm_perf_mapping_ms_ok")
_ok("wm_perf_memory_mb_ok")

_pipeline = [{"type": "measurement", "value": float(i), "units": "kg"}
             for i in range(60)]
_t0 = time.perf_counter()
for _item in _pipeline:
    _det = detector.detect(_item)
    _dec = decipher.decipher(dict(_det))
    world_mapping.map_to_world(_det)
_elapsed_pipe = time.perf_counter() - _t0
assert _elapsed_pipe < 10.0, "pipeline too slow: %.3fs" % _elapsed_pipe
print("wm_perf_pipeline_60_avg_ms=%.3f" % (_elapsed_pipe / 60 * 1000.0))
_ok("wm_perf_pipeline_ms_ok")

print("test_world_mapping=PASS")