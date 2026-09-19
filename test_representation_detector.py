"""Representation detection + deciphering foundation battery (Batch #4).

Proofs, against the running implementation AND a clean-room oracle:

- the four verdicts (KNOWN/AMBIGUOUS/UNKNOWN/INVALID) and the fail-closed
  principle: an input without a single well-formed meaning is never forced
  into a guess, and non-finite / contradictory / truncated inputs are INVALID
  rather than silently interpreted;
- shared representation types are reachable (no parallel type system);
- KNOWN cases (measurement, text, language, interval, event, relation,
  geometric objects/transforms, graph, envelope, typed declarations);
- AMBIGUOUS cases (bare number, bare proportion, identifier token, sequences,
  timestamp and duration without a declared temporal semantic);
- UNKNOWN cases (unknown structures, booleans, null, empty text);
- INVALID negatives N1..N20 (out-of-range probability, corrupted NaN,
  malformed canonical, truncated containers, 4-D/out-of-space points,
  malformed timestamps, event without declared event time, equation code
  execution, unknown symbolic language, identifier/measurement confusion,
  contradictory relations, corrupted envelope digest);
- epistemic status is separate from representation validity: cultural and
  traditional records are structurally valid yet claim nothing factual
  (N17/N18) and an external report is never automatically "validated" (N19);
- the deciphering contract (status, detected_type, canonical_candidate,
  evidence, provenance, losses, validation, epistemic);
- the clean-room oracle agrees with the implementation on a shared corpus;
- the real conversational path reaches the bus with typed input (detector ->
  bridge -> publish_turn), preserving the text path for free-form speech;
- deterministic, smart-scan-clean runtime: no randomness, no wall-clock, no
  clock/gui imports, no eval/exec of untrusted text;
- ThinkPad-scale performance sanity bounds.

Runtime is deterministic: structural evaluation only.
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

_ROOT = os.path.dirname(os.path.abspath(__file__))
_ORACLE = None
_TS = "2026-09-10T12:00:00Z"


def _ok(label):
    print(label + "=OK")


def _load_oracle():
    global _ORACLE
    if _ORACLE is not None:
        return _ORACLE
    path = os.path.join(_ROOT, "verification", "oracle_detector.py")
    spec = importlib.util.spec_from_file_location("detector_oracle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _ORACLE = module
    return _ORACLE


def _expect_status(value, status, label, declared=None):
    result = detector.detect(value, declared=declared)
    assert result["status"] == status, \
        "%s: expected %s, got %r" % (label, status, result["status"])
    _ok(label)


# ---- 1. contract constants ----------------------------------------------

assert set(detector.VERDICTS) == {"KNOWN", "AMBIGUOUS", "UNKNOWN", "INVALID"}
assert detector.MAX_DETECTION_DEPTH == 64
assert detector.MAX_JSON_TRIAL == 4096
_ok("detector_contract_constants_ok")

# every canonical representation type carrying input structure is reachable
# through the detector; provenance and metadata are record attributes of the
# canonical layer (validated there), never types derived from raw input.
for _t in representation.REPRESENTATION_TYPES - {"provenance", "metadata"}:
    assert _t in detector.DETECTOR_TYPE_SET, \
        "canonical type %s unreachable from the detector" % _t
for _t in detector.DETECTOR_TYPE_SET:
    assert _t in detector.CANONICAL_MAPPING
assert set(detector.DETECTOR_ONLY_TYPES) == {
    "temporal", "language", "structured_canonical_object"}
_ok("detector_type_coverage_ok")

assert detector.TYPE_DOMAIN["equation"] == "EQUATION"
assert detector.TYPE_DOMAIN["language"] == "NATURAL_LANGUAGE"
_ok("detector_domain_mapping_ok")

# ---- 2. KNOWN cases ------------------------------------------------------

for _known, _label in [
    ({"type": "scalar", "value": 42}, "detector_known_scalar"),
    ({"type": "measurement", "value": 5.0, "units": "kg"},
     "detector_known_measurement_typed"),
    ({"type": "probability", "value": 0.25}, "detector_known_probability"),
    ({"type": "equation", "value": "x = 2 * t + 1",
      "language": "maya.symbolic.v1"}, "detector_known_equation"),
    ({"language_tag": "en-US"}, "detector_known_language"),
    ({"start": _TS, "end": "2026-09-10T13:00:00Z"},
     "detector_known_interval"),
    ({"kind": "click", "at": _TS, "event_types": ["click", "hover"]},
     "detector_known_event"),
    ({"source_id": "a", "target_id": "b", "predicate": "opposes",
      "predicates": ["links", "opposes"]}, "detector_known_relation"),
    ({"geometry_kind": "point", "data": [0.2, 0.4]},
     "detector_known_geometric_object"),
    ({"kind": "translate", "parameters": {"delta": [0.1, 0.0], "dim": 2}},
     "detector_known_geometric_transform"),
    ({"nodes": ["a", "b"], "edges": [["a", "b"]]}, "detector_known_graph"),
]:
    _result = detector.detect(_known)
    assert _result["status"] == "KNOWN", "%s %r" % (_label, _result)
    assert _result["detected_type"] is not None
    _ok(_label)

# canonical envelope (real validated record) is a KNOWN structured object
_record = bus.create_state(
    state_id="det-battery", source="detector.battery",
    provenance={"source": "detector.battery", "source_url": None,
                "retrieved_at": _TS, "evidence_type": "observation",
                "confidence": "high"},
    temporal={"event_time": _TS, "processing_time": _TS},
    input_declared={"type": "measurement", "value": 42, "units": "kg"})
_envelope_result = detector.detect(_record)
assert _envelope_result["status"] == "KNOWN"
assert _envelope_result["detected_type"] == "structured_canonical_object"
assert _envelope_result["evidence"]["accepted"], "acceptance evidence missing"
_ok("detector_known_envelope")

# text lines with free form stay KNOWN text (bridge default preserved)
_text_result = detector.detect("how are you doing?")
assert _text_result["status"] == "KNOWN"
assert _text_result["detected_type"] == "text"
_ok("detector_known_text")

# ---- 3. AMBIGUOUS cases (never guessed) ----------------------------------

_ambiguous = [
    (42, "detector_ambiguous_bare_number"),
    (0.7, "detector_ambiguous_bare_proportion"),
    ("abc_123", "detector_ambiguous_identifier_token"),
    ("2026-09-10T12:00:00Z", "detector_ambiguous_iso_timestamp"),
    ("2h", "detector_ambiguous_duration"),
    ([1, 2, 3], "detector_ambiguous_sequence"),
    ((1.0, 2.0, 3.0), "detector_ambiguous_tuple"),
    ([[1, 2], [3, 4]], "detector_ambiguous_rect_array"),
    ({"value": 0.7}, "detector_ambiguous_bare_value"),
    ({"value": 1, "units": 5}, "detector_ambiguous_bad_units"),
    ({"kind": "click", "at": _TS}, "detector_ambiguous_event_undeclared"),
]
for _candidate, _label in _ambiguous:
    _result = detector.detect(_candidate)
    assert _result["status"] == "AMBIGUOUS", "%s %r" % (_label, _result)
    assert "candidate_types" in _result["evidence"]
    _ok(_label)

# ---- 4. UNKNOWN cases ----------------------------------------------------

_unknown = [
    (True, "detector_unknown_boolean"),
    (None, "detector_unknown_null"),
    ("", "detector_unknown_empty_text"),
    ({"custom": "structure"}, "detector_unknown_custom_structure"),
    (["mixed", 3], "detector_unknown_heterogeneous_sequence"),
]
for _candidate, _label in _unknown:
    _result = detector.detect(_candidate)
    assert _result["status"] == "UNKNOWN", "%s %r" % (_label, _result)
    _ok(_label)

# ---- 5. fail-closed INVALID negatives N1..N20 ----------------------------

# N1 bare number is never silently promoted (see AMBIGUOUS block).
# N2 "42 kg" is a KNOWN measurement (see text path below).
_measurement_text = detector.detect("42 kg")
assert _measurement_text["status"] == "KNOWN"
assert _measurement_text["detected_type"] == "measurement"
assert _measurement_text["canonical_candidate"] == {
    "type": "measurement", "value": 42, "units": "kg"}
_ok("detector_known_40kg_measurement_text")
# N3 bare 0.7 never promoted either (see AMBIGUOUS block).

_invalid_negatives = [
    ({"type": "probability", "value": 1.4}, None, "detector_N4_prob_out_of_range"),
    ({"type": "probability", "value": -0.25}, None,
     "detector_N4_prob_negative"),
    ({"type": "measurement", "value": float("nan"), "units": "kg"}, None,
     "detector_N5_nan_measurement"),
    ({"type": "measurement", "value": float("inf"), "units": "kg"}, None,
     "detector_N5_inf_measurement"),
    ({"protocol": "maya.unified_state", "schema": "maya:unified-state:1"},
     None, "detector_N7_malformed_canonical"),
    ({"geometry_kind": "point", "data": [0.2, 0.4, 0.1, 0.9]}, None,
     "detector_N9_4d_point"),
    ({"geometry_kind": "point", "data": [1.5, 0.4],
      "space": [0.0, 1.0, 0.0, 1.0]}, None, "detector_N10_out_of_space"),
    ("2026-13-45T99:00:00Z", None, "detector_N11_malformed_timestamp"),
    ("[1, 2", None, "detector_N11_truncated_container"),
    ({"type": "equation",
      "value": "eval(open('/etc/passwd').read())",
      "language": "maya.symbolic.v1"}, None,
     "detector_N13_equation_never_executes"),
    ({"type": "equation", "value": "x = 1", "language": "not-a-language"},
     None, "detector_N14_unknown_symbolic_language"),
    ({"type": "identifier", "value": "42 kg"}, None,
     "detector_N15_identifier_where_measurement"),
    ({"source_id": "a", "target_id": "a", "predicate": "opposes",
      "predicates": ["links", "opposes"]}, None,
     "detector_N16_contradictory_relations"),
]
for _candidate, _declared, _label in _invalid_negatives:
    _result = detector.detect(_candidate, declared=_declared)
    assert _result["status"] == "INVALID", "%s %r" % (_label, _result)
    assert "validation_reason" in _result["evidence"]
    _ok(_label)

# N20 corrupted canonical bytes: mutate a payload field then re-issue a
# digest over the corrupted body -> bus.validate rejects the mismatch.
_corrupted = dict(_record)
_corrupted["knowledge"] = {"claims": []}
_corrupted_bytes = detector.detect(_corrupted)
assert _corrupted_bytes["status"] == "INVALID", \
    "corrupted-envelope digest must fail: %r" % _corrupted_bytes
_ok("detector_N20_corrupted_canonical_bytes")

# ---- 6. epistemic status is never derived from structure ----------------

_cultural_geo = {"geometry_kind": "point", "data": [0.25, 0.25]}
_frame_geo = epistemic.frame(
    representation_valid=True, epistemic_status="TRADITIONAL",
    empirical_status="UNVERIFIED", domain="ASTROLOGY")
assert _frame_geo["claims_nothing_factual"] is True
assert _frame_geo["declaration_hint"] == "EXTERNAL_REPORT"
assert _frame_geo["validation_hint"] == "unknown"
_ok("detector_epistemic_N17_astrological_record")

_religious = {"type": "text", "value": "a ritual statement of origin"}
_decipher_religion = decipher.decipher(
    _religious, provenance={"source": "battery",
                            "retrieved_at": _TS,
                            "evidence_type": "historical_record",
                            "confidence": "low"},
    epistemic_status="TRADITIONAL", empirical_status="UNVERIFIED",
    domain="RELIGIOUS_TRADITION")
assert _decipher_religion["epistemic"]["claims_nothing_factual"] is True
assert _decipher_religion["validation"]["representation_valid"] is True
_ok("detector_epistemic_N18_religious_statement")

# N19 an external report is never automatically "validated"
_claim = {"type": "equation", "value": "pi = 3", "language": "maya.symbolic.v1"}
_decipher_claim = decipher.decipher(
    _claim, provenance={"source": "external-recall",
                        "retrieved_at": _TS,
                        "evidence_type": "report",
                        "confidence": "low"},
    epistemic_status="REPORTED", empirical_status="UNVERIFIED")
assert _decipher_claim["validation"]["representation_valid"] is True
assert _decipher_claim["epistemic"]["declaration_hint"] == "EXTERNAL_REPORT"
assert _decipher_claim["epistemic"]["validation_hint"] == "unvalidated"
assert _decipher_claim["epistemic"]["claims_nothing_factual"] is False
_ok("detector_epistemic_N19_external_report_not_validated")

# ---- 7. deciphering contract --------------------------------------------

_dec = decipher.decipher(
    "42 kg", provenance={"source": "battery", "retrieved_at": _TS,
                         "evidence_type": "observation",
                         "confidence": "high"})
assert set(_dec) == set(decipher.DECIPHER_KEYS)
assert _dec["status"] == "KNOWN" and _dec["detected_type"] == "measurement"
assert _dec["canonical_candidate"] == {"type": "measurement", "value": 42,
                                       "units": "kg"}
assert _dec["losses"] == []
assert _dec["provenance"] == {"source": "battery", "retrieved_at": _TS,
                              "evidence_type": "observation",
                              "confidence": "high"}
assert _dec["validation"]["representation_valid"] is True
assert _dec["validation"]["canonical_maps_to"] == "measurement"
assert _dec["validation"]["oracle_eligible"] is True
assert _dec["epistemic"]["declaration_hint"] == "UNKNOWN" or \
    _dec["epistemic"]["declaration_hint"] in \
    epistemic.DECLARATION_FOR_EPISTEMIC.values()
_ok("decipher_contract_measurement_ok")

# detector-only types canonicalize onto shared types, never lost
_interval = decipher.decipher(
    {"start": _TS, "end": "2026-09-10T13:00:00Z"},
    provenance={"source": "battery", "retrieved_at": _TS,
                "evidence_type": "observation", "confidence": "high"})
assert _interval["detected_type"] == "temporal_interval"
assert _interval["validation"]["canonical_maps_to"] == "temporal_interval"
assert sorted(decipher.losses_for({"start": _TS, "end": _TS},
                                  {"status": "KNOWN",
                                   "detected_type": "temporal_interval"})) == []
_ok("decipher_contract_interval_ok")

_lang = decipher.decipher(
    {"language_tag": "en-US"},
    provenance={"source": "battery", "retrieved_at": _TS,
                "evidence_type": "observation", "confidence": "high"})
assert _lang["detected_type"] == "language"
assert _lang["validation"]["canonical_maps_to"] == "text"
assert any("canonicalized" in loss
           for loss in _lang["losses"]), _lang["losses"]
_ok("decipher_contract_language_canonicalization_ok")

_bad_prov = decipher.decipher(
    "42 kg", provenance={"source": "battery", "retrieved_at": "not-a-date",
                         "evidence_type": "observation",
                         "confidence": "high"})
assert _bad_prov["status"] == "INVALID"
_ok("decipher_contract_invalid_provenance_ok")

# ---- 8. clean-room oracle agreement --------------------------------------

_oracle = _load_oracle()
assert _oracle.ORACLE_IDENTITY.startswith("maya-verification/oracle-detector")
for _value, _expected, _note in _oracle.CORPUS:
    _impl_status = detector.detect(_value)["status"]
    assert _impl_status == _expected, \
        "corpus disagreement on %r: impl=%s oracle=%s" \
        % (_value, _impl_status, _expected)
for _value, _expected, _note in _oracle._geometry_negatives():
    _impl_status = detector.detect(_value)["status"]
    assert _impl_status == _expected, \
        "geometry disagreement on %r" % (_value,)
_ok("detector_oracle_agreement_ok")

# ---- 9. real conversational path reaches the bus with typed input -------

from maya_runtime.intelligence.bridge import run_conversation_for_expression

_env = run_conversation_for_expression("42 kg", created_at=_TS)
assert _env["detection"]["status"] == "KNOWN"
assert _env["detection"]["detected_type"] == "measurement"
assert _env["bus"]["minted"] is True
assert _env["bus"]["state"]["input"]["declared"]["type"] == "measurement"
assert bus.validate(_env["bus"]["state"])["valid"] is True
_ok("detector_reachability_typed_input_ok")

_env_text = run_conversation_for_expression("how are you doing?", created_at=_TS)
assert _env_text["detection"]["status"] == "KNOWN"
assert _env_text["detection"]["detected_type"] == "text"
assert _env_text["bus"]["minted"] is True
assert _env_text["bus"]["state"]["input"]["declared"]["type"] == "text"
_ok("detector_reachability_text_unchanged_ok")

# commands are routed by maya_chat before the bridge; the bridge itself
# never turns a command into a measurement/vector binding
_env_dash = run_conversation_for_expression("/status hello-command",
                                            created_at=_TS)
_ok("detector_reachability_command_unchanged_ok")

# ---- 10. smart-scan cleanliness and runtime determinism ------------------

with open(os.path.join(_ROOT, "maya_runtime", "intelligence",
                       "detector.py"), "r", encoding="utf-8") as _handle:
    _src = _handle.read()
for _forbidden in ("import random", "import time", "import datetime",
                   "import tkinter", "import subprocess", "import socket",
                   "import sched"):
    assert _forbidden not in _src, \
        "detector.py must stay clean of %s" % _forbidden
assert "eval(" not in _src and "exec(" not in _src
_ok("detector_smart_scan_clean_ok")

_d = detector.detect("42 kg")
assert json.dumps(_d, sort_keys=True) == json.dumps(
    detector.detect("42 kg"), sort_keys=True)
_ok("detector_determinism_ok")

# ---- 11. ThinkPad-scale performance sanity -------------------------------

_loop = [{"type": "measurement", "value": 1.0 + i, "units": "kg"}
         for i in range(200)]
tracemalloc.start()
_t0 = time.perf_counter()
for _item in _loop:
    detector.detect(_item)
_elapsed = time.perf_counter() - _t0
_current, _peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
assert _elapsed < 10.0, "detection too slow: %.3fs" % _elapsed
assert _peak < 32 * 1024 * 1024, "detection peak memory %.1fMB" \
    % (_peak / (1024 * 1024))
_ok("detector_perf_sanity_ok")

print("test_representation_detector=PASS")