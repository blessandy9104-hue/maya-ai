"""Orchestration + conversational pipeline verification suite.

Verifies, at the pure Python layer (no Qt required), that one user message
becomes one request with:

- a stable correlation id and an optional idempotency key that prevents a
  duplicate execution after a retry or a UI refresh;
- an explicit lifecycle ending in exactly one terminal outcome
  (completed / denied / cancelled / timeout / unavailable / error / refused);
- bounded, idempotent retries that never produce a second terminal outcome;
- distinct failure classes (backend unavailable vs approval required vs action
  refused vs internal error) with the diagnostic reason preserved;
- fail-closed handling of malformed input, plans and executor results;
- a user-facing response rendered from the outcome that never claims an action
  completed unless the outcome really is completed;
- the chat pipeline and the student UI bridge reaching the same path without
  writing trust artifacts.

Skills: this module may print only benign lines (``=OK`` labels). No free-form
text, no tracebacks on the passing path.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import maya_orchestration as orch  # noqa: E402
import maya_pending as pending  # noqa: E402
from maya_runtime.ui.qt import bridge as ui_bridge  # noqa: E402

_REAL_FILES = (
    _REPO / "trusted_capabilities.jsonl",
    _REPO / "maya_trust_actions.jsonl",
)
_REAL_BEFORE = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
                for p in _REAL_FILES}


def _ok(label):
    print("=" + label + "=OK")


def _clock(value=0.0):
    return lambda: value


def _term_count(request):
    return sum(1 for row in request["history"]
               if row["state"] in orch.TERMINAL_OUTCOMES)


# ---- 1. deterministic completion ------------------------------------------

def test_orch_deterministic_completes_ok():
    o = orch.Orchestrator(clock=_clock())
    r = o.submit("hi", classify=lambda t, c: {
        "category": "conversation", "response": "Hello there."})
    assert r["state"] == "completed", r["state"]
    assert r["outcome"] == "completed"
    assert r["terminal"] is True
    assert r["confirmed"] is True
    assert r["response"] == "Hello there."
    assert r["outcome_class"] == "completed"
    _ok("orch_deterministic_completes_ok")


def test_orch_state_history_ok():
    o = orch.Orchestrator(clock=_clock())
    r = o.submit("hi", classify=lambda t, c: {"response": "ok"})
    states = [row["state"] for row in r["history"]]
    assert states[0] == "received"
    assert "planning" in states and "validating" in states
    assert states[-1] == "completed"
    _ok("orch_state_history_ok")


def test_orch_ids_unique_ok():
    o = orch.Orchestrator(clock=_clock())
    ids = {o.submit("m%d" % i, classify=lambda t, c: {"response": "x"})
           ["request_id"] for i in range(5)}
    assert len(ids) == 5
    assert all(i.startswith("req-") for i in ids)
    _ok("orch_ids_unique_ok")


# ---- 2. idempotency / retries ---------------------------------------------

def test_orch_idempotent_no_double_execute_ok():
    o = orch.Orchestrator(clock=_clock())
    calls = {"n": 0}

    def execute(request, context, attempt):
        calls["n"] += 1
        return {"status": "ok", "response": "done", "confirmed": True}

    first = o.submit("go", idempotency_key="k-1",
                     classify=lambda t, c: {"requires_execution": True},
                     execute=execute)
    again = o.submit("go", idempotency_key="k-1",
                     classify=lambda t, c: {"requires_execution": True},
                     execute=execute)
    assert first["request_id"] == again["request_id"]
    assert again["duplicate"] is True
    assert calls["n"] == 1
    _ok("orch_idempotent_no_double_execute_ok")


def test_orch_retry_bounded_ok():
    o = orch.Orchestrator(clock=_clock(), max_attempts=2)
    r = o.submit("go", classify=lambda t, c: {"requires_execution": True},
                 execute=lambda req, ctx, a: {"status": "error",
                                              "reason": "boom"})
    assert r["state"] == "error", r["state"]
    assert r["attempts"] == 2
    assert r["outcome_class"] == "internal_error"
    _ok("orch_retry_bounded_ok")


def test_orch_retry_recovers_ok():
    o = orch.Orchestrator(clock=_clock(), max_attempts=1)
    r = o.submit("go", classify=lambda t, c: {"requires_execution": True},
                 execute=lambda req, ctx, a: {"status": "unavailable",
                                              "reason": "backend"})
    assert r["state"] == "unavailable"
    r2, note = o.resolve(r["request_id"], "retry",
                         execute=lambda req, ctx, a: {
                             "status": "ok", "response": "Recovered.",
                             "confirmed": True})
    assert note == "retried", note
    assert r2["state"] == "completed"
    assert r2["response"] == "Recovered."
    _ok("orch_retry_recovers_ok")


# ---- 3. approval-required vs refused vs unavailable vs error ---------------

def test_orch_approval_required_ok():
    store = pending.PendingStore(clock=_clock())
    o = orch.Orchestrator(clock=_clock(), pending=store)
    r = o.submit("install it", classify=lambda t, c: {
        "requires_approval": True, "pending_title": "Install dependency",
        "pending_required_action": "approve",
        "pending_next_step": "Review and approve."})
    assert r["state"] == "awaiting_approval"
    assert r["outcome_class"] == "approval_required"
    assert r["pending_id"]
    assert store.get(r["pending_id"])["status"] == "pending"
    assert r["pending_id"] in r["response"]
    assert ":pending approve" in r["response"]
    _ok("orch_approval_required_ok")


def test_orch_approve_executes_once_ok():
    store = pending.PendingStore(clock=_clock())
    o = orch.Orchestrator(clock=_clock(), pending=store)
    r = o.submit("install it", classify=lambda t, c: {
        "requires_approval": True, "pending_title": "Install dependency"})
    calls = {"n": 0}
    r2, note = o.resolve(
        r["request_id"], "approve",
        execute=lambda req, ctx, a: (calls.__setitem__("n", calls["n"] + 1)
                                     or {"status": "ok",
                                         "response": "Installed.",
                                         "confirmed": True}))
    assert note == "approved", note
    assert r2["state"] == "completed"
    assert calls["n"] == 1
    assert store.get(r["pending_id"])["status"] == "approved"
    assert r2["response"] == "Installed."
    _ok("orch_approve_executes_once_ok")


def test_orch_deny_terminal_ok():
    store = pending.PendingStore(clock=_clock())
    o = orch.Orchestrator(clock=_clock(), pending=store)
    r = o.submit("install it", classify=lambda t, c: {"requires_approval": True,
                                                      "pending_title": "X"})
    r2, note = o.resolve(r["request_id"], "deny")
    assert note == "denied"
    assert r2["state"] == "denied"
    assert "won't" in r2["response"]
    again, note2 = o.resolve(r["request_id"], "approve")
    assert note2.startswith("already_terminal")
    assert again["state"] == "denied"
    assert store.get(r["pending_id"])["status"] == "denied"
    _ok("orch_deny_terminal_ok")


def test_orch_cancel_ok():
    o = orch.Orchestrator(clock=_clock())
    r = o.submit("x", classify=lambda t, c: {"requires_approval": True,
                                             "pending_title": "X"})
    r2, note = o.resolve(r["request_id"], "cancel")
    assert note == "cancelled"
    assert r2["state"] == "cancelled"
    assert "Cancelled" in r2["response"]
    _ok("orch_cancel_ok")


def test_orch_refused_distinct_ok():
    o = orch.Orchestrator(clock=_clock())
    r = o.submit("delete everything",
                 classify=lambda t, c: {"requires_execution": True},
                 execute=lambda req, ctx, a: {"status": "refused",
                                              "reason": "out_of_scope"})
    assert r["state"] == "refused"
    assert r["outcome_class"] == "action_refused"
    assert "No action was taken" in r["response"]
    _ok("orch_refused_distinct_ok")


def test_orch_unavailable_distinct_ok():
    o = orch.Orchestrator(clock=_clock(), max_attempts=1)
    r = o.submit("answer me",
                 classify=lambda t, c: {"requires_execution": True},
                 execute=lambda req, ctx, a: {"status": "unavailable",
                                              "reason": "no_model"})
    assert r["state"] == "unavailable"
    assert r["outcome_class"] == "backend_unavailable"
    assert "haven't done it" in r["response"]
    _ok("orch_unavailable_distinct_ok")


def test_orch_internal_error_preserves_reason_ok():
    def boom(request, context, attempt):
        raise ValueError("kaboom")

    o = orch.Orchestrator(clock=_clock(), max_attempts=1)
    r = o.submit("go", classify=lambda t, c: {"requires_execution": True},
                 execute=boom)
    assert r["state"] == "error"
    assert "ValueError" in r["diagnostic"]["reason"] or \
        "ValueError" in r["reason"]
    assert "Reason:" in r["response"]
    _ok("orch_internal_error_preserves_reason_ok")


# ---- 4. fail-closed validation --------------------------------------------

def test_orch_invalid_payload_fail_closed_ok():
    o = orch.Orchestrator(clock=_clock())
    for bad in ("", "   ", None, 5):
        r = o.submit(bad, classify=lambda t, c: {"response": "should not run"})
        assert r["state"] == "error", (bad, r["state"])
        assert r["reason"].startswith("invalid_payload")
        assert "changed nothing" in r["response"]
    _ok("orch_invalid_payload_fail_closed_ok")


def test_orch_invalid_plan_fail_closed_ok():
    o = orch.Orchestrator(clock=_clock())
    r1 = o.submit("x", classify=lambda t, c: "not a dict")
    assert r1["state"] == "error"
    assert "invalid_plan" in r1["reason"]
    r2 = o.submit("x", classify=lambda t, c: {"response": 123})
    assert r2["state"] == "error"
    assert "invalid_plan" in r2["reason"]
    r3 = o.submit("x", classify=lambda t, c: {"kind": "bogus"})
    assert r3["state"] == "error"
    assert "invalid_plan" in r3["reason"]
    _ok("orch_invalid_plan_fail_closed_ok")


def test_orch_clarify_awaits_user_ok():
    o = orch.Orchestrator(clock=_clock())
    r = o.submit("do the thing", classify=lambda t, c: {
        "kind": "clarify", "response": "Which thing do you mean?"})
    assert r["state"] == "awaiting_user"
    assert r["outcome_class"] == "clarification_required"
    assert r["response"] == "Which thing do you mean?"
    _ok("orch_clarify_awaits_user_ok")


def test_orch_timeout_ok():
    calls = {"n": 0}

    def clock():
        calls["n"] += 1
        return 0.0 if calls["n"] == 1 else 1000.0

    o = orch.Orchestrator(clock=clock, timeout_seconds=90.0)
    r = o.submit("slow", classify=lambda t, c: {"requires_execution": True},
                 execute=lambda req, ctx, a: {"status": "ok",
                                              "response": "late"})
    assert r["state"] == "timeout", r["state"]
    assert "Nothing was completed" in r["response"]
    _ok("orch_timeout_ok")


# ---- 5. one terminal outcome + honest responses ---------------------------

def test_orch_one_terminal_outcome_ok():
    o = orch.Orchestrator(clock=_clock(), max_attempts=1)
    requests = [
        o.submit("a", classify=lambda t, c: {"response": "x"}),
        o.submit("b", classify=lambda t, c: {"requires_execution": True},
                 execute=lambda req, ctx, a: {"status": "error",
                                              "reason": "e"}),
        o.submit("c", classify=lambda t, c: {"requires_approval": True,
                                             "pending_title": "T"}),
    ]
    for r in requests:
        if r["terminal"]:
            assert _term_count(r) == 1, r["history"]
        else:
            assert _term_count(r) == 0, r["history"]
    _ok("orch_one_terminal_outcome_ok")


def test_orch_honest_responses_ok():
    assert "Done" in orch._response_for(
        {"outcome": "completed", "confirmed": True})
    assert "changed nothing" in orch._response_for({"outcome": "error"}).lower()
    refused = orch._response_for({"outcome": "refused"})
    assert "No action was taken" in refused
    unavail = orch._response_for({"outcome": "unavailable"})
    assert "haven't done it" in unavail
    _ok("orch_honest_responses_ok")


# ---- 6. real chat pipeline integration ------------------------------------

def test_orch_chat_deterministic_ok():
    import maya_chat
    r = maya_chat.orchestrate_chat_turn("hello", [])
    assert r["state"] == "completed", (r["state"], r["reason"])
    assert r["outcome"] == "completed"
    assert r["response"] == "Hello. I'm Maya."
    assert _term_count(r) == 1
    _ok("orch_chat_deterministic_ok")


def test_orch_chat_model_path_ok():
    import maya_chat
    original = maya_chat.ask
    maya_chat.ask = lambda history, text: "Stub answer."
    try:
        r = maya_chat.orchestrate_chat_turn(
            "tell me about quantum widgets in the abstract", [])
    finally:
        maya_chat.ask = original
    assert r["state"] == "completed", (r["state"], r["reason"])
    assert r["response"] == "Stub answer."
    assert r["confirmed"] is True
    _ok("orch_chat_model_path_ok")


def test_orch_chat_model_unavailable_ok():
    import maya_chat
    original = maya_chat.ask

    def boom(history, text):
        raise OSError("no model")

    maya_chat.ask = boom
    try:
        r = maya_chat.orchestrate_chat_turn(
            "tell me about quantum widgets in the abstract", [])
    finally:
        maya_chat.ask = original
    assert r["state"] == "unavailable", (r["state"], r["reason"])
    assert "OSError" in r["diagnostic"]["reason"]
    assert isinstance(r["response"], str) and r["response"].strip()
    _ok("orch_chat_model_unavailable_ok")


def test_orch_chat_classify_no_side_effects_ok():
    import maya_chat
    plan = maya_chat._orchestration_classify("hello", [])
    assert plan.get("response") == "Hello. I'm Maya."
    assert plan.get("requires_execution") is False
    _ok("orch_chat_classify_no_side_effects_ok")


# ---- 7. UI bridge pending surface -----------------------------------------

def test_orch_bridge_pending_surface_ok():
    ticker = ui_bridge.UiTicker()
    item = pending.make_item("orchestration", "Install dependency",
                             "Needs your OK", "approve", "Review and approve.",
                             now=1.0, item_id="p-1")
    ticker.set_pending([item])
    view = ticker.apply_tick_snapshot(ticker.make_tick_payload("idle"))
    assert len(view["ui"]["pending"]) == 1
    assert view["ui"]["pending_open"] == 1
    assert "approval item" in view["ui"]["human_summary"]
    assert len(view["pending"]) == 1
    assert len(view["live_lines"]) == 7
    _ok("orch_bridge_pending_surface_ok")


def test_orch_bridge_pending_controls_ok():
    item = pending.make_item("orchestration", "T", "s", "approve", "n",
                             now=1.0, item_id="p-2")
    view = ui_bridge.student_view(None, "unavailable", [item])
    row = view["pending"][0]
    assert row["id"] == "p-2"
    assert "approve" in row["controls"]
    deterministic = ui_bridge.student_view(None, "unavailable", [item])
    assert view == deterministic
    _ok("orch_bridge_pending_controls_ok")


def test_orch_real_artifacts_untouched_ok():
    after = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
             for p in _REAL_FILES}
    assert after == _REAL_BEFORE, (after, _REAL_BEFORE)
    _ok("orch_real_artifacts_untouched_ok")


if __name__ == "__main__":
    for _name in sorted(globals()):
        if _name.startswith("test_") and callable(globals()[_name]):
            globals()[_name]()
    print("test_orchestration_lifecycle=PASS")
