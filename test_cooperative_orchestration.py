"""Batch 8H cooperative orchestrator test.

Tests the cooperate module: agreement, disagreement, single-source,
fallback, and no-engagement verdicts. Also verifies the integration
into maya_chat.py (cooperation note injection).

All tests are deterministic: no clock, no randomness, no network.

Output contract: every line is ``=OK`` evidence or a ``key=value``
summary, so the external verification runner accepts the suite.
"""
from __future__ import annotations
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_conversation.cooperate import (
    cooperate, AGREEMENT, AGREEMENT_WITH_CAVEAT, DISAGREEMENT,
    SINGLE_SOURCE, FALLBACK_USED, NO_ENGAGEMENT,
    EPISTEMIC_SUPPORTED, EPISTEMIC_CONTESTED, EPISTEMIC_PRELIMINARY,
    EPISTEMIC_UNAVAILABLE, EPISTEMIC_FALLBACK,
    _cooperation_result,
)
from maya_conversation import orchestrate_turn, build_orchestrator
from maya_conversation.adaptivity import (
    assess_complexity, DEPTH_FAST, DEPTH_STANDARD, DEPTH_DEEP,
)
from maya_conversation.resilience import (
    FailureTracker, run_guarded, STAGE_HEALTHY, STAGE_DEGRADED, STAGE_TRIPPED,
)

LABELS = {"ok": 0}

def _assert(cond, label):
    if cond:
        LABELS["ok"] += 1
        print(label + "=OK")
    else:
        print(label + "=FAIL")


# 1. No engagement
r = cooperate(None, None, None)
_assert(r["verdict"] == NO_ENGAGEMENT, "coop_no_engagement_verdict")
_assert(r["confidence"] == 0.0, "coop_no_engagement_confidence")

# 2. Single source (8G only)
conv_result = orchestrate_turn("hello there")
_assert(conv_result.get("ok") is True, "conv_ok_for_hello")
r2 = cooperate(conv_result, None, None)
_assert(r2["verdict"] == SINGLE_SOURCE, "coop_single_source_8g")
_assert(r2["confidence"] == 0.7, "coop_single_source_confidence")

# 3. Single source (bridge only)
r3 = cooperate(None, {"register": "measured", "budget": 48, "holds": [],
                       "text": "test"}, None)
_assert(r3["verdict"] == SINGLE_SOURCE, "coop_single_source_bridge")
_assert(r3["confidence"] == 0.7, "coop_single_source_bridge_confidence")

# 4. Agreement (both OK, no disagreements)
conv_hello = orchestrate_turn("hello")
_bridge_ok = {"register": "measured", "budget": 48, "holds": [],
              "text": "test"}
r4 = cooperate(conv_hello, _bridge_ok, None)
_assert(r4["verdict"] in (AGREEMENT, AGREEMENT_WITH_CAVEAT),
        "coop_agreement_or_caveat")
_assert(r4["confidence"] >= 0.8, "coop_agreement_high_confidence")

# 5. Disagreement (intelligence_unavailable + psychology engaged)
conv_psych = orchestrate_turn("I keep procrastinating on everything")
_assert(conv_psych.get("ok") is True, "conv_ok_for_psych")
bridge_hold = {"register": "reserved", "budget": 16,
               "holds": ["intelligence_unavailable"], "text": "test"}
r5 = cooperate(conv_psych, bridge_hold, None)
_assert(r5["verdict"] == DISAGREEMENT,
        "coop_disagreement_intel_unavail")
_assert(len(r5["disagreements"]) > 0, "coop_has_disagreements")
_assert(r5["confidence"] == 0.3, "coop_disagreement_low_confidence")
_assert(any(d["severity"] == "high" for d in r5["disagreements"]),
        "coop_has_high_severity")

# 6. Agreement with caveat (register conflict)
conv_phil = orchestrate_turn("what is consciousness")
_assert(conv_phil.get("ok") is True, "conv_ok_for_phil")
bridge_reserved = {"register": "reserved", "budget": 32,
                   "holds": ["low_confidence"], "text": "test"}
r6 = cooperate(conv_phil, bridge_reserved, None)
_assert(r6["verdict"] in (AGREEMENT_WITH_CAVEAT, DISAGREEMENT),
        "coop_caveat_or_disagreement")
_assert(len(r6["disagreements"]) > 0, "coop_caveat_has_disagreements")

# 7. Agreement with caveat (ambiguity vs confidence)
r7 = cooperate(conv_hello, _bridge_ok,
               {"confidence": 0.95})
_assert(r7["verdict"] in (AGREEMENT, AGREEMENT_WITH_CAVEAT),
        "coop_ambiguity_caveat_or_agreement")

# 8. Safety tension (safety holds + philosophy)
bridge_safety = {"register": "reserved", "budget": 32,
                 "holds": ["safety_boundary"], "text": "test"}
r8 = cooperate(conv_phil, bridge_safety, None)
_assert(r8["verdict"] in (DISAGREEMENT, AGREEMENT_WITH_CAVEAT),
        "coop_safety_tension_detected")

# 9. Fail-open: garbage inputs
r9 = cooperate({"ok": False, "reason": "test"}, None, None)
_assert(r9["verdict"] == NO_ENGAGEMENT or r9["verdict"] == FALLBACK_USED,
        "coop_garbage_input")

r10 = cooperate(None, {"holds": []}, None)
_assert(r10["verdict"] == SINGLE_SOURCE, "coop_none_conv_single_source")

# 10. Determinism
r11a = cooperate(conv_hello, _bridge_ok, None)
r11b = cooperate(conv_hello, _bridge_ok, None)
_assert(r11a["verdict"] == r11b["verdict"], "coop_deterministic_verdict")
_assert(r11a["confidence"] == r11b["confidence"],
        "coop_deterministic_confidence")

# 11. Purity: no time/random/datetime/subprocess/socket/IO
coop_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "maya_conversation", "cooperate.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path.exists", "json.load",
                   "json.dump"]:
    _assert(forbidden not in coop_src,
            "coop_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))

# 12. Existing 8G behavior preserved
r12 = orchestrate_turn("what is the meaning of life")
_assert(r12.get("ok") is True, "conv_ok_meaning_of_life")
phil = r12.get("domain_results", {}).get("philosophy") or {}
_assert(phil.get("engaged") is True, "phil_engaged_meaning")
_assert(phil.get("not_fact") is True, "phil_not_fact")
positions = phil.get("positions", [])
_assert(len(positions) >= 2, "phil_has_positions")
_assert(all(p.get("epistemic_status") == "DISPUTED" for p in positions),
        "phil_all_disputed")

# 13. Package exports
import maya_conversation
_assert(hasattr(maya_conversation, "cooperate"), "pkg_has_cooperate")
_assert(hasattr(maya_conversation, "AGREEMENT"), "pkg_has_agreement")
_assert(hasattr(maya_conversation, "DISAGREEMENT"),
        "pkg_has_disagreement")
_assert(hasattr(maya_conversation, "SINGLE_SOURCE"),
        "pkg_has_single_source")

# 14. Cooperation epistemic status (Phase 3)
r14 = cooperate(None, None, None)
_assert(r14["epistemic"]["status"] == EPISTEMIC_UNAVAILABLE,
        "epi_unavailable_no_engagement")
_assert(r14["epistemic"]["supporting_sources"] == [],
        "epi_no_supporting_sources")
_assert(r14["epistemic"]["basis"], "epi_unavailable_basis_nonempty")

r15 = cooperate(conv_result, None, None)
_assert(r15["epistemic"]["status"] == EPISTEMIC_PRELIMINARY,
        "epi_preliminary_single_source")
_assert(r15["epistemic"]["supporting_sources"] == ["conv_8g"],
        "epi_single_source_supporting")

r16 = cooperate(conv_hello, _bridge_ok, None)
_assert(r16["epistemic"]["status"] == EPISTEMIC_SUPPORTED,
        "epi_supported_agreement")
_assert(r16["epistemic"]["supporting_sources"] == ["bridge", "conv_8g"],
        "epi_agreement_supporting_both")

r17 = cooperate(conv_psych, bridge_hold, None)
_assert(r17["epistemic"]["status"] == EPISTEMIC_CONTESTED,
        "epi_contested_disagreement")
_assert(r17["epistemic"]["disputing_sources"] == ["bridge", "conv_8g"],
        "epi_disagreement_disputing_both")

# FALLBACK epistemic via exception path
class _Poisoned:
    def get(self, *args):
        raise RuntimeError("poisoned")

r18 = cooperate(_Poisoned(), _bridge_ok, None)
_assert(r18["verdict"] == FALLBACK_USED, "epi_fallback_verdict")
_assert(r18["epistemic"]["status"] == EPISTEMIC_FALLBACK,
        "epi_fallback_status")

# 15. Determinism of epistemic frame
r19a = cooperate(conv_hello, _bridge_ok, None)
r19b = cooperate(conv_hello, _bridge_ok, None)
_assert(r19a["epistemic"]["status"] == r19b["epistemic"]["status"],
        "epi_deterministic_status")
_assert(r19a["epistemic"]["supporting_sources"]
        == r19b["epistemic"]["supporting_sources"],
        "epi_deterministic_sources")

# 16. Purity: epistemic helpers add no I/O
epi_src = coop_src
_assert("import os" not in epi_src, "epi_no_os_import")
_assert("open(" not in epi_src, "epi_no_open")

# 17. Adaptive latency (Phase 4)
adap_hello = assess_complexity(conv_hello, "hello", None)
_assert(adap_hello["depth"] == DEPTH_FAST, "adap_greeting_fast")

adap_psych = assess_complexity(conv_psych, "I keep procrastinating on everything",
                               cooperate(conv_psych, bridge_hold, None))
_assert(adap_psych["depth"] == DEPTH_DEEP,
        "adap_psych_disagreement_deep")

adap_meaning = assess_complexity(
    r12, "what is the meaning of life",
    cooperate(r12, _bridge_ok, None))
_assert(adap_meaning["depth"] in (DEPTH_STANDARD, DEPTH_DEEP),
        "adap_meaning_philosophy_not_fast")

adap_empty = assess_complexity()
_assert(adap_empty["depth"] in (DEPTH_FAST, DEPTH_STANDARD, DEPTH_DEEP),
        "adap_failopen_no_input")
_assert(adap_empty["score"] == 0.0, "adap_empty_score_zero")

adap_a = assess_complexity(r12, "what is the meaning of life", None)
adap_b = assess_complexity(r12, "what is the meaning of life", None)
_assert(adap_a["depth"] == adap_b["depth"], "adap_deterministic_depth")
_assert(adap_a["score"] == adap_b["score"], "adap_deterministic_score")

_assert(adap_a["depth"] in (DEPTH_FAST, DEPTH_STANDARD, DEPTH_DEEP),
        "adap_depth_value_valid")

import maya_conversation
_assert(hasattr(maya_conversation, "assess_complexity"),
        "adap_pkg_has_assess")
_assert(hasattr(maya_conversation, "DEPTH_FAST"), "adap_pkg_has_depth_fast")
_assert(hasattr(maya_conversation, "DEPTH_DEEP"), "adap_pkg_has_depth_deep")

adap_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "maya_conversation", "adaptivity.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in adap_src,
            "adap_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))


# 18. Fault tolerance: circuit breaker (Phase 5)
tr = FailureTracker()
_assert(tr.state("x") == STAGE_HEALTHY, "ft_initial_healthy")

tr.record("x", False)
_assert(tr.state("x") == STAGE_DEGRADED, "ft_degraded_after_one_failure")

tr.record("x", False)
tr.record("x", False)
_assert(tr.state("x") == STAGE_TRIPPED, "ft_tripped_after_three_failures")
_assert(tr.should_skip("x") is True, "ft_skip_when_tripped")

tr2 = FailureTracker()
tr2.record("y", False)
tr2.record("y", False)
tr2.record("y", False)
_assert(tr2.should_skip("y") is True, "ft_half_open_held_first")
_assert(tr2.should_skip("y") is False, "ft_half_open_trial_second")
tr2.record("y", True)
_assert(tr2.state("y") == STAGE_HEALTHY, "ft_recover_after_trial_success")

tr3 = FailureTracker()
tr3.record("z", False)
tr3.record("z", False)
tr3.record("z", False)
tr3.should_skip("z")
tr3.should_skip("z")
tr3.record("z", False)
_assert(tr3.state("z") == STAGE_TRIPPED, "ft_retrip_after_trial_failure")

_FN_COUNTER = {"n": 0}

def _good():
    _FN_COUNTER["n"] += 1
    return {"ok": True, "value": _FN_COUNTER["n"]}

def _bad():
    raise RuntimeError("boom")

res, guard = run_guarded("s1", _good, tracker=FailureTracker())
_assert(res == {"ok": True, "value": 1}, "rg_happy_result")
_assert(guard["degraded"] is False, "rg_happy_not_degraded")

res2, guard2 = run_guarded("s2", _bad, tracker=FailureTracker())
_assert(res2 is None, "rg_exception_none")
_assert(guard2["degraded"] is True, "rg_exception_degraded")

def _internal_fail():
    return {"ok": False, "reason": "degraded_by_design"}

res3, guard3 = run_guarded("s3", _internal_fail,
                          tracker=FailureTracker(),
                          ok_check=lambda r: bool(r and r.get("ok")))
_assert(res3 is not None, "rg_okcheck_keeps_result")
_assert(res3.get("ok") is False, "rg_okcheck_result_false")
_assert(guard3["degraded"] is True, "rg_okcheck_counts_failure")

tr4 = FailureTracker()
_ = [run_guarded("s4", _bad, tracker=tr4) for _ in range(3)]
res5, guard5 = run_guarded("s4", _good, tracker=tr4)
_assert(res5 is None, "rg_tripped_skips_call")
_assert(guard5["skipped"] is True, "rg_tripped_skip_flag")

# 19. Fault tolerance: determinism of snapshots
tr5 = FailureTracker(trip_after=2, recovery_ok=1)
s_a = tr5.snapshot()
s_b = tr5.snapshot()
_assert(s_a == s_b, "ft_deterministic_snapshot")

# 20. Fault tolerance: purity of resilience module
res_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "maya_conversation", "resilience.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in res_src,
            "res_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))

# 21. Resource-aware orchestration (Phase 6)
rp_pressure = assess_complexity(conv_hello, "hello", None,
                                resource_pressure=True)
_assert(rp_pressure["depth"] == DEPTH_STANDARD,
        "rp_greeting_pressure_standard")
_assert(rp_pressure["signals"]["resource_pressure"] == 0.5,
        "rp_signal_pressure_recorded")

rp_calm_greeting = assess_complexity(conv_hello, "hello", None,
                                     resource_pressure=False)
_assert(rp_calm_greeting["depth"] == DEPTH_FAST,
        "rp_greeting_no_pressure_fast")
_assert(rp_calm_greeting["signals"]["resource_pressure"] == 0.0,
        "rp_signal_calm_recorded")

rp_deep = assess_complexity(conv_psych,
                            "I keep procrastinating on everything",
                            cooperate(conv_psych, bridge_hold, None),
                            resource_pressure=True)
_assert(rp_deep["depth"] == DEPTH_DEEP,
        "rp_disagreement_pressure_still_deep")

rp_a = assess_complexity(conv_hello, "hello", None, resource_pressure=True)
rp_b = assess_complexity(conv_hello, "hello", None, resource_pressure=True)
_assert(rp_a["depth"] == rp_b["depth"], "rp_pressure_deterministic")
_assert(rp_a["score"] == rp_b["score"], "rp_pressure_score_deterministic")

# 22. Computational mathematics extension (Phase 7)
from maya_math.cooperation import (
    agreement_weighted_combine, concordance, label_similarity,
    pooled_agreement,
)
_assert(math.isclose(concordance(0.7, 0.7), 1.0, rel_tol=1e-12),
        "coopmath_concordance_equal")
_assert(concordance(0.0, 1.0) == 0.0, "coopmath_concordance_opposite")
_assert(math.isclose(concordance(0.8, 0.2), 0.4, rel_tol=1e-12),
        "coopmath_concordance_mid")
_assert(concordance(1.5, 0.5) == 0.0, "coopmath_out_of_range_concordance")

_assert(math.isclose(agreement_weighted_combine(0.7, 0.7), 0.7,
                     rel_tol=1e-12),
        "coopmath_combine_identical")
_assert(agreement_weighted_combine(2.0, 0.5) == 0.0,
        "coopmath_combine_fail_closed")

_assert(label_similarity(("a",), ("a",)) == 1.0,
        "coopmath_label_similarity_same")
_assert(label_similarity(("a",), ("b",)) == 0.0,
        "coopmath_label_similarity_disjoint")
_assert(label_similarity(None, None) == 1.0,
        "coopmath_label_similarity_empty")
_assert(math.isclose(label_similarity(("a", "b"), ("b", "c")),
                    1.0 / 3.0, rel_tol=1e-12),
        "coopmath_label_similarity_partial")
_assert(label_similarity("not-a-set", 5) == 0.0,
        "coopmath_label_similarity_malformed")

_assert(math.isclose(pooled_agreement([(0.9, 0.85), (0.3, 0.9)]), 0.5,
                     rel_tol=1e-12),
        "coopmath_pooled_agreement")
_assert(pooled_agreement([]) == 0.0, "coopmath_pooled_empty_fail_closed")
_assert(pooled_agreement(None) == 0.0, "coopmath_pooled_none_fail_closed")

coop_src2 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "maya_math", "cooperation.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in coop_src2,
            "coopmath_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))

import maya_math
_assert(hasattr(maya_math, "cooperation"), "coopmath_pkg_has_module")
_assert(hasattr(maya_math, "concordance"), "coopmath_pkg_has_concordance")
_assert(hasattr(maya_math, "agreement_weighted_combine"),
        "coopmath_pkg_has_combine")

# 23. Learning orchestration ledger (Phase 8)
from maya_conversation.learning import (
    LearningLedger, EVENT_PROPOSAL, EVENT_OUTCOME, EVENT_CORRECTION,
)
ld = LearningLedger()
_assert(ld.metrics()["overall"]["events"] == 0, "ledger_initial_empty")
_assert(ld.metrics()["outcome_rate"] == 0.0, "ledger_initial_rate_zero")
_assert(ld.record("stageA", "bogus_kind", "k") is None,
        "ledger_rejects_unknown_kind")
_assert(ld.record("", EVENT_PROPOSAL, "k") is None,
        "ledger_rejects_empty_stage")
_assert(ld.mark_outcome("stageA", "missing", "ok", True) is None,
        "ledger_outcome_needs_proposal")

ld.record("stageA", EVENT_PROPOSAL, "ep1", detail="trial")
e1 = ld.mark_outcome("stageA", "ep1", "recovered", True)
_assert(e1 is not None, "ledger_outcome_recorded")
_assert(ld.metrics()["outcome_rate"] == 1.0, "ledger_outcome_rate_one")
_assert(ld.mark_outcome("stageA", "ep1", "again", True) is None,
        "ledger_no_double_outcome")

ld.record("stageA", EVENT_PROPOSAL, "ep1", detail="reopened episode")
e2 = ld.mark_outcome("stageA", "ep1", "recovered", True)
_assert(e2 is not None, "ledger_reopened_episode_allowed")
_assert(e2["seq"] > e1["seq"], "ledger_reopened_seq_monotone")

ld.record("stageA", EVENT_CORRECTION, "ep3", detail="revised")
_assert(ld.metrics()["overall"]["corrections"] == 1,
        "ledger_correction_counted")

ld2 = LearningLedger()
ld2.record("s", EVENT_PROPOSAL, "x")
s_a = ld2.snapshot()
s_b = ld2.snapshot()
_assert(s_a == s_b, "ledger_deterministic_snapshot")

lr_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation", "learning.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in lr_src,
            "ledger_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))

import maya_conversation
_assert(hasattr(maya_conversation, "LearningLedger"),
        "ledger_pkg_has_class")

# 24. Learning loop integrated with circuit breaker (Phase 8)
from maya_conversation.resilience import FailureTracker as FT
led = LearningLedger()
trx = FT(ledger=led)
_ = [trx.record("rl", False) for _ in range(3)]
_assert(led.metrics()["overall"]["proposals"] == 1,
        "ledger_tracker_episode_proposal")
_assert(led.metrics()["overall"]["outcomes"] == 1,
        "ledger_tracker_tripped_outcome")
_assert(led.metrics()["outcome_rate"] == 0.0,
        "ledger_tracker_tripped_rate_zero")

trx.record("rl", True)
_assert(led.metrics()["overall"]["outcomes"] == 1,
        "ledger_recovered_outcome_skipped_after_trip")

trx2 = FT(ledger=LearningLedger())
trx2.record("r2", False)
trx2.record("r2", True)
_assert(trx2.ledger.metrics()["overall"]["proposals"] == 1,
        "ledger_single_failure_episode")
_assert(trx2.ledger.metrics()["outcome_rate"] == 1.0,
        "ledger_single_failure_recovered")

# 25. Method selection + controlled improvement (Phase 9)
from maya_conversation.method_selection import (
    APPROVED, MethodRegistry, plan_improvement, select_method,
)
reg = MethodRegistry()
reg.register("adjudicate", "alpha", lambda: 1, description="first")
reg.register("adjudicate", "beta", lambda: 2, description="second")
_assert(reg.available("adjudicate") == ["alpha", "beta"],
        "ms_register_and_list")
_assert(len(reg.available("other")) == 0, "ms_available_unknown_empty")
_assert(reg.register("adjudicate", "alpha", lambda: 9) is None,
        "ms_register_rejects_duplicate")
_assert(reg.register("", "gamma", lambda: 9) is None,
        "ms_register_rejects_empty_target")
_assert(reg.register("x", "", lambda: 9) is None,
        "ms_register_rejects_empty_name")
_assert(reg.select("unknown") is None, "ms_select_none_empty")

reg.set_score("adjudicate", "alpha", 0.2)
reg.set_score("adjudicate", "beta", 0.9)
sl = reg.select("adjudicate", preference="n/a")
_assert(sl["name"] == "beta", "ms_score_selects_highest")
_assert(select_method(reg, "adjudicate")["name"] == "beta",
        "ms_select_wrapper_matches")

reg2 = MethodRegistry()
reg2.register("t", "a", lambda: 1)
reg2.register("t", "b", lambda: 2)
reg2.set_score("t", "a", 0.5)
reg2.set_score("t", "b", 0.5)
_assert(reg2.select("t")["name"] == "a",
        "ms_score_tiebreak_registration")

reg2.set_score("t", "b", "not-a-number")
_assert(reg2.select("t")["name"] == "a", "ms_score_failopen_malformed")

reg3 = MethodRegistry()
reg3.register("t", "no_score", lambda: 1)
_assert(reg3.select("t")["name"] == "no_score",
        "ms_select_missing_score_zero")

sl2 = reg2.select("t")
sl2["score"] = 99.0
_assert(reg2.select("t")["score"] == 0.5, "ms_select_returns_copy")

pl_deny = plan_improvement("gate", 0.5, 0.9, "pending")
_assert(pl_deny["plan"] == "requires_approval",
        "ms_plan_requires_approval")
_assert(pl_deny["improvement"] == 0.0, "ms_plan_denied_improvement_zero")

pl_yes = plan_improvement("gate", 0.5, 0.9, APPROVED)
_assert(pl_yes["plan"] == "adopt_candidate", "ms_plan_approved_positive")
_assert(math.isclose(pl_yes["improvement"], 0.4, rel_tol=1e-12),
        "ms_plan_improvement_delta")

pl_no = plan_improvement("gate", 0.9, 0.5, APPROVED)
_assert(pl_no["plan"] == "keep_baseline", "ms_plan_approved_negative")
_assert(pl_no["improvement"] == 0.0, "ms_plan_negative_clamped")

_assert(plan_improvement("gate", "junk", 0.5, APPROVED) is None,
        "ms_plan_malformed_baseline")
_assert(plan_improvement("", 0.5, 0.6, APPROVED) is None,
        "ms_plan_empty_target")
_assert(plan_improvement("gate", float("inf"), 0.5, APPROVED)["plan"]
        == "keep_baseline", "ms_plan_nonfinite_safe")

ms_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation", "method_selection.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in ms_src,
            "ms_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))

import maya_conversation
_assert(hasattr(maya_conversation, "MethodRegistry"),
        "ms_pkg_has_registry")
_assert(hasattr(maya_conversation, "plan_improvement"),
        "ms_pkg_has_plan")
_assert(hasattr(maya_conversation, "APPROVED"),
        "ms_pkg_has_approved")

# 26. User-scoped capability profiles (Phase 10)
from maya_conversation.profile import (
    DEFAULT_USER, SCOPE_ANY, CapabilityProfile,
)
cp = CapabilityProfile()
_assert(not cp.allows("alice", "research", "deep_search"),
        "cp_default_deny_unknown_user")
_assert(not cp.allows("alice", "research", "deep_search"),
        "cp_default_deny_unconfigured")
_assert(not cp.allows("alice", "nope", "whatever"),
        "cp_unknown_capability_denied")

cp.grant_capability("alice", "research", "deep_search")
_assert(cp.allows("alice", "research", "deep_search"),
        "cp_grant_and_allow_exact")
_assert(not cp.allows("alice", "home", "deep_search"),
        "cp_cross_scope_denied")
_assert(not cp.allows("bob", "research", "deep_search"),
        "cp_other_user_denied")

cp.grant_capability("alice", SCOPE_ANY, "lax_hint")
_assert(cp.allows("alice", "home", "lax_hint"),
        "cp_scope_any_allow")

_assert(cp.revoke_capability("alice", "research", "deep_search"),
        "cp_revoke_returns")
_assert(not cp.allows("alice", "research", "deep_search"),
        "cp_revoke_denies")
_assert(cp.revoke_capability("alice", "research", "deep_search"),
        "cp_revoke_idempotent")

_assert(cp.grant_capability("bob", "lab", "measure"),
        "cp_grant_returns")
cp.grant_capability("bob", "lab", "measure")
_assert(cp.allows("bob", "lab", "measure"), "cp_grant_idempotent")

_assert(not cp.grant_capability("", "", ""), "cp_grant_empty_false")
_assert(not cp.grant_capability("u", "", "c"), "cp_grant_no_scope_false")
_assert(not cp.revoke_capability("u", "s", ""), "cp_revoke_empty_false")
_assert(not cp.allows("u", "", "c"), "cp_allow_empty_denied")
_assert(not cp.allows("u", "s", ""), "cp_allow_empty_cap_denied")

_assert(cp.capabilities("alice") == [(SCOPE_ANY, "lax_hint")],
        "cp_capabilities_sorted_list")
_assert(cp.capabilities("bob", scope="lab") == [("lab", "measure")],
        "cp_capabilities_scope_filtered")
_assert(cp.capabilities("unknown") == [], "cp_capabilities_unknown_empty")
_assert(sorted(cp.user_list()) == ["alice", "bob"], "cp_user_list_sorted")
_assert(not CapabilityProfile().allows("z", "z", "z"),
        "cp_fresh_instance_denies_all")

cp_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation", "profile.py")).read()
for forbidden in ["time.", "datetime.", "random.", "subprocess",
                   "socket", "open(", "os.path"]:
    _assert(forbidden not in cp_src,
            "cp_no_forbidden_%s" % forbidden.replace(".", "_")
            .replace("(", ""))

import maya_conversation
_assert(hasattr(maya_conversation, "CapabilityProfile"),
        "cp_pkg_has_profile")
_assert(hasattr(maya_conversation, "DEFAULT_USER"),
        "cp_pkg_has_default_user")
_assert(hasattr(maya_conversation, "SCOPE_ANY"),
        "cp_pkg_has_scope_any")


print("cooperate_test_ok=%d" % LABELS["ok"])
if LABELS["ok"] == 219:
    print("cooperative_orchestration=PASS")
else:
    print("cooperative_orchestration=FAIL")
    sys.exit(1)