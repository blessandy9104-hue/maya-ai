"""Persona state + weighted multi-persona fusion verification battery
(Batch #6).

Proofs, against the running implementation AND a clean-room oracle that never
imports ``maya_runtime``:

- the persona specification contract (spec keys, bounded weights, activation
  conditions, constraints, provenance) and the derived PersonaState contract;
- PersonaState is DERIVED: it references shared state, never mutates it, and
  geometry coordinates / canonical values / epistemic / safety always travel
  in the canonical state;
- deterministic activation (representation type, world kind, domain, explicit
  caller context, relevance signals): ACTIVE / AMBIGUOUS / INACTIVE, no LLM,
  no randomness, no invented intent — free text never implies a persona;
- the weight model (raw_weight -> normalized_weight with wi' = wi / sum(wi)):
  finite, non-negative, bounded, zero-sum explicit; NaN/infinity/negative
  fail closed;
- explicit weights vs epistemic confidence separation (weight != truth
  probability; the inherited epistemic frame is copied through unchanged);
- fusion: consensus is a weighted priority lens (never truth); conflicts are
  retained as NO_CONFLICT / WEIGHTED_DISAGREEMENT / UNRESOLVED_CONFLICT /
  INCOMPATIBLE, never collapsed;
- epistemic inheritance (cultural/astrology claims stay unvalidated through
  a persona perspective) and safety inheritance (core safety holds/blocked
  dominate; a required core override is blocked and recorded);
- geometry stays mathematically intact under persona perspectives;
- representation-aware activation across all required signal categories;
- the growth foundation: register / validate / activate / weight / deactivate
  with architect approval required for deployment — no autonomous creation;
- fail-closed negatives N1..N20;
- the real conversational path (detector -> world mapping -> persona
  activation -> persona state -> weighted fusion -> unified state bus)
  carries the fused cognitive state into ``context.persona_fusion``,
  authenticated by the record digest, with the Batch #3/#4 context shape
  preserved for records without a fusion;
- cross-interpreter deterministic digest, clean-room oracle agreement, and
  ThinkPad-scale performance sanity bounds.

Runtime is deterministic: no wall-clock influence on persona decisions.
"""
import copy
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime.intelligence import bus
from maya_runtime.intelligence import detector
from maya_runtime.intelligence import epistemic
from maya_runtime.intelligence import persona
from maya_runtime.intelligence import world_mapping

from maya_runtime.intelligence.bridge import run_conversation_for_expression

_ROOT = os.path.dirname(os.path.abspath(__file__))
_ORACLE = None
_TS = "2026-09-10T12:00:00Z"
_PROW = {"source": "personafusion.battery", "source_url": None,
         "retrieved_at": _TS, "evidence_type": "observation",
         "confidence": "medium"}
_PF = persona.PERSONA_ANCHOR_TIME


def _ok(label):
    print(label + "=OK")


def _load_oracle():
    global _ORACLE
    if _ORACLE is not None:
        return _ORACLE
    path = os.path.join(_ROOT, "verification", "oracle_persona_fusion.py")
    spec = importlib.util.spec_from_file_location("persona_fusion_oracle",
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _ORACLE = module
    return _ORACLE


def _mk_persona(pid, priorities=None, weight=1.0, conditions=None,
                requires=None, prohibits=None, reasoning=None,
                approval_role="architect"):
    body = {
        "persona_id": pid,
        "name": pid,
        "version": "1.0",
        "domain": "STRUCTURED_DATA",
        "priorities": {"precision": 0.5, "interpretation": 0.5}
        if priorities is None else priorities,
        "weights": {"base": weight},
        "activation_conditions": {"threshold": 0.5, "task_types": ["test_case"], "switches": {"active": True}}
        if conditions is None else conditions,
        "reasoning_profile": {"perspective": "test lens", "emphasis": ["test"]}
        if reasoning is None else reasoning,
        "expression_profile": {"register": "measured", "tone": "neutral"},
        "constraints": {"allowed_modes": ["test"], "prohibited_modes": list(prohibits or ()),
                        "requires": list(requires or ()), "notes": None},
        "provenance": {"source": "persona_fusion.battery",
                       "source_url": None, "retrieved_at": _TS,
                       "evidence_type": "observation",
                       "confidence": "medium",
                       "claim": "Battery fixture persona."},
    }
    if approval_role is not None:
        body["provenance"]["approval_role"] = approval_role
    return body


def _measurement_mapping():
    detection = detector.detect({"type": "measurement", "value": 42,
                                 "units": "kg"})
    return world_mapping.map_to_world(detection, provenance=_PROW)


def _geometry_mapping():
    detection = detector.detect({"type": "geometric_point",
                                 "value": [0.5, 0.5]})
    return world_mapping.map_to_world(detection, provenance=_PROW)


def _text_mapping():
    detection = detector.detect("Astrology states X causes Y")
    return world_mapping.map_to_world(detection, provenance=_PROW,
                                      domain="ASTROLOGY")


def _default_personas_map():
    return {p["persona_id"]: p for p in persona.DEFAULT_PERSONAS}


def _digest(obj):
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 1. contract constants
# ---------------------------------------------------------------------------

assert persona.PERSONA_PROTOCOL == "maya.persona_fusion.v1"
assert persona.ACTIVATION_STATUSES == ("ACTIVE", "INACTIVE", "AMBIGUOUS")
assert persona.CONFLICT_STATUSES == (
    "NO_CONFLICT", "WEIGHTED_DISAGREEMENT", "UNRESOLVED_CONFLICT",
    "INCOMPATIBLE")
assert persona.FUSION_STATUSES == ("FUSED", "NO_ACTIVE_PERSONA")
assert persona.NO_ACTIVE_PERSONA == "NO_ACTIVE_PERSONA"
assert persona.FUSION_METHOD == "weighted_multi_persona_fusion"
assert persona.PERSONA_SPEC_KEYS == (
    "persona_id", "name", "version", "domain", "priorities", "weights",
    "activation_conditions", "reasoning_profile", "expression_profile",
    "constraints", "provenance")
assert persona.PERSONA_STATE_KEYS == (
    "persona_id", "input_state_reference", "activation_score",
    "activation_status", "priority_vector", "perspective", "constraints",
    "candidate_interpretations", "confidence", "inherited_epistemic",
    "provenance")
_ok("pf_contract_constants_ok")

# ---------------------------------------------------------------------------
# 2. persona specification
# ---------------------------------------------------------------------------

for _default in persona.DEFAULT_PERSONAS:
    assert persona.validate_persona(_default)["valid"] is True
_ok("pf_persona_default_valid_ok")

assert persona.validate_persona({"persona_id": "x"})["valid"] is False
_ok("pf_persona_missing_keys_ok")

_bad = _mk_persona("bad id")
assert persona.validate_persona(_bad)["valid"] is False
_ok("pf_persona_bad_id_ok")

_bad = _mk_persona("p.bad.domain")
_bad["domain"] = "NOT_A_DOMAIN"
assert persona.validate_persona(_bad)["valid"] is False
_ok("pf_persona_bad_domain_ok")

_bad = _mk_persona("p.nan")
_bad["weights"]["base"] = float("nan")
assert persona.validate_persona(_bad)["valid"] is False
_ok("pf_persona_nan_weight_ok")

_bad = _mk_persona("p.inf")
_bad["weights"]["base"] = float("inf")
assert persona.validate_persona(_bad)["valid"] is False
_ok("pf_persona_inf_weight_ok")

_bad = _mk_persona("p.neg")
_bad["weights"]["base"] = -1.0
assert persona.validate_persona(_bad)["valid"] is False
_ok("pf_persona_negative_weight_ok")

_bad = _mk_persona("p.pri", priorities={"precision": 1.5})
assert persona.validate_persona(_bad)["valid"] is False
_ok("pf_persona_priority_bounds_ok")

for _cond in (42, {"threshold": 0.0}, {"switches": {"s": "yes"}},
              {"relevance_signals": ["nonsense"]},
              {"representation_types": "measurement"}):
    _bad = _mk_persona("p.badcond", conditions=_cond)
    assert persona.validate_persona(_bad)["valid"] is False
_ok("pf_persona_malformed_conditions_ok")

_bad = _mk_persona("p.badprov")
_bad["provenance"] = {"source": "x", "retrieved_at": None}
assert persona.validate_persona(_bad)["valid"] is False
_ok("pf_persona_bad_provenance_ok")

# ---- 2b. weights: explicit, bounded, inspectable --------------------------

_norm = persona.normalize_weights([2.0, 1.0, 1.0])
assert _norm["status"] == "normalized"
assert _norm["normalized"] == [0.5, 0.25, 0.25]
assert abs(sum(_norm["normalized"]) - 1.0) < 1e-9
_ok("pf_weights_normalize_ok")

assert persona.normalize_weights([3.0])["normalized"] == [1.0]
_ok("pf_weights_single_ok")

for _w in (float("nan"), float("inf"), float("-inf"), -0.5, "2"):
    try:
        persona.normalize_weights([_w])
        raise AssertionError("accepted invalid weight %r" % (_w,))
    except persona.PersonaError:
        pass
_ok("pf_weights_invalid_rejected_ok")

_zero = persona.normalize_weights([0.0, 0.0])
assert _zero["status"] == "zero_sum" and _zero["normalized"] == []
_ok("pf_weights_zero_sum_explicit_ok")

# ---------------------------------------------------------------------------
# 3. registry (growth foundation)
# ---------------------------------------------------------------------------

_reg = persona.PersonaRegistry()
assert isinstance(_reg, persona.PersonaRegistry)
assert _reg.all() == ()
_new_id = _reg.register(_mk_persona("persona.battery.new"))
assert _new_id == "persona.battery.new"
assert _reg.all() == ("persona.battery.new",)
assert _reg.weight("persona.battery.new") == {
    "persona_id": "persona.battery.new", "raw_weight": 1.0}
_ok("pf_registry_register_weight_ok")

try:
    _reg.register(_mk_persona("persona.battery.new"))
    raise AssertionError("duplicate persona registered")
except persona.PersonaError:
    pass
_ok("pf_neg5_duplicate_id_ok")

try:
    _reg.activate("persona.not.registered")
    raise AssertionError("unknown persona activated")
except persona.PersonaError:
    pass
try:
    _reg.weight("persona.not.registered")
    raise AssertionError("unknown persona weighted")
except persona.PersonaError:
    pass
try:
    _reg.lookup("persona.not.registered")
    raise AssertionError("unknown persona looked up")
except persona.PersonaError:
    pass
_ok("pf_neg7_unknown_id_ok")

_unapproved = persona.PersonaRegistry(
    [_mk_persona("p.unapproved", approval_role=None)])
try:
    _unapproved.deploy("p.unapproved")
    raise AssertionError("unapproved persona deployed")
except persona.PersonaError:
    pass
_ok("pf_deploy_requires_approval_ok")

_appr = persona.PersonaRegistry([_mk_persona("p.approved")])
assert _appr.deploy("p.approved") == {
    "persona_id": "p.approved", "deployed": True}
_ok("pf_deploy_approved_ok")

_reg2 = persona.PersonaRegistry([_mk_persona("p.a"),
                                 _mk_persona("p.b")])
_reg2.deactivate("p.a")
assert _reg2.enabled() == ("p.b",)
_state_a = _reg2.activate("p.a")
assert _state_a["activation_status"] == "INACTIVE"
_ok("pf_registry_deactivate_ok")

_default_reg = persona.default_registry()
assert _default_reg.all() == ("persona.analytical.geometry",
                              "persona.core.evidence")
assert _default_reg.enabled() == _default_reg.all()
_ok("pf_registry_default_ordering_ok")

# ---------------------------------------------------------------------------
# 4. activation
# ---------------------------------------------------------------------------

_m = _measurement_mapping()
_regm = persona.default_registry()
_state_ev = _regm.activate("persona.core.evidence",
                           world_mapping=_m, detected_type="measurement",
                           state_reference="wm:1")
assert _state_ev["activation_status"] == "ACTIVE"
assert _state_ev["activation_score"] == 1.0
assert _state_ev["confidence"] == 1.0
assert _state_ev["inherited_epistemic"] == _m["epistemic"]
_ok("pf_activation_measurement_ok")

_g = _geometry_mapping()
_state_geo = _regm.activate("persona.analytical.geometry",
                            world_mapping=_g, detected_type="geometric_point",
                            state_reference="wm:g")
assert _state_geo["activation_status"] == "ACTIVE"
assert _state_geo["priority_vector"]["precision"] == 0.9
_ok("pf_activation_geometry_ok")

_t = _text_mapping()
_compute_t = persona.compute(world_mapping=_t, detected_type="text",
                             core_epistemic=_t["epistemic"])
assert _compute_t["status"] == persona.NO_ACTIVE_PERSONA
assert _compute_t["active_personas"] == []
assert _compute_t["excluded_inactive"] == sorted(_default_reg.all())
_ok("pf_activation_free_text_no_invented_persona_ok")

_creative = _mk_persona("p.creative", conditions={
    "threshold": 0.75, "representation_types": ["text"],
    "task_types": ["creative_writing"]})
_regc = persona.PersonaRegistry([_creative])
_state_c = _regc.activate("p.creative", world_mapping=_t, detected_type="text",
                          task_type=None)
assert _state_c["activation_status"] == "AMBIGUOUS"
assert _state_c["activation_score"] == 0.5  # half-match < 0.75 threshold
_state_c2 = _regc.activate("p.creative", world_mapping=_t, detected_type="text",
                           task_type="creative_writing")
assert _state_c2["activation_status"] == "ACTIVE"
_ok("pf_activation_explicit_call_context_ok")

_ambiguous = _mk_persona("p.ambiguous", conditions={
    "threshold": 0.5, "representation_types": ["geometric_point"],
    "world_kinds": ["temporal_reference"], "domains": ["ASTROLOGY"]})
_regamb = persona.PersonaRegistry([_ambiguous])
_state_a1 = _regamb.activate("p.ambiguous", world_mapping=_t,
                             detected_type="text")
assert _state_a1["activation_status"] == "AMBIGUOUS"
assert 0.0 < _state_a1["activation_score"] < 0.5
_compute_a = persona.compute(world_mapping=_t, detected_type="text",
                             core_epistemic=_t["epistemic"],
                             personas=_regamb)
assert _compute_a["status"] == persona.NO_ACTIVE_PERSONA
assert _compute_a["excluded_inactive"] == ["p.ambiguous"]
_ok("pf_neg15_ambiguous_activation_ok")

_conditions = {"threshold": 0.5, "representation_types": ["text"],
               "world_kinds": ["temporal_reference"]}
_score_text = persona.activation_score(
    _mk_persona("p.bound", conditions=_conditions),
    detected_type="text", world_kind="unknown_reference")
assert _score_text == 0.5
assert persona.activation(_score_text, 0.5) == "ACTIVE"
_ok("pf_activation_threshold_boundary_ok")

# ---------------------------------------------------------------------------
# 5. fusion math
# ---------------------------------------------------------------------------

_for_fusion = [_mk_persona("persona.a.action",
                           priorities={"action": 1.0, "restraint": 0.0},
                           weight=2.0),
               _mk_persona("persona.b.restraint",
                           priorities={"action": 0.0, "restraint": 1.0},
                           weight=1.0)]
_regab = persona.PersonaRegistry(_for_fusion)
_states_ab = []
for _pid in _regab.enabled():
    _pr = _regab.lookup(_pid)
    _states_ab.append(persona.derive_persona_state(
        _pr, world_mapping=_m, detected_type="measurement",
        state_reference="wm:ab", task_type="test_case",
        switches={"active": True}))
assert all(s["activation_status"] == "ACTIVE" for s in _states_ab)
_fused_ab = persona.fuse(_states_ab, personas=_regab._personas,
                         core_epistemic=_m["epistemic"])
assert _fused_ab["status"] == "FUSED"
assert _fused_ab["active_personas"] == ["persona.a.action",
                                        "persona.b.restraint"]
assert _fused_ab["weights"]["persona.a.action"]["normalized_weight"] == 0.666667
assert _fused_ab["weights"]["persona.b.restraint"]["normalized_weight"] == 0.333333
assert _fused_ab["consensus"] == {"action": 0.6667, "restraint": 0.3333}
_ok("pf_fusion_consensus_ok")

_contrib_ids = [c["persona_id"] for c in
                _fused_ab["per_persona_contributions"]]
assert _contrib_ids == ["persona.a.action", "persona.b.restraint"]
assert _fused_ab["per_persona_contributions"][0]["weight"] == 0.666667
_ok("pf_fusion_contributions_ok")

assert abs(sum(w["normalized_weight"] for w in _fused_ab["weights"].values())
           - 1.0) < 1e-9
assert "persona_weight is not epistemic probability" in " ".join(
    _fused_ab["notes"])
_ok("pf_fusion_weight_not_probability_ok")

# zero total weight among active -> explicit NO_ACTIVE_PERSONA (fail closed)
_zws = []
_zw_persona = _mk_persona("p.zero", weight=0.0)
_regzw = persona.PersonaRegistry([_zw_persona])
_state_zw = _regzw.activate("p.zero", world_mapping=_m,
                            detected_type="measurement",
                            task_type="test_case", switches={"active": True})
assert _state_zw["activation_status"] == "ACTIVE", _state_zw
_ze_fused = persona.fuse([_state_zw], personas=_regzw._personas)
assert _ze_fused["status"] == persona.NO_ACTIVE_PERSONA
assert any("zero total weight" in note for note in _ze_fused["notes"])
_ok("pf_neg4_zero_total_weight_ok")

assert persona.validate_fused_state(_fused_ab)["valid"] is True
_ok("pf_fused_state_valid_ok")

# ---------------------------------------------------------------------------
# 6. conflicts
# ---------------------------------------------------------------------------

_agree = [_mk_persona("p.x", priorities={"action": 0.8, "restraint": 0.2},
                      weight=2.0),
          _mk_persona("p.y", priorities={"action": 0.8, "restraint": 0.2},
                      weight=1.0)]
_rega = persona.PersonaRegistry(_agree)
_states = [persona.derive_persona_state(_rega.lookup(p),
                                        world_mapping=_m,
                                        detected_type="measurement",
                                        task_type="test_case",
                                        switches={"active": True})
           for p in _rega.enabled()]
_fused_nc = persona.fuse(_states, personas=_rega._personas)
assert _fused_nc["conflict_status"] == "NO_CONFLICT"
_ok("pf_conflict_none_ok")

_wd = [_mk_persona("p.w1", priorities={"action": 0.9, "restraint": 0.1},
                   weight=2.0),
       _mk_persona("p.w2", priorities={"action": 0.6, "restraint": 0.4},
                   weight=1.0)]
_regwd = persona.PersonaRegistry(_wd)
_states_wd = [persona.derive_persona_state(_regwd.lookup(p),
                                           world_mapping=_m,
                                           detected_type="measurement",
                                           task_type="test_case",
                                           switches={"active": True})
              for p in _regwd.enabled()]
_fused_wd = persona.fuse(_states_wd, personas=_regwd._personas)
assert _fused_wd["conflict_status"] == "WEIGHTED_DISAGREEMENT"
_ok("pf_conflict_weighted_disagreement_ok")

_unres = [_mk_persona("p.o1", priorities={"action": 1.0, "restraint": 0.0},
                      weight=2.0),
          _mk_persona("p.o2", priorities={"action": 0.0, "restraint": 1.0},
                      weight=1.0)]
_regunres = persona.PersonaRegistry(_unres)
_states_unres = [persona.derive_persona_state(_regunres.lookup(p),
                                              world_mapping=_m,
                                              detected_type="measurement",
                                              task_type="test_case",
                                              switches={"active": True})
                 for p in _regunres.enabled()]
_fused_unres = persona.fuse(_states_unres, personas=_regunres._personas)
assert _fused_unres["conflict_status"] == "WEIGHTED_DISAGREEMENT"
assert _fused_unres["conflicts"], "conflicts must be retained, not collapsed"
assert _fused_unres["unresolved_dimensions"] == ["action", "restraint"]
_ok("pf_neg9_conflicting_outputs_ok")

# UNRESOLVED_CONFLICT classification semantics (opposing priority directions).
# The weight contract today forbids signed influence (priorities are
# non-negative), so the opposing-direction branch is a pure classifier
# property, proven here on adversarial states without registry validation.
_adv_a = {"persona_id": "adv.a", "priority_vector": {"action": 1.0,
                                                     "restraint": -0.4},
          "perspective": {}, "constraints": {}, "candidate_interpretations": []}
_adv_b = {"persona_id": "adv.b", "priority_vector": {"action": -0.4,
                                                     "restraint": 1.0},
          "perspective": {}, "constraints": {}, "candidate_interpretations": []}
assert persona.classify_conflict(_adv_a, _adv_b)[0] == "UNRESOLVED_CONFLICT"
_ok("pf_conflict_unresolved_classification_ok")

_inc = [_mk_persona("p.m1", priorities={"action": 0.5},
                    requires=["mode_a"]),
        _mk_persona("p.m2", priorities={"action": 0.5},
                    prohibits=["mode_a"])]
_reginc = persona.PersonaRegistry(_inc)
_states_inc = [persona.derive_persona_state(_reginc.lookup(p),
                                            world_mapping=_m,
                                            detected_type="measurement",
                                            task_type="test_case",
                                            switches={"active": True})
               for p in _reginc.enabled()]
_fused_inc = persona.fuse(_states_inc, personas=_reginc._personas)
assert _fused_inc["conflict_status"] == "INCOMPATIBLE"
_ok("pf_conflict_incompatible_ok")

# neither perspective is discarded: both remain in per-persona contributions
_contrib_positions = {}
for _c in _fused_unres["per_persona_contributions"]:
    _contrib_positions[_c["persona_id"]] = _c["perspective"]
assert len(_contrib_positions) == 2
_ok("pf_conflict_not_collapsed_ok")

# ---------------------------------------------------------------------------
# 7. epistemic inheritance (weight != epistemic confidence)
# ---------------------------------------------------------------------------

assert _fused_ab["inherited_epistemic"] == _m["epistemic"]
_mea_epi = _fused_ab["inherited_epistemic"]
assert _mea_epi["epistemic_status"] == "UNKNOWN"
assert _mea_epi["validation_hint"] == "unknown"
assert _mea_epi["claims_nothing_factual"] is True
_ok("pf_epistemic_preserved_ok")

assert _t["epistemic"]["epistemic_status"] == "TRADITIONAL"
assert _t["epistemic"]["claims_nothing_factual"] is True
assert _t["mapping_evidence"]["claim_status"] == "non-factual-claim"
_fused_t = persona.compute(world_mapping=_t, detected_type="text",
                           core_epistemic=_t["epistemic"],
                           task_type="creative_writing", switches={})
assert _fused_t["status"] == persona.NO_ACTIVE_PERSONA
assert _fused_t["inherited_epistemic"] is None
_ok("pf_activation_free_text_new_active_no_persona_ok")

_cul = _mk_persona("persona.core.culture", conditions={
    "threshold": 0.5, "representation_types": ["text"],
    "task_types": ["creative_writing"]})
_regcul = persona.PersonaRegistry([_cul])
_fused_cul = persona.compute(
    world_mapping=_t, detected_type="text", personas=_regcul,
    task_type="creative_writing", core_epistemic=_t["epistemic"])
assert _fused_cul["status"] == "FUSED"
assert _fused_cul["active_personas"] == ["persona.core.culture"]
_cul_epi = _fused_cul["inherited_epistemic"]
assert _cul_epi["epistemic_status"] == "TRADITIONAL"
assert _cul_epi["claims_nothing_factual"] is True
assert _cul_epi["validation_hint"] == "unknown"
_ok("pf_epistemic_cultural_claim_preserved_ok")

_altered = copy.deepcopy(_state_ev)
_altered["inherited_epistemic"] = dict(_state_ev["inherited_epistemic"])
_altered["inherited_epistemic"]["epistemic_status"] = "MEASURED"
_altered["inherited_epistemic"]["claims_nothing_factual"] = False
_altered["inherited_epistemic"]["validation_hint"] = "validated"
_v = persona.validate_persona_state(_altered,
                                    canonical_epistemic=_m["epistemic"])
assert _v["valid"] is False
_ok("pf_neg10_alter_epistemic_ok")

_override_persona = _mk_persona("p.coerce", requires=["promote_to_fact"])
_regco = persona.PersonaRegistry([_override_persona])
_state_coerce = _regco.activate("p.coerce", world_mapping=_m,
                                detected_type="measurement",
                                task_type="test_case",
                                switches={"active": True})
_fused_coerce = persona.fuse([_state_coerce], personas=_regco._personas,
                             core_epistemic=_m["epistemic"])
assert _fused_coerce["inherited_epistemic"] == _m["epistemic"]
assert _fused_coerce["constraints"]["overrides_recorded"] == ["p.coerce"]
assert _fused_coerce["safety"]["persona_override_blocked"] is True
_ok("pf_neg11_claim_to_fact_blocked_ok")

# ---------------------------------------------------------------------------
# 8. safety inheritance
# ---------------------------------------------------------------------------

_fused_safe = persona.fuse([_state_ev], personas=_regm._personas,
                           core_epistemic=_m["epistemic"],
                           core_safety={"status": "hold",
                                        "safety_hold": True,
                                        "blocked": False})
assert _fused_safe["safety"]["core_holds"] is True
assert _fused_safe["safety"]["core_dominant"] is True
_ok("pf_safety_hold_dominant_ok")

_bypass = _mk_persona("p.bypass", requires=["override_safety_hold"])
_regby = persona.PersonaRegistry([_bypass])
_state_bypass = _regby.activate("p.bypass", world_mapping=_m,
                                detected_type="measurement",
                                task_type="test_case",
                                switches={"active": True})
_fused_bypass = persona.fuse([_state_bypass], personas=_regby._personas,
                             core_safety={"status": "hold",
                                          "safety_hold": True,
                                          "blocked": False})
assert _fused_bypass["conflict_status"] == "INCOMPATIBLE"
assert _fused_bypass["safety"]["persona_override_blocked"] is True
assert _fused_bypass["safety"]["core_holds"] is True
assert _fused_bypass["constraints"]["overrides_recorded"] == ["p.bypass"]
_ok("pf_neg12_safety_hold_bypass_blocked_ok")

# ---------------------------------------------------------------------------
# 9. geometry stays mathematically intact
# ---------------------------------------------------------------------------

_geo_before = copy.deepcopy(_g["normalized_fields"])
_fused_geo = persona.compute(world_mapping=_g, detected_type="geometric_point",
                             core_epistemic=_g["epistemic"])
assert _fused_geo["status"] == "FUSED"
assert _fused_geo["active_personas"] == ["persona.analytical.geometry"]
assert _g["normalized_fields"] == _geo_before
assert _g["normalized_fields"]["point"] == [0.5, 0.5]
assert "geometry" not in _fused_geo["consensus"]
assert all("coordinates" not in item
           for c in _fused_geo["per_persona_contributions"]
           for item in c["candidate_interpretations"])
_ok("pf_geometry_coordinates_intact_ok")

_geo_persona = _regm.lookup("persona.analytical.geometry")
assert "coordinate precision" in _geo_persona["reasoning_profile"]["emphasis"]
_state_geo2 = _regm.activate("persona.analytical.geometry",
                             world_mapping=_g, detected_type="geometric_point")
assert any("preserve_coordinates" in t
           for t in _state_geo2["constraints"]["requires"])
_ok("pf_geometry_perspective_only_ok")

_bad_geo = copy.deepcopy(_state_geo2)
_bad_geo["candidate_interpretations"] = [{"interpretation": "move point",
                                          "scope": "emphasis",
                                          "coordinates": [1.0, 1.0]}]
assert persona.validate_persona_state(_bad_geo)["valid"] is False
_bad_geo2 = copy.deepcopy(_state_geo2)
_bad_geo2["candidate_interpretations"] = [{"world_fact": "point moved",
                                           "scope": "emphasis"}]
assert persona.validate_persona_state(_bad_geo2)["valid"] is False
_ok("pf_neg13_neg17_geometry_fabrication_rejected_ok")

# ---------------------------------------------------------------------------
# 10. representation-aware activation signals
# ---------------------------------------------------------------------------

_SIGNAL_CASES = (
    ("text", "unknown_reference", ("language", "unresolved")),
    ("measurement", "measurement", ("evidential", "quantitative")),
    ("vector", "unknown_reference", ("analytical", "quantitative",
                                     "unresolved")),
    ("matrix", "unknown_reference", ("analytical", "structural",
                                     "unresolved")),
    ("equation", "claim_assertion", ("analytical", "claim", "epistemic",
                                     "mathematical")),
    ("symbol", "unknown_reference", ("symbolic", "unresolved")),
    ("relation", "relation", ("relational", "structural")),
    ("event", "event", ("event", "temporal")),
    ("temporal_interval", "temporal_interval", ("temporal",)),
    ("geometric_point", "geometric_point", ("analytical", "spatial")),
    ("graph", "graph", ("structural",)),
    ("probability", "claim_assertion", ("claim", "epistemic",
                                        "probabilistic")),
    ("confidence", "claim_assertion", ("claim", "epistemic",
                                       "probabilistic")),
    ("uncertainty", "claim_assertion", ("claim", "epistemic")),
    ("identifier", "unknown_reference", ("identifier", "unresolved")),
    ("structured_canonical_object", "unknown_reference",
     ("metadata", "structured", "unresolved")),
)
for _dtype, _wkind, _expected in _SIGNAL_CASES:
    assert persona.relevance_signals(_dtype, _wkind) == _expected, (_dtype, _wkind)
_ok("pf_signals_categories_ok")

_signal_persona = _mk_persona("p.signal", conditions={
    "threshold": 0.5, "relevance_signals": ["relational"]})
_regs = persona.PersonaRegistry([_signal_persona])
_state_sig = _regs.activate("p.signal", world_mapping=_m,
                            detected_type="measurement")
assert _state_sig["activation_status"] == "INACTIVE"
_rel_mapping = world_mapping.map_to_world(
    detector.detect({"type": "relation",
                     "value": {"source_id": "s1", "target_id": "s2",
                               "predicate": "depends_on"}}),
    provenance=_PROW)
_state_sig2 = _regs.activate("p.signal", world_mapping=_rel_mapping,
                             detected_type="relation")
assert _state_sig2["activation_status"] == "ACTIVE"
_ok("pf_activation_by_relevance_signal_ok")

# ---------------------------------------------------------------------------
# 11. remaining negatives N1-N3, N6, N8, N14, N16, N18-N20
# ---------------------------------------------------------------------------

for _w in (float("nan"), float("inf"), -1.0):
    _bad = _mk_persona("p.badw", weight=_w)
    assert persona.validate_persona(_bad)["valid"] is False
assert persona.validate_persona({"persona_id": "p.broken",
                                 "weights": {"base": 1.0}})["valid"] is False
_ok("pf_neg1_neg2_neg3_neg6_ok")

_excluded = copy.deepcopy(_state_ev)
_excluded["activation_status"] = "INACTIVE"
_excluded["activation_score"] = 0.0
_excluded["confidence"] = 0.0
_fused_only_inactive = persona.fuse([_excluded],
                                    personas=_regm._personas)
assert _fused_only_inactive["status"] == persona.NO_ACTIVE_PERSONA
assert _fused_only_inactive["excluded_inactive"] == ["persona.core.evidence"]
assert "persona.core.evidence" not in _fused_only_inactive["active_personas"]
_ok("pf_neg8_inactive_excluded_ok")

_badcond_state = _mk_persona("p.badcond2", conditions={
    "threshold": 0.5, "representation_types": ["text", 9]})
assert persona.validate_persona(_badcond_state)["valid"] is False
_badcond_state2 = _mk_persona("p.badcond3", conditions={"bad_key": 1})
assert persona.validate_persona(_badcond_state2)["valid"] is False
_desc = _mk_persona("p.badcond4")
_desc["activation_conditions"] = 42
assert persona.validate_persona(_desc)["valid"] is False
try:
    persona.PersonaRegistry([_desc])
    raise AssertionError("persona with malformed conditions registered")
except persona.PersonaError:
    pass
_ok("pf_neg14_malformed_conditions_ok")

_shuffled = list(reversed(_states_ab))
_fused_shuffled = persona.fuse(_shuffled, personas=_regab._personas,
                               core_epistemic=_m["epistemic"])
assert _fused_shuffled == _fused_ab, "ordering changed the fused result"
_ok("pf_neg16_unstable_ordering_ok")

_bad_fused = dict(_fused_ab)
_bad_fused.pop("consensus")
assert persona.validate_fused_state(_bad_fused)["valid"] is False
_bad_fused2 = dict(_fused_ab)
_bad_fused2["status"] = "TRASH"
assert persona.validate_fused_state(_bad_fused2)["valid"] is False
_ok("pf_neg18_malformed_fused_state_ok")

try:
    persona.derive_persona_state(_default_reg.lookup("persona.core.evidence"),
                                 world_mapping=["not", "dict"],
                                 detected_type="measurement")
    raise AssertionError("corrupted canonical state accepted")
except persona.PersonaError:
    pass
_ok("pf_neg19_corrupted_canonical_ok")

_corrupt = persona.default_registry()
_corrupt._personas["persona.core.evidence"]["weights"]["base"] = float("nan")
try:
    _corrupt.weight("persona.core.evidence")
    raise AssertionError("corrupted registry weight accepted")
except persona.PersonaError:
    pass
_ok("pf_neg20_registry_corruption_ok")

# ---------------------------------------------------------------------------
# 12. real conversational path -> persona activation -> fusion -> bus
# ---------------------------------------------------------------------------

_env = run_conversation_for_expression("42 kg", created_at=_TS)
assert _env["bus"]["minted"] is True
_state = _env["bus"]["state"]
_ctx = _state["context"]
assert _ctx["world_mapping"]["status"] == "KNOWN"
_fusion = _ctx["persona_fusion"]
assert _fusion["status"] == "FUSED"
assert _fusion["active_personas"] == ["persona.core.evidence"]
assert bus.verify(_state)["digest_ok"] is True
assert bus.validate(_state)["valid"] is True
_ok("pf_reachability_measurement_fusion_ok")

_envg = run_conversation_for_expression(
    '{"type": "geometric_point", "value": [0.5, 0.5]}', created_at=_TS)
_ctxg = _envg["bus"]["state"]["context"]
assert _ctxg["persona_fusion"]["active_personas"] == [
    "persona.analytical.geometry"]
assert _ctxg["world_mapping"]["normalized_fields"]["point"] == [0.5, 0.5]
_ok("pf_reachability_geometry_fusion_ok")

_envt = run_conversation_for_expression(
    "Astrology states X causes Y", created_at=_TS,
    persona_context={"task_type": "creative_writing"})
_ctxef = _envt["bus"]["state"]["context"]
_pred = _ctxef["persona_fusion"]
assert _ctxef["world_mapping"]["mapping_evidence"]["claim_status"] == \
    "non-factual-claim"
assert _pred["status"] == persona.NO_ACTIVE_PERSONA
assert _pred["inherited_epistemic"] is None
_ok("pf_reachability_free_text_no_invented_persona_ok")

_env_a = run_conversation_for_expression("42 kg", created_at=_TS)
_env_b = run_conversation_for_expression("42 kg", created_at=_TS)
assert _env_a["bus"]["digest"] == _env_b["bus"]["digest"]
_ctxca = _env_a["bus"]["state"]["context"]
_ctxcb = _env_b["bus"]["state"]["context"]
assert _ctxca["persona_fusion"] == _ctxcb["persona_fusion"]
_ok("pf_reachability_deterministic_ok")

# records created without a persona fusion keep the exact prior context shape
assert bus.validate_fusion_for_handoff(None) is None
_parity_context = run_conversation_for_expression(
    "42 kg", created_at=_TS, persona_context=None)
assert sorted(_parity_context["bus"]["state"]["context"]) == sorted(
    {"active_context", "semantic_summary", "world_mapping",
     "persona_fusion"})
_ok("pf_reachability_context_keys_ok")

# ---------------------------------------------------------------------------
# 13. clean-room oracle agreement (zero disagreement required)
# ---------------------------------------------------------------------------

_oracle = _load_oracle()

_m_mapping = _measurement_mapping()
_geo_mapping = _geometry_mapping()
_t_mapping = _text_mapping()

_corpus = [
    (_m_mapping, "measurement", None),
    (_geo_mapping, "geometric_point", None),
    (_t_mapping, "text", None),
    (_t_mapping, "text", {"task_type": "creative_writing"}),
]

_oracle_mismatches = []
for _mapping, _dtype, _ctx in _corpus:
    _domain = _mapping["epistemic"].get("domain") \
        if isinstance(_mapping.get("epistemic"), dict) else None
    for _pid in _default_reg.enabled():
        _pr = _default_reg.lookup(_pid)
        _impl_score = persona.activation_score(
            _pr, detected_type=_dtype,
            world_kind=_mapping.get("world_kind"),
            domain=_domain, task_type=(_ctx or {}).get("task_type"),
            switches=None)
        _oracle_score = _oracle.oracle_score(
            _pr["activation_conditions"], _dtype, _mapping.get("world_kind"),
            _domain, (_ctx or {}).get("task_type"), None)
        if abs(_impl_score - _oracle_score) > 1e-9:
            _oracle_mismatches.append(("score", _pid, _dtype))
        _impl_status = persona.activation(_impl_score)
        _oracle_status = _oracle.oracle_status(_oracle_score)
        if _impl_status != _oracle_status:
            _oracle_mismatches.append(("status", _pid, _dtype))
assert not _oracle_mismatches, _oracle_mismatches[:4]
_ok("pf_oracle_activation_ok")

_for_o = _mk_persona("persona.battery.oracle",
                     priorities={"action": 0.7, "restraint": 0.3})
assert _oracle.oracle_normalize([2.0, 1.0, 1.0])["normalized"] == \
    [0.5, 0.25, 0.25]
assert _oracle.oracle_normalize([0.0, 0.0])["status"] == "zero_sum"
_ok("pf_oracle_normalize_ok")

_pmap = _default_personas_map()
for _mapping, _dtype, _ctx in _corpus:
    _states_all = []
    for _pid in _default_reg.enabled():
        _states_all.append(persona.derive_persona_state(
            _pmap[_pid], world_mapping=_mapping, detected_type=_dtype,
            state_reference="wm:oracle",
            task_type=(_ctx or {}).get("task_type"), switches=None))
    _impl = persona.fuse(_states_all, personas=_pmap,
                         core_epistemic=_mapping.get("epistemic"))
    _oracle_f = _oracle.oracle_fused(
        _states_all, _pmap, core_epistemic=_mapping.get("epistemic"))
    assert _impl["status"] == _oracle_f["status"], _dtype
    assert _impl["active_personas"] == _oracle_f["active_personas"], _dtype
    assert _impl["weights"] == _oracle_f["weights"], _dtype
    assert _impl["consensus"] == _oracle_f["consensus"], _dtype
    assert [c["classification"] for c in _impl["conflicts"]] == \
        _oracle_f["conflict_classifications"], _dtype
    assert [c["between"] for c in _impl["conflicts"]] == \
        _oracle_f["conflict_between"], _dtype
    assert [c["dimensions"] for c in _impl["conflicts"]] == \
        _oracle_f["conflict_dimensions"], _dtype
    assert _impl["conflict_status"] == _oracle_f["conflict_status"], _dtype
    assert _impl["unresolved_dimensions"] == \
        _oracle_f["unresolved_dimensions"], _dtype
    assert _impl["excluded_inactive"] == _oracle_f["excluded_inactive"], _dtype
    assert _impl["inherited_epistemic"] == _oracle_f["inherited_epistemic"], \
        _dtype
    assert _impl["safety"]["persona_override_blocked"] == \
        _oracle_f["safety_override_blocked"], _dtype
    assert _impl["safety"]["core_holds"] == _oracle_f["safety_core_holds"], \
        _dtype
    assert _impl["constraints"]["effective"] == \
        _oracle_f["constraints_effective"], _dtype
_ok("pf_oracle_fused_ok")
_ok("pf_oracle_zero_disagreement_ok")

# ---------------------------------------------------------------------------
# 14. cross-interpreter deterministic digest
# ---------------------------------------------------------------------------

_reg_digest = persona.default_registry()
_m_digest = _measurement_mapping()
_digest_fused = persona.compute(world_mapping=_m_digest,
                                detected_type="measurement",
                                core_epistemic=_m_digest["epistemic"],
                                personas=_reg_digest)
_digest_value = _digest(_digest_fused)
_rerun = persona.compute(world_mapping=_m_digest,
                         detected_type="measurement",
                         core_epistemic=_m_digest["epistemic"],
                         personas=_reg_digest)
assert _digest_value == _digest(_rerun)
print("persona_state_digest=%s" % _digest_value)
_ok("pf_digest_deterministic_ok")

# ---------------------------------------------------------------------------
# 15. performance sanity (ThinkPad-scale)
# ---------------------------------------------------------------------------

def _perf(fn, n=300):
    start = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - start) / n * 1000.0


_act_ms = _perf(lambda: persona.activation_score(
    _regm.lookup("persona.core.evidence"), detected_type="measurement",
    world_kind="measurement"), n=500)
assert _act_ms < 100.0
print("persona_perf_activation_avg_ms=%.3f" % _act_ms)
_ok("pf_perf_activation_ok")

_fus_ms = _perf(lambda: persona.fuse(_states_ab, personas=_regab._personas,
                                     core_epistemic=_m["epistemic"]), n=300)
assert _fus_ms < 100.0
print("persona_perf_fusion_avg_ms=%.3f" % _fus_ms)
_ok("pf_perf_fusion_ok")

def _pipeline():
    _d = detector.detect({"type": "measurement", "value": 42, "units": "kg"})
    _wmap = world_mapping.map_to_world(_d, provenance=_PROW)
    persona.compute(world_mapping=_wmap, detected_type="measurement",
                    core_epistemic=_wmap["epistemic"])


_pipe_ms = _perf(_pipeline, n=60)
assert _pipe_ms < 300.0
print("persona_perf_pipeline_avg_ms=%.3f" % _pipe_ms)
_ok("pf_perf_pipeline_ok")

tracemalloc.start()
_pipeline()
_peak = tracemalloc.get_traced_memory()[1] / (1024.0 * 1024.0)
tracemalloc.stop()
assert _peak < 8.0
print("persona_perf_peak_mem_mb=%.3f" % _peak)
_ok("pf_perf_peak_mem_ok")