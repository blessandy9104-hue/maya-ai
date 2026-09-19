"""Asynchronous orchestration verification suite (contract layer).

Verifies that :mod:`maya_async_orchestration` schedules the pure orchestration
state machine without changing any of its guarantees:

- a turn runs off the caller's thread and reaches exactly one terminal outcome;
- every turn carries a stable correlation id and generation before dispatch;
- results for a conversation are delivered in acceptance order even when the
  work finishes out of order;
- the worker pool is bounded (queue overflow is an explicit ``internal_error``);
- queued work cancels before it runs; running work stops cooperatively;
- timeouts, refusals, denials, approvals, unavailable backends and worker
  exceptions keep their distinct, honest outcomes;
- duplicate (idempotent) requests never execute twice;
- late/superseded results are suppressed;
- shutdown leaves no worker or delivery behind.

Skills: this module may print only benign lines (``=OK`` labels). No free-form
text, no tracebacks on the passing path.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import maya_async_orchestration as aorch  # noqa: E402


def _ok(label):
    print("=" + label + "=OK")


def _answer(_text, _context):
    return {"kind": "answer", "requires_execution": True}


def _ok_exec(response="Done."):
    return lambda request, context, attempt: {"status": "ok",
                                              "response": response}


def _make(**kwargs):
    kwargs.setdefault("clock", lambda: 0.0)
    kwargs.setdefault("max_workers", 2)
    kwargs.setdefault("max_queue", 8)
    return aorch.AsyncOrchestrator(**kwargs)


# ---- 1. successful asynchronous turn --------------------------------------

def test_async_successful_turn_ok():
    o = _make()
    try:
        seen = []
        ack = o.submit_turn("hi", classify=_answer, execute=_ok_exec("Hello."),
                            on_result=lambda r: seen.append(r))
        assert ack["accepted"] is True
        assert ack["request_id"].startswith("req-")
        result = o.wait(ack["request_id"])
        assert result["outcome"] == "completed", result
        assert result["terminal"] is True
        assert seen and seen[0]["response"] == "Hello."
    finally:
        o.shutdown()
    _ok("async_successful_turn_ok")


def test_async_correlation_id_stable_ok():
    o = _make()
    try:
        ack = o.submit_turn("hi", classify=_answer, execute=_ok_exec())
        rid = ack["request_id"]
        assert o.request(rid)["request_id"] == rid
        assert ack["generation"] == 0
        assert o.wait(rid)["request_id"] == rid
    finally:
        o.shutdown()
    _ok("async_correlation_id_stable_ok")


def test_async_runs_off_caller_thread_ok():
    o = _make(max_workers=1)
    caller = threading.get_ident()
    seen = {}
    try:
        def execute(request, context, attempt):
            seen["tid"] = threading.get_ident()
            return {"status": "ok", "response": "x"}
        ack = o.submit_turn("hi", classify=_answer, execute=execute)
        o.wait(ack["request_id"])
        assert seen["tid"] != caller
    finally:
        o.shutdown()
    _ok("async_runs_off_caller_thread_ok")


# ---- 2. ordering ----------------------------------------------------------

def test_async_conversation_ordering_ok():
    o = _make(max_workers=2)
    delivered = []
    try:
        def slow(request, context, attempt):
            time.sleep(0.15)
            return {"status": "ok", "response": "A"}

        def fast(request, context, attempt):
            return {"status": "ok", "response": "B"}

        a = o.submit_turn("a", classify=_answer, execute=slow,
                          on_result=lambda r: delivered.append("A"))
        b = o.submit_turn("b", classify=_answer, execute=fast,
                          on_result=lambda r: delivered.append("B"))
        o.wait(a["request_id"])
        o.wait(b["request_id"])
        assert delivered == ["A", "B"], delivered
    finally:
        o.shutdown()
    _ok("async_conversation_ordering_ok")


def test_async_ordering_with_approval_ok():
    o = _make(max_workers=2)
    events = []
    try:
        def approval(_text, _context):
            return {"kind": "act", "requires_approval": True,
                    "requires_execution": True, "pending_title": "Task-X"}

        a = o.submit_turn(
            "act", classify=approval, execute=_ok_exec("acted"),
            on_update=lambda r: events.append("A-update"),
            on_result=lambda r: events.append("A-result"))
        o.wait(a["request_id"])
        b = o.submit_turn("b", classify=_answer, execute=_ok_exec(),
                          on_result=lambda r: events.append("B-result"))
        o.wait(b["request_id"])
        o.resolve_turn(a["request_id"], "approve", execute=_ok_exec("acted"))
        o.wait(a["request_id"])
        assert events == ["A-update", "B-result", "A-result"], events
    finally:
        o.shutdown()
    _ok("async_ordering_with_approval_ok")


def test_async_sessions_independent_ok():
    o = _make(max_workers=2)
    delivered = []
    try:
        a = o.submit_turn("a", session_id="s1", classify=_answer,
                          execute=_ok_exec(), on_result=lambda r: None)
        b = o.submit_turn("b", session_id="s2", classify=_answer,
                          execute=_ok_exec(), on_result=lambda r: None)
        o.wait(a["request_id"])
        o.wait(b["request_id"])
        assert o.request(a["request_id"])["session_id"] == "s1"
        assert o.request(b["request_id"])["session_id"] == "s2"
    finally:
        o.shutdown()
    _ok("async_sessions_independent_ok")


def test_async_concurrent_turns_ok():
    o = _make(max_workers=3, max_queue=16)
    try:
        acked = []
        for i in range(6):
            acked.append(o.submit_turn(
                "t%d" % i, classify=_answer,
                execute=(lambda r, c, a: (time.sleep(0.01),
                                          {"status": "ok",
                                           "response": "ok"})[1])))
        outcomes = [o.wait(a["request_id"])["outcome"] for a in acked]
        assert outcomes == ["completed"] * 6, outcomes
    finally:
        o.shutdown()
    _ok("async_concurrent_turns_ok")


# ---- 3. bounded pool / overflow -------------------------------------------

def test_async_pool_bounds_ok():
    o = _make(max_workers=2, max_queue=3)
    gate = threading.Event()
    try:
        for i in range(2):
            o.submit_turn("run%d" % i, classify=_answer,
                          execute=lambda r, c, a: (gate.wait(2),
                                                   {"status": "ok"})[1])
        time.sleep(0.05)
        for i in range(3):
            o.submit_turn("q%d" % i, classify=_answer, execute=_ok_exec())
        time.sleep(0.05)
        stats = o.stats()["executor"]
        assert stats["running"] <= 2, stats
        assert stats["queued"] <= 3, stats
    finally:
        gate.set()
        o.shutdown()
    _ok("async_pool_bounds_ok")


def test_async_queue_overflow_explicit_error_ok():
    o = _make(max_workers=1, max_queue=1)
    gate = threading.Event()
    try:
        o.submit_turn("hold", classify=_answer,
                      execute=lambda r, c, a: (gate.wait(2),
                                               {"status": "ok"})[1])
        time.sleep(0.05)
        o.submit_turn("queued", classify=_answer, execute=_ok_exec())
        extra = o.submit_turn("overflow", classify=_answer, execute=_ok_exec())
        assert extra["accepted"] is False
        assert extra["outcome"] == "error", extra
        assert extra["outcome_class"] == "internal_error"
        assert extra["reason"] == aorch.REASON_QUEUE_FULL
        assert o.stats()["turns_rejected"] == 1
    finally:
        gate.set()
        o.shutdown()
    _ok("async_queue_overflow_explicit_error_ok")


def test_async_session_inflight_bound_ok():
    o = _make(max_workers=1, max_queue=8, max_inflight_per_session=2)
    gate = threading.Event()
    try:
        o.submit_turn("hold", classify=_answer,
                      execute=lambda r, c, a: (gate.wait(2),
                                               {"status": "ok"})[1])
        time.sleep(0.05)
        b = o.submit_turn("queued", classify=_answer, execute=_ok_exec())
        # A third turn over the cap cancels the oldest queued turn.
        c = o.submit_turn("third", classify=_answer, execute=_ok_exec())
        assert o.wait(b["request_id"])["outcome"] == "cancelled"
        assert c["accepted"] is True
    finally:
        gate.set()
        o.shutdown()
    _ok("async_session_inflight_bound_ok")


# ---- 4. cancellation ------------------------------------------------------

def test_async_cancel_before_execution_ok():
    o = _make(max_workers=1, max_queue=4)
    gate = threading.Event()
    ran = []
    try:
        o.submit_turn("hold", classify=_answer,
                      execute=lambda r, c, a: (gate.wait(2),
                                               {"status": "ok"})[1])
        time.sleep(0.05)
        b = o.submit_turn("cancelme", classify=_answer,
                          execute=lambda r, c, a: (ran.append(True),
                                                   {"status": "ok"})[1])
        assert o.cancel(b["request_id"]) == "queued"
        result = o.wait(b["request_id"])
        assert result["outcome"] == "cancelled", result
        assert ran == []
    finally:
        gate.set()
        o.shutdown()
    _ok("async_cancel_before_execution_ok")


def test_async_cancel_during_execution_ok():
    o = _make(max_workers=1, max_queue=2)
    stopped = []
    started = threading.Event()
    try:
        def cooperative(request, context, attempt):
            token = request.get("async_token")
            started.set()
            for _ in range(400):
                if token is not None and token.cancelled:
                    stopped.append(True)
                    return {"status": "error", "reason": "cooperative_stop"}
                time.sleep(0.005)
            return {"status": "ok"}

        a = o.submit_turn("run", classify=_answer, execute=cooperative)
        started.wait(2)
        assert o.cancel(a["request_id"]) == "running"
        result = o.wait(a["request_id"])
        assert result["outcome"] == "cancelled", result
        assert stopped == [True]
    finally:
        o.shutdown()
    _ok("async_cancel_during_execution_ok")


def test_async_cancel_reconciles_pending_ok():
    o = _make(max_workers=1)
    try:
        def approval(_text, _context):
            return {"kind": "act", "requires_approval": True,
                    "requires_execution": True, "pending_title": "Task-Y"}

        a = o.submit_turn("act", classify=approval, execute=_ok_exec())
        o.wait(a["request_id"])
        assert [p["status"] for p in o.pending_view()] == ["pending"]
        assert o.cancel(a["request_id"]) == "queued"
        assert o.wait(a["request_id"])["outcome"] == "cancelled"
        assert [p["status"] for p in o.pending_view()] == ["cancelled"]
    finally:
        o.shutdown()
    _ok("async_cancel_reconciles_pending_ok")


# ---- 5. distinct honest outcomes ------------------------------------------

def test_async_timeout_honest_ok():
    state = {"t": 0.0}
    o = _make(clock=lambda: state["t"], max_workers=1)
    try:
        def slow(request, context, attempt):
            state["t"] = 1000.0
            return {"status": "unavailable", "reason": "slow"}

        a = o.submit_turn("t", classify=_answer, execute=slow)
        result = o.wait(a["request_id"])
        assert result["outcome"] == "timeout", result
        assert result["outcome_class"] == "timeout"
    finally:
        o.shutdown()
    _ok("async_timeout_honest_ok")


def test_async_approval_denied_ok():
    o = _make(max_workers=1)
    try:
        def approval(_text, _context):
            return {"kind": "act", "requires_approval": True,
                    "requires_execution": True, "pending_title": "Task-Z"}

        a = o.submit_turn("act", classify=approval, execute=_ok_exec())
        o.wait(a["request_id"])
        o.resolve_turn(a["request_id"], "deny")
        result = o.wait(a["request_id"])
        assert result["outcome"] == "denied", result
        assert result["outcome_class"] == "denied"
        assert [p["status"] for p in o.pending_view()] == ["denied"]
    finally:
        o.shutdown()
    _ok("async_approval_denied_ok")


def test_async_refusal_preserved_ok():
    o = _make(max_workers=1)
    try:
        a = o.submit_turn(
            "do bad", classify=_answer,
            execute=lambda r, c, a: {"status": "refused",
                                     "reason": "not_permitted"})
        result = o.wait(a["request_id"])
        assert result["outcome"] == "refused", result
        assert result["outcome_class"] == "action_refused"
        assert result["confirmed"] is False
        assert result["response"].lower().startswith("i can't")
    finally:
        o.shutdown()
    _ok("async_refusal_preserved_ok")


def test_async_unavailable_backend_ok():
    o = _make(max_workers=1)
    try:
        a = o.submit_turn(
            "hi", classify=_answer,
            execute=lambda r, c, a: {"status": "unavailable",
                                     "reason": "no_backend"})
        result = o.wait(a["request_id"])
        assert result["outcome"] == "unavailable", result
        assert result["outcome_class"] == "backend_unavailable"
    finally:
        o.shutdown()
    _ok("async_unavailable_backend_ok")


def test_async_worker_exception_internal_error_ok():
    o = _make(max_workers=1)
    try:
        def boom(request, context, attempt):
            raise RuntimeError("kaboom")

        a = o.submit_turn("hi", classify=_answer, execute=boom)
        result = o.wait(a["request_id"])
        assert result["outcome"] == "error", result
        assert result["outcome_class"] == "internal_error"
    finally:
        o.shutdown()
    _ok("async_worker_exception_internal_error_ok")


def test_async_malformed_payload_fails_closed_ok():
    o = _make(max_workers=1)
    try:
        a = o.submit_turn(None, classify=_answer, execute=_ok_exec())
        result = o.wait(a["request_id"])
        assert result["outcome"] == "error", result
        assert result["reason"] == "invalid_payload:not_text"
    finally:
        o.shutdown()
    _ok("async_malformed_payload_fails_closed_ok")


# ---- 6. idempotency / stale / terminal-once --------------------------------

def test_async_duplicate_request_no_reexec_ok():
    o = _make(max_workers=1)
    runs = []
    try:
        def counting(request, context, attempt):
            runs.append(request["request_id"])
            return {"status": "ok", "response": "x"}

        a = o.submit_turn("hi", classify=_answer, execute=counting,
                          idempotency_key="K1")
        dup = o.submit_turn("hi", classify=_answer, execute=counting,
                            idempotency_key="K1")
        o.wait(a["request_id"])
        assert dup["duplicate"] is True
        assert dup["accepted"] is False
        assert runs == [a["request_id"]]
    finally:
        o.shutdown()
    _ok("async_duplicate_request_no_reexec_ok")


def test_async_late_result_suppressed_ok():
    o = _make(max_workers=1)
    delivered = []
    try:
        def slow(request, context, attempt):
            time.sleep(0.15)
            return {"status": "ok", "response": "late"}

        a = o.submit_turn("hi", classify=_answer, execute=slow,
                          on_result=lambda r: delivered.append("late"))
        assert o.supersede(a["request_id"]) is True
        o.wait(a["request_id"])
        assert delivered == []
        assert o.stats()["stale_suppressed"] >= 1
    finally:
        o.shutdown()
    _ok("async_late_result_suppressed_ok")


def test_async_single_terminal_outcome_ok():
    o = _make(max_workers=1)
    try:
        a = o.submit_turn("hi", classify=_answer, execute=_ok_exec())
        result = o.wait(a["request_id"])
        assert result["terminal"] is True
        assert o.resolve_turn(a["request_id"], "approve")["request_id"]
        again = o.wait(a["request_id"])
        assert again["outcome"] == "completed", again
    finally:
        o.shutdown()
    _ok("async_single_terminal_outcome_ok")


# ---- 7. deterministic shutdown --------------------------------------------

def test_async_shutdown_no_worker_leak_ok():
    base = threading.active_count()
    o = _make(max_workers=2, max_queue=4)
    gate = threading.Event()
    o.submit_turn("hold", classify=_answer,
                  execute=lambda r, c, a: (gate.wait(2),
                                           {"status": "ok"})[1])
    o.submit_turn("queued", classify=_answer, execute=_ok_exec())
    gate.set()
    o.shutdown()
    time.sleep(0.1)
    assert o._executor.alive_workers() == 0
    assert threading.active_count() <= base, threading.active_count()
    try:
        o.submit_turn("x", classify=_answer, execute=_ok_exec())
        raise AssertionError("shutdown should reject new work")
    except RuntimeError:
        pass
    _ok("async_shutdown_no_worker_leak_ok")


def test_async_shutdown_suppresses_late_delivery_ok():
    o = _make(max_workers=1, max_queue=2)
    late = []
    try:
        o.submit_turn("hi", classify=_answer,
                      execute=lambda r, c, a: (time.sleep(0.2),
                                               {"status": "ok"})[1],
                      on_result=lambda r: late.append("x"))
        o.shutdown()
        time.sleep(0.3)
        assert late == []
    finally:
        o.shutdown()
    _ok("async_shutdown_suppresses_late_delivery_ok")


def test_async_close_session_ok():
    o = _make(max_workers=1, max_queue=4)
    gate = threading.Event()
    try:
        o.submit_turn("hold", session_id="s1", classify=_answer,
                      execute=lambda r, c, a: (gate.wait(2),
                                               {"status": "ok"})[1])
        time.sleep(0.05)
        b = o.submit_turn("b", session_id="s1", classify=_answer,
                          execute=_ok_exec())
        assert o.close_session("s1") is True
        assert o.wait(b["request_id"])["outcome"] == "cancelled"
        assert o.stats()["sessions_closed"] == 1
    finally:
        gate.set()
        o.shutdown()
    _ok("async_close_session_ok")


def test_async_repeated_approval_rearms_pending_ok():
    o = _make(max_workers=2, max_queue=4)

    def _approval(_t, _c):
        return {"kind": "act", "requires_execution": True,
                "requires_approval": True, "pending_title": "Same action"}

    try:
        first = o.submit_turn("do it", classify=_approval)
        first_snap = o.wait(first["request_id"])
        assert first_snap["outcome_class"] == "approval_required"
        assert first_snap["pending_id"]
        o.resolve_turn(first["request_id"], "deny")
        assert o.wait(first["request_id"])["outcome"] == "denied"
        # The same action asked again must re-arm, not collide on the stable
        # pending id and fail the turn.
        second = o.submit_turn("do it", classify=_approval)
        snap = o.wait(second["request_id"])
        assert snap["outcome_class"] == "approval_required", snap
        assert snap["pending_id"] == first_snap["pending_id"]
        ran = []
        o.resolve_turn(second["request_id"], "approve",
                       execute=lambda r, c, a: (ran.append(1),
                                                {"status": "ok",
                                                 "response": "done"})[1])
        done = o.wait(second["request_id"])
        assert done["outcome"] == "completed" and done["confirmed"] is True
        assert ran == [1]
    finally:
        o.shutdown()
    _ok("async_repeated_approval_rearms_pending_ok")


if __name__ == "__main__":
    for _name in sorted(
            n for n in dir() if n.startswith("test_")
            and callable(globals().get(n))):
        gl_blob = globals()[_name]
        if getattr(gl_blob, "__module__", "") != "__main__":
            continue
        gl_blob()
    print("test_async_orchestration=PASS")
