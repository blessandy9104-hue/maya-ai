"""Phase 4 retention & mailbox-bound suite (``expected_ok=17``).

Contract (registered in ``verification/manifest.py``):

Arm executor -- ``BoundedExecutor`` retention (R1 release + R2 bounded tracking):
  - terminal callables (``_fn``/``_args``/``_kwargs``) are released and counted,
    the live handle state/result stay readable and evicted handles return
    ``None`` from ``handle()`` (existing unknown-id semantics);
  - tracking stays capped at ``max_tracked`` once everything settles, eviction
    drops oldest-completed handles first (newest retained, all terminal refs
    already released), and a non-terminal handle is never evicted;
  - queued cancellation still removes work before run and still counts/reports
    ``queued``; cancelling into a terminal/unknown id still resolves to
    ``None``;
  - a running job that observes its cancelled token suppresses the late value
    (state ``cancelled``, ``result`` stays ``None``, cancel_reason
    ``late_result``);
  - delivered results keep ordering/identity invariants under a capped registry;
  - shutdown cancels queued work cooperatively, joins promptly, leaves at most
    ``max_tracked`` terminal handles behind and rejects new submissions.

Arm mailbox -- ``maya_app.Mailbox`` bound UI control-box:
  - the queue never grows past the cap under a flood: capacity holds, the
    controller's drop counter tracks every dropped message;
  - content (chat/log) keeps the newest message by retiring the oldest, so a
    flood can never silence the most recent line (incl. an emergency line);
  - refresh state (tick/settings/chip/activity/...) drops newest at the door
    when full;
  - a ``[_mailbox] UI behind`` truncation banner surfaces (rate-limited) once
    output is dropped, and the drained box ends empty with the ``poll``-style
    ``get_nowait``/``queue.Empty`` loop intact;
  - the tick generation stream the ``poll`` continuation guard consumes stays
    in strictly non-decreasing order, and the guard attributes
    (``_stale_skips``/``_last_committed_gen``/``poll``) remain wired.

Skills: prints only benign ``=OK`` labels; never writes files; runs headless on
any interpreter (no Tk window, no Qt, no subprocess).
"""
from __future__ import annotations

import queue as _queue
import sys
import threading
import time

import maya_app
from maya_async import BoundedExecutor, CancelToken


def _ok(label):
    print("=" + label + "=OK")


def _wait(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.004)
    return predicate()


def _finished(ex):
    s = ex.stats()
    return s["completed"] + s["failed"] + s["cancelled"]


def _wait_finish(ex, total, timeout=20.0):
    return _wait(lambda: _finished(ex) >= total, timeout=timeout)


def _quick(value):
    return value


def _run_many(njobs, *, cap, workers=4, seed_jobs=True):
    ex = BoundedExecutor(max_workers=workers, max_queue=2048,
                         max_tracked=cap, name="ret-bounded")
    handles = []
    completions = []

    def on_done(value, handle):
        completions.append(handle.request_key)

    for i in range(njobs):
        handles.append(
            ex.submit(_quick, i, request_id="rt-%02d" % i, generation=i,
                      on_done=on_done))
    if not _wait_finish(ex, njobs):
        raise AssertionError("jobs never settled: " + str(ex.stats()))
    return ex, handles, completions


# ---------------------------------------------------------------------------
# Executor retention arm -- R2 bounded tracking
# ---------------------------------------------------------------------------

def test_retention_cap_holds_ok():
    ex, handles, completions = _run_many(12, cap=4)
    s = ex.stats()
    assert s["tracked"] <= 4 and s["tracked"] > 0, s
    assert s["queued"] == 0 and s["running"] == 0, s
    ex.shutdown()
    _ok("retention_cap_holds_ok")


def test_retention_evicted_count_ok():
    ex, handles, completions = _run_many(12, cap=4)
    s = ex.stats()
    assert s["evicted"] == 8, s
    ex.shutdown()
    _ok("retention_evicted_count_ok")


def test_retention_oldest_gone_newest_ok():
    ex, handles, completions = _run_many(12, cap=4)
    assert len(completions) == 12, completions
    first = completions[:8]
    last = completions[-4:]
    for key in first:
        assert ex.handle(key) is None, key
    for key in last:
        found = ex.handle(key)
        assert found is not None, key
        assert found.result == int(key.split("-")[1]), key
    s = ex.stats()
    assert s["tracked"] == 4, s
    ex.shutdown()
    _ok("retention_oldest_gone_newest_ok")


def test_retention_release_refs_ok():
    ex, handles, completions = _run_many(12, cap=4)
    for h in handles:
        assert h.released is True, h.task_id
        assert h._fn is None, h.task_id
        assert h._args is None, h.task_id
        assert h._kwargs is None, h.task_id
    s = ex.stats()
    assert s["released"] == 12, s
    ex.shutdown()
    _ok("retention_release_refs_ok")


def test_retention_nonterminal_never_evicted_ok():
    ex = BoundedExecutor(max_workers=1, max_queue=8, max_tracked=1,
                         name="ret-live")
    gate = threading.Event()
    hold = ex.submit(gate.wait, 10.0, request_id="nt-hold", generation=0)
    assert _wait(lambda: ex.handle("nt-hold").state == "running"), "hold never ran"
    for idx in ("nt-a", "nt-b", "nt-c"):
        ex.submit(_quick, idx, request_id=idx, generation=1)
    s = ex.stats()
    assert s["tracked"] == 4, s
    assert s["evicted"] == 0, s
    assert s["released"] == 0, s
    assert ex.handle("nt-hold").state == "running", "non-terminal was evicted"
    for idx in ("nt-a", "nt-b", "nt-c"):
        assert ex.handle(idx).state == "queued", idx
    gate.set()
    assert _wait_finish(ex, 4)
    s = ex.stats()
    assert s["tracked"] == 1 and s["evicted"] >= 3, s
    ex.shutdown()
    _ok("retention_nonterminal_never_evicted_ok")


def test_retention_cancel_queued_ok():
    ex = BoundedExecutor(max_workers=1, max_queue=8, max_tracked=4,
                         name="ret-cancel")
    gate = threading.Event()
    ran = []
    hold = ex.submit(gate.wait, 10.0, request_id="cq-hold", generation=0)
    assert _wait(lambda: ex.handle("cq-hold").state == "running"), "hold never ran"
    for idx in ("cq-a", "cq-b", "cq-c"):
        ex.submit(lambda idx=idx: ran.append(idx), request_id=idx,
                  generation=1)
    assert ex.cancel("cq-b") == "queued"
    assert ex.cancel("cq-a") == "queued"
    assert ex.cancel("cq-c") == "queued"
    assert ex.cancel("cq-none") is None
    assert ex.handle("cq-hold").state == "running"
    gate.set()
    assert _wait_finish(ex, 4)
    assert ran == [], "cancelled queued tasks ran"
    assert ex.handle("cq-hold").state == "done"
    assert ex.cancel("cq-hold") is None, "cancelling a terminal handle changed"
    ex.shutdown()
    _ok("retention_cancel_queued_ok")


def test_retention_late_suppress_ok():
    ex = BoundedExecutor(max_workers=1, max_queue=8, max_tracked=4,
                         name="ret-late")
    token = CancelToken()

    def late_job():
        time.sleep(0.05)
        token.cancel()
        return "late-value"

    h = ex.submit(late_job, request_id="ls-1", generation=1,
                  cancel_token=token)
    assert _wait(lambda: ex.handle("ls-1").state == "cancelled", timeout=8.0)
    assert h.result is None, "late value was delivered"
    assert h.cancel_reason == "late_result", h.cancel_reason
    assert h.released is True and h._fn is None
    s = ex.stats()
    assert s["cancelled"] == 1 and s["completed"] == 0 and s["released"] == 1, s
    ex.shutdown()
    _ok("retention_late_suppress_ok")


def test_retention_ordering_ok():
    ex = BoundedExecutor(max_workers=4, max_queue=32, max_tracked=8,
                         name="ret-order")
    completions = []

    def on_done(value, handle):
        completions.append((handle.request_key, value))

    for i in range(20):
        ex.submit(_quick, i, request_id="ro-%02d" % i, generation=i,
                  on_done=on_done)
    assert _wait_finish(ex, 20)
    assert len(completions) == 20, completions
    seen = {}
    for key, value in completions:
        assert key not in seen, "duplicate delivery: " + key
        seen[key] = True
        assert value == int(key.split("-")[1]), (key, value)
    s = ex.stats()
    assert s["tracked"] == 8 and s["evicted"] == 12 and s["released"] == 20, s
    ex.shutdown()
    _ok("retention_ordering_ok")


def test_retention_shutdown_bounded_ok():
    ex = BoundedExecutor(max_workers=2, max_queue=64, max_tracked=2,
                         name="ret-down")
    gate = threading.Event()
    for i in range(20):
        ex.submit(gate.wait, 10.0, request_id="sd-%02d" % i, generation=i)

    def release_later():
        time.sleep(0.2)
        gate.set()

    threading.Thread(target=release_later, daemon=True).start()
    started = time.monotonic()
    ex.shutdown(wait=True, timeout=8.0)
    elapsed = time.monotonic() - started
    assert elapsed < 6.0, "shutdown joined slowly: %.2fs" % elapsed
    s = ex.stats()
    assert s["cancelled"] == 20, s
    assert s["completed"] == 0, s
    assert s["released"] == 20, s
    assert s["tracked"] == 2, s
    assert s["evicted"] == 18, s
    try:
        ex.submit(_quick, 1, request_id="sd-after")
        raise AssertionError("submit after shutdown did not raise")
    except RuntimeError:
        pass
    ex.shutdown()  # idempotent
    _ok("retention_shutdown_bounded_ok")


def test_retention_race_invariant_ok():
    ex = BoundedExecutor(max_workers=4, max_queue=512, max_tracked=8,
                         name="ret-race")
    result = {"submitted": 0}

    def submitter(batch):
        for i in range(50):
            ex.submit(_quick, i, request_id="rc-%s-%02d" % (batch, i),
                     generation=i)
            result["submitted"] += 1

    threads = [threading.Thread(target=submitter, args=(b,), daemon=True)
               for b in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _wait_finish(ex, 200)
    s = ex.stats()
    assert result["submitted"] == 200 and s["submitted"] == 200, (result, s)
    assert s["completed"] == 200, s
    assert s["released"] == 200, s
    assert s["tracked"] == 8 and s["evicted"] == 192, s
    with ex._cond:
        assert len(ex._by_request) == len(ex._handles), \
            (len(ex._by_request), len(ex._handles))
        assert len(ex._terminal_order) == len(ex._handles), \
            (len(ex._terminal_order), len(ex._handles))
        for h in ex._handles.values():
            assert h.terminal and h.released, h.task_id
    ex.shutdown()
    _ok("retention_race_invariant_ok")


# ---------------------------------------------------------------------------
# Mailbox bound arm -- maya_app.Mailbox
# ---------------------------------------------------------------------------

def _drain(mb):
    out = []
    while True:
        try:
            out.append(mb.get_nowait())
        except _queue.Empty:
            return out


def test_mailbox_cap_holds_ok():
    mb = maya_app.Mailbox(maya_app._MAIL_CAP)
    assert mb.maxsize == maya_app._MAIL_CAP
    for i in range(2000):
        mb.put("log", "sink", "line-%d" % i, maya_app.C["ink"])
        assert mb.qsize() <= maya_app._MAIL_CAP
    assert mb.qsize() == maya_app._MAIL_CAP
    assert mb.drops > 0
    _ok("mailbox_cap_holds_ok")


def test_mailbox_refresh_drop_newest_ok():
    mb = maya_app.Mailbox(maya_app._MAIL_CAP)
    for i in range(maya_app._MAIL_CAP):
        mb.put("tick", None)
    drops_before = mb.drops
    dropped = mb.put("settings_refresh", None)
    assert dropped is True, "overflowing refresh must report a drop"
    assert mb.drops == drops_before + 1
    assert mb.qsize() == maya_app._MAIL_CAP
    contents = _drain(mb)
    assert all(item[0] == "tick" for item in contents)
    assert not any(item[0] == "settings_refresh" for item in contents), \
        "refresh drop-newest must not queue the newest refresh"
    _ok("mailbox_refresh_drop_newest_ok")


def test_mailbox_content_preserved_newest_ok():
    mb = maya_app.Mailbox(maya_app._MAIL_CAP)
    for i in range(maya_app._MAIL_CAP):
        mb.put("tick", None)
    dropped = mb.put("chat", "latest line")
    assert dropped is True
    assert mb.qsize() == maya_app._MAIL_CAP
    contents = _drain(mb)
    assert contents[-1][0] == "chat" and contents[-1][1] == "latest line", \
        "the newest content message must survive"
    assert all(item[0] != "chat" for item in contents[:-1])
    _ok("mailbox_content_preserved_newest_ok")


def test_mailbox_log_never_silent_ok():
    mb = maya_app.Mailbox(maya_app._MAIL_CAP)
    for i in range(2000):
        mb.put("log", "thinking", "line-%d\n" % i, maya_app.C["ink"])
    mb.put("log", "control", "[EMERGENCY] newest line must land\n",
           maya_app.C["bad"])
    assert mb.qsize() == maya_app._MAIL_CAP
    contents = _drain(mb)
    assert contents[-1][1] == "control"
    assert "[EMERGENCY]" in contents[-1][2], "emergency line was silenced"
    assert mb.drops > 0
    app = object.__new__(maya_app.MayaApp)
    app.q = maya_app.Mailbox(maya_app._MAIL_CAP)
    app._mail_drops = 0
    app._mail_overflow_at = 0.0
    for i in range(maya_app._MAIL_CAP):
        maya_app.MayaApp.mail(app, "log", "sink", "prefill-%d\n" % i,
                              maya_app.C["ink"])
    maya_app.MayaApp.mail(app, "log", "sink", "overflow-1\n",
                          maya_app.C["ink"])
    assert app._mail_drops >= 1, "overflow not counted"
    assert app._mail_overflow_at > 0.0, "banner gate never opened"
    banners = [item for item in _drain(app.q)
               if item[0] == "log" and len(item) > 2 and item[1] == "control"]
    assert banners and "[mailbox] UI behind" in banners[-1][2], \
        "truncation banner missing: %r" % [b[2] for b in banners]
    _ok("mailbox_log_never_silent_ok")


def test_mailbox_drain_empty_ok():
    mb = maya_app.Mailbox(maya_app._MAIL_CAP)
    for i in range(70):
        mb.put("set", "settings_service", str(i), maya_app.C["ok"])
    assert mb.qsize() == 70 and len(mb) == 70
    drained = _drain(mb)
    assert len(drained) == 70
    assert mb.qsize() == 0 and len(mb) == 0
    try:
        mb.get_nowait()
        raise AssertionError("drained box returned a message")
    except _queue.Empty:
        pass
    _ok("mailbox_drain_empty_ok")


def test_mailbox_generation_guard_intact_ok():
    mb = maya_app.Mailbox(maya_app._MAIL_CAP)
    for round_i in range(6):
        for gen in range(40):
            g = round_i * 40 + gen
            mb.put("tick_ready", ("parts-%d" % g), g)
            for junk in range(3):
                mb.put("activity", "processing")
        mb.put("log", "control", "flood round %d\n" % round_i, maya_app.C["ink"])
    gens = [item[2] for item in _drain(mb)
            if item[0] == "tick_ready" and len(item) > 2]
    assert gens, "tick_ready stream disappeared"
    assert all(a <= b for a, b in zip(gens, gens[1:])), \
        "generation stream reordered: %r" % gens[:20]
    names = maya_app.MayaApp.__init__.__code__.co_names
    assert "_stale_skips" in names, "tick generation guard slot removed"
    assert "_last_committed_gen" in names, "committed generation slot removed"
    assert callable(maya_app.MayaApp.poll), "poll continuation removed"
    _ok("mailbox_generation_guard_intact_ok")


def test_harness_complete_ok():
    _ok("harness_complete_ok")


if __name__ == "__main__":
    for _name in sorted(
            n for n in dir() if n.startswith("test_")
            and callable(globals().get(n))
            and getattr(globals().get(n), "__module__", "") == "__main__"):
        globals()[_name]()