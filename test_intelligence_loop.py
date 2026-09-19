"""Verification battery for the intelligence subsystem.

Checks that the 7-stage loop enforces architect ordering, that every math
value either comes from the verified surface or is a neutral fallback,
that persona fusion stays inside channel ceilings, that safety runs
before meaning/language, that evolution is architect-gated, and that the
whole package is deterministic (no RNG, clock, or GUI couplings).
"""
import sys
import os
import math as _m

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime import determinism
from maya_runtime import core
from maya_runtime.intelligence import (
    run,
    step,
    STAGES,
    ENCODER,
    STATE_ENGINE,
    PERSONA_FUSION,
    CONFIDENCE,
    RELEVANCE,
    SAFETY,
    MEANING,
    LANGUAGE,
    SAFETY_LOCKS,
    EVOLUTION,
    DEPLOYMENT,
    DEPLOYMENT_PROFILES,
    ANCHOR_VECTORS,
    INTELLIGENCE,
)
from maya_runtime.intelligence.feature_map import (
    FEATURE_MATH_MAP,
    PRIMITIVE_BINDINGS,
    apply_primitive,
    feature_key,
)
from maya_runtime.isolation.ceilings import WEB_PERSONA_ALLOWLIST

FALLBACK = dict(
    semantic={"coherence": 0.8, "salience": 0.6},
    emotional={"intensity": 0.4, "arousal": 0.5, "valence": 0.6},
    contextual={"urgency": 0.3, "impact": 0.4, "effort": 0.5},
    historical={"stability": [0.5, 0.51, 0.5, 0.505, 0.5]},
    render={"glow": 0.6, "depth": 0.5, "thickness": 2.0},
    reference=(0.5, 0.5, 0.5),
    metrics={"cpu_percent": 10, "memory_percent": 20,
             "process_count": 1, "launches": 0},
    now="2026-09-09T00:00:00Z",
    sequence=1,
    environment="local",
)

# ---- invariant helpers -------------------------------------------------

def _ok(label):
    print(label + "=OK")


def _assert(condition, label, detail=""):
    assert condition, "%s: %s" % (label, detail)


# ---- 1. determinism ----------------------------------------------------

_module_names = [
    "maya_runtime.intelligence",
    "maya_runtime.intelligence.encoder",
    "maya_runtime.intelligence.state",
    "maya_runtime.intelligence.fusion",
    "maya_runtime.intelligence.confidence",
    "maya_runtime.intelligence.relevance",
    "maya_runtime.intelligence.safety",
    "maya_runtime.intelligence.meaning",
    "maya_runtime.intelligence.language",
    "maya_runtime.intelligence.reports",
    "maya_runtime.intelligence.anchors",
    "maya_runtime.intelligence.locks",
    "maya_runtime.intelligence.evolution",
    "maya_runtime.intelligence.profiles",
    "maya_runtime.intelligence.loop",
    "maya_runtime.intelligence.feature_map",
]
import importlib

for _mn in _module_names:
    _mod = importlib.import_module(_mn)
omp_api = ("random", "time", "tkinter", "datetime", "subprocess", "socket")
for _mn in _module_names:
    _mod = importlib.import_module(_mn)
    for _banned in omp_api:
        _assert(not hasattr(_mod, _banned),
                "intelligence_free_of_" + _banned, _mn)
_ok("intelligence_package_free_of_rng_clock_gui")

_det = determinism.report()
_assert(all(_det.values()), "determinism_report_all_green", str(_det))
_ok("determinism_report")

r1 = run(**dict(FALLBACK))
r2 = run(**dict(FALLBACK))
_assert(r1["result"]["meaning"] == r2["result"]["meaning"],
        "loop_deterministic_identical_frames")
_ok("loop_deterministic")

# ---- 2. feature-to-math mapping table ---------------------------------

_assert(FEATURE_MATH_MAP["render"]["glow"]["primitive"] == "glow01",
        "map_render_glow_glow01")
_assert(FEATURE_MATH_MAP["render"]["depth"]["primitive"] == "depth01",
        "map_render_depth_depth01")
_assert(FEATURE_MATH_MAP["render"]["thickness"]["primitive"] == "thickness01",
        "map_render_thickness_thickness01")
_assert(FEATURE_MATH_MAP["contextual"]["urgency"]["primitive"] == "task_fuse",
        "map_context_urgency_task_fuse")
_assert(feature_key("semantic", "topic_vector").startswith("semantic"),
        "map_key_semantic")
for _cat, _feats in FEATURE_MATH_MAP.items():
    for _name, _spec in _feats.items():
        _assert(_spec["primitive"] in PRIMITIVE_BINDINGS,
                "map_primitive_bound", "%s.%s -> %s" % (_cat, _name,
                                                        _spec["primitive"]))
_ok("feature_to_math_mapping_table")

_encoded = ENCODER.encode(
    semantic={"coherence": 0.8},
    historical={"stability": [0.5, 0.51, 0.5]},
    render={"glow": 0.6, "depth": 0.5, "thickness": 2.0},
    reference=(0.5, 0.5, 0.5),
)
_assert(_encoded["governing"]["render.glow"] == "glow01",
        "encoder_governing_trace")
_flags = _encoded["flags"]
for _k, _v in _encoded["scalars"].items():
    _assert(0.0 <= _v <= 1.0, "encoder_scalar_domain", _k)

try:
    ENCODER.encode(semantic={"not_a_feature": 0.5}, reference=(0.5,))
    _assert(False, "encoder_unknown_feature_rejected")
except ValueError:
    pass
_ok("feature_encoder")

# ---- 3. verified primitives -------------------------------------------

_assert(core.cosine_similarity((0.4, 0.2), (0.8, 0.4)) > 0.99,
        "primitive_cosine_identity_near_one")
_assert(apply_primitive(PRIMITIVE_BINDINGS["glow01"], 0.5) ==
        core.glow01(0.5), "primitive_glow01_direct_call")
_assert(core.clamp01(float("nan")) == 0.0, "primitive_nan_neutral")
_assert(apply_primitive(PRIMITIVE_BINDINGS["world_index"], 5, ceiling=10) ==
        0.5, "primitive_world_index_formula")
_assert(apply_primitive(PRIMITIVE_BINDINGS["world_index"], float("nan"),
                        ceiling=10) == 0.0, "primitive_world_index_nan_neutral")
_assert(apply_primitive(PRIMITIVE_BINDINGS["glow01"], float("nan")) ==
        core.glow01(float("nan")),
        "primitive_glow01_preserves_fail_degraded_path")
_assert(apply_primitive(PRIMITIVE_BINDINGS["thickness01"], float("nan")) ==
        core.thickness01(float("nan")),
        "primitive_thickness01_preserves_fail_degraded_path")
_assert(apply_primitive(PRIMITIVE_BINDINGS["world_stability"],
                        None, series=[0.5, 0.5, 0.5])["std"] == 0.0,
        "primitive_stability_zero_std")
_ok("verified_primitives")

# ---- 4. state engine ---------------------------------------------------

_state = STATE_ENGINE.compute(
    _encoded, world_series=[0.5, 0.51, 0.5, 0.505, 0.5],
    reference=(0.5, 0.5, 0.5),
    metrics={"cpu_percent": 10, "memory_percent": 20,
             "process_count": 1, "launches": 0},
)
for _comp in ("emotional_intensity", "cognitive_clarity", "stability",
              "drift", "alignment"):
    _assert(0.0 <= _state[_comp] <= 1.0, "state_component_domain", _comp)
_assert(_state["stability"] > 0.5, "state_stability_high_for_stable_series")
_assert(_state["std"] is not None and _state["std"] < 0.05,
        "state_std_within_tolerance", str(_state.get("std")))
_assert(_state["ok"], "state_ok_for_safe_frame")
_ok("state_engine")

# ---- 5. persona fusion -------------------------------------------------

_fusion = PERSONA_FUSION.compute(_encoded, state=_state,
                                 context_vector=(0.5, 0.5, 0.5))
_wtotal = sum(_fusion["weights"].values())
_assert(_m.isclose(_wtotal, 1.0), "fusion_weights_normalized",
        str(_wtotal))
_assert(set(_fusion["weights"]) == set(WEB_PERSONA_ALLOWLIST),
        "fusion_weights_cover_web_personas")
for _ch, _v in _fusion["channels"].items():
    _assert(0.0 <= _v <= float(core.CHANNEL_MAX[_ch]),
            "fusion_channel_within_ceiling", "%s=%s" % (_ch, _v))
_assert(_fusion["dominant"] in WEB_PERSONA_ALLOWLIST,
        "fusion_dominant_in_allowlist", str(_fusion["dominant"]))
_ok("persona_fusion")

# ---- 6. world-model confidence and restriction -------------------------

_high = CONFIDENCE.score(state=_state, evidence_ok=True)
_assert(0.0 <= _high["confidence"] <= 1.0, "confidence_domain")
_low = CONFIDENCE.score(state={"stability": 0.05, "alignment": 0.05},
                        evidence_ok=False)
_assert(_low["restricted"], "confidence_restricted_below_floor")
_assert(CONFIDENCE.restrict(confidence=_low["confidence"], scalar=0.9) == 0.0,
        "confidence_restriction_neutral_on_low")
_ok("world_confidence")

# ---- 7. relevance / alignment -----------------------------------------

_rel = RELEVANCE.evaluate(fused_channels=_fusion["channels"], state=_state)
_assert(_rel["alignment"] <= 1.0 and _rel["alignment"] >= 0.0,
        "relevance_alignment_domain")
_assert(isinstance(_rel["ok"], bool), "relevance_ok_bool")
_ok("relevance_alignment")

# ---- 8. safety enforcement --------------------------------------------

_safe = SAFETY.enforce(encoded=_encoded, state=_state, fusion=_fusion)
_assert(_safe["ok"], "safety_ok_for_safe_frame")
for _ch, _v in _safe["channels"].items():
    _assert(0.0 <= _v <= float(core.CHANNEL_MAX[_ch]),
            "safety_channel_within_ceiling", "%s=%s" % (_ch, _v))
_safe_bad = SAFETY.enforce(
    encoded=None, state={"drift": 0.9, "ok": False}, fusion=_fusion,
    series=[0.1, 0.5, 0.9, 0.2, 0.8])
_assert(not _safe_bad["ok"], "safety_denies_drift_frame")
_assert(any(v["rule"] == "drift_beyond_tolerance"
            for v in _safe_bad["violations"]),
        "safety_drift_violation_recorded")
_ok("safety_enforcement")

# ---- 9. meaning requires prereq stages --------------------------------

try:
    MEANING.compute(state=None, fusion=None, alignment=None, safety=None)
    _assert(False, "meaning_requires_prerequisites")
except RuntimeError:
    pass
_meaning = MEANING.compute(
    state=_state, fusion=_fusion, alignment=_rel, safety=_safe)
_assert(len(_meaning["meaning_vector"]) == 3, "meaning_vector_dimension")
_assert(_meaning["ok"], "meaning_ok_for_safe_frame")
_ok("meaning_stabilized")

# ---- 10. language from meaning only -----------------------------------

_lang = LANGUAGE.generate(_meaning)
_assert(_lang["text"] and isinstance(_lang["text"], str),
        "language_text_present")
_assert(_lang["meaning_sha"].startswith("m-"),
        "language_meaning_fingerprint")
_assert(_lang["tone"] in ("reserved", "measured"),
        "language_tone_enum")
_ok("language_from_meaning")

# ---- 11. full 7-stage loop --------------------------------------------

_ctx = run(**dict(FALLBACK))
for _stage in STAGES:
    _assert(_stage in _ctx["trace"], "loop_stage_runs", _stage)
_assert(_ctx["result"]["meaning"]["ok"], "loop_result_ok")
_assert(bool(_ctx["result"]["language"]["text"]), "loop_language_ok")
_assert(not _ctx["reflect"]["evolved"], "loop_reflection_never_applies")
_assert(set(_ctx["log"]) == {"decision", "evidence", "stability"},
        "loop_reports_present")
_ok("seven_stage_loop")

# ordering: skipping a stage must raise before it runs
_ctx_skip = {}
try:
    INTELLIGENCE.step("interpret", _ctx_skip)
    _assert(False, "ordering_interpret_without_sense")
except RuntimeError:
    pass

_ctx_a = {}
try:
    INTELLIGENCE.step("express", _ctx_a)
    _assert(False, "ordering_express_without_decide")
except RuntimeError:
    pass

_ctx_b = {}
try:
    INTELLIGENCE.step("log", _ctx_b)
    _assert(False, "ordering_log_without_express")
except RuntimeError:
    pass
_ok("loop_stage_ordering_enforced")

# ---- 12. identity anchors ---------------------------------------------

for _pers in WEB_PERSONA_ALLOWLIST:
    _vec = ANCHOR_VECTORS[_pers]
    _assert(len(_vec) == 3, "anchor_vector_dimension", _pers)
    for _v in _vec:
        _assert(0.0 <= _v <= 1.0, "anchor_vector_bounded", _pers)
_ok("identity_anchors")

# ---- 13. safety locks + architect-gated evolution ----------------------

_denied = SAFETY_LOCKS.verify_modify("math", None, change={"x": 1})
_assert(not _denied["allowed"], "locks_deny_without_architect")
_allowed = SAFETY_LOCKS.verify_modify("identity", "architect approves",
                                      change={})
_assert(_allowed["allowed"], "locks_allow_with_architect_instruction")
try:
    SAFETY_LOCKS.verify_modify("unknown_surface", "architect approves")
    _assert(False, "locks_unknown_surface_rejected")
except ValueError:
    pass

_ledger = []
e1 = EVOLUTION.record("math", {"algo": "exact"}, architect_instruction=None)
_assert(not e1["allowed"], "evolution_denies_autonomous")
e2 = EVOLUTION.record("personas", {"weight": 0.5},
                      architect_instruction="update per policy",
                      sequence=1, now="2026-09-09T00:00:00Z")
_assert(e2["allowed"], "evolution_allows_architect")
EVOLUTION.append(e2, _ledger)
_assert(len(_ledger) == 1 and _ledger[0]["role"] == "architect",
        "evolution_ledger_appends_allowed")
_prop = EVOLUTION.propose("identity", {"anchors": "static"})
_assert(not _prop["allowed"], "evolution_proposals_never_apply")
_ok("safety_locks_and_evolution")

# ---- 14. deployment profiles ------------------------------------------

for _env in DEPLOYMENT_PROFILES:
    _prof = DEPLOYMENT.select(_env)
    _assert(_prof["environment"] == _env, "profile_env_match", _env)
    _assert(_prof["version"], "profile_versioned", _env)
    _assert(isinstance(_prof["personas"], list) and _prof["personas"],
            "profile_personas", _env)
    _assert(_prof["confidence_floor"] > 0.0, "profile_confidence_floor",
            _env)
_ver = DEPLOYMENT.verify_channel_limits(
    {"expression": 0.2, "viseme": 0.1}, "embed")
_assert(_ver["ok"], "profile_verify_channels_ok")
_ver_bad = DEPLOYMENT.verify_channel_limits(
    {"micro": 0.005}, "kiosk")
_assert(not _ver_bad["ok"], "profile_verify_channels_denied")
try:
    DEPLOYMENT.select("not_an_env")
    _assert(False, "profile_unknown_env_rejected")
except ValueError:
    pass
_ok("deployment_profiles")

# ---- 15. reports -------------------------------------------------------

_dec = _ctx["log"]["decision"]
_assert("pattern_alignment" in _dec, "report_decision_alignment")
_assert(_dec["persona_fusion"]["dominant"] in WEB_PERSONA_ALLOWLIST,
        "report_decision_dominant")
_en_glow = _ctx["interpret"]["encoded"]["scalars"]["glow"]
_assert(_dec["render"]["glow01"] == _en_glow,
        "report_decision_render_glow_matches_encoded")
_evi = _ctx["log"]["evidence"]
_assert(_evi["stage"] == "interpret", "report_evidence_stage")
_stab = _ctx["log"]["stability"]
_assert(_stab["stage"] == "stabilize", "report_stability_stage")
_ok("decision_evidence_stability_reports")

print("test_intelligence_loop=PASS")