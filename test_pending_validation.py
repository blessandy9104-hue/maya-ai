"""Pending-validation lifecycle verification suite.

Verifies that every pending validation has an explicit lifecycle with exactly
one terminal outcome (approved / denied / expired / cancelled / failed /
unavailable), that stale items expire deterministically, that resolution is
idempotent and never duplicates, that the actionable projection always carries
the specific item, required action, next step and controls, and that the chat
surface can resolve items explicitly. Nothing here writes trust artifacts.

Skills: this module may print only benign lines (``=OK`` labels). No free-form
text, no tracebacks on the passing path.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import maya_pending as pending  # noqa: E402

_REAL_FILES = (
    _REPO / "trusted_capabilities.jsonl",
    _REPO / "maya_trust_actions.jsonl",
)
_REAL_BEFORE = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
                for p in _REAL_FILES}


def _ok(label):
    print("=" + label + "=OK")


# ---- 1. item construction -------------------------------------------------

def test_pend_item_shape_ok():
    item = pending.make_item("capability", "Browser access", "Grant browse",
                             "approve", "Review the request.", now=10,
                             ttl_seconds=60, source="trust")
    for key in ("id", "kind", "title", "summary", "required_action",
                "next_step", "status", "created_at", "updated_at",
                "expires_at", "source", "reason", "attempts"):
        assert key in item, key
    assert item["status"] == pending.PENDING
    assert item["created_at"] == 10.0
    assert item["expires_at"] == 70.0
    assert pending.is_terminal(item["status"]) is False
    _ok("pend_item_shape_ok")


def test_pend_stable_id_ok():
    a = pending.make_item("capability", "Browser access", "Grant browse",
                          "approve", "Review.", now=1, source="trust")
    b = pending.make_item("capability", "Browser access", "changed summary",
                          "approve", "changed.", now=2, source="trust")
    assert a["id"] == b["id"]
    c = pending.make_item("capability", "Browser access", "Grant browse",
                          "approve", "Review.", now=1, source="other")
    assert c["id"] != a["id"]
    _ok("pend_stable_id_ok")


def test_pend_unknown_status_fails_closed_ok():
    item = pending.make_item("capability", "T", "s", "a", "n",
                             status="totally_made_up")
    assert item["status"] == pending.UNAVAILABLE
    assert pending.is_terminal(item["status"]) is True
    _ok("pend_unknown_status_fails_closed_ok")


def test_pend_input_not_mutated_ok():
    item = pending.make_item("capability", "T", "s", "a", "n", now=0)
    snapshot = dict(item)
    pending.resolve(item, "approve", now=5)
    pending.sweep([item], now=500)
    assert item == snapshot
    _ok("pend_input_not_mutated_ok")


# ---- 2. terminal outcomes -------------------------------------------------

def test_pend_approve_terminal_ok():
    item = pending.make_item("capability", "T", "s", "a", "n", now=0)
    out, changed, note = pending.resolve(item, "approve", now=3)
    assert changed is True and note == "approved"
    assert out["status"] == pending.APPROVED
    assert pending.is_terminal(out["status"]) is True
    assert out["updated_at"] == 3.0
    _ok("pend_approve_terminal_ok")


def test_pend_deny_and_reject_ok():
    item = pending.make_item("capability", "T", "s", "a", "n")
    for decision in ("deny", "reject"):
        out, changed, note = pending.resolve(item, decision, now=1)
        assert changed is True
        assert out["status"] == pending.DENIED
    _ok("pend_deny_and_reject_ok")


def test_pend_cancel_and_dismiss_ok():
    item = pending.make_item("capability", "T", "s", "a", "n")
    for decision in ("cancel", "dismiss"):
        out, changed, _note = pending.resolve(item, decision, now=1)
        assert changed is True
        assert out["status"] == pending.CANCELLED
    _ok("pend_cancel_and_dismiss_ok")


def test_pend_internal_outcomes_ok():
    item = pending.make_item("capability", "T", "s", "a", "n")
    for decision, expected in (("expire", pending.EXPIRED),
                               ("fail", pending.FAILED),
                               ("unavailable", pending.UNAVAILABLE)):
        out, changed, _note = pending.resolve(item, decision, now=1)
        assert changed is True
        assert out["status"] == expected
    _ok("pend_internal_outcomes_ok")


def test_pend_retry_rearms_ok():
    item = pending.make_item("capability", "T", "s", "a", "n")
    failed, _c, _n = pending.resolve(item, "fail", now=1)
    retried, changed, note = pending.resolve(failed, "retry", now=2)
    assert changed is True and note == "retried"
    assert retried["status"] == pending.PENDING
    assert retried["attempts"] == 1
    assert pending.is_terminal(retried["status"]) is False
    _ok("pend_retry_rearms_ok")


def test_pend_retry_non_retryable_ok():
    item = pending.make_item("capability", "T", "s", "a", "n")
    out, changed, note = pending.resolve(item, "retry", now=1)
    assert changed is False
    assert note == "not_retryable:pending"
    assert out["status"] == pending.PENDING
    _ok("pend_retry_non_retryable_ok")


def test_pend_double_resolve_idempotent_ok():
    item = pending.make_item("capability", "T", "s", "a", "n")
    first, _c, _n = pending.resolve(item, "approve", now=1)
    second, changed, note = pending.resolve(first, "deny", now=2)
    assert changed is False
    assert note == "already_terminal:approved"
    assert second["status"] == pending.APPROVED
    _ok("pend_double_resolve_idempotent_ok")


def test_pend_unknown_decision_ok():
    item = pending.make_item("capability", "T", "s", "a", "n")
    out, changed, note = pending.resolve(item, "explode", now=1)
    assert changed is False
    assert note == "unknown_decision:explode"
    assert out["status"] == pending.PENDING
    _ok("pend_unknown_decision_ok")


def test_pend_controls_matrix_ok():
    assert pending.controls_for(pending.PENDING) == ("approve", "deny", "cancel")
    assert pending.controls_for(pending.APPROVED) == ()
    assert pending.controls_for(pending.DENIED) == ()
    assert pending.controls_for(pending.FAILED) == ("retry", "dismiss")
    assert pending.controls_for(pending.UNAVAILABLE) == ("retry", "dismiss")
    _ok("pend_controls_matrix_ok")


# ---- 3. TTL / sweep -------------------------------------------------------

def test_pend_ttl_sweep_expires_ok():
    item = pending.make_item("capability", "T", "s", "a", "n", now=0,
                             ttl_seconds=30)
    not_yet = pending.sweep([item], now=29)
    assert not_yet[0]["status"] == pending.PENDING
    expired = pending.sweep([item], now=30)
    assert expired[0]["status"] == pending.EXPIRED
    assert expired[0]["reason"] == "ttl_elapsed"
    _ok("pend_ttl_sweep_expires_ok")


def test_pend_no_ttl_never_expires_ok():
    item = pending.make_item("capability", "T", "s", "a", "n", now=0)
    assert item["expires_at"] is None
    swept = pending.sweep([item], now=10 ** 9)
    assert swept[0]["status"] == pending.PENDING
    _ok("pend_no_ttl_never_expires_ok")


def test_pend_terminal_not_swept_ok():
    item = pending.make_item("capability", "T", "s", "a", "n", now=0,
                             ttl_seconds=1)
    approved, _c, _n = pending.resolve(item, "approve", now=0)
    swept = pending.sweep([approved], now=999)
    assert swept[0]["status"] == pending.APPROVED
    _ok("pend_terminal_not_swept_ok")


# ---- 4. projection / ordering / summary -----------------------------------

def test_pend_surface_order_ok():
    old_open = pending.make_item("capability", "old", "s", "a", "n", now=1,
                                 item_id="p-old")
    new_open = pending.make_item("capability", "new", "s", "a", "n", now=5,
                                 item_id="p-new")
    closed = pending.make_item("capability", "closed", "s", "a", "n", now=9,
                               item_id="p-closed")
    closed, _c, _n = pending.resolve(closed, "deny", now=9)
    rows = pending.surface([old_open, closed, new_open])
    assert [r["id"] for r in rows] == ["p-new", "p-old", "p-closed"]
    assert rows[0]["terminal"] is False and rows[0]["controls"]
    assert rows[2]["terminal"] is True and rows[2]["controls"] == []
    _ok("pend_surface_order_ok")


def test_pend_summary_counts_ok():
    open_item = pending.make_item("capability", "a", "s", "a", "n",
                                  item_id="1")
    approved_item = pending.resolve(
        pending.make_item("capability", "b", "s", "a", "n", item_id="2"),
        "approve", now=1)[0]
    items = [open_item, approved_item]
    counts = pending.summarize(items)
    assert counts["open"] == 1
    assert counts["total"] == 2
    assert counts["outcomes"]["approved"] == 1
    _ok("pend_summary_counts_ok")


def test_pend_human_summary_ok():
    assert pending.human_summary([]) == \
        "Nothing needs your approval right now."
    item = pending.make_item("capability", "Browser access", "s", "approve",
                             "n", now=0)
    text = pending.human_summary([item])
    assert "Browser access" in text
    assert "approve" in text
    _ok("pend_human_summary_ok")


# ---- 5. store -------------------------------------------------------------

def test_pend_store_duplicate_id_ok():
    store = pending.PendingStore(clock=lambda: 0.0)
    store.add(pending.make_item("capability", "T", "s", "a", "n",
                                item_id="dup"))
    try:
        store.add(pending.make_item("capability", "T2", "s", "a", "n",
                                    item_id="dup"))
        raised = False
    except ValueError:
        raised = True
    assert raised is True
    _ok("pend_store_duplicate_id_ok")


def test_pend_store_unknown_item_ok():
    store = pending.PendingStore(clock=lambda: 0.0)
    item, changed, note = store.resolve("nope", "approve")
    assert item is None and changed is False and note == "unknown_item"
    _ok("pend_store_unknown_item_ok")


def test_pend_store_clock_ttl_ok():
    now = {"t": 0.0}
    store = pending.PendingStore(clock=lambda: now["t"])
    store.create("capability", "T", "s", "approve", "n", ttl_seconds=10,
                 item_id="ttl")
    now["t"] = 5.0
    store.sweep()
    assert store.get("ttl")["status"] == pending.PENDING
    now["t"] = 11.0
    store.sweep()
    assert store.get("ttl")["status"] == pending.EXPIRED
    _ok("pend_store_clock_ttl_ok")


# ---- 6. explicit chat resolution surface ----------------------------------

def test_pend_chat_command_list_ok():
    import maya_chat
    maya_chat._CHAT_PENDING = pending.PendingStore(clock=lambda: 0.0)
    maya_chat._CHAT_PENDING.create("capability", "Browser access", "s",
                                   "approve", "Review it.", item_id="c-1")
    text = maya_chat._pending_command(":pending")
    assert "Browser access" in text
    assert "approve" in text
    assert "c-1" in text or "controls" in text
    _ok("pend_chat_command_list_ok")


def test_pend_chat_command_resolve_ok():
    import maya_chat
    store = pending.PendingStore(clock=lambda: 0.0)
    maya_chat._CHAT_PENDING = store
    store.create("capability", "Browser access", "s", "approve", "Review.",
                 item_id="c-2")
    text = maya_chat._pending_command(":pending approve c-2")
    assert "Approved" in text
    assert store.get("c-2")["status"] == pending.APPROVED
    denied = maya_chat._pending_command(":pending deny c-2")
    assert "already" in denied.lower() or "approved" in denied.lower()
    _ok("pend_chat_command_resolve_ok")


def test_pend_chat_command_usage_ok():
    import maya_chat
    maya_chat._CHAT_PENDING = pending.PendingStore(clock=lambda: 0.0)
    assert "Unknown pending action" in \
        maya_chat._pending_command(":pending frobnicate x")
    assert "Which item" in maya_chat._pending_command(":pending approve")
    assert "No pending item" in \
        maya_chat._pending_command(":pending approve missing-id")
    assert "Use :pending" in maya_chat._pending_command(":pending help")
    _ok("pend_chat_command_usage_ok")


def test_pend_real_artifacts_untouched_ok():
    after = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
             for p in _REAL_FILES}
    assert after == _REAL_BEFORE, (after, _REAL_BEFORE)
    _ok("pend_real_artifacts_untouched_ok")


if __name__ == "__main__":
    for _name in sorted(globals()):
        if _name.startswith("test_") and callable(globals()[_name]):
            globals()[_name]()
    print("test_pending_validation=PASS")
