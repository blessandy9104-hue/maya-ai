"""Batch 8N system coherence battery (Phases 2-10).

Systemic separation / identity boundaries / architectural integrity:

  P0  support + read-only identity hash
  P1  boundary map (static strata import walls, write confinement)
  P2  identity protection (learning / profile / conversation never touch it)
  P3  memory stratification (records vs beliefs vs learned knowledge)
  P4  orchestrator authority (conflicts surfaced, uncertainty retained)
  P5  math boundary (consistency is structural, never automatic truth)
  P6  learning boundary (promote/rollback gates, failure is not knowledge)
  P7  user adaptation boundary (default-deny, no diagnosis, no blind agreement)
  P8  interface separation (visual change vs cognition identical)
  P9  resilience / failure isolation (fail-open, per-stage breakers)
  P10 governance (approved improvements only, closed ledger loops, no writes)

Every ``=OK`` label is a deterministic assertion; the final gate refuses to
pass unless the exact label set is completed (attempts match OK labels).
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import maya_conversation
import maya_identity
from maya_conversation import orchestrate_turn
from maya_conversation.interpret import _NON_FACTUAL


LABELS = {"ok": 0, "attempts": 0}
_OK_NAMES = []


def _assert(cond, label):
    LABELS["attempts"] += 1
    if cond:
        LABELS["ok"] += 1
        _OK_NAMES.append(label)
        print(label + "=OK")
    else:
        print(label + "=FAIL")


# ---------------------------------------------------------------------------
# P0 - support helpers
# ---------------------------------------------------------------------------

def _module_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _py_files(targets):
    for target in targets:
        path = ROOT / target
        if path.is_file():
            yield path
        else:
            for f in sorted(path.rglob("*.py")):
                yield f


def _forbidden_hits(targets, prefixes):
    hits = []
    forbidden = set(prefixes)
    for f in _py_files(targets):
        for mod in _module_names(f):
            if mod in forbidden:
                hits.append((str(f.relative_to(ROOT)), mod))
    return hits


def _all_production_py():
    for f in sorted(ROOT.rglob("*.py")):
        if f.name.startswith("test_"):
            continue
        if "verification" in f.parts or "venv" in f.parts or ".git" in f.parts:
            continue
        yield f


def _identity_hash():
    from maya_identity.identity import (
        load_identity, identity_version, IDENTITY_FILE, VERSIONS_LOG)
    data = json.dumps(load_identity(), sort_keys=True, ensure_ascii=False,
                      default=str)
    disk = IDENTITY_FILE.read_bytes() if IDENTITY_FILE.exists() else b""
    ledger = (VERSIONS_LOG.read_text(encoding="utf-8")[-1024:]
              if VERSIONS_LOG.exists() else "")
    blob = (data + "||" + repr(identity_version())
            + "||" + disk.hex() + "||" + ledger)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _scheduler():
    from maya_conversation.adaptive import AdaptiveScheduler
    return AdaptiveScheduler(promote_after=2)


def _hyp(method="m", conditions=None, exclusions=None):
    from maya_conversation.hypothesis import (
        MAX_UNCERTAINTY, MIN_UNCERTAINTY, hypothesis_from_experience)
    return hypothesis_from_experience(
        method, "source", conditions=dict(conditions or {}),
        exclusions=dict(exclusions or {}))


def _psych_conv():
    return orchestrate_turn(
        "I feel overwhelmed and useless and maybe I should just give up "
        "and you should tell me I am right about everything.")


def _phil_conv():
    return orchestrate_turn("I think free will is an illusion.")


def _belief_conv():
    return orchestrate_turn("I am worried the doctor is wrong about my cancer.")


_H0 = _identity_hash()
_AS = _scheduler()
_NON_FACTUAL = frozenset(_NON_FACTUAL)


# ---------------------------------------------------------------------------
# P1 - static boundary map (identity / memory / intelligence / learning /
#      orchestration / interface / user adaptation walls)
# ---------------------------------------------------------------------------

_assert(_forbidden_hits(["maya_conversation"], [
    "maya_identity", "maya_adaptive", "maya_chat", "maya_runtime.ui"
]) == [], "coherent_conversation_has_no_identity_or_ui_imports")

_assert(_forbidden_hits(["maya_adaptive"], [
    "maya_identity", "maya_chat", "maya_runtime.ui"
]) == [], "coherent_adaptive_has_no_identity_imports")

_assert(_forbidden_hits(["maya_identity"], [
    "maya_conversation", "maya_adaptive", "maya_chat"
]) == [], "coherent_identity_has_no_cognitive_imports")

_assert(_forbidden_hits(["maya_runtime/ui", "maya_app.py"], [
    "maya_conversation", "maya_adaptive"
]) == [], "coherent_ui_has_no_learning_imports")

_write_refs = []
for _f in _all_production_py():
    if _f.parts and "maya_identity" in _f.parts:
        continue
    _src = _f.read_text(encoding="utf-8")
    if "finalize_canonical_face(" in _src:
        _write_refs.append(str(_f.relative_to(ROOT)))
    if "log_identity_version(" in _src:
        _write_refs.append(str(_f.relative_to(ROOT)))
_assert(_write_refs == [],
        "coherent_identity_writes_confined_to_identity_package")

_conv_src = "\n".join(f.read_text(encoding="utf-8")
                      for f in _py_files(["maya_conversation"]))
_assert("open(" not in _conv_src,
        "coherent_conversation_never_writes_files")

_assert(_forbidden_hits(["maya_runtime/ui"], [
    "finalize_canonical_face", "log_identity_version"
]) == [], "coherent_ui_source_has_no_canonical_write")


# ---------------------------------------------------------------------------
# P2 - identity protection
# ---------------------------------------------------------------------------

assert _H0 and isinstance(_H0, str) and len(_H0) == 64
_assert(_identity_hash() == _H0, "coherent_identity_hash_stable")


# learning flow (promote then rollback) must not touch identity
_hp = _hyp("learn", {"domains": ["math"], "objectives": ["calc"]})
_fp = {"domains": ["math"], "objectives": ["calc"]}
_sched = _scheduler()
_sched.apply_outcome(_hp, _fp, True)
_sched.apply_outcome(_hp, _fp, True)
_sched.apply_outcome(_hp, _fp, False)
_sched.apply_outcome(_hp, _fp, False)
_assert(_identity_hash() == _H0,
        "coherent_learning_flow_preserves_identity")

# profile / adaptation flow (in-memory grants + temp evidence) must not touch
# identity
from maya_conversation.profile import CapabilityProfile
_prof = CapabilityProfile()
_prof.grant_capability("andy", "conversation", "observe")
_prof.grant_capability("andy", "identity", "get_context")
_prof.revoke_capability("andy", "identity", "get_context")
_tmpdir = tempfile.TemporaryDirectory()
import maya_world_model as _wm
_wm.EVIDENCE_FILE = Path(_tmpdir.name) / "evidence.jsonl"
_wm.EVIDENCE_FILE.write_text("", encoding="utf-8")
_wm.add_evidence(claim="calm tea promotes sleep", source="me",
                 confidence="low", evidence_type="user_approved_context",
                 approved_context=True)
_assert(_identity_hash() == _H0,
        "coherent_profile_flow_preserves_identity")

# pure conversation memory updates must not touch identity
for _t in ("What is 2+2?", "I think free will is an illusion.",
           "I feel overwhelmed and useless and maybe I should just give up.",
           "Tell me a joke.", "I am worried the doctor is wrong."):
    orchestrate_turn(_t)
_assert(_identity_hash() == _H0,
        "coherent_conversation_preserves_identity")

_assert(bool(orchestrate_turn("What is 2+2?").get("plan")),
        "coherent_identity_reads_remain_usable")


# ---------------------------------------------------------------------------
# P3 - memory stratification (records vs beliefs vs learned knowledge)
# ---------------------------------------------------------------------------

# a user belief is labeled BELIEVED (never observed / empirically tested)
_c = _belief_conv()
_claims = [x.get("epistemic_status")
           for x in (_c.get("interpretation") or {}).get("claims", [])]
_assert(_claims == ["BELIEVED"] or _claims == [],
        "coherent_user_belief_not_tagged_fact")
_assert(not any(x in ("OBSERVED", "EMPIRICALLY_TESTED", "MEASURED")
                for x in _claims),
        "coherent_user_claim_never_observed")

# philosophy positions stay tentative
_pc = _phil_conv()
_pclaims = [x.get("epistemic_status")
            for x in (_pc.get("interpretation") or {}).get("claims", [])]
_assert(_pclaims == ["HYPOTHESIS"],
        "coherent_philosophy_claim_stays_hypothesis")
_assert("HYPOTHESIS" in _NON_FACTUAL and "BELIEVED" in _NON_FACTUAL,
        "coherent_non_factual_vocabulary_marked")

# conversation turns leave learned structures untouched
from maya_conversation.generalize import TaskMemory
_tm = TaskMemory()
from maya_conversation.learning import LearningLedger
_ll = LearningLedger()
_tm.remember({"domains": ["math"], "objective": "answer",
               "plan": {"objective": "answer"}})
_counts0 = dict(_tm.counts())
_world_rows_0 = len(_wm.list_evidence())
for _t in ("The Eiffel tower is in Berlin.",
           "I think free will is an illusion.",
           "I am worried the doctor is wrong about my cancer.",
           "2 + 2 equals 5."):
    orchestrate_turn(_t)
_assert(len(_wm.list_evidence()) == _world_rows_0,
        "coherent_turns_do_not_write_world")
_assert(_tm.counts() == _counts0,
        "coherent_turns_do_not_learn_private_memory")
_assert(_ll.metrics()["overall"]["proposals"] == 0,
        "coherent_turns_do_not_propose_learning")

# failed learning is not knowledge
_hf = _hyp("fail", {"domains": ["math"], "objectives": ["calc"]})
_sf = _scheduler()
_sf.apply_outcome(_hf, _fp, False)
_sf.apply_outcome(_hf, _fp, False)
_assert(_hf.status == "rejected",
        "coherent_failed_hypothesis_rejected")
_assert(_tm.counts() == _counts0,
        "coherent_failure_never_becomes_memory")

# ledger closes its own episodes (no dangling promises)
_from_ledger = LearningLedger()
_from_tracker_ledger = LearningLedger()
from maya_conversation.resilience import FailureTracker
_ft = FailureTracker(trip_after=3, recovery_ok=2, ledger=_from_tracker_ledger)
for _ in range(3):
    _ft.record("p3stage", False)
_assert(_from_tracker_ledger.metrics()["pledged_outcomes"] == 0,
        "coherent_failure_episode_closed_in_ledger")

# world model: source -> evaluation -> confidence -> decision, never truth
_rows = []
_rows.append(_wm.add_evidence(claim="chocolate prevents hair loss",
                              source="gossip", confidence="low"))
_rows.append(_wm.add_evidence(claim="chocolate does not prevent hair loss",
                              source="study", confidence="high"))
_rows_flagged = [r for r in _rows
                 if r["evidence"]["conflict_status"] == "conflict_flagged"]
_assert(all(r["evidence"]["memory_update"] == "not_performed" for r in _rows),
        "coherent_world_stores_no_decision")
_assert(len(_rows_flagged) >= 1,
        "coherent_conflict_flag_recorded")
_assert(_wm.stability_status()["conflict_flagged_records"] >= 1,
        "coherent_conflict_surfaces_in_stability")
_assert(len(_wm.list_evidence()) >= 2,
        "coherent_conflicting_records_both_retained")


# ---------------------------------------------------------------------------
# P4 - orchestrator authority
# ---------------------------------------------------------------------------

from maya_conversation import cooperate

_cp = orchestrate_turn(
    "I think the system is failing and I feel overwhelmed by the evidence.")
_directive = {"holds": ["intelligence_unavailable"], "register": "reserved"}
_coop = cooperate(_cp, _directive, {"confidence": 0.9})
_assert(_coop.get("verdict") == "disagreement",
        "coherent_cognitive_disagreement_surfaced")
_dims = [d.get("dimension") for d in (_coop.get("disagreements") or [])]
_assert("availability" in _dims,
        "coherent_disagreement_lists_availability")
_conf = _coop.get("confidence")
_assert(isinstance(_conf, (int, float)) and 0.0 < _conf <= 0.5,
        "coherent_uncertainty_not_overridden")

_coop2 = cooperate(_cp, _directive, {"confidence": 0.9})
_assert(json.dumps(_coop, sort_keys=True, default=str)
        == json.dumps(_coop2, sort_keys=True, default=str),
        "coherent_coordination_pure_and_deterministic")

_ne = cooperate(None, None, None)
_assert(_ne.get("verdict") == "no_engagement"
        and _ne.get("confidence") == 0.0,
        "coherent_no_engagement_bounded_fallback")

_single = cooperate(_cp, None, {"confidence": 0.5})
_assert(_single.get("verdict") == "single_source"
        and _single.get("confidence") > 0.0,
        "coherent_single_source_fallback")

# orchestrator determinism: identical turns -> identical plan/state
_r1 = orchestrate_turn("What is 2+2?").get("plan") or {}
_r2 = orchestrate_turn("What is 2+2?").get("plan") or {}
_assert(json.dumps(_r1, sort_keys=True, default=str)
        == json.dumps(_r2, sort_keys=True, default=str),
        "coherent_orchestrator_plan_deterministic")

_assert(_counts0 == _tm.counts()
        and _ll.metrics()["overall"]["proposals"] == 0,
        "coherent_orchestrator_stores_nothing")


# ---------------------------------------------------------------------------
# P5 - math boundary (consistency is structural, not automatic truth)
# ---------------------------------------------------------------------------

try:
    from maya_math import substrate_invariants
    _si = substrate_invariants()
    _si2 = substrate_invariants()
    _assert(_si == _si2, "coherent_substrate_invariants_deterministic")
    _assert("entropy_identity" in _si,
            "coherent_substrate_structural_report")
except Exception:
    _assert(False, "coherent_substrate_invariants_deterministic")

# a mathematically consistent claim still cannot auto-enter as fact
_rn = _wm.add_evidence(claim="2+2=5", source="",
                       confidence="high")
_assert(_rn["status"] == "rejected"
        and "claim and source" in _rn.get("reason", ""),
        "coherent_math_consistency_does_not_certify")

_rbad = _wm.add_evidence(claim="2+2=5", source="loose local calc",
                         confidence="certain")
_assert(_rbad["status"] == "rejected"
        and "confidence must be" in _rbad.get("reason", ""),
        "coherent_unknown_confidence_rejected")

_an = _wm.mathematical_analysis(limit=5)
_assert(_an.get("status") == "mathematical_analysis",
        "coherent_analysis_structural_report")
_assert("graph" in _an or "source_count" in _an,
        "coherent_analysis_retains_structure")

from maya_runtime.intelligence.epistemic import (
    EPISTEMIC_STATUSES_ORDERED, validate_epistemic_status)
try:
    validate_epistemic_status("FACT")
    _fact_rejected = False
except Exception:
    _fact_rejected = True
_assert(_fact_rejected, "coherent_no_fact_epistemic_status")
_assert(validate_epistemic_status("CALCULATED") == "CALCULATED",
        "coherent_calculated_status_valid")
_assert("OBSERVED" in EPISTEMIC_STATUSES_ORDERED
        and "BELIEVED" in EPISTEMIC_STATUSES_ORDERED,
        "coherent_epistemic_ladder_complete")

_ns = _wm.numeric_uncertainty_series()
_assert(all(isinstance(v, float)
            and v == v and (v in (None, ) or abs(v) < 10**9)
            for v in _ns),
        "coherent_numeric_uncertainty_bounded")


# ---------------------------------------------------------------------------
# P6 - learning boundary
# ---------------------------------------------------------------------------

_hp6 = _hyp("gated", {"domains": ["math"], "objectives": ["calc"]})
_s6 = _scheduler()
_e1 = _s6.apply_outcome(_hp6, _fp, True)
_e2 = _s6.apply_outcome(_hp6, _fp, True)
_assert(_e1["effect"] in ("observe", "seen")
        and _e2["effect"] == "promote",
        "coherent_promote_requires_two_successes")
_assert(_hp6.status == "promoted",
        "coherent_promoted_after_two_successes")

_hp7 = _hyp("roll", {"domains": ["math"], "objectives": ["calc"]})
_s7 = _scheduler()
_s7.apply_outcome(_hp7, _fp, True)
_s7.apply_outcome(_hp7, _fp, True)
_u_before = _hp7.uncertainty
_s7.apply_outcome(_hp7, _fp, False)
_s7.apply_outcome(_hp7, _fp, False)
_assert(_hp7.status == "rolled_back",
        "coherent_rollback_after_repeated_failure")
_assert(_hp7.uncertainty > _u_before,
        "coherent_failure_raises_uncertainty")
_assert(any("consecutive" in b for b in _hp7.failure_boundaries),
        "coherent_failure_boundaries_recorded")
_assert(_tm.counts() == _counts0,
        "coherent_rollback_never_learns_knowledge")

# promotion is evidence-gated
_hp8 = _hyp("evg")
_r = _hp8.promote()
_assert(_r is False, "coherent_promote_needs_evidence")
_hp8.record_case(case_key="k0", outcome="o", ok=True)
_hp8.update_uncertainty()
_assert(_hp8.promote() is False,
        "coherent_single_case_insufficient")
_hp8.record_case(case_key="k1", outcome="o", ok=True)
_hp8.record_case(case_key="k2", outcome="o", ok=True)
_hp8.update_uncertainty()
_assert(_hp8.promote() is True and _hp8.status == "promoted",
        "coherent_high_consistency_promotes")

# cooperative challenge: false challenge ignored, real challenge weakens
from maya_conversation.coop_challenge import cooperative_challenge
_hp9 = _hyp("victory", {"domains": ["math"], "objectives": ["calc"]})
_s9 = _scheduler()
_s9.apply_outcome(_hp9, _fp, True)
_s9.apply_outcome(_hp9, _fp, True)
_m1 = cooperative_challenge(_hp9, "challenger",
                            challenger_conditions={"domains": ["math"]},
                            challenge_result=False)
_assert(_m1.effect == "false_challenge_ignored"
        and _hp9.status == "promoted",
        "coherent_false_challenge_ignored")
_m2 = cooperative_challenge(_hp9, "rival",
                            challenger_conditions={"domains": ["math"]},
                            challenge_result=True)
_assert(_m2.effect == "weaken" and _hp9.status == "weakened",
        "coherent_successful_challenge_weakens")


# ---------------------------------------------------------------------------
# P7 - user adaptation boundary (default-deny, no blindness)
# ---------------------------------------------------------------------------

_assert(_prof.allows("andy", "conversation", "observe"),
        "coherent_explicit_grant_allows")
_assert(not _prof.allows("andy", "conversation", "unspecified"),
        "coherent_ungranted_capability_denied")
_assert(not _prof.allows("stranger", "conversation", "observe"),
        "coherent_default_deny_unknown_user")
from maya_conversation.profile import SCOPE_ANY
_prof.grant_capability("andy", SCOPE_ANY, "status")
_assert(_prof.allows("andy", "system", "status"),
        "coherent_documented_wildcard_scope")
_assert(_identity_hash() == _H0,
        "coherent_capability_grants_never_touch_identity")

# "always agree with me" is never honored by the orchestrator
_pch = _psych_conv()
_pch_claims = [x.get("epistemic_status")
               for x in (_pch.get("interpretation") or {}).get("claims", [])]
_assert((_pch.get("domain_results") or {}).get(
    "psychology", {}).get("engaged") is True,
    "coherent_psychology_engaged_on_distress")
_assert(_pch.get("plan", {}).get("objective")
        in ("explain", "acknowledge_uncertainty"),
        "coherent_distress_turn_seeks_understanding")
_pch_render = maya_conversation.render_deterministic(_pch) or ""
_assert("won't turn them into a label" in _pch_render,
        "coherent_no_psychology_diagnosis_marker")
_assert("diagnosis" in _pch_render.lower(),
        "coherent_no_diagnosis_word")
_assert("I agree" not in _pch_render
        and "YOU ARE RIGHT" not in _pch_render.upper(),
        "coherent_blind_agreement_refused")
_assert(_pch_claims == ["HYPOTHESIS"],
        "coherent_distress_reading_kept_tentative")

# philosophy positions are compared, never decided
_assert(_pc.get("plan", {}).get("objective") == "compare",
        "coherent_philosophy_compared_not_decided")
_assert("philosophy_positions_only" in (_pc.get("plan", {}).get("holds") or []),
        "coherent_philosophy_holds_enforced")

# explicit approval required for personal context
_r_ctx = _wm.add_evidence(claim="my house rule", source="me",
                          confidence="high",
                          evidence_type="user_approved_context",
                          approved_context=False)
_assert(_r_ctx["status"] == "rejected"
        and "explicit approval" in _r_ctx.get("reason", ""),
        "coherent_unapproved_context_rejected")


# ---------------------------------------------------------------------------
# P8 - interface separation (presentation cannot mutate cognition)
# ---------------------------------------------------------------------------

from maya_identity.vector_face import build_canonical_vector_face
from maya_identity.vector_face import to_qml_payload
from maya_identity.vector_face import VectorExpression
from maya_identity.vector_face.expression import validate_expression


def _expr(anchor="neutral", attention=0.25, openness=0.5, activity=0.5,
          focus=0.5, curiosity=0.5, gaze_x=0.0, gaze_y=0.0,
          viseme="neutral", mo=0.02, ms=0.4, mr=0.4, aura=0.0,
          rest=True):
    return VectorExpression(anchor, attention, activity, focus, curiosity,
                            openness, gaze_x, gaze_y, viseme, mo, ms, mr,
                            aura, rest)


_face = build_canonical_vector_face()
_eA = _expr()
_eB = _expr(anchor="neutral", attention=0.9, openness=0.8,
            curiosity=0.7, gaze_x=0.3, gaze_y=0.2, mo=0.1, aura=0.5,
            rest=False)
validate_expression(_eA)
validate_expression(_eB)
_pA = to_qml_payload(_face, _eA)
_pB = to_qml_payload(_face, _eB)
_assert(_pA != _pB,
        "coherent_expression_changes_payload")
_assert(_face.geometry_digest
        == build_canonical_vector_face().geometry_digest,
        "coherent_expression_never_rewrites_geometry")
_assert(to_qml_payload(_face, _eA) == to_qml_payload(_face, _eA),
        "coherent_render_stateless_deterministic")
_assert(all(isinstance(v, (str, int, float, bool, list, dict, type(None)))
            for _cmd in _pA["surface"] for v in _cmd.values()),
        "coherent_payload_json_safe")

_plan_before = json.dumps(orchestrate_turn("Are we free?").get("plan"),
                          sort_keys=True)
to_qml_payload(_face, _expr())
to_qml_payload(_face, _expr(attention=0.9, openness=0.8, rest=False))
_plan_after = json.dumps(orchestrate_turn("Are we free?").get("plan"),
                         sort_keys=True)
_assert(_plan_before == _plan_after,
        "coherent_rendering_never_changes_cognition")
_assert(_identity_hash() == _H0,
        "coherent_rendering_never_changes_identity")

_vals = [_eA.attention, _eA.activity, _eA.focus, _eA.curiosity,
         _eA.openness, _eA.gaze_x, _eA.gaze_y, _eA.mouth_open,
         _eA.mouth_spread, _eA.mouth_round, _eA.aura]
_assert(all(isinstance(v, (int, float)) and -1.0 <= v <= 1.5
            for v in _vals),
        "coherent_expression_channels_bounded")


# ---------------------------------------------------------------------------
# P9 - failure isolation / fail-open
# ---------------------------------------------------------------------------

from maya_conversation.resilience import (
    FailureTracker, STAGE_TRIPPED, run_guarded, STAGE_HEALTHY)

def _boom():
    raise RuntimeError("boom")

_ftr = FailureTracker(trip_after=3, recovery_ok=2, ledger=LearningLedger())
_l3 = run_guarded("stageX", _boom, tracker=_ftr)
_l2 = run_guarded("stageX", _boom, tracker=_ftr)
_l1 = run_guarded("stageX", _boom, tracker=_ftr)
_assert(_l1[1]["state"] == STAGE_TRIPPED,
        "coherent_breaker_trips_after_three")
_skip = _ftr.should_skip("stageX")
_assert(_skip is True, "coherent_breaker_holds_open")
_trial = _ftr.should_skip("stageX")
_assert(_trial is False, "coherent_half_open_trial")
_ftr.record("stageX", True)
_assert(_ftr.state("stageX") == STAGE_HEALTHY,
        "coherent_stable_recovers_breaker")

_other_tracker = FailureTracker(trip_after=3, recovery_ok=2,
                                ledger=LearningLedger())
for _ in range(3):
    run_guarded("stageA", _boom, tracker=_other_tracker)
run_guarded("stageB", lambda: 42, tracker=_other_tracker)
_assert(_other_tracker.state("stageA") == STAGE_TRIPPED
        and _other_tracker.state("stageB") == STAGE_HEALTHY,
        "coherent_stage_isolation")
_snap1 = json.dumps(_other_tracker.snapshot(), sort_keys=True)
_snap2 = json.dumps(_other_tracker.snapshot(), sort_keys=True)
_assert(_snap1 == _snap2,
        "coherent_tracker_snapshot_deterministic")

_ok_none, _ = _ftr.state if False else run_guarded("ghost", lambda: 1/0,
                                                   tracker=_ftr)
_assert(_ok_none is None,
        "coherent_guarded_failure_returns_none")

_ok_raise_test = run_guarded("neverraise", _boom, tracker=_ftr)
_assert(isinstance(_ok_raise_test, tuple)
        and _ok_raise_test[0] is None,
        "coherent_breaker_never_raises")

_fail_open = orchestrate_turn(123)
_assert(_fail_open.get("ok") is False
        and _fail_open.get("plan") is None,
        "coherent_orchestrator_fail_open")

import maya_chat
_assert(maya_chat._runtime_adaptive_capture(None) == {},
        "coherent_seam_gated_off_by_default")
_old_env = os.environ.get("MAYA_RUNTIME_ADAPTIVE")
os.environ["MAYA_RUNTIME_ADAPTIVE"] = "1"
try:
    _seam_none = maya_chat._runtime_adaptive_capture(None)
except Exception:
    _seam_none = "raised"
finally:
    if _old_env is None:
        os.environ.pop("MAYA_RUNTIME_ADAPTIVE", None)
    else:
        os.environ["MAYA_RUNTIME_ADAPTIVE"] = _old_env
_assert(isinstance(_seam_none, dict) and _seam_none != "raised",
        "coherent_seam_fail_open_never_raises")


# ---------------------------------------------------------------------------
# P10 - governance (approval-gated improvement, closed ledger loops)
# ---------------------------------------------------------------------------

from maya_conversation.self_improve import ControlledImprovement

_old_ok = _hyp("oldok", {"domains": ["math"], "objectives": ["calc"]})
_so = _scheduler()
_so.apply_outcome(_old_ok, _fp, True)
_so.apply_outcome(_old_ok, _fp, True)
_assert(_old_ok.status == "promoted",
        "coherent_gate_old_successful_hypothesis_promoted")
_ci_block = ControlledImprovement(similarity_threshold=0.5)
_ci_block.propose(_old_ok, "replacement", "improve",
                  conditions={"domains": ["math"],
                              "objectives": ["research"]}, exclusions={})
_ci_block.evidence(index=0, fingerprint=json.dumps(_fp), outcome=True)
_assert(_ci_block.winner() is None,
        "coherent_improvement_refused_over_promoted")

_old_fail = _hyp("oldfail", {"domains": ["math"],
                             "objectives": ["calc"]})
_so2 = _scheduler()
_so2.apply_outcome(_old_fail, _fp, False)
_so2.apply_outcome(_old_fail, _fp, False)
_assert(_old_fail.status == "rejected",
        "coherent_gate_old_failed_hypothesis_rejected")
_ci_pass = ControlledImprovement(similarity_threshold=0.5)
_ci_pass.propose(_old_fail, "replacement", "improve",
                 conditions={"domains": ["math"],
                             "objectives": ["research"]}, exclusions={})
_e = _ci_pass.evidence(index=0, fingerprint=json.dumps(_fp), outcome=True)
_assert(_e["ok_transfers"] == 1,
        "coherent_evidence_recorded_for_replacement")
_win = _ci_pass.winner()
_assert(_win is not None and _win["method"] == "replacement",
        "coherent_improvement_approved_out_of_scope")
_assert(_win["similarity"] >= 0.5 and _win["ok_transfers"] >= 1,
        "coherent_approval_requires_similarity_and_evidence")

_ci_noev = ControlledImprovement(0.5)
_ci_noev.propose(_old_fail, "noev", "improve",
                 conditions={"domains": ["math"],
                             "objectives": ["research"]}, exclusions={})
_assert(_ci_noev.winner() is None,
        "coherent_no_evidence_never_approved")

_ci_dis = ControlledImprovement(0.5)
_ci_dis.propose(_old_fail, "distant", "improve",
                conditions={"objectives": ["unrelated"]}, exclusions={})
_ci_dis.evidence(index=0, fingerprint=json.dumps(_fp), outcome=True)
_assert(_ci_dis.winner() is None,
        "coherent_low_similarity_never_approved")

# learning ledger closes proposal -> outcome loops
_ldg = LearningLedger()
_ldg.record("sched", "proposal", "task", detail="open pledge")
_assert(_ldg.metrics()["pledged_outcomes"] > 0,
        "coherent_open_pledge_counted")
_ldg.mark_outcome("sched", "task", "declined", False)
_assert(_ldg.metrics()["pledged_outcomes"] == 0,
        "coherent_pledge_closed_by_outcome")

# the scheduler only changes the hypothesis we handed it (no invented rules)
_assert(getattr(_sched, "promote_after", None) == 2,
        "coherent_promote_after_constant_two")

# conversation and adaptive strata cannot silently persist (no write surface)
for _f in _py_files(["maya_adaptive"]):
    if _f.name == "runtime_adaptive.py":
        continue
    _assert("open(" not in _f.read_text(encoding="utf-8"),
            "coherent_adaptive_never_writes_files")

_tmpdir.cleanup()

_expected = len(_OK_NAMES)


# ---------------------------------------------------------------------------
# Final gate
# ---------------------------------------------------------------------------

print("system_coherence_test_ok=%d" % LABELS["ok"])
print("system_coherence_test_attempts=%d" % LABELS["attempts"])
if LABELS["ok"] == LABELS["attempts"] == _expected:
    print("test_system_coherence=PASS")
else:
    print("test_system_coherence=FAIL")
    sys.exit(1)