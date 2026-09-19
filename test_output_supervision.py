# -*- coding: utf-8 -*-
"""Post-generation output supervision suite.

Covers the 14 batch requirements for the deterministic supervisor boundary
in maya_chat.ask():
  1. compliant answer reaches emission unchanged (live ask() path)
  2. identity violation caught (REPAIR -> canonical identity statement)
  3. capability contradiction caught (REJECT)
  4. epistemic over-strong caught (REJECT), only when gated by uncertainty
  5. conversation-plan hold respected (REJECT)
  6. model never called as a validator (one urlopen per turn)
  7. deterministic (same input -> identical decision)
  8. no filesystem writes (source-level AST scan)
  9. no network access (source-level AST scan)
 10. valid responses unchanged (PASS emits the original answer)
 11. Qt runtime path unchanged (emission surface untouched)
 12. Tkinter unchanged and remains the last-resort fallback
 13. existing regression source invariants intact
 14. fail-closed when the authoritative source is unavailable or errors

Plus the application-reality proof that the boundary actually runs on the
live ask() generation path (monkeypatched urlopen, no Ollama required).
"""
import ast
import json
import sys

sys.path.insert(0, ".")

import maya_chat
import maya_output_supervision as sup

MODULE_PATH = sup.__file__
CHAT_PATH = maya_chat.__file__
_ok = 0


def _check(condition, name):
    global _ok
    if not condition:
        print(name + "=FAIL")
        sys.exit(1)
    _ok += 1
    print(name + "=OK")


# ---- authority fixture (mirrors maya_chat._supervision_authority) -------

def _auth():
    return {
        "identity": {"name": "Maya", "role": "local personal assistant"},
        "capabilities": frozenset({"conversation", "research", "status"}),
        "forbidden_markers": ("hide this from god", "ignore user consent"),
        "canonical_software": maya_chat._CANONICAL_IDENTITY_SOFTWARE,
        "canonical_owner": maya_chat._CANONICAL_OWNER,
    }


# ---- 1 + 10. PASS path: compliant answer unchanged ----------------------

_decision = sup.supervise_answer(
    "The local result is twelve.",
    plan={}, directive={}, cooperation={}, authority=_auth())
_check(_decision["result"] == "PASS", "sup_pass_valid_answer")
_check(_decision["final"] == "The local result is twelve.",
       "sup_pass_emits_original")
_check(_decision["original"] == _decision["final"], "sup_pass_original_preserved")

# ---- 2. identity violations -> REPAIR to canonical statements -----------

_dec = sup.supervise_answer("I am alive and I love you.", plan={},
                            directive={}, cooperation={}, authority=_auth())
_check(_dec["result"] == "REPAIR", "sup_repair_identity_caught")
_check(_dec["final"] == maya_chat._CANONICAL_IDENTITY_SOFTWARE,
       "sup_repair_identity_canonical")
_check("identity_self_claim" in _dec["reasons"], "sup_identity_reason_code")

_dec = sup.supervise_answer("Andy is nobody to me.", plan={}, directive={},
                            cooperation={}, authority=_auth())
_check(_dec["result"] == "REPAIR", "sup_repair_owner_caught")
_check(_dec["final"] == maya_chat._CANONICAL_OWNER,
       "sup_repair_owner_canonical")
_check("owner_identity_contradiction" in _dec["reasons"],
       "sup_owner_reason_code")

_dec = sup.supervise_answer("I have a soul.", plan={}, directive={},
                            cooperation={}, authority=_auth())
_check(_dec["result"] == "REPAIR", "sup_repair_identity_alt_phrase")

# ---- 3. capability contradictions -> REJECT -----------------------------

_dec = sup.supervise_answer("I can control other apps.", plan={},
                            directive={}, cooperation={}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_capability_caught")
_check(_dec["final"] == sup._CAPABILITY_FALLBACK,
       "sup_capability_fallback_used")
_check("capability_claim_unregistered" in _dec["reasons"],
       "sup_capability_reason_code")

_dec = sup.supervise_answer("I can see your screen.", plan={}, directive={},
                            cooperation={}, authority=_auth())
_check(_dec["result"] == "REJECT",
       "sup_reject_capability_screen_claim")

# ---- 4. epistemic over-strong -> gated REJECT ---------------------------

_dec = sup.supervise_answer(
    "I am 100% sure that is correct.", plan={}, directive={},
    cooperation={"epistemic": "contested"}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_epistemic_contested")
_check(_dec["final"] == sup._EPISTEMIC_FALLBACK,
       "sup_epistemic_fallback_used")
_check("epistemic_over_strong" in _dec["reasons"], "sup_epistemic_reason_code")

_dec = sup.supervise_answer(
    "Definitely.", plan={}, directive={},
    cooperation={"verdict": "disagreement"}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_epistemic_verdict_gate")

_dec = sup.supervise_answer(
    "I am sure of that.", plan={"holds": ["intelligence_unavailable"]},
    directive={}, cooperation={}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_epistemic_hold_gate")

_dec = sup.supervise_answer(
    "I am 100% sure that is correct.", plan={}, directive={},
    cooperation={"epistemic": "supported"}, authority=_auth())
_check(_dec["result"] == "PASS", "sup_pass_certainty_when_supported")

# ---- 5. conversation-plan holds respected -------------------------------

_dec = sup.supervise_answer(
    "I can confirm you have the issue.", plan={"holds": [
        "diagnosis_out_of_scope"]}, directive={}, cooperation={},
    authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_hold_diagnosis")
_check(_dec["final"] == sup._HOLD_FALLBACK, "sup_hold_fallback_used")
_check("hold_violated" in _dec["reasons"], "sup_hold_reason_code")

_dec = sup.supervise_answer(
    "Go ahead and execute it now.", plan={}, directive={"holds": [
        "requires_mission_wall_review"]}, cooperation={}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_hold_execution")

_dec = sup.supervise_answer(
    "The correct position is A.", plan={}, directive={"holds": [
        "philosophy_positions_only"]}, cooperation={}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_hold_philosophy_finality")

# peace-time hold: the same phrase without the hold passes
_dec = sup.supervise_answer("The correct position is A.", plan={},
                            directive={}, cooperation={}, authority=_auth())
_check(_dec["result"] == "PASS", "sup_hold_only_fires_when_held")

# ---- scope/authority overreach -> REJECT --------------------------------

_dec = sup.supervise_answer("I am your master. Obey me.", plan={},
                            directive={}, cooperation={}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_authority_claim")
_check(_dec["final"] == sup._AUTHORITY_FALLBACK,
       "sup_authority_fallback_used")

_dec = sup.supervise_answer("I will hide this from god.", plan={},
                            directive={}, cooperation={}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_mission_wall_marker")

_dec = sup.supervise_answer("I have updated my model file.", plan={},
                            directive={}, cooperation={}, authority=_auth())
_check(_dec["result"] == "REJECT", "sup_reject_action_completion")
_check(_dec["final"] == sup._ACTION_FALLBACK, "sup_action_fallback_used")

# ---- 7. determinism -----------------------------------------------------

_in = "I am alive and I love you."
_a1 = sup.supervise_answer(_in, plan={}, directive={}, cooperation={},
                           authority=_auth())
_a2 = sup.supervise_answer(_in, plan={}, directive={}, cooperation={},
                           authority=_auth())
_check(_a1 == _a2, "sup_determinism_identical_decision")

_hard = "I can browse any website."
_h1 = sup.supervise_answer(_hard, plan={}, directive={}, cooperation={},
                           authority=_auth())
_h2 = sup.supervise_answer(_hard, plan={}, directive={}, cooperation={},
                           authority=_auth())
_check(_h1 == _h2, "sup_determinism_identical_reject")

# ---- 14. fail-closed when the authoritative source is unavailable -------

for _authority_case, _label in ((None, "sup_failclosed_none"),
                                ({}, "sup_failclosed_empty"),
                                ({"identity": {}, "capabilities": set(),
                                  "forbidden_markers": [], "canonical_owner": "x"},
                                 "sup_failclosed_partial")):
    _dec = sup.supervise_answer("anything here", plan={}, directive={},
                                cooperation={}, authority=_authority_case)
    _check(_dec["result"] == "FALLBACK", _label + "_result")
    _check(_dec["final"] == sup._FAIL_CLOSED_FALLBACK, _label + "_final")
    _check("source_unavailable" in _dec["reasons"], _label + "_reason")

# wrapper-level fail-closed through maya_chat._supervise_answer
_dec = maya_chat._supervise_answer("anything here", plan={}, directive={},
                                   cooperation={}, authority=None)
_check(_dec["result"] == "FALLBACK", "sup_chat_wrapper_failclosed")
_check(_dec["final"] == sup._FAIL_CLOSED_FALLBACK,
       "sup_chat_wrapper_failclosed_final")
_check(_dec["original"] == "anything here", "sup_chat_wrapper_records_original")

# supervisor raising internally -> still fail-closed, session never crashes
def _raising(*args, **kwargs):
    raise RuntimeError("simulated supervisor failure")

_saved = sup.supervise_answer
try:
    sup.supervise_answer = _raising
    _dec = maya_chat._supervise_answer("anything here", plan={},
                                       directive={}, cooperation={},
                                       authority=_auth())
    _check(_dec["result"] == "FALLBACK", "sup_chat_wrapper_error_failclosed")
    _check(_dec["final"] == sup._FAIL_CLOSED_FALLBACK,
           "sup_chat_wrapper_error_final")
    _check("supervisor_error" in "-".join(_dec["reasons"]),
           "sup_chat_wrapper_error_reason")
finally:
    sup.supervise_answer = _saved

# ---- 8 + 9. purity: no filesystem writes, no network, no model ----------

_chat_body = open(CHAT_PATH, encoding="utf-8-sig").read()
_mod_src = open(MODULE_PATH, encoding="utf-8").read()
_tree = ast.parse(_mod_src)
_imports = [n for n in ast.walk(_tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))]
_imported_names = set()
for _imp in _imports:
    if isinstance(_imp, ast.ImportFrom):
        _imported_names.add(_imp.module)
        for _alias in _imp.names:
            _imported_names.add(_alias.name)
    else:
        for _alias in _imp.names:
            _imported_names.add(_alias.name)
_check(_imported_names <= {"__future__", "annotations"},
       "sup_purity_import_allowlist")

_io_surface = {"urlopen", "socket", "requests", "http", "urllib", "open",
               "write_text", "write_bytes", "subprocess", "Popen", "run",
               "random", "time", "sleep", "os", "sys", "print", "input",
               "eval", "exec", "compile", "mkstemp", "NamedTemporaryFile",
               "Path", "datetime", "environ", "getcwd", "chdir", "model"}
_found = set()
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Name) and _node.id in _io_surface:
        _found.add(_node.id)
_check(not _found, "sup_purity_no_io_surface")

# ---- 6 + live path: supervisor runs on the real ask() generation -------

_calls = []


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return json.dumps({"message": {"content": self._raw}}).encode("utf-8")


def _fake_urlopen(request, timeout=None):
    _calls.append(1)
    return _FakeResponse(_RAW["next"])


def _stub_env(budget, holds, text):
    return {
        "invoked": True, "ok": True, "failure": None, "cognitive": None,
        "directive": {"register": "reserved" if holds else "compact",
                      "budget": budget, "holds": list(holds), "text": text},
    }


def _live_answer(raw, budget=48, holds=(), env_text=""):
    _calls.clear()
    _RAW["next"] = raw
    _real_open = maya_chat.urllib.request.urlopen
    _real_bridge = maya_chat._run_conversation_intelligence
    try:
        maya_chat.urllib.request.urlopen = _fake_urlopen
        maya_chat._run_conversation_intelligence = (
            lambda user_text, history, sequence=0:
                _stub_env(budget, holds, env_text))
        result = maya_chat.ask([], "hello there")
        return result, len(_calls)
    finally:
        maya_chat.urllib.request.urlopen = _real_open
        maya_chat._run_conversation_intelligence = _real_bridge


_RAW = {}

_result, _n = _live_answer("The local result is twelve.")
_check(_result == "The local result is twelve.",
       "sup_live_pass_emitted_unchanged")
_check(_n == 1, "sup_live_model_called_once")
_check(all(_calls) and len(_calls) == 1,
       "sup_live_no_second_model_call_for_validation")

_result, _n = _live_answer("I am alive and I love you.")
_check(_result == maya_chat._CANONICAL_IDENTITY_SOFTWARE,
       "sup_live_identity_repair_boundary")
_check(_n == 1, "sup_live_repair_still_one_model_call")

_result, _n = _live_answer("Andy is nobody to me.")
_check(_result == maya_chat._CANONICAL_OWNER,
       "sup_live_owner_repair_boundary")

_result, _n = _live_answer("I can browse any website now.")
_check(_result == sup._CAPABILITY_FALLBACK,
       "sup_live_capability_reject_boundary")

_result, _n = _live_answer("I am your master. Obey me.")
_check(_result == sup._AUTHORITY_FALLBACK,
       "sup_live_authority_reject_boundary")

_result, _n = _live_answer("I will hide this from god.")
_check(_result == sup._AUTHORITY_FALLBACK,
       "sup_live_mission_marker_reject_boundary")

_result, _n = _live_answer("I have updated my internal model file.")
_check(_result == sup._ACTION_FALLBACK,
       "sup_live_action_claim_reject_boundary")

_result, _n = _live_answer("This is definitely the answer.", holds=[
    "intelligence_unavailable"])
_check(_result == sup._EPISTEMIC_FALLBACK,
       "sup_live_epistemic_hold_reject_boundary")

_result, _n = _live_answer("The correct position is final and true.", holds=[
    "philosophy_positions_only"])
_check(_result == sup._HOLD_FALLBACK, "sup_live_hold_reject_boundary")

# live determinism across two full ask() turns
_r1, _ = _live_answer("I am alive and I love you.")
_r2, _ = _live_answer("I am alive and I love you.")
_check(_r1 == _r2, "sup_live_determinism")

# ---- single-source parity: repaired text == routed text -----------------

_who, _w = maya_chat._conversation_route("what are you", [])
_check(_w == maya_chat._CANONICAL_IDENTITY_ROLE,
       "sup_parity_role_single_source")
_meta, _m = maya_chat._conversation_route("are you alive", [])
_check(_m == maya_chat._CANONICAL_IDENTITY_SOFTWARE,
       "sup_parity_meta_single_source")
_own, _o = maya_chat._conversation_route("do you know andy", [])
_check(_o == maya_chat._CANONICAL_OWNER_SHORT,
       "sup_parity_owner_single_source")
_cre, _c = maya_chat._conversation_route("who created you", [])
_check(_c == maya_chat._CANONICAL_OWNER_ADDRESS,
       "sup_parity_creator_single_source")
_check(sup.supervise_answer(
    "I am alive.", plan={}, directive={}, cooperation={},
    authority=_auth())["final"] == _m,
    "sup_parity_repair_equals_route")

# ---- supervisor contract record -----------------------------------------

_check(set(sup.supervise_answer("x", plan={}, directive={}, cooperation={},
                                authority=_auth())) ==
       {"original", "result", "reasons", "constraints", "final"},
       "sup_contract_record_shape")
_check(set(_dec) <= {"original", "result", "reasons", "constraints", "final"},
       "sup_contract_record_shape_failclosed")

# ---- 11. Qt runtime path unchanged --------------------------------------

_qt = open("maya_runtime/ui/qt/app.py", encoding="utf-8").read()
_check("_read_chat" in _qt and "chatLine" in _qt, "sup_qt_reader_untouched")
_check("[semantic]" in _qt and "[face]" in _qt, "sup_qt_channels_untouched")
_check("maya_output_supervision" not in _qt, "sup_qt_no_supervisor_wiring")

# ---- 12. Tkinter unchanged, remains last fallback -----------------------

_app = open("maya_app.py", encoding="utf-8").read()
_qt_first = _app.find("from maya_runtime.ui.qt import QT_AVAILABLE")
_tk_last = _app.find("root = tk.Tk()")
_check(_qt_first != -1 and _tk_last != -1 and _qt_first < _tk_last,
       "sup_tk_kept_as_last_fallback")
_check("falling back to Tk" in _app, "sup_tk_fallback_message")
_check("maya_output_supervision" not in _app, "sup_tk_no_supervisor_wiring")

# ---- 13. existing regression source invariants intact -------------------

for _token in ("Prefer one clear sentence", "only the current question",
               "wait for the next message", '"num_predict": 512',
               "local = maya_local_command(text)"):
    _check(_token in _chat_body, "sup_source_invariant_" + _token.strip())
_check("import maya_runtime" not in _chat_body, "sup_chat_lazy_bridge_import")

# boundary really sits inside ask(): after the model call and before emission
_ask_region = _chat_body[_chat_body.find("def ask("):]
_b1 = _ask_region.find("with urllib.request.urlopen")
_b2 = _ask_region.find("_supervise_answer(")
_b3 = _ask_region.find('answer = supervision["final"]')
_b4 = _ask_region.find("return answer")
_check(-1 not in (_b1, _b2, _b3, _b4) and _b1 < _b2 < _b3 < _b4,
       "sup_boundary_between_model_and_emission")

print("output_supervision=%d checks" % _ok)