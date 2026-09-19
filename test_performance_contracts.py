"""Performance instrumentation contract suite (observable behaviour only).

These tests treat the chat surface as a black box: they drive it and compare
what a user could observe. Enabling instrumentation must not change any
user-visible output, must not print diagnostics, must not create trust
artifacts, and must not change the terminal outcome of a request.

Skills: prints only benign ``=OK`` labels; subprocess output is captured and
never echoed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_REAL_FILES = (
    _REPO / "trusted_capabilities.jsonl",
    _REPO / "maya_trust_actions.jsonl",
)
_REAL_BEFORE = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
                for p in _REAL_FILES}

_FORBIDDEN_SUBSTRINGS = ("[perf]", "instrument", "[face]")


def _ok(label):
    print("=" + label + "=OK")


def _clean_env(*, instrumented):
    env = dict(os.environ)
    env.pop("MAYA_INSTRUMENT", None)
    env.pop("MAYA_FACE_LINES", None)
    if instrumented:
        env["MAYA_INSTRUMENT"] = "1"
    return env


def _run_chat(instrumented):
    script = "hello\n2+2\n:pending\nexit\n"
    return subprocess.run(
        [sys.executable, str(_REPO / "maya_chat.py")],
        input=script, capture_output=True, text=True, timeout=120,
        cwd=str(_REPO), env=_clean_env(instrumented=instrumented))


def _artifacts_now():
    return {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
            for p in _REAL_FILES}


# ---- 1. observable parity + non-interference ------------------------------

def test_perf_contract_stdout_parity_ok():
    plain = _run_chat(instrumented=False)
    measured = _run_chat(instrumented=True)
    assert plain.returncode == 0, plain.returncode
    assert measured.returncode == 0, measured.returncode
    assert plain.stdout == measured.stdout, (plain.stdout, measured.stdout)
    assert measured.stdout.strip(), "expected visible chat output"
    combined = (measured.stdout + "\n" + measured.stderr).lower()
    for token in _FORBIDDEN_SUBSTRINGS:
        assert token not in combined, token
    assert _artifacts_now() == _REAL_BEFORE
    _ok("perf_contract_stdout_parity_ok")


def test_perf_contract_module_import_clean_ok():
    result = subprocess.run(
        [sys.executable, "-c", "import maya_instrumentation"],
        capture_output=True, text=True, timeout=60, cwd=str(_REPO),
        env=_clean_env(instrumented=False))
    assert result.returncode == 0, result.returncode
    assert result.stdout == "" and result.stderr == "", (result.stdout,
                                                          result.stderr)
    _ok("perf_contract_module_import_clean_ok")


def test_perf_contract_enabled_buffer_no_stdout_ok():
    code = ("import maya_instrumentation as m; m.enable(); "
            "m.record('x', duration_ms=1.0); m.reset()")
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        timeout=60, cwd=str(_REPO), env=_clean_env(instrumented=True))
    assert result.returncode == 0, result.returncode
    assert result.stdout == "" and result.stderr == "", (result.stdout,
                                                          result.stderr)
    _ok("perf_contract_enabled_buffer_no_stdout_ok")


# ---- 2. terminal outcome is unaffected by instrumentation -----------------

def _drive_chat(text):
    import maya_chat
    maya_chat._CHAT_ORCHESTRATOR = None
    maya_chat._CHAT_PENDING = None
    maya_chat._CHAT_EXECUTORS = {}
    maya_chat._LAST_PENDING_JSON = None
    return maya_chat.orchestrate_chat_turn(text, [])


def _terminal_states(request):
    import maya_orchestration as orch
    return [h for h in request["history"]
            if h["state"] in orch.TERMINAL_OUTCOMES]


def test_perf_contract_chat_turn_terminal_once_ok():
    plain = _drive_chat("hello")
    import maya_instrumentation as inst
    inst.disable()
    inst.reset()
    inst.enable()
    try:
        measured = _drive_chat("hello")
    finally:
        inst.disable()
        inst.reset()
    assert plain["terminal"] is True and measured["terminal"] is True
    assert plain["outcome"] == measured["outcome"] == "completed"
    assert ([h["state"] for h in _terminal_states(plain)]
            == [h["state"] for h in _terminal_states(measured)])
    assert len(_terminal_states(measured)) == 1
    assert measured["response"] and measured["response"].strip()
    _ok("perf_contract_chat_turn_terminal_once_ok")


def test_perf_contract_malformed_fail_closed_ok():
    request = _drive_chat("   ")
    assert request["terminal"] is True
    assert request["outcome"] == "error"
    assert len(_terminal_states(request)) == 1
    assert "changed nothing" in request["response"].lower()
    _ok("perf_contract_malformed_fail_closed_ok")


if __name__ == "__main__":
    os.environ.pop("MAYA_INSTRUMENT", None)
    for _name in sorted(globals()):
        if _name.startswith("test_") and callable(globals()[_name]):
            globals()[_name]()
    print("test_performance_contracts=PASS")
