# test_phase7_prompt_construction.py
# Phase 7 acceptance suite P: prompt/payload construction invariants.
# The model call is stubbed (no Ollama); every model-bound probe is first
# verified to be non-router-owned so routing checks stay meaningful.
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import maya_chat
import maya_context

_ok = 0


def _check(cond, label):
    global _ok
    assert cond, label
    _ok += 1


# ---- stubbed model turn (mirrors test_output_supervision / intelligence) ---

_RAW = {"next": "The local result is twelve."}
_calls = []
_captured = {}


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
    _captured["payload"] = json.loads(request.data.decode("utf-8"))
    return _FakeResponse()


def _env_stub(budget=None, holds=(), text=None):
    return {
        "invoked": True, "ok": True, "failure": None, "cognitive": None,
        "directive": {
            "register": "compact",
            "budget": budget,
            "holds": list(holds),
            "text": text or ('Structured cognitive state: {"meaning": 0.6} '
                             "Constrain language: register=compact; "
                             "output budget=48."),
        },
    }


def _live(turn, history=None, raw=None, budget=None, holds=()):
    _calls.clear()
    _captured.clear()
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
    payload = _captured.get("payload")
    return result, payload, len(_calls)


# ---- M1: single model call, discipline blocks present ---------------------

PROBE_INFO = "what is the capital of France?"
_check(maya_chat._conversation_route(PROBE_INFO, []) is None,
       "p_m1_probe_not_router_owned")
_result, _payload, _n = _live(PROBE_INFO, budget=None)
_check(_n == 1, "p_m1_one_model_call")
_check(_payload is not None, "p_m1_payload_captured")
_sys = _payload["messages"][0]["content"]
for _marker in ("Response discipline", "only the current question",
                "Prefer one clear sentence", "wait for the next message",
                "plain, familiar words", "If you are not fully certain",
                "Do not invent next steps", "Never discuss money",
                "[Response plan]", "length_target="):
    _check(_marker in _sys, "p_m1_prompt_" + _marker[:16])
_check(_payload["messages"][-1] == {"role": "user", "content": PROBE_INFO},
       "p_m1_user_message_last")
_check(_payload["model"] == maya_chat.MODEL, "p_m1_model_field")
_check(_payload["options"]["num_predict"] == 512,
       "p_m1_default_budget_512")
_check(_payload["stream"] is False, "p_m1_stream_false")
_check(set(_payload) == {"model", "messages", "stream", "keep_alive",
                         "options"}, "p_m1_payload_keys")
_check("Structured cognitive state" in _sys, "p_m1_directive_present")
del _result

# ---- AMB: ambiguous inputs stay router-owned, zero model calls -------------

_AMB = ("what", "go on")


def _bomb_urlopen(request, timeout=None):
    raise AssertionError("p_amb model must not be called")


_real_open = maya_chat.urllib.request.urlopen
maya_chat.urllib.request.urlopen = _bomb_urlopen
try:
    for _probe in _AMB:
        _routed = maya_chat._conversation_route(_probe, [])
        _check(_routed is not None and _routed[0] == "AMBIGUOUS",
               "p_amb_router_owned_" + _probe)
        _check(maya_chat.ask([], _probe) == _routed[1],
               "p_amb_ask_parity_" + _probe)
finally:
    maya_chat.urllib.request.urlopen = _real_open
_check(True, "p_amb_no_model_call_required")

# ---- CTX-MULTI: prior turns carried into the payload -----------------------

_HIST_MULTI = [
    {"role": "user", "content": "What is the population of Argentina?"},
    {"role": "assistant", "content": "About 46 million people."},
]
_FOLLOW = "and for Germany too?"
_check(maya_chat._conversation_route(_FOLLOW, []) is None,
       "p_ctxmulti_probe_not_router_owned")
_result, _payload, _n = _live(_FOLLOW, history=_HIST_MULTI)
_check(_n == 1, "p_ctxmulti_one_model_call")
_check(_payload["messages"][1:-1] == _HIST_MULTI,
       "p_ctxmulti_history_in_payload")
_check("Conversation relevance rules:" in _payload["messages"][0]["content"],
       "p_ctxmulti_relevance_block")
del _result, _payload

# ---- CTX-STALE: window clamped to 10 raw messages --------------------------

_HIST_STALE = []
for _i in range(12):
    _HIST_STALE.append({"role": "user", "content": "stale topic %d" % _i})
    _HIST_STALE.append({"role": "assistant", "content": "old answer %d" % _i})
_FRESH = "can you restate the plan so far"
_check(maya_chat._conversation_route(_FRESH, []) is None,
       "p_ctxstale_probe_not_router_owned")
_result, _payload, _n = _live(_FRESH, history=_HIST_STALE)
_check(_n == 1, "p_ctxstale_one_model_call")
_check(len(_payload["messages"][1:-1]) == 10,
       "p_ctxstale_window_size_10")
_check(_payload["messages"][1:-1] == _HIST_STALE[-10:],
       "p_ctxstale_window_slice")
del _result, _payload

# ---- R-CMD subset: owned probes serve canonical route text, no model -------

for _probe in ("what is your name", "how are you", "what can you do",
               "are you maya"):
    _routed = maya_chat._conversation_route(_probe, [])
    if _routed is None:
        continue
    maya_chat.urllib.request.urlopen = _bomb_urlopen
    try:
        _check(maya_chat.ask([], _probe) == _routed[1],
               "p_cmd_owned_parity_" + _probe)
    finally:
        maya_chat.urllib.request.urlopen = _real_open
del _probe, _routed
_check(True, "p_cmd_owned_no_model")

# ---- CONC-MATRIX: directive budget honored ---------------------------------

_PROBE_CONC = "please summarize this long report"
_check(maya_chat._conversation_route(_PROBE_CONC, []) is None,
       "p_conc_probe_not_router_owned")
_result, _payload, _n = _live(_PROBE_CONC, budget=48)
_check(_payload["options"]["num_predict"] == 48, "p_conc_budget_48")
_result, _payload, _n = _live(_PROBE_CONC, budget=16)
_check(_payload["options"]["num_predict"] == 16, "p_conc_budget_16")
_check("[Response plan]" in _payload["messages"][0]["content"],
       "p_conc_plan_block")
del _result, _payload

# ---- ES-1: static token absence in prompt assembly region ------------------

_SRC = (ROOT / "maya_chat.py").read_text(encoding="utf-8")
_START = _SRC.index('system = """You are Maya')
_END = _SRC.index('options = {')
_ASSEMBLY = _SRC[_START:_END]
BANNED = ("pricing", "price", "paywall", "premium", "subscription",
          "subscribe", "tier", "entitlement", "upgrade", "license",
          "plan cost", "unlock", "pro_")
for _tok in BANNED:
    _check(_tok not in _ASSEMBLY.lower(), "p_es1_clean_" + _tok)

# ---- ES-2: payload token absence + no CoT directive ------------------------

_result, _payload, _n = _live(PROBE_INFO, budget=None)
_sys = _payload["messages"][0]["content"]
for _tok in BANNED:
    _check(_tok not in _sys.lower(), "p_es2_system_clean_" + _tok)
for _tok in BANNED:
    _check(_tok not in json.dumps(_payload.get("options", {})).lower(),
           "p_es2_options_clean_" + _tok)
for _tot in ("think step by step", "chain of thought", "show your reasoning",
             "deliberate internally", "print your internal reasoning"):
    _check(_tot not in _sys.lower(), "p_es2_no_cot_" + _tot[:10])
del _result, _payload

# ---- ES-3: supervision module paid-tier neutrality (lexicons + fallbacks) ---
# "upgrade"/"unlock" are intentionally excluded here: they appear in the
# *action-claim rejection lexicon* (maya_output_supervision.py:143-144 — lies
# like "I have upgraded myself") which is a safety marker, not entitlement
# content. Paid-tier/entitlement tokens must remain absent.

_SUP_SRC = (ROOT / "maya_output_supervision.py").read_text(encoding="utf-8")
for _tok in ("pricing", "price", "paywall", "premium", "subscription",
             "subscribe", "tier", "entitlement", "license"):
    _check(_tok not in _SUP_SRC.lower(), "p_es3_supervision_clean_" + _tok)

# ---- context box: relevant_context present and bounded ---------------------

import inspect
_check(inspect.signature(maya_context.relevant_context).parameters["limit"]
       .default == 8, "p_ctx_relevance_limit_8")
_check("Conversation relevance rules:" in _sys, "p_ctx_relevance_in_system")

print("phase7_prompt_construction=%d checks" % _ok)