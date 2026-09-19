"""Phase 2 UI-thread-protection suite: async projection / serialized compute.

Contract (registered in ``verification/manifest.py``, ``expected_ok=20``):

Arm A -- pure bridge pulled projection (every interpreter):
  - ``project()`` reproduces ``apply_tick_snapshot()`` byte-for-byte on every
    activity with a live, digest-verified semantic cue and a pending set;
  - ``snapshot_input()`` detaches the UI-held inputs: mutating the live ticker
    after the snapshot never changes the projected view and a fresh identical
    ticker fed the same snapshot emits the identical view (isolation);
  - ``None`` / non-dict payloads resolve to the neutral reset (``None``)
    exactly like ``apply_tick_snapshot``;
  - ``advance_frame()`` on the UI thread leaves exactly the frame the
    projection reads (``frame = snap["shape_frame"] + 1``) and ``project()``
    never advances the counter again;
  - ``project()`` never mutates ticker-held state (``state_signature`` and the
    frame are unchanged afterwards).

Arm B -- ordered projection worker (every interpreter, pure bridge class):
  - a single worker thread executes projections strictly in FIFO order and
    never on the submitting thread;
  - the queue is bounded (``max_queue``) and overflow is a counted drop that
    never blocks the submitter;
  - a raising projection never kills the worker (later work still runs);
  - ``shutdown()`` joins the thread and rejects further submissions.

Arm C -- Tk serialized compute worker (every interpreter, tkinter):
  - payload building and projection run on the compute worker, never on the
    Tk UI thread;
  - widget application (``_apply_tick_parts``) runs on the Tk UI thread;
  - a raising projection fails closed to the reset view and recovers;
  - the single-slot queue is bounded: overflow is a counted, non-blocking
    skip and the worker recovers afterwards;
  - ``close()`` drains, joins the compute thread and makes later submits
    inert.

Arm D -- Qt controller projection pipeline (offscreen, PySide6):
  - the controller owns the ordered projection executor (one worker, bounded
    queue);
  - snapshot/advance/application run on the Qt UI thread while the pull itself
    runs on the projection worker;
  - the delivered view equals the direct projection of the same inputs;
  - a raising projection fails closed to the neutral reset and recovers;
  - a slow projection never blocks the UI event loop and overflow is a bounded
    counted drop, never a UI stall;
  - ``closeNow()`` joins the projection and worker pools and rejects further
    work.

The Qt arm runs in-process when PySide6 is importable (the venv interpreter)
and otherwise re-executes itself under the project venv with
``MAYA_UTP_QT_ARM=1`` -- either route emits the identical ``=OK`` labels, so
the single ``expected_ok`` contract holds on every interpreter.

Skills: this module may print only benign lines (``=OK`` labels, ``key=value``
summaries); the venv child's stdout is relayed only as ``=OK`` labels and
``key=value`` lines, and any Qt chatter is captured, never echoed.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from maya_runtime.ui.qt.bridge import (  # noqa: E402
    ACTIVITY_KEYS,
    OrderedProjectionWorker,
    UiTicker,
)

_LABELS = []


def _ok(name):
    _LABELS.append("=" + name + "=OK")


def _flush():
    for _line in _LABELS:
        print(_line)


def _try_pyside():
    try:
        import PySide6  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


_HAS_PYSIDE = _try_pyside()


# ---------------------------------------------------------------------------
# Arm A -- pure bridge pulled projection
# ---------------------------------------------------------------------------

def _cue_line():
    from maya_identity.embodiment.semantic_interpretation import (
        adapt_semantic, to_line,
    )
    return to_line(adapt_semantic({
        "confidence": 0.8,
        "stability": 0.7,
        "meaning_scalar": 0.66,
        "restricted": False,
        "meaning_ok": True,
        "stability_ok": True,
        "register": "measured",
    }))


def _variants(base):
    variants = {}
    for act in ACTIVITY_KEYS:
        variants[act] = base.make_tick_payload(act)
    awake = dict(variants["idle"])
    awake["raw"] = dict(awake.get("raw") or {})
    awake["raw"]["presence_mode"] = "awake"
    awake["raw"]["service"] = "awake"
    awake["visual_state"] = "awake"
    variants["awake"] = awake
    return variants


def arm_a():
    cue_line = _cue_line()
    base = UiTicker()
    variants = _variants(base)
    p_idle = variants["idle"]

    # 1. parity: project() == apply_tick_snapshot() on every activity, with a
    #    valid semantic cue and a pending set live on both tickers.
    for name, payload in variants.items():
        a = UiTicker()
        b = UiTicker()
        assert a.read_semantic_line(cue_line) is not None, name
        assert b.read_semantic_line(cue_line) is not None, name
        a.set_pending([{"id": "p1", "status": "pending"}])
        b.set_pending([{"id": "p1", "status": "pending"}])
        expected = a.apply_tick_snapshot(payload)
        snap = b.snapshot_input()
        seen = b.project(payload, snap)
        assert seen == expected, name
        assert b.project(payload, snap) == seen, name
    _ok("utp_bridge_projection_parity_ok")

    # 2. snapshot isolation: mutations after the snapshot never reach the
    #    projection, and the same snapshot yields the same view elsewhere.
    t = UiTicker()
    assert t.read_semantic_line(cue_line) is not None
    t.set_pending([{"id": "p1", "status": "pending"}])
    snap = t.snapshot_input()
    assert snap["semantic"] is not None
    t.advance_frame()
    t.set_semantic(None)
    t.set_pending([])
    v = t.project(variants["processing"], snap)
    assert v["semantic"] == snap["semantic"], "snapshot cue lost"
    assert v["semantic"] is not None, "live mutation leaked into snapshot"
    assert v["pending"] == [{"id": "p1", "status": "pending"}], v["pending"]
    assert v["frame"] == snap["shape_frame"] + 1, v["frame"]
    assert UiTicker().project(variants["processing"], snap) == v, "live-state leak"
    _ok("utp_bridge_snapshot_isolation_ok")

    # 3. neutral reset: non-dict payloads resolve to None like apply_tick_snapshot.
    fresh = UiTicker()
    snap = t.snapshot_input()
    assert fresh.project(None, snap) is None
    assert fresh.project("idle", snap) is None
    assert fresh.project([], snap) is None
    assert fresh.apply_tick_snapshot(None) is None
    assert fresh.apply_tick_snapshot("x") is None
    _ok("utp_bridge_projection_reset_ok")

    # 4. frame contract: advance_frame() leaves exactly the frame the
    #    projection reads, and project() never advances it again.
    c = UiTicker()
    snap = c.snapshot_input()
    base_frame = snap["shape_frame"]
    n = c.advance_frame()
    assert n == base_frame + 1, n
    v = c.project(p_idle, snap)
    assert v["frame"] == base_frame + 1, v["frame"]
    assert c.snapshot_input()["shape_frame"] == n, "project advanced the frame"
    _ok("utp_bridge_projection_frame_contract_ok")

    # 5. no UI mutation: state_signature and the animation frame are unchanged.
    d = UiTicker()
    assert d.read_semantic_line(cue_line) is not None
    d.set_pending([{"id": "p1", "status": "pending"}])
    sig0 = d.state_signature()
    snap = d.snapshot_input()
    d.project(p_idle, snap)
    sig1 = d.state_signature()
    assert sig0 == sig1, "project() mutated ticker-held state"
    assert d.snapshot_input()["shape_frame"] == snap["shape_frame"]
    _ok("utp_bridge_projection_no_ui_mutation_ok")


# ---------------------------------------------------------------------------
# Arm B -- ordered projection worker (pure, every interpreter)
# ---------------------------------------------------------------------------

def _wait_until(predicate, timeout=6.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    return predicate()


def arm_b():
    main_tid = threading.get_ident()

    # 1. one worker thread, strict FIFO, never on the submitting thread.
    w = OrderedProjectionWorker(max_queue=8)
    assert w.max_queue == 8
    assert w.alive_workers() == 1
    order = []
    workers = set()
    hold = threading.Event()
    lock = threading.Lock()

    def job(i):
        def run():
            tid = threading.get_ident()
            with lock:
                workers.add(tid)
                order.append(i)
            if i == 0:
                hold.wait(3.0)
        return run

    assert w.submit(job(0)) is True
    # Park the single worker on job 0, then prove the queue absorbs 1..8.
    assert _wait_until(lambda: order == [0], timeout=5.0), order
    for i in range(1, 9):
        assert w.submit(job(i)) is True, i
    assert len(w._queue) == w.max_queue, len(w._queue)
    hold.set()
    assert _wait_until(lambda: len(order) == 9), len(order)
    assert order == list(range(9)), order
    assert len(workers) == 1, workers
    assert main_tid not in workers, "projection ran on the submitting thread"
    w.shutdown(wait=True, timeout=3.0)
    assert not w.alive_workers()
    _ok("utp_worker_ordered_single_thread_ok")

    # 2. overflow is a counted, non-blocking drop -- never a block.
    w2 = OrderedProjectionWorker(max_queue=4)
    hold2 = threading.Event()
    order2 = []

    def pad(i):
        def run():
            with lock:
                order2.append(i)
            hold2.wait(3.0)
        return run

    assert w2.submit(pad(0)) is True
    assert _wait_until(lambda: order2 == [0], timeout=5.0), order2
    for i in range(1, 5):
        assert w2.submit(pad(i)) is True, i
    assert len(w2._queue) == w2.max_queue, len(w2._queue)
    drops_before = w2._drops
    t0 = time.perf_counter()
    for _ in range(10):
        assert w2.submit(pad(9)) is False
    assert time.perf_counter() - t0 < 1.0, "overflow blocked the submitter"
    assert w2._drops - drops_before == 10, w2._drops - drops_before
    assert len(w2._queue) == w2.max_queue
    hold2.set()
    w2.shutdown(wait=True, timeout=3.0)
    assert not w2.alive_workers()
    _ok("utp_worker_bounded_drop_ok")

    # 3. a raising projection never kills the worker.
    w3 = OrderedProjectionWorker(max_queue=4)
    ran = {"n": 0}

    def bad():
        raise ValueError("projection probe failure")

    def good():
        ran["n"] += 1

    assert w3.submit(bad) is True
    assert w3.submit(good) is True
    assert _wait_until(lambda: ran["n"] == 1), ran["n"]
    assert w3.alive_workers() == 1
    w3.shutdown(wait=True, timeout=3.0)
    assert not w3.alive_workers()
    _ok("utp_worker_fail_closed_ok")

    # 4. shutdown joins the thread; the worker rejects further work.
    w4 = OrderedProjectionWorker(max_queue=4)
    for _ in range(3):
        assert w4.submit(good) is True
    w4.shutdown(wait=True, timeout=3.0)
    assert not w4.alive_workers()
    assert w4.submit(good) is False
    _ok("utp_worker_shutdown_ok")


# ---------------------------------------------------------------------------
# Arm C -- Tk serialized compute worker (every interpreter, tkinter)
# ---------------------------------------------------------------------------

def _tk_pump_until(app, predicate, timeout=16.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.poll()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _tk_arm_labels():
    labels = []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        import tkinter as tk
        from maya_app import MayaApp

        root = tk.Tk()
        root.withdraw()
        app = MayaApp(root)
        ui_tid = threading.get_ident()
        try:
            # 1. payload building + projection run on the compute worker.
            state = {}
            orig_proj = app._project_apply_tick

            def proj_wrap(snapshot, semantic=None, streaming_until=0.0,
                          lab_speak_until=0.0, runtime_enabled=False):
                state["proj_tid"] = threading.get_ident()
                return orig_proj(snapshot, semantic, streaming_until,
                                 lab_speak_until, runtime_enabled)

            app._project_apply_tick = proj_wrap
            baseline = app._tick_ready_count
            app._submit_tick()
            assert _tk_pump_until(
                app, lambda: app._tick_ready_count > baseline), \
                "tick_ready never arrived"
            assert state["proj_tid"] is not None
            assert state["proj_tid"] != ui_tid, "projection ran on the UI thread"
            app._project_apply_tick = orig_proj
            labels.append("=utp_tk_projection_compute_off_ui_thread_ok=OK")

            # 2. widget application runs on the Tk UI thread.
            state.clear()
            orig_parts = app._apply_tick_parts

            def parts_wrap(parts):
                state["apply_tid"] = threading.get_ident()
                return orig_parts(parts)

            app._apply_tick_parts = parts_wrap
            baseline = app._tick_ready_count
            app._submit_tick()
            assert _tk_pump_until(
                app,
                lambda: (app._tick_ready_count > baseline
                         and state.get("apply_tid") is not None),
                timeout=16.0), \
                "second tick_ready never applied"
            assert state.get("apply_tid") == ui_tid, \
                "widget application ran off the UI thread"
            app._apply_tick_parts = orig_parts
            labels.append("=utp_tk_widget_apply_on_ui_thread_ok=OK")

            # 3. fail closed: a raising projection resets the presentation and
            #    recovers on the next submission.
            baseline = app._tick_ready_count
            reset_seen = {"n": 0}
            orig_reset = app._apply_tick

            def reset_wrap(snapshot):
                if snapshot is None:
                    reset_seen["n"] += 1
                return orig_reset(snapshot)

            app._apply_tick = reset_wrap

            def bad_proj(snapshot, semantic=None, streaming_until=0.0,
                         lab_speak_until=0.0, runtime_enabled=False):
                raise RuntimeError("tk projection probe failure")

            app._project_apply_tick = bad_proj
            app._submit_tick()
            assert _tk_pump_until(
                app, lambda: reset_seen["n"] >= 1, timeout=16.0), \
                "fail-closed reset never applied"
            assert app._tick_ready_count == baseline, \
                "a failed projection must not reach the widgets"
            app._project_apply_tick = orig_proj
            app._apply_tick = orig_reset
            app._submit_tick()
            assert _tk_pump_until(
                app, lambda: app._tick_ready_count > baseline), \
                "projection did not recover after failure"
            labels.append("=utp_tk_projection_fail_closed_ok=OK")

            # 4. backpressure: the single-slot bounded queue skips, never
            #    blocks, and the worker recovers afterwards.
            baseline = app._tick_ready_count
            baseline_skips = app._tick_skips
            entered = threading.Event()
            release = threading.Event()

            def slow_proj(snapshot, semantic=None, streaming_until=0.0,
                          lab_speak_until=0.0, runtime_enabled=False):
                entered.set()
                release.wait(6.0)
                return orig_proj(snapshot, semantic, streaming_until,
                                 lab_speak_until, runtime_enabled)

            app._project_apply_tick = slow_proj
            app._submit_tick()
            assert entered.wait(10.0), "slow projection never started"
            app._submit_tick()  # queued while the worker is busy
            t0 = time.perf_counter()
            for _ in range(3):
                app._submit_tick()  # skipped: bounded slot is occupied
            assert time.perf_counter() - t0 < 1.0, \
                "bounded slot blocked the UI thread"
            assert app._tick_skips > baseline_skips, app._tick_skips
            app._project_apply_tick = orig_proj
            release.set()
            deadline = time.monotonic() + 14.0
            while app._tick_ready_count < baseline + 2 \
                    and time.monotonic() < deadline:
                app.poll()
                time.sleep(0.005)
            assert app._tick_ready_count >= baseline + 2, \
                app._tick_ready_count
            labels.append("=utp_tk_projection_backpressure_slot_ok=OK")

            # 5. close drains, joins the compute thread, makes submits inert.
            assert app._compute_thread.is_alive()
            app.close()
            assert not app._compute_thread.is_alive(), \
                "compute thread survived close"
            assert app.stop
            app._submit_tick()  # post-stop no-op
            app.close()  # idempotent
            labels.append("=utp_tk_close_drain_ok=OK")
        finally:
            try:
                app.close()
            except Exception:  # noqa: BLE001
                pass
    return labels


# ---------------------------------------------------------------------------
# Arm D -- Qt controller projection pipeline (offscreen, PySide6)
# ---------------------------------------------------------------------------

def _qt_arm_labels():
    labels = []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QGuiApplication
        from maya_runtime.ui.qt import app as qapp

        app = QGuiApplication.instance() or QGuiApplication([])
        controller = qapp.Controller()
        ui_tid = threading.get_ident()
        state = {}

        def process_until(pred, timeout=8.0):
            deadline = time.monotonic() + timeout
            while not pred() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.004)
            return pred()

        def drain(seconds=0.3):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.004)

        # Warm lazily imported state modules so assertions measure the
        # scheduling contract, not first-call import cost.
        controller._emit_view({"probe": 1})
        drain(0.5)

        orig_snap = controller.ticker.snapshot_input
        orig_adv = controller.ticker.advance_frame
        orig_proj = controller.ticker.project
        orig_apply = controller._on_projected_view

        # 1. the ordered projection executor exists and is bounded.
        proj = controller._project
        assert proj is not None, "ordered projection executor missing"
        assert proj.max_workers == 1, proj.max_workers
        assert 1 <= proj.max_queue <= 64, proj.max_queue
        labels.append("=utp_qt_projection_ordered_executor_ok=OK")

        # 2. thread ownership: snapshot/advance/application on the UI thread,
        #    the pull on the projection worker.
        def snap_wrap():
            state["snap_tid"] = threading.get_ident()
            return orig_snap()

        def adv_wrap():
            state["adv_tid"] = threading.get_ident()
            return orig_adv()

        def proj_wrap(payload, snap):
            state["proj_tid"] = threading.get_ident()
            return orig_proj(payload, snap)

        def apply_wrap(view, reason=None, started=None):
            state["app_tid"] = threading.get_ident()
            return orig_apply(view, reason=reason, started=started)

        controller.ticker.snapshot_input = snap_wrap
        controller.ticker.advance_frame = adv_wrap
        controller.ticker.project = proj_wrap
        controller._on_projected_view = apply_wrap
        controller._emit_view({"probe": 1}, reason="conversation")
        assert process_until(lambda: state.get("app_tid") is not None), \
            "projected view never applied"
        assert state["app_tid"] == ui_tid
        assert state["snap_tid"] == ui_tid
        assert state["adv_tid"] == ui_tid
        assert state["proj_tid"] is not None
        assert state["proj_tid"] != ui_tid
        controller.ticker.snapshot_input = orig_snap
        controller.ticker.advance_frame = orig_adv
        controller.ticker.project = orig_proj
        controller._on_projected_view = orig_apply
        drain(0.3)
        labels.append("=utp_qt_projection_thread_ownership_ok=OK")

        # 3. content parity: the delivered view equals the projection of the
        #    exact detached snapshot the controller captured for that emit
        #    (deterministic regardless of the animation-frame counter).
        payload = controller.ticker.make_tick_payload("idle")
        snap_used = {}
        captured = {}

        def snap_wrap_parity():
            snap_used["s"] = orig_snap()
            return snap_used["s"]

        def capture_view(view, reason=None, started=None):
            captured["view"] = view

        controller.ticker.snapshot_input = snap_wrap_parity
        controller._on_projected_view = capture_view
        controller._emit_view(payload, reason="conversation")
        # A stale warmup projection may still be in flight; select the view
        # whose frame matches the snapshot *this* emit captured.
        assert process_until(lambda: (
            "s" in snap_used
            and captured.get("view") is not None
            and captured["view"].get("frame")
            == snap_used["s"]["shape_frame"] + 1)), "parity view missing"
        expected = orig_proj(payload, snap_used["s"])
        assert captured["view"] == expected, \
            "delivered view drifted from its projection snapshot"
        controller.ticker.snapshot_input = orig_snap
        controller._on_projected_view = orig_apply
        drain(0.3)
        labels.append("=utp_qt_projection_view_parity_ok=OK")

        # 4. fail closed: a raising projection resets to the neutral view and
        #    recovers on the next submission.
        base_drops = controller._proj_drops

        def bad_proj(payload, snap):
            raise RuntimeError("projection probe failure")

        controller.ticker.project = bad_proj
        controller._emit_view({"probe": 1}, reason="conversation")
        assert process_until(
            lambda: controller._proj_drops > base_drops), "error path unseen"
        assert controller._last_view_text == "null", \
            "projection failure did not fail closed to the reset view"
        controller.ticker.project = orig_proj
        captured.clear()
        controller._on_projected_view = capture_view
        controller._emit_view({"probe": 1}, reason="conversation")
        assert process_until(lambda: "view" in captured), "no recovery view"
        assert isinstance(captured["view"], dict)
        controller._on_projected_view = orig_apply
        drain(0.3)
        labels.append("=utp_qt_projection_fail_closed_ok=OK")

        # 5. backpressure: a slow projection never blocks the UI loop and
        #    overflow is a bounded counted drop.
        release = threading.Event()
        drops0 = controller._proj_drops

        def slow_proj(payload, snap):
            release.wait(4.0)
            return orig_proj(payload, snap)

        controller.ticker.project = slow_proj
        controller._emit_view({"probe": 1}, reason="conversation")
        deadline = time.monotonic() + 8.0
        while (controller._proj_drops <= drops0
               and time.monotonic() < deadline):
            controller._emit_view({"probe": 1}, reason="conversation")
            drain(0.02)
        assert controller._proj_drops > drops0, "no bounded drop observed"
        stats = proj.stats()
        assert stats["running"] <= proj.max_workers, stats
        assert stats["queued"] <= proj.max_queue, stats

        ticks = {"n": 0}
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: ticks.__setitem__("n", ticks["n"] + 1))
        timer.start()
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 0.3:
            app.processEvents()
            time.sleep(0.004)
        timer.stop()
        assert ticks["n"] >= 5, ticks

        controller.ticker.project = orig_proj
        release.set()
        assert process_until(
            lambda: controller._last_view_text not in (None, "null"),
            timeout=10.0), "projection did not recover after backpressure"
        drain(0.3)
        labels.append("=utp_qt_projection_backpressure_ok=OK")

        # 6. closeNow joins the projection and worker pools and rejects work.
        controller.closeNow()
        deadline = time.monotonic() + 4.0
        while proj.alive_workers() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not proj.alive_workers(), "projection worker still alive"
        if controller._work is not None:
            while (controller._work.alive_workers()
                   and time.monotonic() < deadline):
                time.sleep(0.01)
            assert not controller._work.alive_workers(), "work pool still alive"
        assert controller._submit_projection({"probe": 1}, {}) is False
        controller._emit_view({"probe": 1}, reason="conversation")
        labels.append("=utp_qt_projection_close_ok=OK")
    return labels


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


def _run_venv_qt_arm():
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["MAYA_UTP_QT_ARM"] = "1"
    proc = subprocess.run(
        [_venv_python(), str(_REPO / "test_ui_thread_protection.py")],
        capture_output=True, text=True, timeout=300, cwd=str(_REPO), env=env)
    assert proc.returncode == 0, ("qt arm exit %r" % proc.returncode)
    ok = [line for line in proc.stdout.splitlines()
          if line.strip().endswith("=OK")]
    assert len(ok) == 6, "expected 6 qt-arm labels, saw %d" % len(ok)
    return [line for line in proc.stdout.splitlines() if line]


def main():
    if os.environ.get("MAYA_UTP_QT_ARM") == "1":
        for line in _qt_arm_labels():
            print(line)
        print("test_ui_thread_protection_qt=PASS")
        return 0

    arm_a()
    arm_b()
    _flush()
    for line in _tk_arm_labels():
        print(line)
    if _HAS_PYSIDE:
        for line in _qt_arm_labels():
            print(line)
    else:
        for line in _run_venv_qt_arm():
            print(line)
    print("test_ui_thread_protection=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())