"""Phase 4 runtime-observability suite (``expected_ok=14``).

Contract (registered in ``verification/manifest.py``):

Arm headless -- pure ``maya_instrumentation`` (every interpreter):
  - ``report_runtime_counts`` merges numeric flow counters into the bounded
    runtime aggregate and ``diagnostics()``/``snapshot()``/``to_json()`` expose
    it (phase, updates, last-at, counter magnitudes);
  - merge arithmetic is exact (synthetic magnitudes sum correctly, non-numeric
    values and malformed inputs are ignored);
  - the aggregate is bounded: more than ``MAX_RUNTIME_KEYS`` distinct keys are
    capped at 64 and late keys never enter;
  - reporting is summary-only: a report call never appends an event, so no
    caller can turn per-interaction work into per-interaction events;
  - a disabled module fully no-ops (``None`` returns, empty counters/meta, no
    threads, no side effects);
  - ``reset`` clears the runtime aggregate and its metadata.

Arm Tk -- ``maya_app.MayaApp`` (every interpreter, tkinter):
  - a clean run reports exactly zero drop/skip counters (mailbox, mail,
    tick_skips, stale_skips, tick_ready, compute queue) through the runtime
    aggregate;
  - one ``runtime_summary`` lands per poll interval (never per interaction), a
    sub-interval burst adds none, and the recorded phase is ``poll``;
  - real app counter values (skips/ready/drops) flow into the aggregate with
    correct magnitudes.

Arm Qt -- offscreen ``Controller`` harness (PySide6 venv via subprocess, or
directly with ``--qt``):
  - measurement guards: a clean projection+delivery trips no suppression, drop,
    supersede or cancel counter, and the exporter sees those zeros (plus the
    emitted counter);
  - flow counter paths: a real suppression path (identical resubmission), a
    real delivery path, and a real bounded-drop path surface through the
    runtime summary with ``proj_*``/``suppressed``/``emitted``/``unchanged``
    plus ``work_*``/``project_*`` executor stats keys;
  - ``closeNow`` always flushes a final summary (aggregate phase ``closeNow``,
    updated metadata, projection/executor counters present).

The command ``python test_observability.py --qt`` runs the offscreen Qt arm
in-process under the PySide6 venv; ``python test_observability.py`` runs every
arm (the Qt arm via the venv subprocess) with the same 14 ``=OK`` labels on
every interpreter.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

MAX_RUNTIME_KEYS = 64

_QT_EXPECTED = (
    "obs_measurement_guards",
    "obs_flow_counters",
    "obs_close_summary",
)


def _ok(label):
    print("=" + label + "=OK")


def _inst():
    import maya_instrumentation as _mi
    return _mi


def _fresh():
    """Enabled, cleared state (the env flag, if set, would also enable it)."""
    mi = _inst()
    mi.disable()
    mi.enable()
    mi.reset()
    return mi


def _fresh_disabled():
    """Explicitly disabled, cleared state (no env flag in this process)."""
    mi = _inst()
    mi.enable()
    mi.reset()
    mi.disable()
    return mi


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
# Headless arm -- the instrumentation aggregate itself (every interpreter)
# ---------------------------------------------------------------------------

def test_obs_diagnostics_contains_runtime_ok():
    mi = _fresh()
    merged = mi.report_runtime_counts({"alpha": 3, "beta": 2}, phase="unit")
    assert merged == {"alpha": 3, "beta": 2}, merged
    d = mi.diagnostics()
    assert d["runtime"]["counters"] == {"alpha": 3, "beta": 2}
    assert d["runtime"]["meta"]["phase"] == "unit"
    assert d["runtime"]["meta"]["updates"] == 1
    assert isinstance(d["runtime"]["meta"]["last_at"], (int, float))
    assert d["limits"]["max_runtime_keys"] == MAX_RUNTIME_KEYS
    assert mi.snapshot()["runtime"]["counters"]["alpha"] == 3
    assert mi.runtime_counters() == {"alpha": 3, "beta": 2}
    parsed = json.loads(mi.to_json())
    assert parsed["runtime"]["counters"]["beta"] == 2
    assert parsed["runtime"]["meta"]["phase"] == "unit"
    _ok("obs_diagnostics_contains_runtime_ok")


def test_obs_runtime_merge_magnitudes_ok():
    mi = _fresh()
    mi.report_runtime_counts({"x": 3}, phase="p")
    mi.report_runtime_counts({"x": 2, "y": 5})
    mi.report_runtime_counts({"y": -1, "z": 0.5})
    c = mi.runtime_counters()
    assert c["x"] == 5 and c["y"] == 4 and c["z"] == 0.5, c
    assert mi.runtime_meta()["updates"] == 3
    mi.report_runtime_counts({"q": "not-a-number"})
    assert "q" not in mi.runtime_counters()
    assert mi.report_runtime_counts("nope") is None
    assert mi.report_runtime_counts({"r": 1.0}) is not None
    mi.report_runtime_counts({"lvl": 6, "cnt": 2}, phase="a", levels=("lvl",))
    mi.report_runtime_counts({"lvl": 2, "cnt": 3}, levels=("lvl",))
    c = mi.runtime_counters()
    assert c["lvl"] == 2, c     # absolute level replaces, never accumulates
    assert c["cnt"] == 5, c     # monotonic counters sum under the key
    _ok("obs_runtime_merge_magnitudes_ok")


def test_obs_runtime_bounded_keys_ok():
    mi = _fresh()
    for index in range(300):
        mi.report_runtime_counts({"k_%d" % index: index}, phase="flood")
    c = mi.runtime_counters()
    assert len(c) == MAX_RUNTIME_KEYS, len(c)
    for index in range(MAX_RUNTIME_KEYS):
        assert c["k_%d" % index] == index, index
    assert "k_200" not in c
    _ok("obs_runtime_bounded_keys_ok")


def test_obs_summary_only_not_per_call_ok():
    mi = _fresh()
    for _ in range(50):
        mi.report_runtime_counts({"s": 1}, phase="flood")
    assert mi.event_count() == 0, "reporting MUST NOT create events"
    assert all(e.get("event") != "runtime_summary"
               for e in mi.snapshot()["events"])
    _ok("obs_summary_only_not_per_call_ok")


def test_obs_disabled_noop_ok():
    threads_before = threading.active_count()
    mi = _fresh_disabled()
    assert mi.report_runtime_counts({"a": 1}, phase="x") is None
    assert mi.runtime_counters() == {}
    assert mi.runtime_meta()["updates"] == 0
    assert mi.runtime_meta()["phase"] is None
    assert threading.active_count() == threads_before
    _ok("obs_disabled_noop_ok")


def test_obs_no_threads_sideeffects_ok():
    mi = _fresh()
    threads_before = threading.active_count()
    for _ in range(500):
        mi.report_runtime_counts({"i": 1}, phase="spin")
        mi.diagnostics()
        mi.runtime_counters()
    assert threading.active_count() == threads_before
    assert mi.runtime_counters()["i"] == 500
    _ok("obs_no_threads_sideeffects_ok")


def test_obs_reset_clears_runtime_ok():
    mi = _fresh()
    mi.report_runtime_counts({"a": 5}, phase="p")
    assert mi.runtime_counters() == {"a": 5}
    mi.reset()
    assert mi.runtime_counters() == {}
    assert mi.runtime_meta() == {"phase": None, "updates": 0, "last_at": 0.0}
    _ok("obs_reset_clears_runtime_ok")


# ---------------------------------------------------------------------------
# Tk arm -- maya_app.MayaApp (every interpreter, tkinter)
# ---------------------------------------------------------------------------

_TKR = {"done": False, "checks": {}}


def _tk_make_app():
    import tkinter as tk
    from maya_app import MayaApp

    root = tk.Tk()
    root.withdraw()
    return root, MayaApp(root)


def _tk_pump(app, polls):
    for _ in range(polls):
        app.poll()


def _tk_run():
    if _TKR["done"]:
        return _TKR
    _TKR["done"] = True
    checks = _TKR["checks"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        # -- check 1: a clean run reports zero drop/skip counters.
        mi = _fresh()
        root, app = _tk_make_app()
        try:
            _tk_pump(app, 16)
            c = mi.diagnostics()["runtime"]["counters"]
            for key in ("mailbox", "mail", "tick_skips", "stale_skips",
                        "tick_ready"):
                assert key in c, (key, c)
                assert c[key] == 0, (key, c[key])
            assert c["compute_queue"] == 0, c
            assert c["compute_alive"] in (0, 1), c
        finally:
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass
        checks["tk_clean_zero"] = True

        # -- check 2: one summary per poll interval, never per interaction.
        mi = _fresh()
        root, app = _tk_make_app()
        try:
            def summaries():
                return [e for e in mi.snapshot()["events"]
                        if e.get("event") == "runtime_summary"]
            _tk_pump(app, 12)
            found = summaries()
            assert 1 <= len(found) <= 3, len(found)
            assert all(e.get("stage") == "tk" for e in found)
            assert mi.runtime_meta()["phase"] == "poll"
            assert mi.runtime_meta()["updates"] >= 1
            before = len(summaries())
            _tk_pump(app, 2)  # sub-interval burst produces no new summary
            assert len(summaries()) - before == 0
        finally:
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass
        checks["tk_interval"] = True

        # -- check 3: app counter values flow into the aggregate unchanged.
        mi = _fresh()
        root, app = _tk_make_app()
        try:
            app._tick_skips = 7
            app._stale_skips = 3
            app._tick_ready_count = 4
            app.q.drops = 9
            app._mail_drops = 2
            wait = time.monotonic() + 12.0
            while True:
                _tk_pump(app, 6)
                c = mi.runtime_counters()
                if (c.get("tick_ready") == 4 and c.get("mailbox") == 9
                        and c.get("tick_skips") == 7):
                    break
                assert time.monotonic() < wait, c
            assert c["stale_skips"] == 3, c
            assert c["mail"] == 2, c
            assert c["compute_queue"] == 0, c
            assert c["compute_alive"] == 1, c
        finally:
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass
        checks["tk_counters"] = True
    return _TKR


def _tk_require(name, label):
    data = _tk_run()
    assert data["checks"].get(name), "tk check missing: " + name
    _ok(label)


def test_obs_tk_clean_zero_ok():
    _tk_require("tk_clean_zero", "obs_tk_clean_zero_ok")


def test_obs_tk_interval_summary_ok():
    _tk_require("tk_interval", "obs_tk_interval_summary_ok")


def test_obs_tk_counters_flow_ok():
    _tk_require("tk_counters", "obs_tk_counters_flow_ok")


# ---------------------------------------------------------------------------
# Qt arm -- offscreen Controller harness (PySide6 venv)
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
            [_venv_python(), str(_REPO / "test_observability.py"), "--qt"],
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


def test_obs_qt_measurement_guards_ok():
    _qt_require("obs_measurement_guards", "obs_qt_measurement_guards_ok")


def test_obs_qt_flow_counters_ok():
    _qt_require("obs_flow_counters", "obs_qt_flow_counters_ok")


def test_obs_qt_close_summary_ok():
    _qt_require("obs_close_summary", "obs_qt_close_summary_ok")


def test_obs_qt_harness_complete_ok():
    data = _run_qt_harness()
    missing = [n for n in _QT_EXPECTED if n not in data["checks"]]
    assert not missing, data["error"] or ("missing " + ",".join(missing))
    _ok("obs_qt_harness_complete_ok")


def _qt_main():
    """In-process offscreen Qt arm (``--qt``); machine-checkable only."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _mi = _inst()
    _mi.enable()
    _mi.reset()
    from PySide6.QtGui import QGuiApplication  # noqa: E402

    from maya_runtime.ui.qt import app as qapp  # noqa: E402

    app = QGuiApplication.instance() or QGuiApplication([])

    def _process_until(predicate, timeout=8.0):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        return predicate()

    def _drain(seconds=0.2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)

    def _make_view(payload):
        return {"s": payload.get("s")} if isinstance(payload, dict) else None

    controller = qapp.Controller()
    # Deterministic arm: no wall-clock periodic emissions alias the harness.
    for timer in ("_timer_tick", "_timer_res", "_timer_obs"):
        try:
            getattr(controller, timer).stop()
        except Exception:  # noqa: BLE001
            pass

    emitted = []
    resets = []
    orig_deliver = controller._on_projected_view

    def deliver_wrap(view, reason=None, started=None):
        emitted.append(view)
        orig_deliver(view, reason=reason, started=started)

    controller._on_projected_view = deliver_wrap
    orig_text = controller._emit_view_text

    def text_wrap(text, *, revision, reason, started, view=None,
                  size_bytes=None):
        if text == "null":
            resets.append(reason)
        return orig_text(text, revision=revision, reason=reason,
                         started=started, view=view, size_bytes=size_bytes)

    controller._emit_view_text = text_wrap

    def sup():
        return controller._proj_superseded

    def canc():
        return controller._proj_cancelled

    def drops():
        return controller._proj_drops

    # ---- check 1: measurement guards + exporter saw the clean zeros.
    controller._emit_view(controller.ticker.make_tick_payload("idle"))
    assert _process_until(lambda: controller._last_committed_gen >= 1), \
        "warmup never committed"
    _drain()
    base = {"sup": sup(), "canc": canc(), "drops": drops()}
    controller._emit_view({"s": 100}, reason="obs-mg")
    assert _process_until(lambda: len(emitted) > 0), "mg never delivered"
    _drain()
    assert sup() == base["sup"], "spurious supersede count"
    assert canc() == base["canc"], "spurious cancel count"
    assert drops() == base["drops"], "spurious drop count"
    assert controller._suppressed_count == 0, \
        "spurious suppression count"
    controller._emit_observability("harness_clean")
    c = _mi.diagnostics()["runtime"]["counters"]
    assert c["proj_drops"] == base["drops"], c
    assert c["proj_superseded"] == base["sup"], c
    assert c["proj_cancelled"] == base["canc"], c
    assert c["suppressed"] == 0, c
    assert c["emitted"] >= 1, c
    assert "project_ready" in c
    print("check:obs_measurement_guards:pass")

    # ---- check 2: real suppression, delivery and bounded-drop paths surface.
    before_drops = drops()
    controller._emit_view({"s": 100}, reason="obs-s1")  # identical view
    _drain(0.3)
    assert controller._suppressed_count >= 1, "suppression path unseen"
    controller._emit_view({"s": 200}, reason="obs-em")
    assert _process_until(lambda: controller._emitted_count >= 2), \
        "delivery path unseen"
    gate = threading.Event()

    def blocked(payload, snap):
        gate.wait(10)
        return _make_view(payload)

    controller.ticker.project = blocked
    controller._emit_view({"s": 3}, reason="obs-drop")  # runs, blocks the worker
    assert _process_until(
        lambda: controller._project is not None
        and controller._project.running_count() >= 1), "drop worker never ran"
    for index in range(12):
        controller._emit_view({"s": 30 + index}, reason="obs-flood")
    assert _process_until(lambda: drops() > before_drops, timeout=8.0), \
        "bounded drop path unseen"
    gate.set()
    _drain(0.4)
    controller._emit_observability("harness")
    c = _mi.runtime_counters()
    assert c["proj_drops"] > before_drops, c
    assert "proj_superseded" in c and "proj_cancelled" in c, c
    assert "suppressed" in c and "emitted" in c and "unchanged" in c, c
    for key in ("work_tracked", "work_workers", "work_queued",
                "project_tracked", "project_workers"):
        assert key in c, (key, c)
    assert _mi.runtime_meta()["phase"] == "harness"
    print("check:obs_flow_counters:pass")

    # ---- check 3: closeNow always flushes a final summary.
    before_updates = _mi.runtime_meta()["updates"]
    before_events = _mi.event_count()
    controller.closeNow()
    meta = _mi.runtime_meta()
    assert meta["phase"] == "closeNow", meta
    assert meta["updates"] > before_updates, meta
    c = _mi.runtime_counters()
    for key in ("proj_drops", "proj_superseded", "proj_cancelled",
                "suppressed", "emitted", "work_tracked", "work_released",
                "project_tracked", "project_released",
                "project_evicted", "project_workers"):
        assert key in c, (key, c)
    events = [e for e in _mi.snapshot()["events"]
              if e.get("event") == "runtime_summary"]
    assert any(e.get("phase") == "closeNow" for e in events)
    assert _mi.event_count() >= before_events
    assert all(e.get("meta", {}).get("source") in ("tk", "qt")
               for e in events)
    print("check:obs_close_summary:pass")

    print("harness=pass")
    print("test_observability=PASS")
    return 0


if __name__ == "__main__":
    if "--qt" in sys.argv[1:]:
        raise SystemExit(_qt_main())
    for _name in sorted(
            n for n in dir() if n.startswith("test_")
            and callable(globals().get(n))
            and getattr(globals().get(n), "__module__", "") == "__main__"):
        globals()[_name]()