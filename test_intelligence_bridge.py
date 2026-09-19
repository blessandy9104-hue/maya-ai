"""Verification battery for the conversational intelligence bridge.

Proves the first runtime repair: the deterministic intelligence core is
connected to the free-form conversational path, and the structured
cognitive result materially and deterministically shapes the data supplied
to the natural-language expression layer.

Requirements covered:
  1. ``intelligence.run`` is invoked by the free-form path.
  2. The structured result reaches the expression layer (directive text).
  3. Altering the intelligence result changes the expression-layer input.
  4. Discarding the result (failure/hold) produces a detectable change.
  5. Intelligence failure degrades to a safe hold, never a crash.
  6. Deterministic command routing in ``maya_chat`` is untouched.
  7. Identical deterministic inputs -> identical structured cognitive state.
  8. The language-expression layer remains distinct from the math cognition
     layer (the bridge never imports nondeterminism sources).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime.intelligence.bridge import (
    _extract_cognitive,
    expression_directive,
    map_conversation,
    run_conversation_for_expression,
)

_RUN_PARAMS = frozenset({
    "semantic", "emotional", "contextual", "historical", "render",
    "reference", "world_series", "metrics", "context_vector", "evidence_ok",
    "now", "sequence", "architect_instruction", "environment",
})
_FORBIDDEN = ("random", "time", "tkinter", "datetime", "subprocess", "socket")
_BRIDGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "maya_runtime", "intelligence", "bridge.py")
_CHAT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "maya_chat.py")


def _ok(label):
    print(label + "=OK")


def _assert(condition, label, detail=""):
    assert condition, "%s: %s" % (label, detail)


# ---- 1. schema + purity ------------------------------------------------

_features = map_conversation("hello, how are you?")
_assert(set(_features.keys()) == _RUN_PARAMS,
        "bridge_schema_run_signature")
_bridge_src = open(_BRIDGE_PATH, encoding="utf-8").read()
for _banned in _FORBIDDEN:
    _assert(("import %s" % _banned) not in _bridge_src,
            "bridge_free_of_" + _banned)
_ok("bridge_schema_ok")

# ---- 2. real engine invocation -----------------------------------------

_env = run_conversation_for_expression("hello, how are you?")
_assert(_env["invoked"] and _env["ok"], "bridge_run_executed")
_assert(_env["directive"]["budget"] in (16, 24, 48), "bridge_run_budget")
_assert(isinstance(_env["directive"]["register"], str)
        and _env["directive"]["register"],
        "bridge_run_register")
_assert(isinstance(_env["directive"]["holds"], list), "bridge_run_holds_list")
_assert("Structured cognitive state" in _env["directive"]["text"],
        "bridge_run_directive_text")
_ok("bridge_run_healthy_ok")

# ---- 3. failure degrades to a safe hold --------------------------------

def _explode(**kwargs):
    raise RuntimeError("intelligence engine unavailable")


_env_fail = run_conversation_for_expression("hello there", run_func=_explode)
_assert(not _env_fail["ok"], "bridge_failure_flagged")
_assert(_env_fail["failure"], "bridge_failure_reported")
_assert(_env_fail["directive"]["holds"] == ["intelligence_unavailable"],
        "bridge_failure_hold_name")
_assert(_env_fail["directive"]["budget"] == 16, "bridge_failure_budget")
_assert(_env_fail["directive"]["register"] == "reserved",
        "bridge_failure_register")
_ok("bridge_failure_safe_hold_ok")

# ---- 4. discarding the result changes the expression input -------------

_env_discard = {"budget": _env["directive"]["budget"], "holds": [],
                "register": "compact", "text": _env["directive"]["text"]}
_hold_only = expression_directive(None)
_assert(_hold_only["budget"] == 16 and _env["directive"]["budget"] >= 24,
        "bridge_discard_budget_gap")
_assert(_hold_only["text"] != _env["directive"]["text"],
        "bridge_discard_text_change")
del _env_discard
_ok("bridge_discard_degradation_ok")

# ---- 5. structured result responds to the input ------------------------

_env_calm = run_conversation_for_expression(
    "hello, how are you?")
_env_urgent = run_conversation_for_expression(
    "URGENT stop everything RIGHT NOW this is critical do not proceed")
_assert(_env_calm["directive"]["text"] != _env_urgent["directive"]["text"],
        "bridge_input_expression_change")
_assert(_env_calm["cognitive"]["meaning_scalar"] !=
        _env_urgent["cognitive"]["meaning_scalar"],
        "bridge_input_cognitive_change")
_assert(map_conversation("hello, how are you?") !=
        map_conversation("URGENT stop everything RIGHT NOW this is critical "
                         "do not proceed"),
        "bridge_input_features_change")
_ok("bridge_alters_on_input_ok")

# ---- 6. determinism -----------------------------------------------------

_feats_b = map_conversation("hello, how are you?")
_assert(_feats_b == _features, "bridge_payload_determinism")
_env_again = run_conversation_for_expression("hello, how are you?")
_assert(_env_again["directive"]["text"] == _env["directive"]["text"],
        "bridge_envelope_determinism")
_assert(_env_again["cognitive"] == _env["cognitive"],
        "bridge_cognitive_determinism")
_ok("bridge_determinism_ok")

# ---- 7. safety hold reduces the output budget --------------------------

_frame_unstable = {
    "meaning": {"meaning_scalar": 0.6, "meaning_vector": (0.6,), "ok": True},
    "language": {"register": "compact", "tone": "measured",
                 "meaning_sha": "abc"},
    "state": {"stability": 0.2, "drift": 0.8, "std": 0.3,
              "alignment": 0.4, "ok": False, "stability_ok": False},
    "safety": {"ok": False, "violations": ["boundary"]},
    "confidence": {"confidence": 0.3, "restricted": True,
                   "output_budget": 24},
    "fusion": {"dominant": "maya"},
}
_dir_hold = expression_directive(_extract_cognitive(_frame_unstable))
_assert(_dir_hold["budget"] == 16, "bridge_safety_budget_min")
_assert(_dir_hold["register"] == "reserved", "bridge_safety_register")
_assert("safety_boundary" in _dir_hold["holds"], "bridge_safety_hold_flag")
_ok("bridge_safety_hold_reduces_budget_ok")

# ---- 8. chat wiring (router untouched, directive wired) ----------------

_chat_src = open(_CHAT_PATH, encoding="utf-8").read()
_assert("_run_conversation_intelligence" in _chat_src,
        "chat_hook_present")
_assert("local = maya_local_command(text)" in _chat_src,
        "chat_router_first")
_assert('"num_predict": 512' in _chat_src, "chat_budget_literal_preserved")
_assert("import maya_runtime" not in _chat_src, "chat_lazy_bridge_import")
_ok("chat_source_integration_ok")

# ---- 9. payload carries the directive into the expression layer --------

import maya_chat

_captured = {}


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"message": {"content": "test answer"}}
                          ).encode("utf-8")


def _fake_urlopen(request, timeout=None):
    _captured["payload"] = json.loads(request.data.decode("utf-8"))
    return _FakeResponse()


def _env_stub(budget, holds, text):
    return {
        "invoked": True, "ok": True, "failure": None, "cognitive": None,
        "directive": {"register": "reserved" if holds else "compact",
                      "budget": budget, "holds": list(holds), "text": text},
    }


_real_open = maya_chat.urllib.request.urlopen
try:
    maya_chat.urllib.request.urlopen = _fake_urlopen
    maya_chat._run_conversation_intelligence = (
        lambda user_text, history, sequence=0:
            _env_stub(48, [], "Structured cognitive state: {\"meaning\": 0.6} "
                              "Constrain language: register=compact; "
                              "output budget=48."))
    maya_chat.ask([], "hello there")
    _payload = _captured["payload"]
    _system_text = _payload["messages"][0]["content"]
    _assert("Structured cognitive state" in _system_text,
            "chat_payload_directive_present")
    _assert(_payload["options"]["num_predict"] == 48,
            "chat_payload_budget_full")
finally:
    maya_chat.urllib.request.urlopen = _real_open
_ok("chat_payload_flows_ok")

# ---- 10. hold reduces tokens in the real payload -----------------------

try:
    maya_chat.urllib.request.urlopen = _fake_urlopen
    maya_chat._run_conversation_intelligence = (
        lambda user_text, history, sequence=0:
            _env_stub(16, ["intelligence_unavailable"],
                      "Structured cognitive state: unavailable. Constrain "
                      "language: reply in one brief sentence."))
    maya_chat.ask([], "hello there")
    _payload_hold = _captured["payload"]
    _assert(_payload_hold["options"]["num_predict"] == 16,
            "chat_payload_budget_hold")
finally:
    maya_chat.urllib.request.urlopen = _real_open
del _payload_hold, _real_open
_ok("chat_hold_reduces_tokens_ok")

print("test_intelligence_bridge=PASS")