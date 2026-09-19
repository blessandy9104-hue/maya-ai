"""Qt chat-subprocess harness (run under the PySide6 venv).

Drives the real :class:`maya_runtime.ui.qt.app.Controller` on an offscreen Qt
event loop against a deterministic fake chat child (selected through
``MAYA_CHAT_SCRIPT``) and asserts the subprocess integration contract:

- the controller owns a bounded chat manager and warms the child;
- a normal turn streams the reply and returns the UI to idle, with every model
  mutation happening on the Qt UI thread;
- a crashed child produces an honest non-completion line and marks chat offline;
- an open pending item is reconciled to a terminal state when the child dies;
- closing the app terminates the child and leaves no orphan process or thread.

Output is machine-checkable only (``check:<name>:pass`` / ``:fail:<detail>``).
Requires PySide6; run with the project venv interpreter.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_FAKE_SOURCE = '''\
import os
import sys
import time


def emit(text):
    sys.stdout.write(text + "\\n")
    sys.stdout.flush()


emit("Maya chat fake ready.")
emit("Face protocol on.")

for raw in sys.stdin:
    text = raw.rstrip("\\n")
    if text == "":
        continue
    sys.stderr.write("[Intent JSON: {\\"text\\": \\"x\\"}]\\n")
    sys.stderr.flush()
    if text == "exit":
        emit("")
        emit("Maya: Goodbye.")
        break
    if text == "hang":
        emit("[face] processing")
        time.sleep(60)
        continue
    if text == "crash":
        os._exit(3)
    if text == "pending":
        emit('[pending] {"items": [{"id": "p1", "kind": "action", '
             '"title": "Do a thing", "summary": "s", '
             '"required_action": "approve", "next_step": "review", '
             '"status": "pending", "attempts": 0}]}')
        emit("Maya: needs approval")
        emit("[face] idle")
        continue
    emit("[face] processing")
    emit("Maya: echo " + text)
    emit("[face] idle")
'''


def _process_until(app, predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    return predicate()


def _drain(app, seconds=0.3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def main():
    fake_dir = tempfile.mkdtemp(prefix="maya_qtchat_")
    fake = Path(fake_dir) / "fake_chat.py"
    fake.write_text(_FAKE_SOURCE, encoding="utf-8", newline="\n")
    os.environ["MAYA_CHAT_SCRIPT"] = str(fake)

    from PySide6.QtGui import QGuiApplication  # noqa: E402
    from maya_runtime.ui.qt import app as qapp  # noqa: E402

    app = QGuiApplication.instance() or QGuiApplication([])
    controller = qapp.Controller()
    # Isolate the harness from the wall-clock resource monitor: a busy CI box
    # must not trigger the real emergency stop (which would close the child).
    controller._timer_res.stop()
    controller._timer_tick.stop()
    ui_tid = threading.get_ident()
    lines = []
    online = []
    controller.chatLine.connect(lambda s: lines.append(s))
    controller.chatOnline.connect(lambda b: online.append(bool(b)))
    app.processEvents()

    # 0. the bounded manager is present.
    assert controller._chat is not None, "no chat manager on the controller"
    assert controller._chat.max_queue >= 1
    assert controller.startChat() is True
    assert _process_until(app, lambda: any("fake ready" in t for t in lines)), \
        "child banner not delivered"
    print("check:chatproc_launch:pass")

    # Warm the (lazily imported) projection pipeline so later checks measure
    # scheduling, not first-call import cost.
    controller._emit_view(controller.ticker.make_tick_payload("idle"))
    _drain(app, 0.3)

    # 1. normal turn: reply streams and the UI returns to idle.
    lines.clear()
    controller.chatSend("hello")
    assert _process_until(app, lambda: any("Maya: echo hello" in t
                                           for t in lines)), "no reply line"
    assert _process_until(app, lambda: controller._activity == "idle", 3.0), \
        ("UI stayed busy after a completed turn: activity=%r lines=%r "
         "turn=%r" % (controller._activity, lines, controller._chat_turn))
    print("check:chatproc_normal_turn:pass")

    # 2. the dispatch path chat state updates use lands on the Qt UI thread.
    applied_tids = []
    original_apply = controller._on_projected_view

    def wrapped_apply(view, reason=None, started=None):
        applied_tids.append(threading.get_ident())
        return original_apply(view, reason=reason, started=started)

    controller._on_projected_view = wrapped_apply
    threading.Thread(
        target=lambda: controller._emit_view({"probe": 1}),
        daemon=True).start()
    assert _process_until(app, lambda: bool(applied_tids)), \
        "queued view dispatch never ran"
    assert all(tid == ui_tid for tid in applied_tids), \
        "chat view mutation happened off the UI thread"
    print("check:chatproc_ui_thread_affinity:pass")
    controller._on_projected_view = original_apply

    # 2. crashed child -> honest non-completion line, chat offline.
    lines.clear()
    controller.chatSend("crash")
    assert _process_until(app, lambda: any("did not complete" in t
                                           for t in lines)), \
        "crash was not reported honestly"
    assert _process_until(app, lambda: controller._chat.alive() is False), \
        "manager still reports a live child after the crash"
    assert online and online[-1] is False, "chat was not marked offline"
    print("check:chatproc_failure_honest:pass")

    # 3. an open pending item is reconciled when the child dies.
    controller.chatSend("pending")
    assert _process_until(
        app,
        lambda: any(i.get("status") == "pending"
                    for i in controller._pending_items), 5.0), \
        "pending item never surfaced"
    lines.clear()
    controller.chatSend("crash")
    assert _process_until(
        app,
        lambda: bool(controller._pending_items)
        and all(i.get("status") != "pending"
                for i in controller._pending_items), 5.0), \
        "open pending item was not reconciled after the child died"
    print("check:chatproc_pending_reconcile:pass")

    # 4. closing the app terminates the child and joins every thread.
    lines.clear()
    controller.chatSend("hang")
    assert _process_until(
        app, lambda: controller._chat.stats()["active"] is not None, 5.0), \
        ("hang turn never became active: %r turn=%r lines=%r"
         % (controller._chat.stats(), controller._chat_turn, lines))
    controller.closeNow()
    assert _process_until(app, lambda: controller._chat.child_alive() == 0,
                          3.0), "orphan child survived close"
    assert _process_until(app, lambda: controller._chat.threads_alive() == 0,
                          3.0), "manager threads survived close"
    print("check:chatproc_close_no_orphan:pass")

    print("harness=pass")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("check:harness:fail:%s: %s" % (type(exc).__name__, exc))
        sys.exit(1)
