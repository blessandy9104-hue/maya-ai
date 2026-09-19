"""Batch 8I generalization battery.

Progressively grows across phases: task representation (P2), similarity and
difference (P3), generalization hypotheses (P4), unseen-case testing (P5),
transfer boundaries (P6), error generalization (P8), method portfolio (P9),
adaptive routing (P10), learning metrics (P11), controlled self-improvement
(P12), cooperative challenge (P13), resource-aware transfer (P14).
"""
from __future__ import annotations
import os, sys, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LABELS = {"ok": 0}


def _assert(cond, label):
    if cond:
        LABELS["ok"] += 1
        print(label + "=OK")
    else:
        print(label + "=FAIL")


import maya_conversation
from maya_conversation.generalize import characterize_task, to_key, TaskMemory

# --------------------------------------------------------------------------
# PHASE 2 — task / problem representation
# --------------------------------------------------------------------------

_MATH_TURN = {
    "ok": True,
    "plan": {
        "objective": "calculate", "holds": [], "deterministic_allowed": True,
    },
    "routes": {"domains": ["math"], "plain": False},
    "interpretation": {
        "primary_intent": "compute",
        "constraints": ["integer units", "range 1..100"],
        "references": [{"antecedent": "the rectangle"}],
        "ambiguous": False, "is_correction": False, "modality": "text",
        "claims": [{"epistemic_status": "CALCULATED"}],
    },
}
_PSYCH_TURN = {
    "ok": True,
    "plan": {"objective": "answer", "holds": ["diagnosis_out_of_scope"]},
    "routes": {"domains": ["psychology"], "plain": False},
    "interpretation": {
        "primary_intent": "explain", "constraints": [],
        "references": [], "ambiguous": True, "is_correction": False,
        "modality": "text",
        "claims": [{"epistemic_status": "REPORTED"}],
    },
}

_char_math = characterize_task(_MATH_TURN, "what is the diagonal of a 3 by 4 rectangle?", resource_pressure=True)
_char_psy = characterize_task(_PSYCH_TURN, "i feel anxious lately", resource_pressure=False)

_assert(_char_math["domains"] == ["math"], "gen2_char_math_domains")
_assert(_char_math["primary_intent"] == "compute", "gen2_char_intent")
_assert(_char_math["objective"] == "calculate", "gen2_char_objective")
_assert(_char_math["constraints"] == ["integer units", "range 1..100"],
        "gen2_char_constraints_sorted")
_assert(_char_math["math_structure"] is True, "gen2_char_math_structure")
_assert(_char_math["evidence_types"] == ["CALCULATED"],
        "gen2_char_evidence")
_assert(_char_math["consequence_level"] == "ordinary",
        "gen2_char_consequence_ordinary")
_assert(_char_math["resource_level"] == "pressure",
        "gen2_char_resource_pressure")
_assert(_char_math["input_brief"] is False, "gen2_char_input_not_brief")

_assert(_char_psy["consequence_level"] == "elevated_guard",
        "gen2_char_consequence_elevated")
_assert(_char_psy["ambiguous"] is True, "gen2_char_ambiguous")
_assert(_char_psy["references_resolved"] == 0, "gen2_char_refs_zero")
_assert(_char_psy["resource_level"] == "safe", "gen2_char_resource_safe")

_char_none = characterize_task(None)
_assert(_char_none["primary_intent"] == "unspecified",
        "gen2_char_default_intent")
_assert(_char_none["objective"] == "answer", "gen2_char_default_objective")
_assert(_char_none["domains"] == [] and _char_none["math_structure"] is False,
        "gen2_char_malformed_neutral")

_key1 = to_key(_char_math)
_key_again = to_key(characterize_task(
    _MATH_TURN, "what is the diagonal of a 3 by 4 rectangle?",
    resource_pressure=True))
_key_other = to_key(characterize_task(
    _MATH_TURN, "what is the diagonal of a 5 by 12 rectangle?",
    resource_pressure=True))
_assert(_key1 == _key_again, "gen2_key_deterministic")
_assert(_key1 != _key_other, "gen2_key_distinguishes_difference")

_memory = TaskMemory()
_assert(not _memory.seen(_char_math), "gen2_memory_new_first")
_memory.remember(_char_math)
_assert(_memory.seen(_char_math), "gen2_memory_seen_after_remember")
_assert(_memory.occurrences(_char_math) == 1, "gen2_memory_count_one")
_memory.remember(characterize_task(
    _MATH_TURN, "what is the diagonal of a 3 by 4 rectangle?",
    resource_pressure=True))
_assert(_memory.occurrences(_char_math) == 2, "gen2_memory_count_two")
_memory.remember(_char_psy)
_memories = _memory.memories()
_assert(len(_memories) == 2, "gen2_memory_distinct_tasks")
_assert(_memories[0][0] == _key1, "gen2_memory_deterministic_order")
_assert(_memory.counts()["total_sightings"] == 3, "gen2_memory_counts")

_gen_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "maya_conversation", "generalize.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _gen_src,
            "gen2_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "characterize_task"),
        "gen2_pkg_has_characterize")
_assert(hasattr(maya_conversation, "TaskMemory"),
        "gen2_pkg_has_memory")

# --------------------------------------------------------------------------
# PHASE 3 — similarity and difference
# --------------------------------------------------------------------------

from maya_conversation.generalize import task_similarity, SEVERITY_ELEVATED

_sm_self = task_similarity(_char_math, _char_math)
_assert(_sm_self["score"] == 1.0, "gen3_sim_identical_same")
_assert(_sm_self["differences"] == [], "gen3_sim_identical_no_differences")

_sm_diff = task_similarity(_char_math, _char_psy)
_assert(_sm_diff["score"] < 0.6, "gen3_sim_different_domain_low")
_assert(len(_sm_diff["differences"]) > 0, "gen3_sim_has_differences")

_cons_diffs = [d for d in _sm_diff["differences"]
               if d["feature"] == "consequence_level"]
_assert(len(_cons_diffs) == 1, "gen3_sim_consequence_diff_found")
_assert(_cons_diffs[0]["severity"] == SEVERITY_ELEVATED,
        "gen3_sim_consequence_elevated")

_domains_diffs = [d for d in _sm_diff["differences"]
                  if d["feature"] == "domains"]
_assert(len(_domains_diffs) == 1, "gen3_sim_domain_diff_found")

_assert(len(_sm_diff["transfer_hints"]) > 0, "gen3_sim_transfer_hints")
_hint_text = " ".join(_sm_diff["transfer_hints"])
_assert("domains" in _hint_text or "consequence" in _hint_text,
        "gen3_sim_transfer_hint_mentions_domains_or_consequence")
_assert(isinstance(_sm_diff["per_feature"], dict)
        and "domains" in _sm_diff["per_feature"],
        "gen3_sim_per_feature_keys")

_sm_partial = task_similarity(
    characterize_task(_MATH_TURN, "task A"),
    characterize_task(_MATH_TURN, "task A, new context"))
_assert(0.7 <= _sm_partial["score"] <= 1.0,
        "gen3_sim_partial_same_domain_high")

_sm_none = task_similarity(None, None)
_assert(_sm_none["score"] == 1.0, "gen3_sim_malformed_symmetric")

_sm_one_none = task_similarity(_char_math, None)
_assert(0.0 <= _sm_one_none["score"] < 0.8,
        "gen3_sim_asymmetric_none_low")

_assert(hasattr(maya_conversation, "task_similarity"),
        "gen3_pkg_has_task_similarity")

# --------------------------------------------------------------------------
# PHASE 4 — generalization hypotheses
# --------------------------------------------------------------------------

from maya_conversation.hypothesis import (
    GeneralizationHypothesis, hypothesis_from_experience,
    ST_UNTESTED, ST_TESTED, ST_PROMOTED, ST_REJECTED, ST_ROLLED_BACK,
)

_hyp = hypothesis_from_experience(
    method="pythagorean_diagonal",
    source_experience="diagonal of 3x4 rectangle succeeded",
    assumptions=["integer side lengths", "euclidean plane"],
    conditions={"domains": ["math"], "math_structure": True},
)
_assert(_hyp.status == ST_UNTESTED, "gen4_hyp_untested_default")
_assert(_hyp.method == "pythagorean_diagonal", "gen4_hyp_method_stored")
_assert(sorted(_hyp.assumptions) == ["euclidean plane", "integer side lengths"],
        "gen4_hyp_assumptions_sorted")
_assert(_hyp.conditions == {"domains": ["math"], "math_structure": True},
        "gen4_hyp_conditions_stored")
_assert(_hyp.uncertainty == 0.5, "gen4_hyp_default_uncertainty")

_c1 = _hyp.record_case("unseen_diag_5_12", "correct", True)
_assert(_c1["ok"] is True, "gen4_hyp_case_recorded")
_assert(_hyp.status == ST_TESTED, "gen4_hyp_tested_after_case")
_assert(_hyp.snapshot()["evidence_count"] == 1,
        "gen4_hyp_snapshot_evidence")

_c1b = _hyp.record_case("unseen_diag_5_12", "correct", True, note="again")
_assert(len(_hyp.cases) == 1, "gen4_hyp_duplicate_case_updates")
_assert(_hyp.cases[0]["note"] == "again", "gen4_hyp_duplicate_updates_note")

_hyp2 = hypothesis_from_experience("m", "s")
_hyp2.record_case("a", "ok", True)
_hyp2.record_case("b", "ok", True)
_hyp2.update_uncertainty()
_assert(_hyp2.uncertainty < 0.35, "gen4_hyp_low_uncertainty_success")
_assert(_hyp2.promote() is True, "gen4_hyp_promote_after_good_evidence")
_assert(_hyp2.status == ST_PROMOTED, "gen4_hyp_promote_status")

_hyp3 = hypothesis_from_experience("m", "s")
_hyp3.record_case("a", "fail", False)
_hyp3.record_case("b", "ok", True)
_hyp3.update_uncertainty()
_assert(_hyp3.uncertainty > 0.35, "gen4_hyp_high_uncertainty_mixed")
_assert(_hyp3.promote() is False, "gen4_hyp_promote_blocked")
_assert(_hyp3.reject("different scale") == ST_REJECTED,
        "gen4_hyp_reject")
_assert("different scale" in _hyp3.snapshot()["failure_boundaries"],
        "gen4_hyp_reject_records_boundary")

_hyp4 = hypothesis_from_experience("m", "s")
_hyp4.record_case("a", "ok", True)
_hyp4.record_case("b", "ok", True)
_hyp4.promote()
_hyp4.rollback("unit mismatch")
_assert(_hyp4.status == ST_ROLLED_BACK, "gen4_hyp_rollback")
_assert("unit mismatch" in _hyp4.snapshot()["failure_boundaries"],
        "gen4_hyp_rollback_records_boundary")

_hyp5 = hypothesis_from_experience("m", "s")
_hyp5.record_case("a", "ok", True)
_hyp5.weaken("new constraints appeared")
_assert(_hyp5.status == "weakened", "gen4_hyp_weaken_status")
_assert("new constraints appeared" in _hyp5.snapshot()["failure_boundaries"],
        "gen4_hyp_weaken_records_boundary")

_gen4 = task_similarity(_char_math, _char_math)
_assert(_gen4["score"] == 1.0, "gen4_controls_still_deterministic")

_hyp_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "maya_conversation", "hypothesis.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _hyp_src,
            "gen4_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "GeneralizationHypothesis"),
        "gen4_pkg_has_hypothesis")

# --------------------------------------------------------------------------
# PHASE 5 — unseen-case testing (KNOWN -> LEARN -> GENERALIZE -> NEW -> TEST)
# --------------------------------------------------------------------------

from maya_conversation.unseen_testing import (
    classify_unseen, run_unseen_trial, trial_measures, accuracy_vs_baseline,
)
from maya_conversation.generalize import TaskMemory as _Gen5Memory
from maya_conversation.hypothesis import hypothesis_from_experience as _G5Hyp

_known_1 = characterize_task(_MATH_TURN, "diagonal of a 3 by 4 rectangle")
_known_2 = characterize_task(_MATH_TURN, "diagonal of a 6 by 8 rectangle")
_new_1 = characterize_task(_MATH_TURN, "diagonal of a 5 by 12 rectangle")
_new_2 = characterize_task(_MATH_TURN, "diagonal of a 9 by 40 rectangle")
_new_3 = characterize_task(_MATH_TURN, "leg of a 7 24 25 right triangle",
                           resource_pressure=False)

_mem5 = _Gen5Memory()
_mem5.remember(_known_1)
_mem5.remember(_known_2)
_hyp5 = hypothesis_from_experience(
    "pythagorean_diagonal", "two right triangles in math domain succeeded",
    conditions={"domains": ["math"], "math_structure": True})

_assert(classify_unseen(_mem5, _new_1)["unseen"] is True,
        "gen5_unseen_new_case")
_assert(classify_unseen(_mem5, _known_1)["unseen"] is False,
        "gen5_seen_case_detected")
_assert(to_key(_new_1) != to_key(_known_1), "gen5_new_not_equal_known")
_assert(to_key(_new_2) != to_key(_new_1), "gen5_new_cases_distinct")


def _pythag_method(fp):
    ok = bool(fp.get("math_structure"))
    guard = any("no_pythagoras" in (c or "").lower()
                for c in (fp.get("constraints") or []))
    return {
        "ok": ok and not guard,
        "latency_steps": 3,
        "resource_cost": 2.0,
        "output": {"diagonal": 5.0, "unit": "units"},
        "unexpected": guard,
    }


_t1 = run_unseen_trial(_mem5, _hyp5, _new_1, _pythag_method)
_assert(_t1["unseen"] is True, "gen5_trial_first_unseen")
_assert(_t1["ok"] is True, "gen5_trial_success_on_new")
_assert(_t1["latency_steps"] == 3, "gen5_trial_latency_recorded")
_assert(_t1["resource_cost"] == 2.0, "gen5_trial_cost_recorded")

_t2 = run_unseen_trial(_mem5, _hyp5, _new_2, _pythag_method)
_new_guard = {
    "domains": ["math"], "primary_intent": "compute", "objective": "calculate",
    "constraints": ["no_pythagoras"], "references_resolved": 0,
    "ambiguous": False, "is_correction": False, "modality": "text",
    "math_structure": True, "evidence_types": ["CALCULATED"],
    "consequence_level": "ordinary", "resource_level": "safe",
    "text_signature": "hypotenuse with no-pythagoras constraint",
    "input_brief": False,
}
_t3 = run_unseen_trial(_mem5, _hyp5, _new_guard, _pythag_method)
_assert(_t3["unexpected"] is True, "gen5_trial_unexpected_violation")
_assert(_t3["ok"] is False, "gen5_trial_guard_blocks_method")

_seen_trial = run_unseen_trial(_mem5, _hyp5, _known_1, _pythag_method)
_assert(_seen_trial["unseen"] is False, "gen5_seen_trial_flagged")
_assert(_seen_trial["was_seen"] is True, "gen5_was_seen_flag")

_measures = trial_measures([_t1, _t2, _t3])
_assert(_measures["total_trials"] == 3, "gen5_measures_total")
_assert(_measures["success_rate"] == 2 / 3, "gen5_measures_success_rate")
_assert(_measures["mean_latency_steps"] == 3, "gen5_measures_latency")
_assert(_measures["mean_resource_cost"] == 2.0, "gen5_measures_cost")
_assert(_measures["unexpected_count"] == 1, "gen5_measures_unexpected")

_acc = accuracy_vs_baseline([_t1, _t2, _t3], [True, True, False])
_assert(_acc == 1.0, "gen5_accuracy_vs_independent")

_hyp5.update_uncertainty()
_assert(_hyp5.snapshot()["evidence_count"] == 4, "gen5_hypothesis_gained_evidence")
_assert(_hyp5.uncertainty < 0.5, "gen5_hypothesis_evidence_reduces_uncertainty")

_assert(len(_hyp5.cases) == 4, "gen5_cases_recorded_total")
_memories5 = _mem5.memories()
_assert(len(_memories5) == 2, "gen5_memory_unchanged_by_trials")

_src5 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "maya_conversation", "unseen_testing.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src5,
            "gen5_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "run_unseen_trial"),
        "gen5_pkg_has_unseen")
_assert(hasattr(maya_conversation, "trial_measures"),
        "gen5_pkg_has_measures")

# --------------------------------------------------------------------------
# PHASE 6 — transfer boundaries
# --------------------------------------------------------------------------

from maya_conversation.generalize import transfer_boundary_check as _tbc
from maya_conversation.hypothesis import hypothesis_from_experience as _G6Hyp

_hyp6 = _G6Hyp(
    "pythagorean_diagonal", "math right triangles succeeded",
    conditions={"domains": ["math"], "math_structure": True},
    exclusions={"resource_level": "pressure"},
)

_in_scope = _tbc(_hyp6, _char_math)
_assert(_in_scope["within_scope"] is False, "gen6_out_scope_exclusion_fired")
_assert(_in_scope["applicable"] is True, "gen6_applicable_conditions_met")
_assert(any("resource_level" in r for r in _in_scope["reasons"]),
        "gen6_reason_mentions_exclusion")

_char_math_safe = characterize_task(
    _MATH_TURN, "diagonal 3x4", resource_pressure=False)
_in_scope_safe = _tbc(_hyp6, _char_math_safe)
_assert(_in_scope_safe["within_scope"] is True, "gen6_in_scope_same_domain")
_assert(_in_scope_safe["applicable"] is True, "gen6_applicable_no_exclusion")
_assert(_in_scope_safe["reasons"] == [], "gen6_no_reasons_when_safe")

_out_domain = _tbc(_hyp6, _char_psy)
_assert(_out_domain["within_scope"] is False, "gen6_out_scope_different_domain")
_assert(_out_domain["applicable"] is False, "gen6_not_applicable_domain_mismatch")
_assert(any("domains" in r for r in _out_domain["reasons"]),
        "gen6_reason_mentions_domain")

_hyp6_multi = _G6Hyp(
    "multi_guard", "test",
    conditions={"domains": ["math"], "math_structure": True},
    exclusions={"resource_level": "pressure",
                "consequence_level": "elevated_guard"},
)
_char_both_bad = characterize_task(
    _PSYCH_TURN, "pressure with guard", resource_pressure=True)
_out_multi = _tbc(_hyp6_multi, _char_both_bad)
_assert(_out_multi["within_scope"] is False, "gen6_multi_exclusion_reasons")
_assert(len(_out_multi["reasons"]) >= 2, "gen6_multi_reasons_count")

_none_hyp = _tbc(None, _char_math)
_assert(_none_hyp["within_scope"] is False, "gen6_none_hypothesis")
_assert(_none_hyp["applicable"] is False, "gen6_none_hyp_not_applicable")

_none_fp = _tbc(_hyp6, None)
_assert(_none_fp["within_scope"] is False, "gen6_none_fingerprint")

_dict_hyp = _tbc({"conditions": {"domains": ["math"]},
                  "exclusions": {"resource_level": "pressure"}},
                 _char_math_safe)
_assert(_dict_hyp["within_scope"] is True, "gen6_dict_hypothesis_works")

_src6 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "maya_conversation", "generalize.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src6,
            "gen6_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "transfer_boundary_check"),
        "gen6_pkg_has_boundary")

# --------------------------------------------------------------------------
# PHASE 8 — error generalization
# --------------------------------------------------------------------------

from maya_conversation.error_generalize import ErrorMemory

_emem = ErrorMemory(min_occurrences=2)
_assert(_emem.occurrences("missing_units") == 0, "gen8_no_failures_yet")
_assert(_emem.learned_for("missing_units") is False,
        "gen8_not_learned_from_zero")

_ef1 = _emem.record(
    "missing_units", "result has no unit label",
    "attach explicit unit when unit context present",
    domains=["math"], resource_level="safe")
_assert(_ef1["cause_key"] == "missing_units", "gen8_failure_recorded")
_assert(_ef1["domains"] == ["math"], "gen8_failure_domains")
_assert(_emem.occurrences("missing_units") == 1, "gen8_one_occurrence")
_assert(_emem.learned_for("missing_units") is False,
        "gen8_single_failure_not_learned")

_emem.record("missing_units", "same unit gap again",
             "attach explicit unit", domains=["math"],
             resource_level="safe")
_assert(_emem.learned_for("missing_units") is True,
        "gen8_second_failure_learned")
_assert(_emem.avoid(characterize_task(
    _MATH_TURN, "area of a field", resource_pressure=False),
    "missing_units") is True, "gen8_avoid_similar_unseen")
_assert(_emem.avoid(characterize_task(
    _PSYCH_TURN, "i feel anxious lately", resource_pressure=False),
    "missing_units") is False, "gen8_no_avoid_other_domain")

_emem.record("numeration_error", "wrong decimal placement",
             "recompute with explicit precision", domains=["math"])
_assert(_emem.stats()["total_failures"] == 3, "gen8_stats_total")
_assert(_emem.stats()["cause_count"] == 2, "gen8_stats_causes")
_assert(_emem.stats()["learned_causes"] == 1, "gen8_stats_learned")

_avoid = _emem.avoid(characterize_task(
    _MATH_TURN, "perimeter of a garden", resource_pressure=False),
    "numeration_error")
_assert(_avoid is False, "gen8_single_other_failure_not_avoided")

_snap8 = _emem.snapshot()
_causes8 = _snap8["causes"]
_assert(len(_causes8) == 2, "gen8_snapshot_causes")
_assert(_causes8[0]["cause_key"] == "missing_units", "gen8_snapshot_order")
_assert(_causes8[0]["learned"] is True, "gen8_snapshot_learned_flag")

_src8 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "maya_conversation", "error_generalize.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src8,
            "gen8_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "ErrorMemory"), "gen8_pkg_has_error_memory")

# --------------------------------------------------------------------------
# PHASE 9 — method portfolio
# --------------------------------------------------------------------------

from maya_conversation.portfolio import MethodPortfolio

_char_math_pressure = characterize_task(
    _MATH_TURN, "pressure diagonal", resource_pressure=True)

_port = MethodPortfolio()
_reg1 = _port.register(
    "classic", conditions={"domains": ["math"]},
    reliability=0.5, verification_strength=0.5, latency_steps=2,
    limitations=["no guard path"])
_assert(_reg1 is not None, "gen9_register_classic")
_assert(_reg1["reliability"] == 0.5, "gen9_register_profile")
_assert(_port.register("classic") is None, "gen9_register_duplicate")
_reg2 = _port.register(
    "guarded", conditions={"domains": ["math"]},
    exclusions={"resource_level": "pressure"},
    resource_requirement="safe", reliability=0.6,
    verification_strength=0.9)
_assert(_reg2 is not None, "gen9_register_guarded")
_reg3 = _port.register(
    "heuristic", conditions={"domains": ["math"]},
    reliability=0.3, verification_strength=0.2)
_reg4 = _port.register(
    "companion", conditions={"domains": ["psychology"]})
_assert(_reg4 is not None, "gen9_register_companion")

_r9 = _port.recommend(_char_math_safe)
_assert(_r9 is not None, "gen9_recommend_returns")
_assert(_r9["method"] == "guarded", "gen9_recommend_prefers_guarded")
_assert(_r9["preferred"] is False, "gen9_recommend_scored")

_r9p = _port.recommend(_char_math_safe, prefer=["classic"])
_assert(_r9p["method"] == "classic", "gen9_prefer_override")
_assert(_r9p["preferred"] is True, "gen9_prefer_flag")

_r9r = _port.recommend(_char_math_safe, reject=["guarded"])
_assert(_r9r["method"] == "classic", "gen9_reject_guarded")

_r9press = _port.recommend(_char_math_pressure)
_assert(_r9press is not None, "gen9_pressure_has_candidate")
_assert(_r9press["method"] != "guarded", "gen9_condition_change_rejects")

_r9psy = _port.recommend(_char_psy)
_assert(_r9psy is not None, "gen9_psych_candidate")
_assert(_r9psy["method"] == "companion", "gen9_choose_by_conditions")

_r9none = _port.recommend({"domains": ["linguistics"],
                           "resource_level": "safe",
                           "math_structure": False})
_assert(_r9none is None, "gen9_no_eligible_none")

_port.record_outcome("classic", _char_math_safe, True)
_port.record_outcome("classic", _char_math_safe, True)
_port.record_outcome("heuristic", _char_math_safe, False)
_r9ev = _port.recommend(_char_math_safe)
_assert(_r9ev["method"] == "classic", "gen9_evidence_rejects_weak")
_assert(_r9ev["scores"]["evidence"] > 0.5, "gen9_evidence_reflects_success")

_rec = _port.record_outcome("unknown_method", _char_math_safe, True)
_assert(_rec is None, "gen9_record_unregistered_none")

_h9 = _port.history()
_assert(len(_h9["methods"]) == 4, "gen9_history_count")
_assert(len(_h9["evidence"]["classic"]) == 2, "gen9_history_evidence")


_src9 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "maya_conversation", "portfolio.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src9,
            "gen9_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "MethodPortfolio"), "gen9_pkg_has_portfolio")

# --------------------------------------------------------------------------
# PHASE 10 — adaptive orchestration (side-channel)
# --------------------------------------------------------------------------

from maya_conversation.adaptive import AdaptiveScheduler

_sch = AdaptiveScheduler(run_context={"run": 1})
_assert(_sch.promote_after == 2, "gen10_schedule_init_rules")

_hpa = hypothesis_from_experience(
    "diagonal", "saw triangle",
    conditions={"domains": ["math"], "math_structure": True},
    exclusions={"resource_level": "pressure"})
_e1 = _sch.apply_outcome(_hpa, _char_math_safe, True)
_assert(_hpa.status == "tested", "gen10_first_success_testing")
_assert(_e1["effect"] in ("observe", "promote"), "gen10_observe_effect")
_e2 = _sch.apply_outcome(_hpa, _char_math_safe, True)
_assert(_hpa.status == "promoted", "gen10_second_success_promotes")
_assert(_e2["effect"] == "promote", "gen10_promote_effect")

_sch_ctx = AdaptiveScheduler(run_context={"run": 7})
_assert(_sch_ctx.run_context["run"] == 7, "gen10_context_seeded")
_hpb = hypothesis_from_experience(
    "b", "see straight lines",
    conditions={"domains": ["math"], "math_structure": True},
    exclusions={"resource_level": "pressure"})
_sch_ctx.apply_outcome(_hpb, _char_math_safe, True)
_sch_ctx.apply_outcome(_hpb, _char_math_safe, False)
_assert(_hpb.status == "weakened", "gen10_weaken_after_failure")
_assert(_sch_ctx.run_context["last_outcome"]["ok"] is False,
        "gen10_context_written")

_sch_r = AdaptiveScheduler()
_hpr = hypothesis_from_experience(
    "r", "see straight lines",
    conditions={"domains": ["math"], "math_structure": True},
    exclusions={"resource_level": "pressure"})
_sch_r.apply_outcome(_hpr, _char_math_safe, True)
_sch_r.apply_outcome(_hpr, _char_math_safe, False)
_sch_r.apply_outcome(_hpr, _char_math_safe, False)
_assert(_hpr.status == "rejected", "gen10_reject_after_two_failures")

_sch_rb = AdaptiveScheduler()
_hp_rb = hypothesis_from_experience(
    "rb", "see straight lines",
    conditions={"domains": ["math"], "math_structure": True},
    exclusions={"resource_level": "pressure"})
_sch_rb.apply_outcome(_hp_rb, _char_math_safe, True)
_sch_rb.apply_outcome(_hp_rb, _char_math_safe, True)
_assert(_hp_rb.status == "promoted", "gen10_promote_before_rollback")
_sch_rb.apply_outcome(_hp_rb, _char_math_safe, False)
_assert(_hp_rb.status == "promoted", "gen10_single_fail_keeps_promoted")
_sch_rb.apply_outcome(_hp_rb, _char_math_safe, False)
_assert(_hp_rb.status == "rolled_back",
        "gen10_rollback_after_two_consecutive")

_weak_h = hypothesis_from_experience(
    "w", "see straight lines",
    conditions={"domains": ["math"], "math_structure": True})
_weak_h.weaken(reason="manual downgrade")
_route = _sch.route(_char_math_safe, [_weak_h, _hpa])
_assert(_route is not None, "gen10_route_returns")
_assert(_route["name"] == "diagonal", "gen10_route_promoted_preferred")

_rej_h = hypothesis_from_experience(
    "d", "see straight lines",
    conditions={"domains": ["math"], "math_structure": True})
_rej_h.reject(reason="manual reject")
_route_rej = _sch.route(_char_math_safe, [_rej_h])
_assert(_route_rej is None, "gen10_route_rejected_never")

_psy_h = hypothesis_from_experience(
    "p", "therapy assist",
    conditions={"domains": ["psychology"]})
_route_unscoped = _sch.route(_char_math_safe, [_psy_h])
_assert(_route_unscoped is None, "gen10_route_unscoped_none")

_route_pref = _sch.route(_char_math_safe, [_rej_h, _weak_h], prefer=["w"])
_assert(_route_pref is not None, "gen10_route_prefer_returns")
_assert(_route_pref["name"] == "w", "gen10_route_prefer_override")

_cnt = _sch.counters()
_assert(_cnt["count"] >= 1, "gen10_counters_recorded")

_port10 = MethodPortfolio()
_port10.register("diagonal", conditions={"domains": ["math"]})
_port10.register("fast", conditions={"domains": ["math"]})
_port10.record_outcome("fast", _char_math_safe, True)
_port10.record_outcome("diagonal", _char_math_safe, False)
_eff10 = _sch.apply_outcome(_weak_h, _char_math_safe, False,
                            portfolio=_port10)
_assert("replaced_by" in _eff10, "gen10_replace_annotated")

_eff_none = _sch.apply_outcome(None, _char_math_safe, True)
_assert(_eff_none["effect"] == "ignore", "gen10_none_hypothesis_ignored")

_src10 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation", "adaptive.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src10,
            "gen10_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "AdaptiveScheduler"),
        "gen10_pkg_has_scheduler")

# --------------------------------------------------------------------------
# PHASE 11 — learning quality metrics
# --------------------------------------------------------------------------

from maya_conversation.learning_metrics import LearningMetrics

_lm = LearningMetrics()
_lm.record_memory(2, 10)
_assert(_lm.memory_efficiency() == 5.0, "gen11_memory_efficiency_healthy")
_lm.record_hypothesis_outcome("promoted")
_lm.record_hypothesis_outcome("promoted")
_lm.record_hypothesis_outcome("rejected")
_lm.record_hypothesis_outcome("rejected")
_lm.record_hypothesis_outcome("rejected")
_assert(_lm.hypothesis_validity() < 0.5,
        "gen11_hypothesis_validity_unhealthy")
_lm.record_promotion_cost(2)
_lm.record_promotion_cost(2)
_assert(_lm.evidence_efficiency() == 2.0, "gen11_evidence_efficiency_healthy")
_lm.record_transfer(0.9, 0.6)
_assert(abs(_lm.transfer_benefit() - 0.3) < 1e-9,
        "gen11_transfer_benefit_healthy")

_pairs11 = [(1.0, 1.0), (0.0, 0.1), (1.0, 0.8), (0.0, 0.0)]
_assert(_lm.similarity_fidelity(_pairs11) >= 0.8,
        "gen11_fidelity_healthy")
_assert(_lm.similarity_fidelity([]) == 0.0, "gen11_fidelity_empty_zero")

_lm.record_stability_batch("a", [0.1, 0.2, 0.3])
_lm.record_stability_batch("b", [0.1, 0.2, 0.3])
_lm.record_stability_batch("c", [0.1, 0.2, 0.3])
_assert(_lm.stability() == 1.0, "gen11_stability_healthy")
_lm2 = LearningMetrics()
_assert(_lm2.stability() == 0.0, "gen11_stability_insufficient_zero")

_lm3 = LearningMetrics()
_assert(_lm3.memory_efficiency() == 0.0, "gen11_memory_no_fp_zero")

_snap11 = _lm.snapshot(pairs=_pairs11)
_assert(_snap11["summary"]["total_metrics"] == 6,
        "gen11_snapshot_total_metrics")
_assert(_snap11["summary"]["learning_health"] == "partial",
        "gen11_snapshot_summary_health")

_eval11 = _lm.evaluate("transfer_benefit", 0.4)
_assert(_eval11["metric"] == "transfer_benefit",
        "gen11_evaluate_metric_label")
_assert(_eval11["healthy"] is True, "gen11_evaluate_healthy_value")

_raw11 = _snap11["raw"]
_assert(_raw11["runs"] == 10, "gen11_raw_runs")
_assert(_raw11["promoted"] == 2, "gen11_raw_promoted")


_src11 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation", "learning_metrics.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src11,
            "gen11_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "LearningMetrics"),
        "gen11_pkg_has_lm")

# --------------------------------------------------------------------------
# PHASE 12 — controlled self-improvement
# --------------------------------------------------------------------------

from maya_conversation.self_improve import ControlledImprovement

_old_hp = hypothesis_from_experience(
    "classic", "old analysis",
    conditions={"domains": ["math"], "math_structure": True},
    exclusions={"resource_level": "pressure"})
_old_hp.reject(reason="old analysis failed on guard path")

_ci = ControlledImprovement()
_new_hp = _ci.propose(_old_hp, "classic2", "new method under fixed guard",
                      conditions={"domains": ["math"]})
_assert(_new_hp.status == "untested", "gen12_propose_creates")
_assert(isinstance(_new_hp, object), "gen12_propose_unique_id")
_assert(_ci.count() == 1, "gen12_snapshot_candidate_count")

_ev = _ci.evidence(0, _char_math_safe, True)
_assert(_ev is not None, "gen12_evidence_accumulates")
_assert(_ev["ok_transfers"] == 1, "gen12_evidence_ok_counts")
_assert(_new_hp.status == "tested", "gen12_evidence_updates_status")

_ci_none = ControlledImprovement()
_winner = _ci.winner()
_assert(_winner is not None, "gen12_winner_exists_success")
_assert(_winner["ok_transfers"] >= 1, "gen12_winner_meets_transfer")
_assert(_old_hp.status == "rejected", "gen12_old_not_mutated_status")

_ci_bad = ControlledImprovement()
_ci_bad.propose(_old_hp, "weak", "no evidence yet",
                conditions={"domains": ["math"]})
_assert(_ci_bad.winner() is None, "gen12_winner_none_no_evidence")

_old_promoted = hypothesis_from_experience(
    "p", "promoted old",
    conditions={"domains": ["math"], "math_structure": True})
_old_promoted.record_case("1", "ok", True)
_old_promoted.record_case("2", "ok", True)
_old_promoted.update_uncertainty()
_old_promoted.promote()
_ci_promoted = ControlledImprovement()
_ci_promoted.propose(_old_promoted, "new_best", "best so far",
                     conditions={"domains": ["math"]})
_ci_promoted.evidence(0, _char_math_safe, True)
_assert(_ci_promoted.winner() is None, "gen12_winner_no_old_promoted")

_ranked = _ci.rank()
_assert(len(_ranked) >= 1, "gen12_rank_returns_nonempty")
_assert(all(r["similarity_to_old"] >= 0.0 for r in _ranked),
        "gen12_rank_similarity_bounded")

_ci_deep = ControlledImprovement()
_ci_deep.propose(_old_hp, "narrow", "narrow guard",
                 conditions={"domains": ["math"]})
_ci_deep.evidence(0, _char_math_safe, True)
_snap12 = _ci.snapshot()
_assert("candidates" in _snap12, "gen12_snapshot_structure")
_assert(len(_snap12["candidates"]) == 1, "gen12_snapshot_one_candidate")


_src12 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation", "self_improve.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src12,
            "gen12_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "ControlledImprovement"),
        "gen12_pkg_has_ci")

# --------------------------------------------------------------------------
# PHASE 13 — cooperative challenge
# --------------------------------------------------------------------------

from maya_conversation.coop_challenge import cooperative_challenge

_hp_ch = hypothesis_from_experience(
    "stable", "old stable analysis",
    conditions={"domains": ["math"], "math_structure": True})
_hp_ch.record_case("ok1", "ok", True)
_hp_ch.record_case("ok2", "ok", True)
_hp_ch.update_uncertainty()
_hp_ch.promote()

_m13 = cooperative_challenge(
    _hp_ch, "alt_math",
    challenger_conditions={"domains": ["math"]},
    challenge_result=True)
_assert(_hp_ch.status == "weakened", "gen13_challenger_weakens_promoted")
_assert(_m13.effect == "weaken", "gen13_metaphor_effect_weaken")
_assert(_m13.challenger.status == "validated",
        "gen13_challenger_validated")
_assert(_m13.result is True, "gen13_result_true")

_hp_ch2 = hypothesis_from_experience(
    "stable2", "another old stable",
    conditions={"domains": ["math"], "math_structure": True})
_hp_ch2.record_case("k1", "ok", True)
_hp_ch2.update_uncertainty()
_hp_ch2.status = "tested"

_m13b = cooperative_challenge(
    _hp_ch2, "alt2",
    challenge_result=True)
_assert(_hp_ch2.status == "rejected",
        "gen13_challenger_rejects_tested")

_hp_ch3 = hypothesis_from_experience(
    "stable3", "fragile old",
    conditions={"domains": ["math"], "math_structure": True})
_hp_ch3.record_case("k3", "ok", True)
_hp_ch3.record_case("k4", "ok", True)
_hp_ch3.update_uncertainty()
_hp_ch3.promote()

_m13c = cooperative_challenge(
    _hp_ch3, "weak_alt",
    challenge_result=False)
_assert(_hp_ch3.status == "promoted",
        "gen13_false_challenge_ignored")
_assert(_m13c.effect == "false_challenge_ignored",
        "gen13_false_challenge_effect")

_m13none = cooperative_challenge(None, "no_target",
                                 challenge_result=True)
_assert(_m13none.effect == "ignore_original_none",
        "gen13_none_original_ignored")

_hp_ch4 = hypothesis_from_experience(
    "stable4", "see straight lines",
    conditions={"domains": ["math"], "math_structure": True})
_hp_ch4.record_case("k5", "ok", True)
_hp_ch4.update_uncertainty()
_hp_ch4.status = "untested"
_m13d = cooperative_challenge(
    _hp_ch4, "alt_already_untested",
    challenge_result=True)
_assert(_m13d.effect == "already_untested",
        "gen13_untested_not_weakened")

_hp_snap = hypothesis_from_experience(
    "snap", "snap test",
    conditions={"domains": ["math"]})
_hp_snap.record_case("s1", "ok", True)
_hp_snap.update_uncertainty()
_m13snap = cooperative_challenge(
    _hp_snap, "snap_alt", challenge_result=True)
_assert(_hp_snap.status == "rejected", "gen13_snap_effect_reject")
_assert(_m13snap.effect == "reject", "gen13_snap_effect_reject_label")


_src13 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation", "coop_challenge.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src13,
            "gen13_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "cooperative_challenge"),
        "gen13_pkg_has_coop_challenge")
_assert(hasattr(maya_conversation, "ChallengeMetaphor"),
        "gen13_pkg_has_metaphor")

# --------------------------------------------------------------------------
# PHASE 14 — resource-aware generalization
# --------------------------------------------------------------------------

from maya_conversation.resource_profiles import ResourceProfile, ResourcePolicy

_p_norm = ResourceProfile(
    "normal", latency=1.0, cost=0.2, pressure_ok=True,
    pressure_success_prob=0.9, domains_excluded=[])
_p_press = ResourceProfile(
    "pressure_opt", latency=0.5, cost=0.1, pressure_ok=True,
    pressure_success_prob=0.7, domains_excluded=[])
_p_exclude = ResourceProfile(
    "no_math", latency=0.3, cost=0.15, pressure_ok=True,
    pressure_success_prob=0.8, domains_excluded=["math"])

_rp = ResourcePolicy()
_reg1 = _rp.register(_p_norm)
_assert(_reg1 is not None, "gen14_register_profile")
_assert(_reg1["name"] == "normal", "gen14_register_profile_name")
_assert(_rp.register(_p_norm) is None, "gen14_register_duplicate")
_rp.register(_p_press)
_rp.register(_p_exclude)
_assert(len(_rp.profiles()) == 3, "gen14_profile_count")

_sel = _rp.select_for_resource(
    _char_math_safe,
    budget={"latency": 1.0, "cost": 0.3})
_assert(_sel is not None, "gen14_select_normal_budget")
_assert(_sel["profile"] == "normal", "gen14_select_normal_preferred")
_assert(_sel["pressure_success_prob"] == 0.9, "gen14_select_prob_normal")

_sel_tight = _rp.select_for_resource(
    _char_math_safe,
    budget={"latency": 0.6, "cost": 0.15})
_assert(_sel_tight is not None, "gen14_select_tight_budget")
_assert(_sel_tight["profile"] == "pressure_opt",
        "gen14_select_pressure_under_tight")

_sel_pressure = _rp.select_for_resource(
    _char_math_safe,
    budget={"latency": 1.0, "cost": 0.3},
    resource_pressure=True)
_assert(_sel_pressure is not None,
        "gen14_select_with_pressure_flag")

_p_no_press = ResourceProfile(
    "no_press", latency=0.4, cost=0.1, pressure_ok=False)
_rp2 = ResourcePolicy()
_rp2.register(_p_norm)
_rp2.register(_p_no_press)
_sel_np = _rp2.select_for_resource(
    _char_math_safe,
    budget={"latency": 1.0, "cost": 0.3},
    resource_pressure=True)
_assert(_sel_np is not None, "gen14_pressure_excludes_nonpress")
_assert(_sel_np["profile"] != "no_press",
        "gen14_pressure_rejects_no_press")

_sel_excl = _rp.select_for_resource(
    _char_math_safe,
    budget={"latency": 1.0, "cost": 0.3})
_assert(_sel_excl["profile"] != "no_math",
        "gen14_exclude_excludes_math")

_sel_none = _rp.select_for_resource(
    _char_math_safe,
    budget={"latency": 0.001, "cost": 0.001})
_assert(_sel_none is None, "gen14_no_eligible_none")

_est = _rp.estimate_costs(_char_math_safe)
_assert("normal" in _est, "gen14_estimate_has_normal")
_assert(_est["normal"]["cost"] == 0.2, "gen14_estimate_cost_value")

_snap14 = _rp.profiles()
_assert(len(_snap14) == 3, "gen14_snapshot_profiles")

_p_fin = ResourceProfile("fin", latency=0.1, cost=0.0)
_assert(_p_fin.within_budget({"latency": 0.2, "cost": 0.1}),
        "gen14_within_budget")
_assert(_p_fin.within_budget({}), "gen14_within_budget_default_inf")
_assert(_p_fin.eligible_for_task(_char_math_safe), "gen14_eligible_task")


_src14 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation", "resource_profiles.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in _src14,
            "gen14_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))
_assert(hasattr(maya_conversation, "ResourceProfile"),
        "gen14_pkg_has_profile")
_assert(hasattr(maya_conversation, "ResourcePolicy"),
        "gen14_pkg_has_policy")


print("generalization_test_ok=%d" % LABELS["ok"])
if LABELS["ok"] == 309:
    print("test_generalization=PASS")
else:
    print("test_generalization=FAIL")
    sys.exit(1)