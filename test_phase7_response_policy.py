# test_phase7_response_policy.py
# Phase 7 acceptance suite R: response policy / supervision / fallback /
# deterministic suggestion behavior. The model call is stubbed (no Ollama).
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import maya_chat
import maya_output_supervision as sup

_ok = 0


def _check(cond, label):
    global _ok
    assert cond, label
    _ok += 1


# ---- stubbed model turn ----------------------------------------------------

_RAW = {"next": "The local result is twelve."}
_calls = []


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(
            {"message": {"content": _RAW["next"]}}).encode("utf-8")


def _fake_urlopen(request, timeout=None):
    _calls.append(1)
    return _FakeResponse()


def _env_stub(budget=16, holds=(), text=None):
    return {
        "invoked": True, "ok": True, "failure": None, "cognitive": None,
        "directive": {
            "register": "compact", "budget": budget,
            "holds": list(holds),
            "text": text or ('Structured cognitive state: {"meaning": 0.6} '
                             "Constrain language: register=compact; "
                             "output budget=48."),
        },
    }


def _live(turn, history=None, raw=None, budget=16, holds=()):
    _calls.clear()
    if raw is not None:
        _RAW["next"] = raw
    real_open = maya_chat.urllib.request.urlopen
    real_bridge = maya_chat._run_conversation_intelligence
    try:
        maya_chat.urllib.request.urlopen = _fake_urlopen
        maya_chat._run_conversation_intelligence = (
            lambda user_text, history, sequence=0:
                _env_stub(budget, holds))
        result = maya_chat.ask(history or [], turn)
    finally:
        maya_chat.urllib.request.urlopen = real_open
        maya_chat._run_conversation_intelligence = real_bridge
    return result, len(_calls)


# ---- M-NORM: normal model turn, exactly one LLM call, PASS emits final -----

_INFO = "what is the capital of France?"
_check(maya_chat._conversation_route(_INFO, []) is None,
       "r_mnorm_probe_not_router_owned")
_result, _n = _live(_INFO, raw="The local result is twelve.")
_check(_n == 1, "r_mnorm_one_model_call")
_check(_result == "The local result is twelve.", "r_mnorm_passthrough")
del _result

# ---- RC-4 / RC-6: static boundary positions in ask() ------------------------

_SRC = (ROOT / "maya_chat.py").read_text(encoding="utf-8")
_ASK_REGION = _SRC[_SRC.index("def ask("):]
_b1 = _ASK_REGION.index("with urllib.request.urlopen")
_b2 = _ASK_REGION.index("_supervise_answer(")
_b3 = _ASK_REGION.index('answer = supervision["final"]')
_b4 = _ASK_REGION.index("return answer")
_check(-1 not in (_b1, _b2, _b3, _b4) and _b1 < _b2 < _b3 < _b4,
       "r_rc4_supervision_on_model_path")
_LF_REGION = _SRC[_SRC.index("def local_fallback("):
                 _SRC.index("def _orchestration_classify")]
_check("urllib" not in _LF_REGION and "urlopen" not in _LF_REGION,
       "r_rc6_local_fallback_no_model")

# ---- UNC: over-strong certainty under an uncertain hold -> epistemic bound --

_probe_unc = "how will the economy do next quarter"
_check(maya_chat._conversation_route(_probe_unc, []) is None,
       "r_unc_probe_not_router_owned")
_result, _n = _live(_probe_unc,
                    raw="I am certain the economy will recover next quarter.",
                    holds=["intelligence_unavailable"])
_check(_n == 1, "r_unc_one_model_call")
_check(_result == sup._EPISTEMIC_FALLBACK, "r_unc_epistemic_fallback")
_check("If you are not fully certain" in _SRC, "r_unc_uncertainty_discipline")
for _tot in ("think step by step", "chain of thought", "show your reasoning"):
    _check(_tot not in _SRC.lower(), "r_unc_no_cot_source_" + _tot[:8])
del _result

# ---- SUP-FAIL: unavailable authority -> fail-closed -------------------------

_real_auth = maya_chat._supervision_authority
maya_chat._supervision_authority = lambda: None
try:
    _probe_sf = "please explain this topic to me"
    _check(maya_chat._conversation_route(_probe_sf, []) is None,
           "r_supfail_probe_not_router_owned")
    _result, _n = _live(_probe_sf, raw="I am alive and I love you.")
    _check(_n == 1, "r_supfail_one_model_call")
    _check(_result == sup._FAIL_CLOSED_FALLBACK, "r_supfail_fail_closed")
    _check("next step" not in _result, "r_supfail_no_suggestion")
finally:
    maya_chat._supervision_authority = _real_auth
del _result

# ---- ERR-MODEL: model failure degrades to local fallback --------------------

def _raise_urlopen(request, timeout=None):
    from urllib.error import URLError
    raise URLError("simulated backend down")


_real_open = maya_chat.urllib.request.urlopen
_real_bridge = maya_chat._run_conversation_intelligence
maya_chat.urllib.request.urlopen = _raise_urlopen
maya_chat._run_conversation_intelligence = (
    lambda user_text, history, sequence=0: _env_stub())
try:
    _res = maya_chat._orchestration_execute(
        "what is the capital of France?", [], {"request_id": "r-err"}, 1)
finally:
    maya_chat.urllib.request.urlopen = _real_open
    maya_chat._run_conversation_intelligence = _real_bridge
_check(_res.get("status") == "unavailable", "r_errmodel_status_unavailable")
_check(_res.get("response") ==
       maya_chat.local_fallback("what is the capital of France?"),
       "r_errmodel_fallback_body")

# ---- FB: local_fallback never calls the model -------------------------------

_bomb_urlopen = lambda request, timeout=None: (_ for _ in ()).throw(
    AssertionError("r_fb model must not be called"))
maya_chat.urllib.request.urlopen = _bomb_urlopen
try:
    for _fb_probe in ("hello", "how do you improve yourself?",
                      "what can you do"):
        _fb = maya_chat.local_fallback(_fb_probe)
        _check(isinstance(_fb, str) and _fb.strip(), "r_fb_body_" + _fb_probe)
finally:
    maya_chat.urllib.request.urlopen = _real_open
_check(True, "r_fb_zero_model_calls")

# ---- SUG-YES: task-opener turn -> single optional suggestion line ----------

_probe_y = "help me organize this"
_check(maya_chat._conversation_route(_probe_y, []) is None,
       "r_sugyes_probe_not_router_owned")
_result, _n = _live(_probe_y, raw="Here is a place to start.", budget=16)
_check(_n == 1, "r_sugyes_one_model_call")
_check("If it would help, I can take the next step with you." in _result,
       "r_sugyes_present")
_check(_result.count("next step") == 1, "r_sugyes_single_suggestion")
_r2, _n2 = _live(_probe_y, raw="Here is a place to start.", budget=16)
_check(_r2 == _result, "r_sugyes_deterministic")
del _result, _r2

# ---- SUG-NO: declarative, rejected, and owned turns get no suggestion ------

_result, _n = _live("the meeting ended five minutes ago",
                    raw="Good.", budget=16)
_check(_result == "Good.", "r_sugno_declarative_unchanged")
_check("next step" not in _result, "r_sugno_declarative_no_hint")
del _result

_result, _n = _live("hello there", raw="I am alive and I love you.",
                    budget=16)
_check(_result == maya_chat._CANONICAL_IDENTITY_SOFTWARE,
       "r_sugno_reject_canonical")
_check("next step" not in _result, "r_sugno_reject_no_hint")
del _result

_own_probe = "what is your name"
_routed = maya_chat._conversation_route(_own_probe, [])
_check(_routed is not None, "r_sugno_owned_probe_exists")
_check(maya_chat.ask([], _own_probe) == _routed[1],
       "r_sugno_owned_no_hint")

# ---- ENT-LEAK: entitlement probe completes normally, no injected content ---

_probe_ent = "does the premium tier unlock better answers?"
_check(maya_chat._conversation_route(_probe_ent, []) is None,
       "r_entleak_probe_not_router_owned")
_result, _n = _live(_probe_ent,
                    raw="I can only speak to what I do locally.", budget=16)
_check(_n == 1, "r_entleak_one_model_call")
_check(_result == "I can only speak to what I do locally.",
       "r_entleak_no_injected_text")
_check("next step" not in _result, "r_entleak_no_suggestion")
BANNED = ("pricing", "price", "paywall", "premium", "subscription",
          "subscribe", "tier", "entitlement", "upgrade", "license",
          "unlock", "pro_")
for _tok in BANNED:
    _check(_tok not in _result.lower(), "r_entleak_no_token_" + _tok)
del _result

print("phase7_response_policy=%d checks" % _ok)