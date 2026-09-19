"""Phase 3 Q4 cancellation/stale-result harness (run under the PySide6 venv).

Drives the real :class:`maya_runtime.ui.qt.app.Controller` on an offscreen Qt
event loop and asserts the cancellation & stale-result contract:

- an explicit ``cancel_projection`` of queued work removes it before it runs
  and nothing is ever delivered for it;
- cancelling a running projection cooperatively suppresses its late value;
- a stale result that would otherwise land *after* a newer frame committed is
  suppressed (``_proj_superseded``), never overwriting the committed view;
- a stale failure never resets the presentation and never adds a drop;
- delivered ordering is strictly the commit order and the final view equals
  the last submission;
- a burst of concurrent submissions keeps the committed generation monotonic
  and consistent;
- a failure from the *current* generation fails closed (reset), as required;
- ``closeNow`` stops accepting projections and joins the worker pool;
- the suppression/drop/cancel counters measure exactly the observed behavior
  (they do not fire spuriously on a clean run).

Output is machine-checkable only (``check:<name>:pass`` / ``:fail:<detail>``).
Requires PySide6; run with the project venv interpreter.
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

from PySide6.QtGui import QGuiApplication  # noqa: E402

from maya_runtime.ui.qt import app as qapp  # noqa: E402


def _process_until(app, predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    return predicate()


def _drain(app, seconds=0.25):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def _make_view(payload, snap=None):
    return {"s": payload.get("s")} if isinstance(payload, dict) else None


def main():
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = qapp.Controller()
    # Isolate from the real periodic status/resource refresh re-submissions so
    # every generation in this harness is caused by an explicit emit below.
    try:
        controller._timer_tick.stop()
        controller._timer_res.stop()
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
                         started=started, view=view,
                         size_bytes=size_bytes)

    controller._emit_view_text = text_wrap

    def sup():
        return controller._proj_superseded

    def canc():
        return controller._proj_cancelled

    def drops():
        return controller._proj_drops

    def committed():
        return controller._last_committed_gen

    def genid():
        return controller._view_gen

    def handle_of(gen):
        return controller._project.handle("proj-%d" % gen)

    def running(gen):
        h = handle_of(gen)
        return h is not None and h.state == "running"

    def queued(gen):
        h = handle_of(gen)
        return h is not None and h.state == "queued"

    def s_views():
        return [v.get("s") for v in emitted]

    # Warm the lazily-imported bridge pipeline so later timing/state checks
    # measure the pipeline, not first-call import cost.
    controller._emit_view(controller.ticker.make_tick_payload("idle"))
    assert _process_until(app, lambda: committed() >= 1), "warmup never committed"
    _drain(app, 0.2)
    base = {"sup": sup(), "canc": canc(), "drops": drops(),
            "emitted": len(emitted), "committed": committed(),
            "gen": genid()}

    # 1. measurement guards: a clean run trips no suppression/drop/cancel.
    controller._emit_view({"s": 200}, reason="mg")
    assert _process_until(
        app, lambda: len(emitted) > base["emitted"]), "mg never delivered"
    assert sup() == base["sup"], "spurious supersede count"
    assert canc() == base["canc"], "spurious cancel count"
    assert drops() == base["drops"], "spurious drop count"
    assert committed() == genid() == base["gen"] + 1, \
        "%s vs %s" % (committed(), genid())
    assert controller._last_proj_request_id == "proj-%d" % genid()
    print("check:measurement_guards:pass")

    # 2. queued cancellation: a request cancelled before it starts is removed,
    #    never delivered, and is not counted as a late-running cancellation.
    gate = threading.Event()

    def gated(payload, snap):
        if isinstance(payload, dict) and payload.get("s") == 1:
            gate.wait(10)
        return _make_view(payload)

    controller.ticker.project = gated
    controller._emit_view({"s": 1}, reason="qcs")
    assert _process_until(app, lambda: running(genid())), "gen1 never ran"
    gen1 = genid()
    controller._emit_view({"s": 2}, reason="qcs2")
    assert genid() == gen1 + 1, genid()
    gen2 = genid()
    assert _process_until(app, lambda: queued(gen2)), "gen2 never queued"
    assert controller.cancel_projection(generation=gen2) == "queued", \
        "queued cancel did not report queued"
    assert canc() == base["canc"], "queued cancel counted as late cancel"
    before_emit = len(emitted)
    gate.set()
    assert _process_until(
        app, lambda: len(emitted) > before_emit), "gen1 never delivered"
    _drain(app, 0.3)
    assert 2 not in s_views(), "cancelled queued projection delivered"
    assert canc() == base["canc"], "queued cancel leaked to the counter"
    print("check:queued_cancel_before_start:pass")

    # 3. running cancellation: the token is set, the cooperative worker
    #    suppresses the late value, and nothing commits for that request.
    gate2 = threading.Event()

    def gated2(payload, snap):
        if isinstance(payload, dict) and payload.get("s") == 3:
            gate2.wait(10)
        return _make_view(payload)

    controller.ticker.project = gated2
    controller._emit_view({"s": 3}, reason="rcs")
    gen3 = genid()
    assert _process_until(app, lambda: running(gen3)), "gen3 never ran"
    before_emit = len(emitted)
    before_committed = committed()
    assert controller.cancel_projection(generation=gen3) == "running", \
        "running cancel did not report running"
    gate2.set()
    assert _process_until(
        app, lambda: canc() > base["canc"]), "late cancellation unobserved"
    _drain(app, 0.2)
    assert len(emitted) == before_emit, "cancelled running projection delivered"
    assert committed() == before_committed, \
        "cancelled projection advanced the committed generation"
    print("check:running_cancel_suppressed:pass")

    # 4. after-compute stale delivery: an older in-flight result that would
    #    land after a newer frame committed is suppressed, not applied.
    gate3 = threading.Event()

    def gated3(payload, snap):
        if isinstance(payload, dict) and payload.get("s") == 4:
            gate3.wait(10)
        return _make_view(payload)

    controller.ticker.project = gated3
    before_sup = sup()
    controller._emit_view({"s": 4}, reason="acs")
    gen4 = genid()
    assert _process_until(app, lambda: running(gen4)), "gen4 never ran"
    controller._emit_view({"s": 5}, reason="acs2")
    gen5 = genid()
    _drain(app, 0.05)
    assert queued(gen5), "gen5 never queued"
    controller._reset_update_state()  # commits gen5 -> gen4 becomes stale
    assert committed() == gen5, committed()
    gate3.set()
    assert _process_until(
        app, lambda: sup() > before_sup), "stale delivery unsuppressed"
    _drain(app, 0.3)
    assert 4 not in s_views(), "stale view was applied"
    assert 5 in s_views(), "newer generation never delivered"
    assert committed() >= gen5, committed()
    print("check:after_compute_stale_suppressed:pass")

    # 5. stale failure: an older generation's failure is suppressed - no reset
    #    emission, no drop count - while the newer generation still delivers.
    gate4 = threading.Event()

    def raise_gated(payload, snap):
        if isinstance(payload, dict) and payload.get("s") == 6:
            gate4.wait(10)
            raise RuntimeError("stale failure probe")
        return _make_view(payload)

    controller.ticker.project = raise_gated
    before_sup = sup()
    before_drops = drops()
    before_resets = len(resets)
    controller._emit_view({"s": 6}, reason="sfr")
    gen6 = genid()
    assert _process_until(app, lambda: running(gen6)), "gen6 never ran"
    controller._emit_view({"s": 7}, reason="sfr2")
    gen7 = genid()
    _drain(app, 0.05)
    assert queued(gen7), "gen7 never queued"
    controller._reset_update_state()  # commits gen7 -> gen6's failure is stale
    gate4.set()
    assert _process_until(
        app, lambda: sup() > before_sup), "stale failure unsuppressed"
    _drain(app, 0.3)
    assert drops() == before_drops, "stale failure counted as a drop"
    assert len(resets) == before_resets, "stale failure reset the presentation"
    assert 7 in s_views(), "newer generation never delivered after stale failure"
    assert 6 not in s_views(), "failed generation delivered a view"
    print("check:stale_failure_no_reset:pass")

    # 6. ordering: delivery strictly follows commit order and the final view
    #    equals the last submission.
    controller.ticker.project = _make_view
    controller._emit_view({"s": 100}, reason="ord")
    controller._emit_view({"s": 101}, reason="ord2")
    controller._emit_view({"s": 102}, reason="ord3")
    assert _process_until(
        app, lambda: len(s_views()) >= base["emitted"] + 3
        and committed() == genid()), "ordered batch never completed"
    _drain(app, 0.2)
    tail = [v for v in s_views() if v in (100, 101, 102)]
    assert tail == [100, 101, 102], tail
    assert committed() == genid(), \
        "%s != %s" % (committed(), genid())
    print("check:ordering_final_equals_latest:pass")

    # 7. race stability: a burst from another thread keeps generations
    #    monotonic and the committed generation ends exactly where submissions
    #    ended, with the newest content winning.
    stop_burst = threading.Event()
    violations = []

    def burst():
        for i in range(500, 524):
            if stop_burst.is_set():
                return
            controller._emit_view({"s": i}, reason="race")
            time.sleep(0.001)

    t = threading.Thread(target=burst, name="race-burst", daemon=True)
    t.start()
    last_committed = committed()
    while t.is_alive() or committed() < genid():
        app.processEvents()
        if committed() < last_committed:
            violations.append(committed())
            break
        last_committed = committed()
        time.sleep(0.002)
    stop_burst.set()
    t.join(5)
    assert not violations, "committed generation regressed"
    assert _process_until(
        app, lambda: committed() == genid(), timeout=10.0), \
        "committed generation never caught up to submissions"
    assert _process_until(
        app, lambda: s_views()[-1] == 523, timeout=10.0), \
        "newest race view never landed: %s" % s_views()[-1]
    print("check:race_stability:pass")

    # 8. current failure fails closed: the current generation's failure resets
    #    the presentation and is counted; the pipeline recovers afterwards.
    def fail_once(payload, snap):
        if isinstance(payload, dict) and payload.get("s") == 50:
            raise RuntimeError("current failure probe")
        return _make_view(payload)

    controller.ticker.project = fail_once
    before_drops = drops()
    before_resets = len(resets)
    before_sup = sup()
    controller._emit_view({"s": 50}, reason="cff")
    assert _process_until(
        app, lambda: drops() > before_drops and len(resets) > before_resets), \
        "current failure did not fail closed"
    _drain(app, 0.2)
    assert sup() == before_sup, "current failure misread as stale"
    assert "projection_error" in resets, resets
    controller._emit_view({"s": 51}, reason="cff2")
    assert _process_until(
        app, lambda: 51 in s_views()), "pipeline did not recover after failure"
    print("check:current_failure_fail_closed:pass")

    # 9. shutdown: closeNow stops accepting projections, joins the worker
    #    pool, and no result is delivered after close.
    controller._emit_view({"s": 90}, reason="sc")
    controller._emit_view({"s": 91}, reason="sc2")
    _drain(app, 0.1)
    controller.closeNow()
    assert controller.stop
    frozen = len(emitted)
    _process_until(
        app, lambda: controller._project.alive_workers() == 0, timeout=5.0)
    assert controller._project.alive_workers() == 0, \
        controller._project.alive_workers()
    _drain(app, 0.3)
    assert len(emitted) == frozen, "result delivered after close"
    assert controller._submit_projection({"s": 99}, {}) is False, \
        "post-close projection was accepted"
    print("check:shutdown_cancels_inflight:pass")

    # 10. stuck-job shutdown + bounded degraded fallback (Phase 4F): a
    #     projection interrupted by nothing (time.sleep(30)) must not hang
    #     closeNow or the executor's join; shutdown returns an explicit
    #     leftover-worker count + join_timeout outcome; submit-after-shutdown
    #     is rejected; the degraded one-shot fallback is bounded and daemon.
    c2 = qapp.Controller()
    try:
        c2._timer_tick.stop()
        c2._timer_res.stop()
    except Exception:  # noqa: BLE001
        pass

    pre_audit = {t.name for t in threading.enumerate()}

    deg_gate = threading.Event()

    def blocked_work():
        deg_gate.wait(15)

    # -- F2: bounded degraded-mode one-shot --------------------------------
    assert c2._degraded_path_used == 0, c2._degraded_path_used
    assert c2._degraded_drops == 0, c2._degraded_drops
    c2._work = None  # force the degraded path (executor unavailable)
    for _ in range(qapp._DEGRADED_GATE):
        c2._submit_worker(blocked_work)
    assert c2._degraded_path_used == 1, c2._degraded_path_used
    assert c2._degraded_drops == 0, c2._degraded_drops
    assert c2._degraded_inflight == 1, c2._degraded_inflight
    deg_alive = [t for t in threading.enumerate()
                 if t.name == "maya-ui-degraded" and t.is_alive()]
    assert len(deg_alive) == 1, len(deg_alive)
    assert deg_alive[0].daemon, "degraded thread not daemonized"
    # A further gated dose never spawns on top of a still-live one-shot.
    for _ in range(qapp._DEGRADED_GATE):
        c2._submit_worker(blocked_work)
    assert c2._degraded_path_used == 1, \
        "second fallback spawn while one was live"
    assert c2._degraded_inflight == 1, c2._degraded_inflight
    # Route the counter through the bounded aggregate (summary-only).
    inst = qapp._instrumentation()
    inst.enable()
    c2._emit_observability("manual")
    merged = inst.runtime_counters()
    assert merged.get("degraded_path_used") == 1, merged
    # A second summary emits a zero delta - never a duplicate count.
    c2._emit_observability("manual")
    assert inst.runtime_counters().get("degraded_path_used") == 1, \
        inst.runtime_counters()
    assert "runtime" in inst.diagnostics(), inst.diagnostics().keys()
    assert inst.diagnostics()["runtime"]["counters"].get(
        "degraded_path_used") == 1, inst.diagnostics()["runtime"]
    inst.disable()
    deg_gate.set()
    drain_end = time.monotonic() + 5.0
    while c2._degraded_inflight != 0 and time.monotonic() < drain_end:
        time.sleep(0.01)
    assert c2._degraded_inflight == 0, c2._degraded_inflight
    assert not [t for t in threading.enumerate()
                if t.name == "maya-ui-degraded" and t.is_alive()], \
        "degraded thread survived release"
    print("check:degraded_fallback_bounded:pass")

    # -- F1: stuck projection, bounded closeNow + explicit shutdown result --
    pre_close = {t.name for t in threading.enumerate()}

    def stuck_project(payload, snap):
        time.sleep(30)  # ignores every cancel for 30 s
        return _make_view(payload)

    c2.ticker.project = stuck_project
    c2._emit_view({"s": 3000}, reason="stuck")
    gen_stuck = c2._view_gen

    def c2_running(gen):
        h = c2._project.handle("proj-%d" % gen)
        return h is not None and h.state == "running"

    assert _process_until(app, lambda: c2_running(gen_stuck), timeout=10.0), \
        "stuck projection never ran"
    assert c2._project.alive_workers() == 1, c2._project.alive_workers()

    close_wall_start = time.monotonic()
    c2.closeNow()
    close_wall = time.monotonic() - close_wall_start
    assert close_wall < 10.0, "closeNow exceeded 10s: %.2f" % close_wall
    assert c2.stop

    result = c2._project.shutdown(wait=True, timeout=0.001)
    assert isinstance(result, dict), result
    assert result["leftover_workers"] >= 1, result
    assert result["join_timeout"] is True, result
    assert result["elapsed"] < 10.0, result
    assert c2._project.alive_workers() >= 1, \
        "stuck worker unexpectedly joined"

    try:
        c2._project.submit(lambda: None)
        raise AssertionError("submit-after-shutdown was accepted")
    except AssertionError:
        raise
    except RuntimeError:
        pass
    assert c2._submit_projection({"s": 3001}, {}) is False, \
        "post-close projection was accepted"

    post_close = {t.name for t in threading.enumerate()}
    assert post_close - pre_close == set(), \
        "new threads appeared across closeNow: %s" % (post_close - pre_close)
    none_leftover = [t for t in threading.enumerate()
                     if t.name.startswith("maya-proj-") and t.is_alive()]
    assert len(none_leftover) == 1, none_leftover
    print("check:stuck_shutdown_bounded:pass")

    print("harness=pass")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("check:harness:fail:%s: %s" % (type(exc).__name__, exc))
        sys.exit(1)
