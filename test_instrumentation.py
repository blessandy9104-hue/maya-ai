"""Performance instrumentation verification suite (read-only, opt-in).

Verifies the instrumentation layer itself: it is off by default, records valid
and monotonic timing fields, survives a broken/missing clock without changing a
request's outcome, stays bounded over repeated turns (no leaks of observers,
timers, threads or handlers), never records message content or secrets, never
writes trust artifacts, and exposes the same honest terminal outcome for the
completion, approval, denial, retry, cancellation and timeout paths.

Skills: this module may print only benign lines (``=OK`` labels). No free-form
text, no tracebacks on the passing path.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import maya_instrumentation as inst  # noqa: E402
import maya_orchestration as orch  # noqa: E402

_REAL_FILES = (
    _REPO / "trusted_capabilities.jsonl",
    _REPO / "maya_trust_actions.jsonl",
)
_REAL_BEFORE = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
                for p in _REAL_FILES}

DEFAULT_EVENTS = 512
DEFAULT_TRACES = 128


def _ok(label):
    print("=" + label + "=OK")


def _fresh(enabled=False, clock=None, **kwargs):
    os.environ.pop(inst.ENV_FLAG, None)
    inst.disable()
    inst.reset()
    inst.configure(max_events=kwargs.pop("max_events", DEFAULT_EVENTS),
                   max_traces=kwargs.pop("max_traces", DEFAULT_TRACES))
    if enabled:
        inst.enable(clock=clock, **kwargs)
    return inst


def _request_classify(text, context):
    return {"kind": "answer", "response": "ok", "requires_execution": False}


def _spy_executor(calls):
    def execute(request, context, attempt):
        calls.append(attempt)
        return {"status": "ok", "response": "done", "confirmed": True}
    return execute


def _events_named(name):
    return [e for e in inst.snapshot()["events"] if e.get("event") == name]


# ---- 1. opt-in / disabled by default --------------------------------------

def test_inst_disabled_default_ok():
    _fresh()
    assert inst.is_enabled() is False
    assert inst.record("nope", duration_ms=1.0) is None
    with inst.span("nope") as scope:
        pass
    assert scope.finish() is None
    assert inst.event_count() == 0
    assert inst.counters() == {}
    assert inst.trace_request({"request_id": "req-x", "terminal": True,
                               "outcome": "completed"}) is None
    _ok("inst_disabled_default_ok")


def test_inst_enable_record_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    assert inst.is_enabled() is True
    entry = inst.record("unit", duration_ms=1.25, size_bytes=42, count=3,
                        meta={"state": "ok"})
    assert entry["event"] == "unit"
    assert entry["duration_ms"] == 1.25
    assert entry["size_bytes"] == 42
    assert inst.event_count() == 1
    _ok("inst_enable_record_ok")


# ---- 2. timing fields and monotonicity ------------------------------------

def test_inst_timing_fields_ok():
    tick = [10.0]
    _fresh(enabled=True, clock=lambda: tick[0])
    with inst.span("phase", stage="executing", request_id="req-abc") as scope:
        tick[0] += 0.25
    scope.finish()
    entry = _events_named("phase")[0]
    assert entry["duration_ms"] == 250.0, entry
    assert entry["stage"] == "executing"
    assert entry["request_id"] == "req-abc"
    _ok("inst_timing_fields_ok")


def test_inst_monotonic_duration_ok():
    assert inst.duration_ms(1.0, 2.0) == 1000.0
    assert inst.duration_ms(2.0, 1.0) is None          # backwards -> refuse
    assert inst.duration_ms(None, 5.0) is None
    assert inst.duration_ms("x", 5.0) is None
    tick = [0.0]
    _fresh(enabled=True, clock=lambda: tick[0])
    durations = []
    for _ in range(5):
        with inst.span("p"):
            tick[0] += 1.0
        durations.append(_events_named("p")[-1]["duration_ms"])
    assert durations == [1000.0] * 5
    _ok("inst_monotonic_duration_ok")


def test_inst_broken_clock_no_break_ok():
    def broken():
        raise RuntimeError("clock down")

    _fresh(enabled=True, clock=broken)
    scope = inst.span("broken")
    scope.finish()                             # must never raise
    entry = _events_named("broken")[0]
    assert "duration_ms" not in entry          # invalid timing dropped
    orchestrator = orch.Orchestrator(clock=lambda: 100.0, max_attempts=1)
    calls = []
    request = orchestrator.submit("hello", classify=_request_classify,
                                  execute=_spy_executor(calls))
    assert request["terminal"] is True
    assert request["outcome"] == "completed"
    _ok("inst_broken_clock_no_break_ok")


# ---- 3. bounded buffers ----------------------------------------------------

def test_inst_bounded_buffers_ok():
    _fresh(enabled=True, clock=lambda: 0.0, max_events=10, max_traces=5)
    for _ in range(200):
        inst.record("flood")
    assert inst.event_count() <= 10
    for index in range(50):
        inst.trace_request({
            "request_id": "req-%d" % index,
            "state": "completed", "outcome": "completed", "terminal": True,
            "attempts": 1, "created_at": 0, "updated_at": 0,
            "history": [{"state": "completed", "at": 0}],
        })
    assert inst.trace_count() <= 5
    limits = inst.buffer_limits()
    assert limits["max_events"] == 10 and limits["max_traces"] == 5
    _ok("inst_bounded_buffers_ok")


# ---- 4. content minimization ----------------------------------------------

def test_inst_meta_allowlist_blocks_content_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    secret = "S3CR3T user words 12345"
    entry = inst.record("unit", meta={
        "state": "ok", "text": secret, "reason": secret, "summary": secret,
        "message": secret, "unknown": secret})
    assert "text" not in entry.get("meta", {})
    assert "reason" not in entry.get("meta", {})
    assert secret not in inst.to_json()
    _ok("inst_meta_allowlist_blocks_content_ok")


def test_inst_chat_content_not_recorded_ok():
    import maya_chat
    _fresh(enabled=True, clock=lambda: 0.0)
    maya_chat._CHAT_ORCHESTRATOR = None
    maya_chat._CHAT_PENDING = None
    maya_chat._CHAT_EXECUTORS = {}
    maya_chat._LAST_PENDING_JSON = None
    secret = "Zx9-QWERTY-secret-pleaseignore-12345"
    original_ask = maya_chat.ask
    maya_chat.ask = lambda history, text: "A brief answer."
    try:
        request = maya_chat.orchestrate_chat_turn(secret, [])
    finally:
        maya_chat.ask = original_ask
    assert request["terminal"] is True
    rendered = inst.to_json()
    assert secret not in rendered
    assert "Zx9" not in rendered
    _ok("inst_chat_content_not_recorded_ok")


# ---- 5. lifecycle paths ----------------------------------------------------

def _error_then_ok(calls, ok_after=2):
    def execute(request, context, attempt):
        calls.append(attempt)
        if len(calls) < ok_after:
            return {"status": "error", "reason": "transient"}
        return {"status": "ok", "response": "done", "confirmed": True}
    return execute


def test_inst_trace_fields_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    orchestrator = orch.Orchestrator(clock=lambda: 0.0)
    request = orchestrator.submit("hello", classify=_request_classify,
                                  execute=_spy_executor([]))
    trace = inst.trace_request(request)
    for field in ("request_id", "state", "outcome", "outcome_class", "terminal",
                  "attempts", "duplicate", "planning_ms", "validation_ms",
                  "execution_ms", "approval_wait_ms", "total_ms"):
        assert field in trace, field
    assert trace["terminal"] is True
    assert trace["outcome"] == "completed"
    assert trace["planning_ms"] is not None and trace["planning_ms"] >= 0
    assert trace["total_ms"] is not None and trace["total_ms"] >= 0
    _ok("inst_trace_fields_ok")


def test_inst_approval_path_ok():
    tick = [100.0]
    _fresh(enabled=True, clock=lambda: tick[0])
    orchestrator = orch.Orchestrator(clock=lambda: tick[0], max_attempts=1)

    def classify(text, context):
        return {"kind": "act", "requires_execution": True,
                "requires_approval": True, "pending_title": "Confirm"}

    request = orchestrator.submit("please act", classify=classify)
    assert request["state"] == "awaiting_approval"
    partial = inst.trace_request(request)
    assert partial["outcome_class"] == "approval_required"
    tick[0] += 5.0
    updated, note = orchestrator.resolve(request["request_id"], "approve",
                                         execute=_spy_executor([]))
    assert note == "approved"
    trace = inst.trace_request(updated, phase="resolve")
    assert trace["outcome"] == "completed"
    assert trace["approval_wait_ms"] == 5000.0, trace["approval_wait_ms"]
    _ok("inst_approval_path_ok")


def test_inst_denial_path_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    orchestrator = orch.Orchestrator(clock=lambda: 0.0, max_attempts=1)
    calls = []
    request = orchestrator.submit(
        "please act",
        classify=lambda text, ctx: {"kind": "act", "requires_execution": True,
                                    "requires_approval": True,
                                    "pending_title": "Confirm"})
    updated, note = orchestrator.resolve(request["request_id"], "deny",
                                         execute=_spy_executor(calls))
    assert note == "denied"
    assert updated["outcome"] == "denied"
    assert calls == []                       # denial prevents execution
    trace = inst.trace_request(updated)
    terminals = [h for h in updated["history"]
                 if h["state"] in orch.TERMINAL_OUTCOMES]
    assert len(terminals) == 1
    assert trace["outcome"] == "denied"
    _ok("inst_denial_path_ok")


def test_inst_cancellation_path_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    orchestrator = orch.Orchestrator(clock=lambda: 0.0, max_attempts=1)
    calls = []
    request = orchestrator.submit(
        "please act",
        classify=lambda text, ctx: {"kind": "act", "requires_execution": True,
                                    "requires_approval": True,
                                    "pending_title": "Confirm"})
    updated, note = orchestrator.resolve(request["request_id"], "cancel",
                                         execute=_spy_executor(calls))
    assert note == "cancelled"
    assert updated["outcome"] == "cancelled"
    assert calls == []                       # cancellation prevents execution
    _ok("inst_cancellation_path_ok")


def test_inst_retry_path_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    orchestrator = orch.Orchestrator(clock=lambda: 0.0, max_attempts=3)
    calls = []
    request = orchestrator.submit("do the thing",
                                  classify=lambda text, ctx: {
                                      "kind": "answer",
                                      "requires_execution": True},
                                  execute=_error_then_ok(calls, ok_after=2))
    assert request["outcome"] == "completed"
    assert request["attempts"] == 2
    inst.trace_request(request)
    assert inst.counters().get("retries", 0) >= 1
    _ok("inst_retry_path_ok")


def test_inst_timeout_path_ok():
    tick = [0.0]
    _fresh(enabled=True, clock=lambda: tick[0])
    orchestrator = orch.Orchestrator(clock=lambda: tick[0], max_attempts=3,
                                     timeout_seconds=5.0)

    def slow_fail(request, context, attempt):
        tick[0] += 10.0
        return {"status": "error", "reason": "still failing"}

    request = orchestrator.submit("slow", classify=lambda t, c: {
        "kind": "answer", "requires_execution": True}, execute=slow_fail)
    assert request["outcome"] == "timeout"
    inst.trace_request(request)
    assert inst.counters().get("timeouts", 0) >= 1
    _ok("inst_timeout_path_ok")


def test_inst_duplicate_detection_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    orchestrator = orch.Orchestrator(clock=lambda: 0.0, max_attempts=1)
    calls = []
    needs_work = lambda text, ctx: {"kind": "answer",
                                    "requires_execution": True}
    first = orchestrator.submit("hello", classify=needs_work,
                                execute=_spy_executor(calls),
                                idempotency_key="turn-1")
    second = orchestrator.submit("hello", classify=needs_work,
                                 execute=_spy_executor(calls),
                                 idempotency_key="turn-1")
    inst.trace_request(first)
    inst.trace_request(second)
    assert second["duplicate"] is True
    assert len(calls) == 1                   # never executes twice
    assert inst.counters().get("duplicate_requests", 0) >= 1
    _ok("inst_duplicate_detection_ok")


def test_inst_terminal_violation_detected_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    base = {"request_id": "req-v", "state": "completed", "outcome": "completed",
            "terminal": True, "attempts": 1, "created_at": 0, "updated_at": 1,
            "history": [{"state": "completed", "at": 1}]}
    inst.trace_request(dict(base))
    conflicting = dict(base)
    conflicting["state"] = "error"
    conflicting["outcome"] = "error"
    inst.trace_request(conflicting)
    assert inst.counters().get("terminal_outcome_violations", 0) == 1
    _ok("inst_terminal_violation_detected_ok")


# ---- 6. startup / resources / pending ages --------------------------------

def test_inst_startup_phases_ok():
    tick = [5.0]
    _fresh(enabled=True, clock=lambda: tick[0])
    inst.mark_startup("bridge_ready", duration_ms=12.5)
    inst.mark_startup("first_frame", at=3.0)          # (5.0 - 3.0) * 1000
    report = inst.startup_report()
    assert report["bridge_ready"]["duration_ms"] == 12.5
    assert report["first_frame"]["duration_ms"] == 2000.0
    assert all(isinstance(v["duration_ms"], (int, float))
               for v in report.values())
    _ok("inst_startup_phases_ok")


def test_inst_resource_snapshot_ok():
    snap = inst.resource_snapshot()
    for field in ("pid", "threads", "cpu_time_s", "rss_bytes", "handles"):
        assert field in snap, field
    assert snap["pid"] == os.getpid()
    assert isinstance(snap["threads"], int) and snap["threads"] >= 1
    for field in ("cpu_time_s", "rss_bytes", "handles"):
        assert snap[field] is None or isinstance(snap[field], (int, float))
    _ok("inst_resource_snapshot_ok")


def test_inst_pending_age_ok():
    items = [{"created_at": 100.0}, {"created_at": None}]
    ages = inst.pending_ages(items, reference=105.0)
    assert ages[0] == 5000.0
    assert ages[1] is None
    _ok("inst_pending_age_ok")


# ---- 7. robustness / non-interference -------------------------------------

def test_inst_span_propagates_error_ok():
    _fresh(enabled=True, clock=lambda: 1.0)
    raised = False
    try:
        with inst.span("boom"):
            raise ValueError("upstream")
    except ValueError:
        raised = True
    assert raised is True                    # span never swallows errors
    entry = _events_named("boom")[0]
    assert entry["meta"]["error"] == "ValueError"
    _ok("inst_span_propagates_error_ok")


def test_inst_no_leak_repeated_turns_ok():
    threads_before = threading.active_count()
    _fresh(enabled=True, clock=lambda: 0.0, max_events=64, max_traces=16)
    orchestrator = orch.Orchestrator(clock=lambda: 0.0, max_attempts=1)
    for _ in range(300):
        request = orchestrator.submit("hello", classify=_request_classify,
                                      execute=_spy_executor([]))
        inst.trace_request(request)
    assert inst.event_count() <= 64
    assert inst.trace_count() <= 16
    assert threading.active_count() == threads_before
    _ok("inst_no_leak_repeated_turns_ok")


def test_inst_disabled_no_side_effects_ok():
    _fresh()
    threads_before = threading.active_count()
    orchestrator = orch.Orchestrator(clock=lambda: 0.0, max_attempts=1)
    request = orchestrator.submit("hello", classify=_request_classify,
                                  execute=_spy_executor([]))
    assert inst.trace_request(request) is None
    assert inst.event_count() == 0
    assert inst.counters() == {}
    assert inst.startup_report() == {}
    assert threading.active_count() == threads_before
    _ok("inst_disabled_no_side_effects_ok")


def test_inst_json_serializable_ok():
    _fresh(enabled=True, clock=lambda: 0.0)
    inst.record("unit", duration_ms=2.0, meta={"state": "ok"})
    inst.mark_startup("bridge_ready", duration_ms=1.0)
    rendered = inst.to_json()
    parsed = json.loads(rendered)
    assert parsed["enabled"] is True
    assert "events" in parsed and "traces" in parsed
    assert parsed["startup"]["bridge_ready"]["duration_ms"] == 1.0
    summary = inst.summary()
    assert summary["event_counts"].get("unit") == 1
    _ok("inst_json_serializable_ok")


def test_inst_ui_hooks_declared_ok():
    source = (_REPO / "maya_runtime" / "ui" / "qt" / "app.py").read_text(
        encoding="utf-8")
    for token in ("ui_tick", "pending_panel_update", "qml_engine_load",
                  "main_window", "first_frame", "first_input",
                  "_instrumentation", "is_enabled()"):
        assert token in source, token
    _ok("inst_ui_hooks_declared_ok")


def test_inst_trust_artifacts_untouched_ok():
    after = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
             for p in _REAL_FILES}
    assert after == _REAL_BEFORE, (after, _REAL_BEFORE)
    source = (_REPO / "maya_instrumentation.py").read_text(encoding="utf-8")
    assert "open(" not in source            # instrumentation never opens files
    _ok("inst_trust_artifacts_untouched_ok")


if __name__ == "__main__":
    os.environ.pop(inst.ENV_FLAG, None)
    for _name in sorted(globals()):
        if _name.startswith("test_") and callable(globals()[_name]):
            globals()[_name]()
    print("test_instrumentation=PASS")
