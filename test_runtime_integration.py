"""Batch 8J runtime adaptive integration battery.

Grows phase by phase (P2 adapter boundary, P3 live capture, P4 live outcome,
P5 live method adaptation, P6 live generalization, P7 cooperative challenge,
P8 rollback/safety, P10 latency, P11 sabotage). Every ``=OK`` label is a
deterministic, independently-recomputed assertion.
"""
from __future__ import annotations
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LABELS = {"ok": 0, "attempts": 0}

def _assert(cond, label):
    LABELS["attempts"] += 1
    if cond:
        LABELS["ok"] += 1
        print(label + "=OK")
    else:
        print(label + "=FAIL")

import maya_conversation
from maya_conversation import plan as _plan_mod

_pre_imported = "maya_adaptive.runtime_adaptive" not in sys.modules

from maya_adaptive.runtime_adaptive import (
    RuntimeAdaptive, enabled, _verify_objective_vocabulary,
    _OBJECTIVES, ENV_ENABLE, _public, _method_spec)


# --------------------------------------------------------------------------
# P2 — adapter boundary (bounded capability, opt-in)
# --------------------------------------------------------------------------

_MODULE_SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "maya_adaptive", "runtime_adaptive.py")
                   ).read()
import ast
_tree = ast.parse(_MODULE_SRC)
_broken_names = set()
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Name):
        _broken_names.add(_node.id)
    elif isinstance(_node, ast.Attribute) and isinstance(_node.value, ast.Name):
        _broken_names.add(_node.value.id)
    if isinstance(_node, (ast.Import, ast.ImportFrom)):
        for _alias in _node.names:
            _root = _alias.name.split(".")[0]
            _broken_names.add(_root)
_forbidden_in_30times = ("time", "datetime", "random", "subprocess",
                         "socket", "os")
for _nb, _forbidden in enumerate(("time", "datetime", "random",
                                  "subprocess", "socket")):
    _assert(_forbidden not in _broken_names,
            "rtj2_no_forbidden_%d" % _nb)
_assert(_MODULE_SRC.count("open(") == 1,
        "rtj2_open_single_site")
_assert("open(" not in _MODULE_SRC.split("def _journal_append")[0],
        "rtj2_no_open_before_journal")
_assert(_pre_imported, "rtj2_package_does_not_auto_import")

_prev_env = os.environ.pop(ENV_ENABLE, None)
try:
    _default_off = not enabled()
finally:
    if _prev_env is not None:
        os.environ[ENV_ENABLE] = _prev_env
_assert(_default_off, "rtj2_disabled_by_default_env")

_dis = RuntimeAdaptive()
_assert(not _dis.enable, "rtj2_disable_flag")
_assert(_dis.capture({}) is None, "rtj2_capture_none_when_off")
_assert(_dis.observe({}, "full_standard", True) is None,
        "rtj2_observe_none_when_off")
_assert(_dis.suggest({}) is None, "rtj2_suggest_none_when_off")
_assert(_dis.challenge("full_standard", {}) is None,
        "rtj2_challenge_none_when_off")
_assert(_dis.rollback("full_standard") is None, "rtj2_rollback_none_when_off")
_assert(_dis.counters() is None, "rtj2_counters_none_when_off")
_assert(_dis.status()["enabled"] is False, "rtj2_status_reports_off")

_rt = RuntimeAdaptive(enable=True)
_assert(_rt.enable, "rtj2_enable_explicit")

_cap = _rt.capture({}, user_text="private phrase should not leak")
_assert(_cap is not None, "rtj2_capture_enabled")
_assert(_cap.get("text_signature") == "", "rtj2_capture_strips_text")
_assert(_cap.get("input_brief") is False, "rtj2_capture_strips_brief")
_assert(_cap.get("key") and "=" in _cap.get("key", ""),
        "rtj2_capture_canonical_key")
_assert("private phrase" not in _cap.get("key", ""),
        "rtj2_capture_key_has_no_raw_text")
_assert(_rt.counters()["total_sightings"] >= 1, "rtj2_capture_memory")

_assert(_public({}) == {}, "rtj2_public_empty")
_pub = _public({"text_signature": "x", "input_brief": True, "domains": []})
_assert("text_signature" not in _pub and "input_brief" not in _pub,
        "rtj2_public_strips_private")
_priv_raw = {"text_signature": "SECRET MARKER 8J", "input_brief": True,
             "domains": ["math"], "objective": "answer"}
_priv_pub = _public(_priv_raw)
_assert("text_signature" not in _priv_pub and "input_brief" not in _priv_pub
        and "SECRET MARKER 8J" not in str(_priv_pub),
        "rtj2_private_roundtrip_stripped")

_his = _rt.portfolio.history()
_names = {m["name"] for m in _his["methods"]}
_assert({"lean_fast", "math_precise", "guard_careful", "full_standard"} <=
        _names, "rtj2_methods_registered")
_assert(len(_names) == 4, "rtj2_method_count")

_sug = _rt.suggest({"resource_level": "pressure",
                    "consequence_level": "ordinary",
                    "domains": ["math"], "math_structure": False,
                    "objective": "answer"})
_assert(_sug is not None and _sug.get("rejectable") is True,
        "rtj2_suggest_advisory_rejectable")
_sug2 = _rt.suggest({"consequence_level": "elevated_guard",
                     "resource_level": "pressure", "domains": [],
                     "math_structure": False, "objective": "answer"},
                    prefer=["guard_careful"])
_assert(_sug2 and _sug2["method"] == "guard_careful",
        "rtj2_guard_careful_eligible")
_fp_reject = {"resource_level": "pressure", "consequence_level":
              "elevated_guard", "domains": ["math"], "math_structure": True,
              "objective": "answer"}
_sug3 = _rt.suggest(_fp_reject, reject=["guard_careful"])
_assert(_sug3 is not None and _sug3["method"] != "guard_careful",
        "rtj2_suggest_honors_reject")

_fp_math = {
    "domains": ["math"], "primary_intent": "compute", "objective": "calculate",
    "constraints": ["integer units"], "references_resolved": 0,
    "ambiguous": False, "is_correction": False, "modality": "text",
    "math_structure": True, "evidence_types": ["fact"],
    "consequence_level": "ordinary", "resource_level": "safe",
}
_obs1 = _rt.observe(_fp_math, "math_precise", True)
_assert(_obs1 is not None and _obs1["effect"]["effect"] == "observe",
        "rtj2_observe_ledger_episode")
_assert(_obs1["status"] == "tested", "rtj2_first_case_tested")
_obs2 = _rt.observe(_fp_math, "math_precise", True)
_assert(_obs2["effect"]["effect"] == "promote",
        "rtj2_promotion_after_two_ok")
_assert(_obs2["status"] == "promoted", "rtj2_promoted_status")
_assert(_obs2["fingerprint_key"] == _obs1["fingerprint_key"],
        "rtj2_ledger_provenance_key")
_assert(_obs2["uncertainty"] <= 0.35, "rtj2_uncertainty_gate_satisfied")

_assert(set(_verify_objective_vocabulary()) ==
        set(_plan_mod.objective_vocabulary()),
        "rtj2_objective_vocabulary_parity")
_assert(_OBJECTIVES == frozenset(_plan_mod.objective_vocabulary()),
        "rtj2_objective_exact_parity")

_spec = _method_spec("lean_fast")
_assert(_spec["conditions"].get("resource_level") == "pressure",
        "rtj2_lean_fast_spec")
_assert(_method_spec("guard_careful")["conditions"].get(
    "consequence_level") == "elevated_guard", "rtj2_guard_spec")
_assert(_method_spec("full_standard")["conditions"] == {},
        "rtj2_standard_spec")

_rt2 = RuntimeAdaptive(enable=True)
_o1 = _rt2.observe(_fp_math, "math_precise", True)
_rt3 = RuntimeAdaptive(enable=True)
_o2 = _rt3.observe(_fp_math, "math_precise", True)
for _dfield in ("key", "fingerprint_key", "ok", "method", "outcome",
                "status"):
    _assert(_o1.get(_dfield) == _o2.get(_dfield),
            "rtj2_determinism_%s" % _dfield)


# journal: bounded append, privacy-stripped, fail-open
import tempfile, json as _json
_tmpdir = tempfile.mkdtemp(prefix="rtj8j_")
_jpath = os.path.join(_tmpdir, "journal.jsonl")
_jrt = RuntimeAdaptive(enable=True, journal=_jpath)
_fp_plain = {"resource_level": "safe", "consequence_level": "ordinary",
             "domains": ["math"], "math_structure": False,
             "objective": "answer"}
_fp_a = dict(_fp_plain)
_fp_a["constraints"] = ["alpha units"]
_fp_b = dict(_fp_plain)
_fp_b["constraints"] = ["beta units"]
_jrt.observe(_fp_a, "full_standard", True)
_jrt.observe(_fp_b, "full_standard", False)
_lines = []
with open(_jpath, encoding="utf-8") as _fh:
    _lines = [l for l in _fh.read().splitlines() if l.strip()]
_assert(len(_lines) == 2, "rtj2_journal_appends")
_payloads = [_json.loads(l) for l in _lines]
_assert(all("text_signature" not in p and "input_brief" not in p
            for p in _payloads), "rtj2_journal_privacy")
_assert(_jrt._journal_seen == 2, "rtj2_journal_seq_count")
_assert(_jrt.ledger.metrics()["pledged_outcomes"] == 0,
        "rtj2_ledger_closed_loop")
import shutil
shutil.rmtree(_tmpdir, ignore_errors=True)

_sta = _rt.status()
_assert(_sta["enabled"] is True, "rtj2_status_enabled")
_assert(isinstance(_sta["counters"], dict), "rtj2_status_counters")


# --------------------------------------------------------------------------
# P3/P4 — live task capture + outcome recording at the real generation seam
# --------------------------------------------------------------------------

import maya_chat as _maya_chat
from maya_conversation import build_orchestrator as _build_orchestrator

_seam_prev = os.environ.get("MAYA_RUNTIME_ADAPTIVE")
os.environ.pop("MAYA_RUNTIME_ADAPTIVE", None)
try:
    _off_ctx = _maya_chat._runtime_adaptive_capture({"ok": False})
finally:
    if _seam_prev is not None:
        os.environ["MAYA_RUNTIME_ADAPTIVE"] = _seam_prev
_assert(_off_ctx == {}, "rtj2_seam_off_by_default")

_conv_real = _build_orchestrator("rtj8j_live_probe")(
    "If two trains leave platforms 40 minutes apart and the first "
    "travels at 60 km/h, how far apart will they be in 2 hours?")
_assert(bool(_conv_real.get("ok")), "rtj2_probe_conv_generates")

_rt_live = RuntimeAdaptive(enable=True)
_fp_live = _rt_live.capture(_conv_real, resource_pressure=False)
_assert(_fp_live is not None, "rtj2_live_capture_real_conv")
_assert(_fp_live["math_structure"] is True, "rtj2_live_capture_math")
_assert("domains" in _fp_live and "objective" in _fp_live and
        "consequence_level" in _fp_live and "resource_level" in _fp_live,
        "rtj2_live_capture_shape")
_assert(not _fp_live.get("text_signature") and
        not _fp_live.get("input_brief"), "rtj2_live_capture_no_raw_text")

_env_ctx = None
try:
    os.environ["MAYA_RUNTIME_ADAPTIVE"] = "1"
    _env_ctx = _maya_chat._runtime_adaptive_capture(
        _conv_real, resource_pressure=False)
finally:
    os.environ.pop("MAYA_RUNTIME_ADAPTIVE", None)
_assert(bool(_env_ctx) and "fp" in _env_ctx and "advice" in _env_ctx and
        "adapter" in _env_ctx, "rtj2_seam_env_on")
_assert(not _env_ctx["fp"].get("text_signature") and
        not _env_ctx["fp"].get("input_brief"), "rtj2_seam_privacy")
_assert(_env_ctx["advice"].get("method") in
        ("full_standard", "math_precise", "lean_fast", "guard_careful"),
        "rtj2_seam_advisory_method")
_fail_open = None
try:
    os.environ["MAYA_RUNTIME_ADAPTIVE"] = "1"
    _fail_open = _maya_chat._runtime_adaptive_capture([1, 2, 3], False)
finally:
    os.environ.pop("MAYA_RUNTIME_ADAPTIVE", None)
_assert(not isinstance(_fail_open, Exception), "rtj2_seam_fail_open")

_row = _env_ctx["adapter"].observe(_env_ctx["fp"], "full_standard", True)
_assert(_row is not None and _row["effect"]["effect"] == "observe",
        "rtj2_live_outcome_recording")
_assert(_env_ctx["adapter"].ledger.metrics()["overall"]["proposals"] >= 1 and
        _env_ctx["adapter"].ledger.metrics()["overall"]["outcomes"] >= 1,
        "rtj2_live_ledger_moves")
_assert(_env_ctx["adapter"].ledger.metrics()["pledged_outcomes"] == 0,
        "rtj2_live_ledger_closed")

import maya_conversation
_mc_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "maya_chat.py")).read()
_assert("MAYA_RUNTIME_ADAPTIVE" in _mc_src and
        "rtj_ctx = _runtime_adaptive_capture(" in _mc_src,
        "rtj2_seam_wired_in_production")
_assert('["adapter"].observe(' in _mc_src, "rtj2_seam_outcome_wired")


# --------------------------------------------------------------------------
# P5 / P6 / P7 / P8 — live adaptation, generalization, challenge, rollback
# --------------------------------------------------------------------------

_conv_guard = _build_orchestrator("rtj8j_guard_probe")(
    "Is consciousness just an illusion, according to philosophy?")
_ra5 = RuntimeAdaptive(enable=True)
_fp_guard = _ra5.capture(_conv_guard, resource_pressure=True)
_assert(_fp_guard is not None and
        _fp_guard["consequence_level"] == "elevated_guard",
        "rtj2_guard_live_fingerprint")
_adv_guard = _ra5.suggest(_fp_guard)
_assert(_adv_guard and _adv_guard["method"] == "guard_careful",
        "rtj2_advice_requires_guard_careful")
_adv_guard_rej = _ra5.suggest(_fp_guard, reject=["guard_careful"])
_assert(_adv_guard_rej and _adv_guard_rej["method"] == "full_standard",
        "rtj2_advice_guard_rejectable")
_adv_math = _ra5.suggest(_fp_guard)
_assert(_adv_math.get("advisory") is True and
        _adv_math.get("rejectable") is True, "rtj2_advice_flags_present")

_c1 = dict(_conv_real)
_c1["interpretation"] = dict(_conv_real.get("interpretation") or {})
_c1["interpretation"]["constraints"] = ["one unit"]
_c2 = dict(_conv_real)
_c2["interpretation"] = dict(_conv_real.get("interpretation") or {})
_c2["interpretation"]["constraints"] = ["two units"]
_ra6 = RuntimeAdaptive(enable=True)
_r1 = _ra6.capture(_c1)
_r2 = _ra6.capture(_c2)
_assert(_r1["key"] != _r2["key"], "rtj2_new_case_distinct_key")
_assert(_r1["occurrences"] == 1 and _ra6.recall(_r1)["seen"] is True,
        "rtj2_new_case_seen_state")
_ks = _ra6.counters()
_assert(_ks["total_sightings"] == 2 and _ks["distinct_tasks"] == 2,
        "rtj2_memory_tracks_two_cases")
_ok1 = _ra6.observe(_r1, "math_precise", True)
_ok2 = _ra6.observe(_r1, "math_precise", True)
_assert(_ok1["effect"]["effect"] == "observe" and
        _ok2["effect"]["effect"] == "promote",
        "rtj2_live_pair_promotes")
_adv_new = _ra6.suggest(_r2)
_assert(_adv_new and _adv_new["method"] == "math_precise",
        "rtj2_math_generalizes_to_unseen_case")

_ch_vocab = _ra6.challenge(
    "full_standard",
    {"objective": "not_a_real_objective", "consequence_level": "ordinary",
     "resource_level": "safe", "math_structure": False, "domains": ["math"]},
    validators=["vocabulary"])
_assert(_ch_vocab["challenge_fired"] is True and
        any("outside verified vocabulary" in str(r)
            for r in _ch_vocab["reasons"]), "rtj2_challenge_vocabulary_fires")
_ch_guard = _ra6.challenge(
    "lean_fast",
    {"objective": "answer", "consequence_level": "elevated_guard",
     "resource_level": "pressure", "math_structure": False,
     "domains": ["safety"]},
    validators=["guard"])
_assert(_ch_guard["challenge_fired"] is True and
        "lean_fast" in str(_ch_guard["reasons"]),
        "rtj2_challenge_guard_fires")
_ch_boundary = _ra6.challenge(
    "math_precise",
    {"objective": "answer", "consequence_level": "ordinary",
     "resource_level": "safe", "math_structure": False,
     "domains": ["math"]},
    validators=["boundary"])
_assert(_ch_boundary["challenge_fired"] is True,
        "rtj2_challenge_boundary_fires")
_ch_clean = _ra6.challenge(
    "full_standard",
    {"objective": "answer", "consequence_level": "ordinary",
     "resource_level": "safe", "math_structure": False,
     "domains": ["math"]},
    validators=["vocabulary", "guard"])
_assert(_ch_clean["challenge_fired"] is False and
        _ch_clean["effect"] == "false_challenge_ignored",
        "rtj2_challenge_clean_no_fire")
_assert(set(_ch_clean["validators_run"]) == {"vocabulary", "guard"},
        "rtj2_challenge_validators_run")

_rb = _ra6.rollback("math_precise")
_assert(_rb is not None and _rb["restored_status"] == "tested",
        "rtj2_rollback_restores_preimage")
_assert(_ra6.ledger.metrics()["overall"]["corrections"] >= 1,
        "rtj2_rollback_correction_recorded")
_assert(_ra6.rollback("full_standard") is None,
        "rtj2_rollback_none_without_preimage")


print("runtime_integration_test_ok=%d" % LABELS["ok"])
print("runtime_integration_test_attempts=%d" % LABELS["attempts"])
if LABELS["ok"] == LABELS["attempts"] == 87:
    print("test_runtime_integration=PASS")
else:
    print("test_runtime_integration=FAIL")
    sys.exit(1)