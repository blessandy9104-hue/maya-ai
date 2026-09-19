"""Phase 3 cancellation & stale-result suite (``expected_ok=23``).

Contract (registered in ``verification/manifest.py``):

Arm Qt -- offscreen PySide6 harness (``qt_cancel_harness.py``), always run on
the project venv interpreter. Ten checks:
  - measurement guards: a clean projection trips no suppression/drop/cancel
    counter and the generation/commit bookkeeping stays consistent;
  - a queued projection cancelled before it starts is removed and never
    delivered (and is not counted as a late cancellation);
  - a running projection cancelled cooperatively suppresses its late value:
    nothing is delivered and nothing commits for it;
  - a stale result that would land after a newer frame committed is suppressed
    (``_proj_superseded``) and can never overwrite the committed view;
  - a stale failure is equally suppressed: no reset emission, no drop count,
    while the newer generation still delivers;
  - delivered ordering strictly follows commit order and the final view equals
    the last submission;
  - a concurrent submission burst keeps the committed generation monotonic and
    ends exactly where submissions ended;
  - a failure from the *current* generation fails closed (reset view, counted
    drop) and the pipeline recovers;
  - ``closeNow`` stops accepting projections, joins the worker pool and nothing
    is delivered afterwards;
  - a projection stuck in ``time.sleep(30)`` never hangs ``closeNow`` or the
    executor join: shutdown returns an explicit leftover-worker count and
    ``join_timeout`` outcome, submit-after-shutdown stays rejected, the
    pre/post thread audit shows no new threads, and the degraded-mode one-shot
    fallback is bounded (one daemon thread, gated per N drops) with
    ``degraded_path_used`` routed summary-only into the bounded aggregate.

Arm Tk -- serialized compute worker (every interpreter, tkinter):
  - a stale ``tick_ready`` (older than the committed frame) is dropped and
    counted (``_stale_skips``), never regressing the applied state;
  - a stale ``tick_failed`` is dropped too: no extra fail-closed reset, no
    regression, while the newer generation still applies;
  - applied ordering is monotonic in committed generation and the final applied
    generation equals the last submission;
  - a non-dict reset advances the committed generation so any in-flight older
    tick can no longer claim the presentation.

Arm chat -- ``ChatProcessManager`` over a deterministic fake child:
  - a queued turn cancelled before execution reports ``queued``, is terminal
    ``cancelled`` and never completes;
  - a running turn cancelled reports ``running``, is terminal ``cancelled`` and
    never completes;
  - result isolation: a rejected duplicate under a live request id and a
    cancelled turn never produce a competing completed reply under that id;
  - a child that exits without a reply yields a non-completion terminal outcome
    (``partial``), never ``completed``.

Arm executor -- ``BoundedExecutor`` directly:
  - cancelling a queued task removes it before run: state ``cancelled``,
    ``on_done`` never fires;
  - cancelling a running task suppresses the late value: ``on_cancelled``
    fires, ``on_done`` never fires, state ``cancelled``;
  - ``shutdown`` returns an explicit dict (``leftover_workers``/
    ``join_timeout``/``elapsed``): a worker blocked in an uninterruptible
    ``wait`` never hangs the join, reports ``join_timeout=True`` with a
    leftover worker, ``submit`` stays rejected after shutdown, and a clean
    drain reports ``leftover_workers=0``/``join_timeout=False`` on the
    idempotent second call.

Skills: prints only benign ``=OK`` labels; the venv child's stdout is captured
and relayed only as ``=OK`` labels; all Tk/chat arm output is captured and
never echoed. The single ``expected_ok`` contract (23) holds on every
interpreter: the Qt arm always runs on the venv interpreter via subprocess.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_QT_EXPECTED = (
    "measurement_guards",
    "queued_cancel_before_start",
    "running_cancel_suppressed",
    "after_compute_stale_suppressed",
    "stale_failure_no_reset",
    "ordering_final_equals_latest",
    "race_stability",
    "current_failure_fail_closed",
    "shutdown_cancels_inflight",
    "stuck_shutdown_bounded",
    "degraded_fallback_bounded",
)


def _ok(label):
    print("=" + label + "=OK")


def _venv_python():
    candidates = (
        _REPO / "venv" / "Scripts" / "python.exe",
        _REPO / "venv" / "bin" / "python",
        _REPO / ".venv" / "Scripts" / "python.exe",
        _REPO / ".venv" / "bin" / "python",
    )
    for path in candidates:
        if path.exists():
            return str(path)
    return sys.executable


# ---------------------------------------------------------------------------
# Qt arm -- offscreen harness under the PySide6 venv
# ---------------------------------------------------------------------------

_QT = {"done": False, "checks": {}, "error": ""}


def _run_qt_harness():
    if _QT["done"]:
        return _QT
    _QT["done"] = True
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    try:
        proc = subprocess.run(
            [_venv_python(), str(_REPO / "qt_cancel_harness.py")],
            capture_output=True, text=True, timeout=240, cwd=str(_REPO),
            env=env)
    except Exception as exc:  # noqa: BLE001
        _QT["error"] = "%s: %s" % (type(exc).__name__, exc)
        return _QT
    for line in proc.stdout.splitlines():
        if line.startswith("check:") and line.endswith(":pass"):
            name = line.split(":")[1]
            if name != "harness":
                _QT["checks"][name] = True
    if not _QT["checks"]:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        _QT["error"] = " | ".join(tail) or "no harness output"
    return _QT


def _qt_require(name, label):
    data = _run_qt_harness()
    assert name in data["checks"], data["error"] or ("missing check " + name)
    _ok(label)


def test_cancel_stale_qt_measurement_guards_ok():
    _qt_require("measurement_guards", "cancel_stale_qt_measurement_guards_ok")


def test_cancel_stale_qt_queued_cancel_ok():
    _qt_require("queued_cancel_before_start",
                "cancel_stale_qt_queued_cancel_ok")


def test_cancel_stale_qt_running_cancel_ok():
    _qt_require("running_cancel_suppressed",
                "cancel_stale_qt_running_cancel_ok")


def test_cancel_stale_qt_stale_delivery_ok():
    _qt_require("after_compute_stale_suppressed",
                "cancel_stale_qt_stale_delivery_ok")


def test_cancel_stale_qt_stale_failure_ok():
    _qt_require("stale_failure_no_reset", "cancel_stale_qt_stale_failure_ok")


def test_cancel_stale_qt_ordering_ok():
    _qt_require("ordering_final_equals_latest",
                "cancel_stale_qt_ordering_ok")


def test_cancel_stale_qt_race_stability_ok():
    _qt_require("race_stability", "cancel_stale_qt_race_stability_ok")


def test_cancel_stale_qt_fail_closed_ok():
    _qt_require("current_failure_fail_closed", "cancel_stale_qt_fail_closed_ok")


def test_cancel_stale_qt_shutdown_ok():
    _qt_require("shutdown_cancels_inflight", "cancel_stale_qt_shutdown_ok")


def test_cancel_stale_qt_stuck_shutdown_ok():
    _qt_require("stuck_shutdown_bounded",
                "cancel_stale_qt_stuck_shutdown_ok")


def test_cancel_stale_qt_degraded_bounded_ok():
    _qt_require("degraded_fallback_bounded",
                "cancel_stale_qt_degraded_bounded_ok")


def test_cancel_stale_qt_harness_complete_ok():
    data = _run_qt_harness()
    missing = [n for n in _QT_EXPECTED if n not in data["checks"]]
    assert not missing, data["error"] or ("missing " + ",".join(missing))
    _ok("cancel_stale_harness_complete_ok")


# ---------------------------------------------------------------------------
# Tk arm -- serialized compute worker (every interpreter)
# ---------------------------------------------------------------------------

_TKR = {"done": False, "checks": {}}


def _tk_pump_until(app, predicate, timeout=16.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.poll()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _tk_parts(service):
    return {
        "service": service, "svc_color": "#00aa00", "learning": "off",
        "learning_color": "#777777", "presence_mode": "off",
        "presence_color": "#777777", "visual": "idle", "commands": {},
        "vs": None, "fs": None, "visual_command": None, "reset": False,
        "meta": {}, "snapshot": {}, "resources": "safe",
    }


def _tk_run():
    if _TKR["done"]:
        return _TKR
    _TKR["done"] = True
    checks = _TKR["checks"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        import tkinter as tk
        from maya_app import MayaApp

        root = tk.Tk()
        root.withdraw()
        app = MayaApp(root)
        try:
            applied = []
            resets = {"n": 0}
            orig_parts = app._apply_tick_parts

            def parts_wrap(parts):
                if parts is not None and isinstance(parts, dict):
                    applied.append(parts.get("service"))
                return orig_parts(parts)

            app._apply_tick_parts = parts_wrap
            orig_apply = app._apply_tick

            def apply_wrap(snapshot):
                if snapshot is None:
                    resets["n"] += 1
                return orig_apply(snapshot)

            app._apply_tick = apply_wrap

            gates = {}

            def controlled_apply(snapshot, semantic=None, streaming_until=0.0,
                                 lab_speak_until=0.0, runtime_enabled=False):
                key = str(semantic or "")
                if key in gates:
                    entry = gates[key]
                    entry["enter"].set()
                    if entry["gate"].wait(10) is False:
                        return _tk_parts("svc-" + key + "-timeout")
                    if entry["raise"]:
                        raise RuntimeError("controlled tick failure probe")
                return _tk_parts("svc-" + key)

            app._project_apply_tick = controlled_apply

            def submit(service_marker):
                app._latest_semantic = service_marker
                app._submit_tick(payload={})

            def base_state():
                return {"gen": app._tick_gen, "stale": app._stale_skips}

            # -- Tk check 1: stale tick_ready is dropped, never applied.
            app.poll()
            before = base_state()
            gates["A-slow"] = {"enter": threading.Event(),
                               "gate": threading.Event(), "raise": False}
            submit("A-slow")
            assert gates["A-slow"]["enter"].wait(8.0), "slow tick never ran"
            submit("B-fast")
            _tk_pump_until(app, lambda: app._tick_gen >= before["gen"] + 2,
                           timeout=8.0)
            # reset while A-slow is still in flight -> its ready becomes stale
            app.mail("tick", None)
            app.poll()
            assert resets["n"] >= 1, "manual reset never applied"
            assert app._last_committed_gen == app._tick_gen
            gates["A-slow"]["gate"].set()
            assert _tk_pump_until(
                app, lambda: app._stale_skips >= before["stale"] + 1, timeout=8.0), \
                "stale tick_ready never dropped"
            _tk_pump_until(app, lambda: "svc-B-fast" in applied, timeout=8.0)
            assert "svc-A-slow" not in applied, "stale tick_ready was applied"
            checks["tk_stale_ready_suppressed"] = True

            # -- Tk check 2: stale tick_failed is dropped (no extra reset, no
            #    regression) while the newer generation still applies.
            before = base_state()
            before_resets = resets["n"]
            gates["B-raise"] = {"enter": threading.Event(),
                                "gate": threading.Event(), "raise": True}
            submit("B-raise")
            assert gates["B-raise"]["enter"].wait(8.0), "raising tick never ran"
            submit("C-fast")
            _tk_pump_until(app, lambda: app._tick_gen >= before["gen"] + 2,
                           timeout=8.0)
            app.mail("tick", None)
            app.poll()
            assert resets["n"] == before_resets + 1, "manual reset missing"
            baseline_committed = app._last_committed_gen
            gates["B-raise"]["gate"].set()
            assert _tk_pump_until(
                app, lambda: app._stale_skips >= before["stale"] + 1, timeout=8.0), \
                "stale tick_failed never dropped"
            _tk_pump_until(app, lambda: "svc-C-fast" in applied, timeout=8.0)
            assert resets["n"] == before_resets + 1, \
                "stale failure triggered an extra fail-closed reset"
            assert app._last_committed_gen >= baseline_committed, \
                "committed generation regressed after stale failure"
            checks["tk_stale_failure_suppressed"] = True

            # -- Tk check 3: ordering is monotonic and final == latest.
            app.poll()
            base_committed = app._last_committed_gen
            submit("ord-1")
            assert _tk_pump_until(
                app, lambda: app._last_committed_gen == base_committed + 1), \
                "ord-1 never committed"
            submit("ord-2")
            assert _tk_pump_until(
                app, lambda: app._last_committed_gen == base_committed + 2), \
                "ord-2 never committed"
            submit("ord-3")
            assert _tk_pump_until(
                app, lambda: app._last_committed_gen == base_committed + 3), \
                "ord-3 never committed"
            assert applied[-3:] == ["svc-ord-1", "svc-ord-2", "svc-ord-3"], \
                applied[-4:]
            assert app._last_committed_gen == app._tick_gen, \
                "committed generation lags submissions"
            checks["tk_ordering_committed_monotonic"] = True

            # -- Tk check 4: a non-dict reset advances the committed generation
            #    so no in-flight older tick can ever claim the presentation.
            app.poll()
            submit("rc-1")
            assert _tk_pump_until(
                app, lambda: app._tick_gen >= app._last_committed_gen), \
                "steady-state generation never committed"
            gen_before = app._tick_gen
            app.mail("tick", None)
            app.poll()
            assert resets["n"] >= 1
            assert app._last_committed_gen >= gen_before, \
                "reset did not advance the committed generation"
            assert app._last_committed_gen == app._tick_gen, \
                "reset left the committed generation lagging submissions"
            checks["tk_reset_commits_gen"] = True
        finally:
            try:
                app.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass
    return _TKR


def _tk_require(name, label):
    data = _tk_run()
    assert data["checks"].get(name), "tk check missing: " + name
    _ok(label)


def test_cancel_stale_tk_stale_ready_ok():
    _tk_require("tk_stale_ready_suppressed",
                "cancel_stale_tk_stale_ready_ok")


def test_cancel_stale_tk_stale_failure_ok():
    _tk_require("tk_stale_failure_suppressed",
                "cancel_stale_tk_stale_failure_ok")


def test_cancel_stale_tk_ordering_ok():
    _tk_require("tk_ordering_committed_monotonic",
                "cancel_stale_tk_ordering_ok")


def test_cancel_stale_tk_reset_commit_ok():
    _tk_require("tk_reset_commits_gen", "cancel_stale_tk_reset_commit_ok")


# ---------------------------------------------------------------------------
# Chat arm -- ChatProcessManager over a deterministic fake child
# ---------------------------------------------------------------------------

_CHAT_FAKE_SOURCE = '''\
import sys


def emit(x):
    sys.stdout.write(x + "\\n")
    sys.stdout.flush()


emit("Maya chat fake ready.")
emit("Face protocol on.")

for raw in sys.stdin:
    text = raw.rstrip("\\n")
    if text == "":
        continue
    sys.stderr.write("[Intent JSON: {\\"text\\": \\"x\\"}]\\n")
    sys.stderr.flush()
    if text == "quit":
        break
    if text.startswith("slow:"):
        import time
        time.sleep(float(text.split(":", 1)[1]))
        emit("[semantic] theme slow")
        emit("Maya: slow reply")
        emit("[face] idle")
        continue
    if text == "noreply":
        emit("[face] processing")
        sys.exit(0)
    emit("[face] processing")
    emit("Maya: echo " + text)
    emit("[face] idle")
'''

_CHAT_TMP = Path(tempfile.mkdtemp(prefix="maya_cancel_stale_"))
_CHAT_FAKE = _CHAT_TMP / "fake_chat.py"
_CHAT_FAKE.write_text(_CHAT_FAKE_SOURCE, encoding="utf-8", newline="\n")

_CHAT = {"manager": None, "done_arm": False, "checks": {}}


def _chat_manager():
    if _CHAT["manager"] is None:
        import maya_chat_process as proc
        os.environ["MAYA_CHAT_SCRIPT"] = str(_CHAT_FAKE)
        manager = proc.ChatProcessManager(turn_timeout=180.0, grace=2.0,
                                          max_queue=32)
        manager.start()
        _CHAT["manager"] = manager
    return _CHAT["manager"]


def _chat_submit(manager, text, request_id, generation):
    done = []
    ack = manager.submit(
        text, request_id=request_id, generation=generation,
        on_done=lambda payload: done.append(payload))
    return ack, done


def _chat_wait_done(done, timeout=20.0):
    deadline = time.monotonic() + timeout
    while not done and time.monotonic() < deadline:
        time.sleep(0.01)
    assert done, "on_done never fired"
    return done[0]


def _chat_active(manager, request_id):
    return manager.stats().get("active") == request_id


def _chat_arm():
    if _CHAT["done_arm"]:
        return _CHAT
    _CHAT["done_arm"] = True
    checks = _CHAT["checks"]
    manager = _chat_manager()
    try:
        # -- chat check 1: queued cancellation.
        ack, done1 = _chat_submit(manager, "slow:1", "cs-1", 1)
        assert ack["accepted"] is True, ack
        deadline = time.monotonic() + 15
        while not _chat_active(manager, "cs-1") and time.monotonic() < deadline:
            time.sleep(0.01)
        assert _chat_active(manager, "cs-1"), "turn cs-1 never started"
        ack2, done2 = _chat_submit(manager, "echo second", "cs-2", 2)
        assert ack2["accepted"] is True, ack2
        assert manager.cancel("cs-2") == "queued"
        payload = _chat_wait_done(done2)
        assert payload["outcome"] == "cancelled", payload
        assert payload["terminal"] is True, payload
        assert payload["reason"] == "cancelled_before_execution", payload
        assert payload["reply"] is None, payload
        assert manager.turn("cs-2").state == "cancelled"
        payload1 = _chat_wait_done(done1)
        assert payload1["outcome"] == "completed", payload1
        assert "slow reply" in (payload1.get("reply") or ""), payload1
        checks["chat_queued_cancel"] = True

        # -- chat check 2: running cancellation.
        ack3, done3 = _chat_submit(manager, "slow:60", "cs-3", 3)
        assert ack3["accepted"] is True, ack3
        deadline = time.monotonic() + 15
        while not _chat_active(manager, "cs-3") and time.monotonic() < deadline:
            time.sleep(0.01)
        assert _chat_active(manager, "cs-3"), "turn cs-3 never started"
        assert manager.cancel("cs-3") == "running"
        payload = _chat_wait_done(done3)
        assert payload["outcome"] == "cancelled", payload
        assert payload["terminal"] is True, payload
        assert payload["reply"] is None, payload
        assert manager.stats()["cancelled"] >= 2, manager.stats()
        checks["chat_running_cancel"] = True

        # -- chat check 3: result isolation.
        ack4, done4 = _chat_submit(manager, "echo alpha", "cs-4", 4)
        assert ack4["accepted"] is True, ack4
        payload = _chat_wait_done(done4)
        assert payload["outcome"] == "completed", payload
        assert "echo alpha" in (payload.get("reply") or ""), payload
        ack5, done5 = _chat_submit(manager, "slow:60", "cs-5", 5)
        assert ack5["accepted"] is True, ack5
        deadline = time.monotonic() + 15
        while not _chat_active(manager, "cs-5") and time.monotonic() < deadline:
            time.sleep(0.01)
        dup, dupe_done = _chat_submit(manager, "echo beta", "cs-5", 6)
        assert dup["accepted"] is False and dup["error"] == "duplicate", dup
        assert dupe_done == [], "duplicate submission fired on_done"
        assert manager.stats()["duplicate"] >= 1
        assert manager.cancel("cs-5") == "running"
        payload = _chat_wait_done(done5)
        assert payload["outcome"] == "cancelled", payload
        assert payload["reply"] is None, payload
        terminal = manager.turn("cs-5")
        assert terminal.state == "cancelled" and terminal.reply is None, \
            terminal.reply
        checks["chat_result_isolation"] = True

        # -- chat check 4: a child that exits without a reply never completes.
        ack6, done6 = _chat_submit(manager, "noreply", "cs-6", 7)
        assert ack6["accepted"] is True, ack6
        payload = _chat_wait_done(done6)
        assert payload["outcome"] != "completed", payload
        assert payload["terminal"] is True, payload
        assert payload["reply"] is None, payload
        assert payload["outcome"] == "partial", payload
        assert manager.turn("cs-6").state == "partial"
        checks["chat_no_completion"] = True
    finally:
        try:
            manager.close()
        except Exception:  # noqa: BLE001
            pass
    return _CHAT


def _chat_require(name, label):
    data = _chat_arm()
    assert data["checks"].get(name), "chat check missing: " + name
    _ok(label)


def test_cancel_stale_chat_queued_ok():
    _chat_require("chat_queued_cancel", "cancel_stale_chat_queued_cancel_ok")


def test_cancel_stale_chat_running_ok():
    _chat_require("chat_running_cancel", "cancel_stale_chat_running_cancel_ok")


def test_cancel_stale_chat_isolation_ok():
    _chat_require("chat_result_isolation",
                  "cancel_stale_chat_result_isolation_ok")


def test_cancel_stale_chat_no_completion_ok():
    _chat_require("chat_no_completion",
                  "cancel_stale_chat_no_completion_ok")


# ---------------------------------------------------------------------------
# Pure executor arm -- BoundedExecutor cancellation semantics
# ---------------------------------------------------------------------------

def _exec_wait(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.005)
    return predicate()


def test_cancel_stale_exec_queued_ok():
    from maya_async import BoundedExecutor
    ex = BoundedExecutor(max_workers=1, max_queue=16, name="cs-exec")
    ran = []
    gate = threading.Event()
    hold = ex.submit(gate.wait, 5.0, request_id="cs-hold", generation=0)
    assert _exec_wait(
        lambda: ex.handle("cs-hold").state == "running"), "hold never ran"
    target = ex.submit(lambda: ran.append("ran"),
                       request_id="cs-t1", generation=1)
    assert _exec_wait(
        lambda: ex.handle("cs-t1").state == "queued"), "target never queued"
    assert ex.cancel("cs-t1") == "queued"
    gate.set()
    assert _exec_wait(
        lambda: ex.handle("cs-hold").state == "done"), "hold never done"
    _exec_wait(lambda: ex.handle("cs-t1").state == "cancelled")
    assert ran == [], "cancelled queued task ran"
    assert ex.handle("cs-t1").state == "cancelled"
    ex.shutdown()
    _ok("cancel_stale_exec_queued_ok")


def test_cancel_stale_exec_running_late_ok():
    from maya_async import BoundedExecutor
    ex = BoundedExecutor(max_workers=1, max_queue=8, name="cs-exec2")
    gate = threading.Event()
    done = []
    cancelled = []

    def blocking():
        gate.wait(10.0)
        return "late-value"

    ex.submit(blocking, request_id="cs-t2", generation=2,
              on_done=lambda value, handle: done.append(value),
              on_cancelled=lambda value, handle: cancelled.append(value))
    assert _exec_wait(
        lambda: ex.handle("cs-t2").state == "running"), "target never ran"
    assert ex.cancel("cs-t2") == "running"
    gate.set()
    assert _exec_wait(lambda: len(cancelled) > 0, timeout=8.0), \
        "on_cancelled never fired"
    time.sleep(0.05)
    assert done == [], "late value delivered after cancellation"
    assert ex.handle("cs-t2").state == "cancelled"
    ex.shutdown()
    _ok("cancel_stale_exec_running_late_ok")


def test_cancel_stale_exec_shutdown_result_ok():
    from maya_async import BoundedExecutor
    ex = BoundedExecutor(max_workers=1, max_queue=8, name="cs-exec-f1")
    gate = threading.Event()

    def uninterruptible():
        gate.wait(30.0)  # cooperatively uninterruptible block
        return "late"

    ex.submit(uninterruptible, request_id="cs-f1-hold", generation=10)
    assert _exec_wait(
        lambda: ex.handle("cs-f1-hold").state == "running"), "hold never ran"
    started = time.monotonic()
    result = ex.shutdown(wait=True, timeout=0.05)
    elapsed = time.monotonic() - started
    assert isinstance(result, dict), result
    assert result["leftover_workers"] == 1, result
    assert result["join_timeout"] is True, result
    assert result["elapsed"] < 10.0 and elapsed < 10.0, (elapsed, result)
    try:
        ex.submit(lambda: None, request_id="cs-f1-late", generation=11)
        raise AssertionError("submit-after-shutdown was accepted")
    except AssertionError:
        raise
    except RuntimeError:
        pass
    gate.set()
    assert _exec_wait(lambda: ex.alive_workers() == 0, timeout=5.0), \
        "worker never drained after release"
    after = ex.shutdown()
    assert after["leftover_workers"] == 0, after
    assert after["join_timeout"] is False, after
    _ok("cancel_stale_exec_shutdown_result_ok")


if __name__ == "__main__":
    for _name in sorted(
            n for n in dir() if n.startswith("test_")
            and callable(globals().get(n))
            and getattr(globals().get(n), "__module__", "") == "__main__"):
        globals()[_name]()
