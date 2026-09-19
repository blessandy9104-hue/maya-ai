# -*- coding: utf-8 -*-
"""Orchestration-readiness boundary tests for the resource-pressure seam.

The deterministic depth adjudication in ``ask()`` must consume the resource
monitor's real verdict — not a phantom key. ``maya_safety_monitor.status()``
never returned a ``"resources"`` field (it exposes ``safe``), so the previous
read ``_res_snap.get("resources") != "safe"`` evaluated to ``True`` on every
monitored turn, permanently forcing ``resource_pressure`` into
``assess_complexity`` and defeating the hardware-adaptive depth seam.

Requirements covered:
  1. A monitor report of ``safe=True`` MUST reach ``assess_complexity`` as
     ``resource_pressure=False`` (no artificial pressure).
  2. A monitor report of ``safe=False`` MUST reach ``assess_complexity`` as
     ``resource_pressure=True`` (genuine pressure).
  3. The monitor's own fail-closed report (unavailable) MUST reach
     ``assess_complexity`` as ``resource_pressure=True`` (fail closed).
  4. The observed depth envelope still flows from the real ``assess_complexity``.
  5. Supervision still governs emission on the same live ask() path.
"""
import json
import sys

sys.path.insert(0, ".")

import maya_chat
import maya_conversation.adaptivity as _adaptivity
import maya_safety_monitor as _monitor

_ok = 0


def _check(condition, name):
    global _ok
    if not condition:
        print(name + "=FAIL")
        sys.exit(1)
    _ok += 1
    print(name + "=OK")


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return json.dumps({"message": {"content": self._raw}}).encode("utf-8")


def _stub_env(budget, text):
    return {
        "invoked": True, "ok": True, "failure": None, "cognitive": None,
        "directive": {"register": "compact", "budget": budget, "holds": [],
                      "text": text},
    }


def _run_turn(monitor_report):
    """Run one live ask() turn with a controlled monitor report.

    Returns (observed_resource_pressure, depth_envelope, final_answer).
    The seam imports ``assess_complexity`` and ``status`` at call time, so
    patching the module attributes before the call is picked up by ask().
    """
    observed = {}

    _real_open = maya_chat.urllib.request.urlopen
    _real_bridge = maya_chat._run_conversation_intelligence
    _real_status = _monitor.status
    _real_assess = _adaptivity.assess_complexity

    def _assess_spy(conv_result=None, user_text=None, cooperation=None,
                    interpret=None, resource_pressure=False):
        observed["resource_pressure"] = resource_pressure
        observed["depth_envelope"] = _real_assess(
            conv_result, user_text, cooperation,
            interpret=interpret, resource_pressure=resource_pressure)
        return observed["depth_envelope"]

    _payload = {}

    def _fake_urlopen(request, timeout=None):
        del timeout
        _payload["captured"] = True
        return _FakeResponse("The local result is twelve.")

    try:
        maya_chat.urllib.request.urlopen = _fake_urlopen
        maya_chat._run_conversation_intelligence = (
            lambda user_text, history, sequence=0:
                _stub_env(48, "Structured cognitive state: {\"meaning\": 0.6} "
                              "Constrain language: register=compact; "
                              "output budget=48."))
        _monitor.status = lambda: dict(monitor_report)
        _adaptivity.assess_complexity = _assess_spy
        answer = maya_chat.ask([], "hello there")
    finally:
        maya_chat.urllib.request.urlopen = _real_open
        maya_chat._run_conversation_intelligence = _real_bridge
        _monitor.status = _real_status
        _adaptivity.assess_complexity = _real_assess
    return (observed.get("resource_pressure"),
            observed.get("depth_envelope"), answer, _payload)


# ---- 1. safe monitor report -> no artificial resource pressure -----------

_pressure, _env, _answer, _payload = _run_turn({
    "safe": True, "monitor_available": True, "reasons": [],
    "checks": {}, "margin": 1.0, "snapshot": {}, "policy": {},
})
_check(_pressure is False, "readiness_safe_report_no_pressure")
_check(isinstance(_env, dict), "readiness_depth_envelope_present")
_check(_answer == "The local result is twelve.",
       "readiness_supervised_answer_unchanged")
_check(bool(_payload.get("captured")), "readiness_model_called_once")

# ---- 2. unsafe monitor report -> genuine resource pressure ---------------

_pressure, _env, _answer, _payload = _run_turn({
    "safe": False, "monitor_available": True, "reasons": ["CPU threshold"],
    "checks": {}, "margin": 0.0, "snapshot": {}, "policy": {},
})
_check(_pressure is True, "readiness_unsafe_report_forces_pressure")

# ---- 3. fail-closed monitor report (unavailable) -> pressure ------------

_pressure, _env, _answer, _payload = _run_turn({
    "safe": False, "monitor_available": False,
    "reason": "resource monitor unavailable; fail closed",
})
_check(_pressure is True, "readiness_failclosed_forces_pressure")

print("test_orchestration_readiness=PASS")