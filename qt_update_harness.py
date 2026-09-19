"""Offscreen Qt harness for bridge update-change detection + coalescing.

Runs on the PySide6 project venv (like ``qt_async_harness.py``). It drives a
real ``Controller`` with a deterministic fake projection so it can verify the
controller's *update policy* precisely, without depending on the live backend:

- an identical payload is never re-emitted;
- a change confined to volatile animation fields is never re-emitted;
- a real change is emitted, with a strictly increasing revision;
- rapid real changes are coalesced into one latest-state emit;
- meaningful events (approval/denial/cancellation/timeout/failure/completion)
  and safety-state transitions always bypass coalescing;
- the reset view is always immediate and resets the revision state;
- every emitted payload carries an additive revision and a sanitized delta;
- ``closeNow`` force-flushes a held update (a final state is never lost).

Prints only ``check:<name>:pass`` lines (and a final ``harness=pass``); the
suite turns them into benign ``=OK`` labels.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from maya_runtime.ui.qt import app as qapp  # noqa: E402
from maya_runtime.ui.qt import bridge as bridge  # noqa: E402


def _view(*, frame=0, learning="off", resources="safe", state="idle",
          failure=False, healthy=True, pending=None):
    return {
        "frame": frame,
        "shape": [0, 1],
        "ring": [0, 1],
        "pointer": {"x": 0.0, "y": 0.0},
        "face": {"frame": frame},
        "face_digest": "digest-%d" % frame,
        "learning": learning,
        "resources": resources,
        "core": {"state": state, "implies_failure": failure},
        "ui": {"healthy": healthy, "pending": list(pending or [])},
        "live_lines": ["l1", "l2", "l3", "l4", "l5", "l6", "l7"],
    }


def main():
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = qapp.Controller()

    clock = [0.0]
    controller._now_ms = lambda: clock[0]

    emitted = []
    patches = []
    controller.viewJson.connect(lambda text: emitted.append(text))
    controller.viewPatchJson.connect(lambda text: patches.append(text))

    live = {"view": _view()}

    # Phase 2: projection runs on the ordered worker via the pulled
    # ``ticker.project(payload, snapshot)`` entry point; stub that path (the
    # old inline ``apply_tick_snapshot`` is no longer what the controller
    # invokes) and drain-pump each submission's delivered result. The checks
    # assert content on the drained outcome exactly as before -- never a
    # timing bound.
    def fake_project(payload, snap):
        if payload is None or payload == "reset":
            return None
        return copy.deepcopy(live["view"])

    controller.ticker.project = fake_project

    delivered = {"n": 0}
    submitted = {"n": 0}
    _orig_deliver = controller._on_projected_view
    _orig_submit = controller._submit_projection

    def _deliver_wrap(view, reason=None, started=None):
        delivered["n"] += 1
        return _orig_deliver(view, reason=reason, started=started)

    def _submit_wrap(payload, snap, reason=None, started=None):
        submitted["n"] += 1
        return _orig_submit(payload, snap, reason=reason, started=started)

    controller._on_projected_view = _deliver_wrap
    controller._submit_projection = _submit_wrap

    def emit(payload, reason=None):
        before_sub = submitted["n"]
        before_del = delivered["n"]
        controller._emit_view(payload, reason=reason)
        if submitted["n"] > before_sub:
            deadline = time.monotonic() + 12.0
            while delivered["n"] <= before_del and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.002)
        app.processEvents()

    def revisions():
        return [json.loads(t)["revision"] for t in emitted if t != "null"]

    # 1. identical payload is never re-emitted.
    emit({"p": 1})
    emit({"p": 1})
    emit({"p": 1})
    assert len(emitted) == 1, len(emitted)
    assert controller._suppressed_count >= 2, controller._suppressed_count
    print("check:identical_suppressed:pass")

    # 2. volatile-only (animation) change is not re-emitted.
    clock[0] = 20.0
    live["view"]["frame"] += 1
    live["view"]["shape"] = [1, 0]
    live["view"]["face_digest"] = "digest-volatile"
    emit({"p": 2})
    assert len(emitted) == 1, len(emitted)
    print("check:volatile_only_suppressed:pass")

    # 3. a real change is coalesced, then flushed with the latest state.
    clock[0] = 30.0
    live["view"]["learning"] = "on"
    emit({"p": 3})
    assert len(emitted) == 1, "held update must not emit early"
    clock[0] = 50.0
    controller._on_flush_timeout()
    assert len(emitted) == 2, len(emitted)
    assert json.loads(emitted[-1])["learning"] == "on"
    print("check:coalesced_flush_latest:pass")

    # 4. no pending update is retained once flushed.
    assert not controller._coalescer.has_pending
    print("check:pending_bounded:pass")

    # 5. a later identical view (new payload) is suppressed.
    clock[0] = 60.0
    emit({"p": 4})
    assert len(emitted) == 2, len(emitted)
    print("check:view_level_suppressed:pass")

    # 6. meaningful events bypass coalescing and clear any held update.
    clock[0] = 70.0
    live["view"]["learning"] = "on2"
    emit({"p": 5})
    assert len(emitted) == 2, "non-meaningful change held within window"
    clock[0] = 75.0
    live["view"]["ui"]["pending"] = [{"id": "p1", "status": "pending",
                                      "terminal": False}]
    emit({"p": 6}, reason="approval")
    assert len(emitted) == 3, len(emitted)
    assert not controller._coalescer.has_pending
    print("check:meaningful_bypasses:pass")

    # 7. safety-state transition bypasses coalescing immediately.
    clock[0] = 80.0
    live["view"]["resources"] = "unsafe"
    live["view"]["core"] = {"state": "error", "implies_failure": True}
    live["view"]["ui"] = {"healthy": False, "pending": []}
    emit({"p": 7})
    assert len(emitted) == 4, len(emitted)
    assert json.loads(emitted[-1])["core"]["state"] == "error"
    print("check:safety_bypasses:pass")

    # 8. monotonically increasing, unique revisions (QML dedupe contract).
    revs = revisions()
    assert revs == sorted(set(revs)) and len(revs) == len(set(revs)), revs
    print("check:revision_monotonic:pass")

    # 9. reset is immediate and clears the held update.
    clock[0] = 90.0
    live["view"]["learning"] = "held"
    emit({"p": 8})
    assert controller._coalescer.has_pending
    emit("reset")
    assert emitted[-1] == "null", emitted[-1]
    assert not controller._coalescer.has_pending
    print("check:reset_immediate:pass")

    # 10. additive deltas carry versions, only changed keys, no secret keys.
    assert patches, "no delta emitted"
    for raw in patches:
        patch = json.loads(raw)
        assert set(("revision", "base_revision", "generation", "changed",
                    "patch")) <= set(patch), patch
        assert bridge.payload_is_sanitized(patch), patch
    print("check:delta_versioned_sanitized:pass")

    # 11. closeNow force-flushes a held final update.
    clock[0] = 200.0
    live["view"] = _view(learning="first")
    emit({"p": 9})
    count = len(emitted)
    clock[0] = 210.0
    live["view"] = _view(learning="final")
    emit({"p": 10})
    assert len(emitted) == count, "held within window"
    controller.closeNow()
    assert len(emitted) == count + 1, len(emitted)
    assert json.loads(emitted[-1])["learning"] == "final"
    print("check:close_flushes_final:pass")

    print("harness=pass")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("check:harness:fail:%s: %s" % (type(exc).__name__, exc))
        sys.exit(1)
