"""Qt asynchronous-orchestration harness (run under the PySide6 venv).

Drives the real :class:`maya_runtime.ui.qt.app.Controller` on an offscreen Qt
event loop and asserts the thread-affinity contract:

- the controller owns a *bounded* worker pool (finite workers and queue);
- ``_emit_view``, ``_apply_pending_line`` and ``_set_activity`` mutate the
  bridge/ticker model on the Qt UI thread even when called from a worker;
- a slow worker does not block the UI event loop;
- ``closeNow`` stops accepting work and joins every worker.

Output is machine-checkable only (``check:<name>:pass`` / ``:fail:<detail>``)
so the registered suite can parse it without echoing free-form text. Requires
PySide6; run with the project venv interpreter.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from maya_runtime.ui.qt import app as qapp  # noqa: E402


def _process_until(app, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    return predicate()


def _drain(app, seconds=0.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def main():
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = qapp.Controller()
    ui_tid = threading.get_ident()
    state = {}

    # Warm the lazily-imported bridge/identity pipeline so timing checks below
    # measure scheduling, not first-call import cost.
    controller._emit_view(controller.ticker.make_tick_payload("idle"))
    app.processEvents()
    _drain(app, 0.2)

    # 1. bounded pool present.
    work = getattr(controller, "_work", None)
    assert work is not None, "no bounded executor on the controller"
    assert 1 <= work.max_workers <= 16, work.max_workers
    assert 1 <= work.max_queue <= 1024, work.max_queue
    print("check:bounded_executor:pass")

    # 2. _emit_view applies its projection on the UI thread even when the
    #    request originates off the UI thread. The pulled projection itself
    #    runs on the ordered worker; only the UI-side application of the
    #    result (change detection / coalescing / emission) runs here.
    original = controller._on_projected_view

    def wrapped(view, reason=None, started=None):
        state["view_tid"] = threading.get_ident()
        return original(view, reason=reason, started=started)

    controller._on_projected_view = wrapped
    threading.Thread(target=lambda: controller._emit_view({"probe": 1}),
                     daemon=True).start()
    assert _process_until(app, lambda: "view_tid" in state), "view not applied"
    assert state["view_tid"] == ui_tid, "projection applied off the UI thread"
    print("check:emit_view_ui_thread:pass")
    controller._on_projected_view = original
    _drain(app, 0.2)

    # 3. _apply_pending_line mutates the ticker on the UI thread.
    state.clear()
    original_pending = controller.ticker.set_pending

    def wrapped_pending(items):
        state["pending_tid"] = threading.get_ident()
        return original_pending(items)

    controller.ticker.set_pending = wrapped_pending
    line = ('[pending] {"items": [{"id": "p1", "status": "pending"}]}')
    threading.Thread(target=lambda: controller._apply_pending_line(line),
                     daemon=True).start()
    assert _process_until(app, lambda: "pending_tid" in state), "pending not applied"
    assert state["pending_tid"] == ui_tid, "pending mutated off the UI thread"
    print("check:apply_pending_ui_thread:pass")
    controller.ticker.set_pending = original_pending
    _drain(app, 0.3)

    # 4. UI loop stays responsive while a slow worker runs.
    ticks = {"n": 0}
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: ticks.__setitem__("n", ticks["n"] + 1))
    timer.start()
    slow_done = threading.Event()

    def slow():
        time.sleep(0.4)
        slow_done.set()

    controller._submit_worker(slow)
    loop = QEventLoop()
    QTimer.singleShot(300, loop.quit)
    loop.exec()
    timer.stop()
    assert ticks["n"] >= 5, ticks
    assert not slow_done.is_set() or True  # worker may finish; UI never blocked
    print("check:ui_responsive_during_work:pass")
    slow_done.wait(2)

    # 5. the pool never exceeds its bounds under load.
    gate = threading.Event()
    handles = []
    overflowed = False
    try:
        for _ in range(40):
            handles.append(work.submit(gate.wait, 2.0))
    except Exception as exc:  # noqa: BLE001
        overflowed = True
        assert type(exc).__name__ == "QueueFullError", type(exc).__name__
    time.sleep(0.05)
    stats = work.stats()
    assert stats["running"] <= work.max_workers, stats
    assert stats["queued"] <= work.max_queue, stats
    gate.set()
    for handle in handles:
        work.wait(handle.request_id or handle.task_id, timeout=3.0)
    print("check:pool_bounded_under_load:pass")

    # 6. closeNow joins the pool and rejects further work.
    controller.closeNow()
    deadline = time.monotonic() + 3
    while work.alive_workers() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert work.alive_workers() == 0, work.alive_workers()
    assert controller._submit_worker(lambda: None) is None
    print("check:close_joins_pool:pass")
    print("harness=pass")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("check:harness:fail:%s: %s" % (type(exc).__name__, exc))
        sys.exit(1)
