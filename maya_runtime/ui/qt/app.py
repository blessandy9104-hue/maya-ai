"""Maya Qt desktop window (PySide6 / Qt Quick) — Batch 8E.

Builds the interface-only Qt window over the pure state bridge (``bridge.py``).
The controller owns the Qt thread, the chat subprocess reader and the two
tickers (status every 3000 ms, resources every 2500 ms) — the same cadence and
sources as the Tk interface.

Key invariants:
- no intelligence is computed here; every view value comes from the bridge's
  authoritative state pipeline (snapshot -> cognitive state -> presence ->
  driven FaceState -> VisualState -> shape projection) or from the digest
  verified ``[semantic] `` channel.
- worker threads (local commands, presence, settings, cache, suggestions,
  resource sampling) emit only view signals; Qt forwards them queued to QML.
- if PySide6 is missing, ``maya_app`` falls back to the Tk window; this module
  is never imported in that path.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QIcon, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from . import bridge as _bridge

#: Pure single-thread ordered projection fallback (defined in the bridge so the
#: default sweep interpreter without PySide6 can exercise the same contract).
_OrderedProjectionWorker = _bridge.OrderedProjectionWorker

_QML_DIR = Path(__file__).resolve().parent / "qml"

#: Non-meaningful tick updates that arrive within this window are coalesced
#: into a single latest-state emit. Meaningful events (approvals, denials,
#: cancellation, timeout, failure, completion, safety, conversational replies)
#: always bypass this window; see ``bridge.MEANINGFUL_EVENTS``.
_VIEW_COALESCE_MS = 50.0

#: Degraded-mode one-shot gate (Phase 4F): when the bounded pool is
#: unavailable, a single daemon fallback thread may run at most once per
#: ``_DEGRADED_GATE`` dropped requests and never on top of a still-live one,
#: so the degraded path cannot grow threads without bound.
_DEGRADED_GATE = 3

_INSTRUMENTATION = {"ref": None, "loaded": False}


def _instrumentation():
    """Optional, read-only performance instrumentation (no-op by default)."""
    if not _INSTRUMENTATION["loaded"]:
        _INSTRUMENTATION["loaded"] = True
        try:
            import maya_instrumentation as _inst
            _INSTRUMENTATION["ref"] = _inst
        except Exception:  # noqa: BLE001 - measurements must never break the UI
            _INSTRUMENTATION["ref"] = None
    return _INSTRUMENTATION["ref"]


_ASYNC = {"ref": None, "loaded": False}


def _async_module():
    """Optional bounded-work pool (no-op fallback if unavailable)."""
    if not _ASYNC["loaded"]:
        _ASYNC["loaded"] = True
        try:
            import maya_async as _mod
            _ASYNC["ref"] = _mod
        except Exception:  # noqa: BLE001 - never break the UI over scheduling
            _ASYNC["ref"] = None
    return _ASYNC["ref"]


_CHATPROC = {"ref": None, "loaded": False}


def _chatproc_module():
    """Optional bounded chat-subprocess owner (``None`` if unavailable)."""
    if not _CHATPROC["loaded"]:
        _CHATPROC["loaded"] = True
        try:
            root = str(_bridge.ROOT)
            if root not in sys.path:
                sys.path.insert(0, root)
            import maya_chat_process as _mod
            _CHATPROC["ref"] = _mod
        except Exception:  # noqa: BLE001 - never break the UI over the child
            _CHATPROC["ref"] = None
    return _CHATPROC["ref"]


def _measure_startup(phase, *, duration_ms=None):
    inst = _instrumentation()
    if inst is None or not inst.is_enabled():
        return None
    try:
        return inst.mark_startup(phase, duration_ms=duration_ms)
    except Exception:  # noqa: BLE001
        return None


class Controller(QObject):
    """The object exposed to QML as ``ui``."""

    # -- view signals (emitted from any thread; QML receives queued) -------
    viewJson = Signal(str)          # full tick view (chips, live, shape)
    viewPatchJson = Signal(str)     # additive versioned delta (opt-in consumers)
    chatLine = Signal(str)          # conversational output line
    logLine = Signal(str, str, str) # page, text, color
    settingsJson = Signal(str)      # settings snapshot
    suggestionsJson = Signal(str)   # pending suggestion list
    pendingJson = Signal(str)       # actionable pending-validation queue
    chatOnline = Signal(bool)
    identityJson = Signal(str)
    typingDetected = Signal()   # QML text-field activity (typing overlay)
    uiTask = Signal(object)     # marshal a callable onto the Qt UI thread
    # Phase 4E: bounded, summary-only pipeline snapshot for the cold-start
    # skeleton and the queue/drop indicators (see ``_emit_pipeline``).
    pipelineJson = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._work = None
        # Phase 2: a dedicated, ordered (single worker) bounded executor for
        # view projection. The UI thread only captures a detached snapshot and
        # schedules; the expensive projection runs here and its result is
        # posted back to the UI thread. Never blocks: a full queue drops a
        # presentation frame (chat/approval outcomes flow on other channels).
        self._project = None
        self._project_fallback = None
        mod = _async_module()
        if mod is not None:
            try:
                self._work = mod.BoundedExecutor(
                    max_workers=3, max_queue=24, name="maya-ui",
                    dispatcher=self._dispatch_to_ui)
            except Exception:  # noqa: BLE001
                self._work = None
            try:
                self._project = mod.BoundedExecutor(
                    max_workers=1, max_queue=8, name="maya-proj",
                    dispatcher=self._dispatch_to_ui)
            except Exception:  # noqa: BLE001
                self._project = None
        self._proj_drops = 0
        self._proj_ready = False
        self._last_proj_log_ts = 0.0
        # Phase 4F: bounded degraded-mode accounting for the one-shot fallback
        # (no raw unbounded threads; see ``_submit_worker``).
        self._degraded_drops = 0
        self._degraded_inflight = 0
        self._degraded_path_used = 0
        self._degraded_path_used_emitted = 0
        # Phase 3: monotonic view-projection generation. Every projection is
        # stamped with a strictly increasing generation; a stale result or a
        # stale failure (a newer frame already committed) can never overwrite
        # the committed view, so neither claims completion. A running projection
        # is never cancelled by a newer frame (the FIFO worker commits it first);
        # stale queued work is removable through ``cancel_projection``.
        self._view_gen = 0
        self._last_committed_gen = 0
        self._proj_superseded = 0
        self._proj_cancelled = 0
        self._last_proj_request_id = None
        self.uiTask.connect(self._run_ui_task, Qt.QueuedConnection)
        self.ticker = _bridge.UiTicker()
        self.command = _bridge.CommandBridge()
        # Bounded, cancellable owner of the chat subprocess. The controller
        # never touches the child's pipes directly: every turn is submitted
        # through the manager and every result is correlated + generation-tagged.
        self._chat_mod = _chatproc_module()
        self._chat = self._make_chat_manager()
        self.chat_p = None  # mirror of the live child (for diagnostics)
        self._chat_seq = 0
        self._chat_generation = 0
        self._chat_turn = None
        self._pending_items = []
        self.stop = False
        self._unsafe_streak = 0
        self._emergency_fired = False
        self._activity = "idle"
        self._identity = None
        self._last_view_text = None
        self._tick_seq = 0
        self._unchanged_count = 0
        self._first_input_marked = False
        # Change detection + coalescing state (pure helpers in bridge.py).
        self._view_tracker = _bridge.ChangeTracker()
        self._coalescer = _bridge.UpdateCoalescer(
            interval_ms=_VIEW_COALESCE_MS)
        self._last_input_sig = None
        self._last_stable_view = None
        self._last_safety_key = None
        self._last_patch_revision = 0
        self._suppressed_count = 0
        self._emitted_count = 0
        from maya_runtime import face_drive as _face_drive
        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(int(_face_drive.TYPING_SETTLE_SECONDS * 1000))
        self._typing_timer.timeout.connect(self._typing_settle)
        self._timer_tick = QTimer(self)
        self._timer_tick.setInterval(3000)
        self._timer_tick.timeout.connect(self._on_status_tick)
        self._timer_tick.start()
        self._timer_res = QTimer(self)
        self._timer_res.setInterval(2500)
        self._timer_res.timeout.connect(self._on_resource_tick)
        self._timer_res.start()
        # Phase 4: bounded periodic runtime-observability summary. Only armed
        # when instrumentation is enabled so an idle controller has zero
        # overhead; ``closeNow`` always flushes a final summary regardless.
        _obs = _instrumentation()
        self._timer_obs = None
        if _obs is not None and _obs.is_enabled():
            self._timer_obs = QTimer(self)
            self._timer_obs.setInterval(5000)
            self._timer_obs.timeout.connect(self._on_observability_tick)
            self._timer_obs.start()
        # Flush timer for coalesced (non-meaningful) view updates.
        self._timer_flush = QTimer(self)
        self._timer_flush.setSingleShot(True)
        self._timer_flush.setInterval(max(1, int(_VIEW_COALESCE_MS)))
        self._timer_flush.timeout.connect(self._on_flush_timeout)
        # Phase 4E: bounded pipeline summary for the QML skeleton +
        # queue/drop indicators. Fixed 2 s cadence (summary-only, never per
        # view), emits nothing while the snapshot is unchanged, and is gated
        # by ``stop`` so teardown never publishes. Independent of
        # instrumentation: the disabled-instrumentation path stays inert.
        self._pipeline_last = None
        self._timer_pipeline = QTimer(self)
        self._timer_pipeline.setInterval(2000)
        self._timer_pipeline.timeout.connect(self._emit_pipeline)
        self._timer_pipeline.start()
        self._emit_identity()

    # ------------------------------------------------------------------
    # thread affinity / bounded work
    # ------------------------------------------------------------------
    def _on_ui_thread(self):
        try:
            return QThread.currentThread() is self.thread()
        except Exception:  # noqa: BLE001
            return True

    def _dispatch_to_ui(self, callback):
        """Run ``callback`` on the Qt UI thread (queued when off-thread)."""
        if not callable(callback) or self.stop:
            return False
        try:
            if self._on_ui_thread():
                callback()
                return True
            self.uiTask.emit(callback)
            return True
        except Exception:  # noqa: BLE001
            return False

    @Slot(object)
    def _run_ui_task(self, callback):
        if self.stop or not callable(callback):
            return
        try:
            callback()
        except Exception:  # noqa: BLE001 - a UI task never crashes the loop
            pass

    def _submit_worker(self, fn):
        """Dispatch background work onto the bounded pool (never unbounded)."""
        if self.stop:
            return None
        mod = _async_module()
        if self._work is not None and mod is not None:
            try:
                return self._work.submit(fn)
            except mod.QueueFullError:
                self.logLine.emit(
                    "control", "[async] work queue full; request dropped\n",
                    _bridge.PALETTE["warn"])
                return None
            except Exception:  # noqa: BLE001
                pass
        # Phase 4F: bounded degraded mode. The raw unbounded
        # ``threading.Thread(target=fn, daemon=True)`` fallback is replaced by
        # a single daemon one-shot that may run at most once per
        # ``_DEGRADED_GATE`` drops and never while one is already live, so the
        # degraded path cannot grow threads without bound. ``degraded_path_used``
        # counts only actual fallback runs and is folded into the bounded
        # runtime-summary aggregate (summary-only, never per drop).
        self._degraded_drops += 1
        if self._degraded_drops >= _DEGRADED_GATE and \
                self._degraded_inflight <= 0:
            self._degraded_drops = 0
            self._degraded_inflight += 1
            self._degraded_path_used += 1
            try:
                degraded = threading.Thread(
                    target=self._run_degraded, args=(fn,),
                    name="maya-ui-degraded", daemon=True)
                degraded.start()
            except Exception:  # noqa: BLE001
                self._degraded_inflight -= 1
        return None

    def _run_degraded(self, fn):
        """Run one accepted degraded-mode job (daemon one-shot worker)."""
        try:
            if callable(fn):
                fn()
        finally:
            self._degraded_inflight -= 1

    def _make_chat_manager(self):
        """Own one bounded, cancellable chat child (or ``None`` if unavailable)."""
        mod = self._chat_mod
        if mod is None:
            return None
        try:
            return mod.ChatProcessManager(
                script=(os.environ.get("MAYA_CHAT_SCRIPT")
                        or str(_bridge.ROOT / "maya_chat.py")),
                cwd=str(_bridge.ROOT),
                env={**os.environ, "MAYA_FACE_LINES": "1"},
                idle_ttl=1800.0,
                max_lifetime=3600.0,
                turn_timeout=600.0,
                on_line=self._read_chat,
                on_idle_line=self._on_chat_idle_line,
                on_stderr=self._read_chat_stderr,
                on_exit=self._on_chat_exit,
                name="maya-chat-ui",
            )
        except Exception:  # noqa: BLE001 - chat degrades honestly, UI survives
            return None

    # ------------------------------------------------------------------
    # identity / lifecycle
    # ------------------------------------------------------------------
    def _emit_identity(self):
        def worker():
            try:
                from maya_identity import load_identity
                identity = load_identity() or {}
            except Exception as exc:  # noqa: BLE001
                identity = {"error": str(exc)}
            self.identityJson.emit(json.dumps(identity, ensure_ascii=False))
        self._submit_worker(worker)

    @Slot(str)
    def _apply_identity_string(self, text):
        try:
            self._identity = json.loads(text)
        except (TypeError, ValueError):
            self._identity = {}

    @Slot(str)
    def chatSend(self, text):
        text = (text or "").strip()
        if not text:
            return
        if not self._first_input_marked:
            self._first_input_marked = True
            _measure_startup("first_input")
        self._typing_timer.stop()
        if self._chat is None:
            self.chatLine.emit(
                "[chat unavailable: Maya's chat process could not be started]"
                "\n")
            self._set_activity("idle")
            return
        self._chat_seq += 1
        self._chat_generation += 1
        # A new turn supersedes any held update; never flush a stale view into
        # the newer request generation.
        self._reset_update_state()
        request_id = "chat-%d" % self._chat_seq
        self._chat_turn = request_id
        self._set_activity("listening")
        ack = self._chat.submit(
            text,
            request_id=request_id,
            generation=self._chat_generation,
            on_line=self._read_chat,
            on_done=self._on_chat_done,
        )
        if not ack.get("accepted"):
            self._set_activity("idle")
            error = ack.get("error")
            if error != "duplicate":
                self.chatLine.emit(
                    "[chat] this message was not sent (%s); no answer was "
                    "produced.\n" % error)
            return
        self.chat_p = self._chat.proc
        self.chatOnline.emit(True)
        self._set_activity("processing")

    def startChat(self):
        """Warm the chat child without sending a turn (idempotent)."""
        if self._chat is None:
            return False
        proc = self._chat.start()
        if proc is not None:
            self.chat_p = proc
            self.chatOnline.emit(True)
            return True
        return False

    def _read_chat(self, kind, line, meta=None):
        """Route one stdout line from the chat child (manager reader thread).

        ``kind`` is the protocol channel already classified by the manager:
        ``face`` / ``semantic`` / ``pending`` (the ``[face] ``, ``[semantic] ``
        and ``[pending] `` stdout prefixes) or ``reply`` / ``text``.

        The reader thread only touches signals and thread-marshalling helpers;
        QTimer access stays on the GUI thread (``_set_activity`` queues it).
        """
        try:
            if kind == "face":
                from maya_runtime.face_drive import parse_face_line
                state = parse_face_line(line)
                if state is not None:
                    self._set_activity(state)
                return
            if kind == "semantic":
                self._dispatch_to_ui(
                    lambda ln=line: self._apply_semantic_line(ln))
                return
            if kind == "pending":
                self._apply_pending_line(line)
                return
            self.chatLine.emit(line)
        except Exception:  # noqa: BLE001
            pass

    def _apply_semantic_line(self, line):
        """Apply one ``[semantic]`` cue on the UI thread (queued)."""
        cue = self.ticker.read_semantic_line(line)
        if cue is not None:
            self._refresh_view(reason="conversation")

    def _on_chat_idle_line(self, line):
        """Startup banner / unsolicited child text (no active turn)."""
        try:
            self.chatLine.emit(line)
        except Exception:  # noqa: BLE001
            pass

    def _read_chat_stderr(self, line):
        line = (line or "").rstrip("\n")
        if line:
            self.logLine.emit(
                "control", f"[chat-stderr] {line}\n",
                _bridge.PALETTE["warn"])

    # -- chat turn outcomes (honest, correlated, generation-guarded) -------
    def _on_chat_done(self, result):
        """Terminal outcome for one turn (manager thread -> UI thread)."""
        self._dispatch_to_ui(lambda r=dict(result): self._on_chat_done_ui(r))

    def _on_chat_done_ui(self, result):
        mod = self._chat_mod
        if mod is None:
            return
        request_id = result.get("request_id")
        if request_id != self._chat_turn:
            return  # superseded: a newer turn already owns the surface
        if result.get("generation") != self._chat_generation:
            return  # stale generation: never let it claim completion
        self._chat_turn = None
        outcome = result.get("outcome")
        if outcome == mod.COMPLETED:
            self._set_activity("idle", reason="completion")
            return
        reason = {
            mod.CANCELLED: "cancellation",
            mod.TIMEOUT: "timeout",
        }.get(outcome, "failure")
        messages = {
            mod.CANCELLED:
                "[chat] the request was cancelled and was not completed.\n",
            mod.TIMEOUT:
                "[chat] the request timed out and was stopped; it did not "
                "complete.\n",
            mod.LAUNCH_FAILED:
                "[chat] Maya's chat process could not start; no answer was "
                "produced.\n",
            mod.CRASHED:
                "[chat] Maya's chat process stopped unexpectedly; the request "
                "did not complete.\n",
            mod.NONZERO_EXIT:
                "[chat] Maya's chat process exited with an error; the request "
                "did not complete.\n",
            mod.MALFORMED:
                "[chat] Maya returned an empty response; the request did not "
                "complete.\n",
            mod.PARTIAL:
                "[chat] Maya stopped before answering; the request did not "
                "complete.\n",
        }
        self.chatLine.emit(messages.get(
            outcome, "[chat] the request did not complete.\n"))
        if not self._chat.alive():
            self.chatOnline.emit(False)
            if self._pending_items:
                self._reconcile_pending("turn_%s" % outcome)
        self._set_activity("idle", reason=reason)

    def _on_chat_exit(self, returncode):
        """Child process ended (manager thread -> UI thread)."""
        self._dispatch_to_ui(lambda rc=returncode: self._on_chat_exit_ui(rc))

    def _on_chat_exit_ui(self, returncode):
        self.chat_p = None
        self.chatOnline.emit(False)
        self._reset_update_state()
        if self._pending_items:
            # The child owns the pending store in memory; its exit loses every
            # still-open item, so reconcile them to a terminal state instead of
            # leaving the UI stuck on an action no process can service.
            self._reconcile_pending("process_exit_%s" % (returncode,))

    def _reconcile_pending(self, reason):
        """Close parent-mirrored open pending items after the child is gone."""
        items = [dict(i) for i in (self._pending_items or [])
                 if isinstance(i, dict)]
        if not items:
            return
        try:
            import maya_pending
        except Exception:  # noqa: BLE001
            self._pending_items = []
            return
        resolved = []
        for item in items:
            if item.get("status") == maya_pending.PENDING:
                new_item, _changed, _note = maya_pending.resolve(
                    item, "cancel", now=time.time(),
                    reason="chat_subprocess_" + str(reason))
                resolved.append(new_item if new_item is not None else item)
            else:
                resolved.append(item)
        self._pending_items = resolved
        try:
            surfaced = maya_pending.surface(resolved)
            payload = {"items": surfaced,
                       "summary": maya_pending.human_summary(resolved),
                       "reconciled": True,
                       "reason": str(reason)}
            self.ticker.set_pending(surfaced)
            self.pendingJson.emit(json.dumps(payload, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass
        self._refresh_view(reason="cancellation")

    def _apply_pending_line(self, line):
        """Consume one ``[pending]`` line on the UI thread (queued)."""
        if not self._on_ui_thread():
            self._dispatch_to_ui(lambda: self._apply_pending_line_ui(line))
            return
        self._apply_pending_line_ui(line)

    def _apply_pending_line_ui(self, line):
        """Apply one ``[pending]`` machine line into the view + QML queue."""
        inst = _instrumentation()
        started = inst.now() if (inst is not None and inst.is_enabled()) else None
        try:
            payload = json.loads(line[len("[pending] "):])
        except (TypeError, ValueError):
            return
        items = payload.get("items") if isinstance(payload, dict) else None
        # Mirror the child's actionable set so it can be reconciled if the
        # child exits while an item is still open (in-memory store lost).
        self._pending_items = [dict(i) for i in (items or [])
                               if isinstance(i, dict)]
        self.ticker.set_pending(items or [])
        self.pendingJson.emit(json.dumps(payload, ensure_ascii=False))
        if started is not None:
            try:
                inst.record("pending_panel_update",
                            duration_ms=inst.duration_ms(started, inst.now()),
                            size_bytes=len(line),
                            meta={"item_count": len(items or [])})
            except Exception:  # noqa: BLE001
                pass
        self._refresh_view(reason="approval")

    @Slot(str, str)
    def pendingAction(self, item_id, action):
        """Resolve a pending validation through the real orchestration path."""
        item_id = (item_id or "").strip()
        action = (action or "").strip().lower()
        if not item_id or action not in ("approve", "deny", "cancel",
                                         "retry", "dismiss"):
            return
        self.chatSend(":pending %s %s" % (action, item_id))

    # ------------------------------------------------------------------
    # tickers
    # ------------------------------------------------------------------
    def _set_activity(self, value, reason=None):
        if not self._on_ui_thread():
            self._dispatch_to_ui(
                lambda: self._set_activity(value, reason=reason))
            return
        self._activity = value if value in _bridge.ACTIVITY_KEYS else "idle"
        self._refresh_view(reason=reason)

    @Slot()
    def notifyTyping(self):
        """QML reports keystroke activity on the chat input."""
        from maya_runtime import face_drive as _face_drive
        overlay = _face_drive.typing_activity(self._activity)
        if overlay is not None and overlay != self._activity:
            self._set_activity(overlay)
        self._typing_timer.start()

    def _typing_settle(self):
        """Settle the typing overlay back to idle. Guarded: if a producer
        state (processing/research) arrived meanwhile, this late fire is a
        no-op — the face never degrades a working state."""
        self._typing_timer.stop()
        if self._activity == "listening":
            self._set_activity("idle")

    def _on_status_tick(self):
        if self.stop:
            return
        def worker():
            try:
                payload = self.ticker.make_tick_payload(self._activity)
                self._emit_view(payload)
            except Exception:  # noqa: BLE001
                pass
        self._submit_worker(worker)

    def _refresh_view(self, reason=None):
        def worker():
            try:
                payload = self.ticker.make_tick_payload(self._activity)
                self._emit_view(payload, reason=reason)
            except Exception:  # noqa: BLE001
                pass
        self._submit_worker(worker)

    # ------------------------------------------------------------------
    # change detection / coalescing / emission
    # ------------------------------------------------------------------
    @staticmethod
    def _now_ms():
        return time.monotonic() * 1000.0

    @staticmethod
    def _safety_key(view):
        """The fail-closed surface whose transition is never coalesced."""
        if not isinstance(view, dict):
            return None
        core = view.get("core")
        ui = view.get("ui")
        return (
            str(view.get("resources")),
            (ui or {}).get("healthy") if isinstance(ui, dict) else None,
            (core or {}).get("state") if isinstance(core, dict) else None,
            ((core or {}).get("implies_failure")
             if isinstance(core, dict) else None),
        )

    def _build_envelope(self, view, revision):
        """Full snapshot plus additive ``revision``/``generation`` metadata."""
        if not isinstance(view, dict):
            return view
        envelope = dict(view)
        envelope["revision"] = int(revision)
        envelope["generation"] = int(self._chat_generation)
        return envelope

    def _emit_view(self, payload=None, reason=None):
        """Capture UI-held state and schedule one projection off the UI thread.

        Correctness rules (preserved from the previous inline pipeline):
        * the first observation and the reset view always emit;
        * safety-state transitions and every meaningful event (approval,
          denial, cancellation, timeout, failure, completion, conversation)
          always emit immediately and clear any held update;
        * a non-meaningful change is emitted immediately when the previous
          emit is older than the coalescing window, otherwise the single
          latest view is held and flushed when the window elapses.

        Thread affinity (Phase 2):
        * the authoritative ticker model is read/mutated only on the Qt UI
          thread. Detached state is captured via ``ticker.snapshot_input()``
          and the animation frame is advanced once, here, on the UI thread;
        * the pulled projection (``ticker.project``) runs on a single ordered
          worker and its result is posted back to the UI thread, where every
          bridge/UI mutation (change detection, coalescing, emission) happens;
        * an invalid (non-dict) payload resolves to the immediate neutral
          reset exactly like the inline reset path - that check is O(1) and
          never projects on the UI thread.
        """
        if not self._on_ui_thread():
            self._dispatch_to_ui(
                lambda: self._emit_view(payload, reason=reason))
            return
        if self.stop:
            return
        inst = _instrumentation()
        enabled = inst is not None and inst.is_enabled()
        started = inst.now() if enabled else None
        meaningful = _bridge.is_meaningful(reason)

        if not isinstance(payload, dict):
            # Startup / emergency reset: always immediate and unserialized.
            # The reset commits the latest generation, so any in-flight older
            # projection becomes stale and can never re-apply over it.
            self._reset_update_state()
            self._emit_view_text("null", revision=0, reason=reason,
                                 started=started)
            return

        # 1) Input-level change detection: skip scheduling the pure projection
        #    entirely when neither the backend snapshot nor ticker-held input
        #    state changed. Never skipped while an update is held (it may
        #    supersede).
        signature = _bridge.input_signature(
            payload, self.ticker.state_signature())
        coalescing = self._coalescer.has_pending
        if (signature == self._last_input_sig and not meaningful
                and not coalescing):
            self._suppressed_count += 1
            self._instrument_suppressed(inst, enabled, reason, "input")
            return
        self._last_input_sig = signature

        # 2) Detach every UI-held input and advance the frame once, here, on
        #    the UI thread. The projection worker reads only its snapshot, so
        #    the ticker is never mutated off the UI thread.
        snap = self.ticker.snapshot_input()
        self.ticker.advance_frame()
        self._submit_projection(payload, snap, reason=reason, started=started)

    def _submit_projection(self, payload, snap, reason=None, started=None,
                           generation=None):
        """Schedule one projection; never blocks, never drops chat/approval.

        A full projection queue drops the *presentation* frame (bounded,
        rate-limited log) - chat/approval outcomes always flow on their own
        signals. Falls back to a lazily created single daemon projection
        thread when the ordered executor is unavailable.

        Phase 3: every submission carries a strictly increasing generation and
        an associated request id, so the delivered result (or failure) can be
        matched against the committed view and stale work suppressed.
        """
        if self.stop:
            return False
        if generation is None:
            self._view_gen += 1
            generation = self._view_gen
        request_id = "proj-%d" % generation
        self._last_proj_request_id = request_id
        mod = _async_module()
        if self._project is not None and mod is not None:
            try:
                self._project.submit(
                    self._project_tick, payload, snap, reason, started,
                    generation,
                    request_id=request_id, generation=generation,
                    on_done=self._on_projection_done,
                    on_error=self._on_projection_error,
                    on_cancelled=self._on_projection_cancelled)
                return True
            except mod.QueueFullError:
                self._proj_drops += 1
                try:
                    self._rate_limited_projection_log()
                except Exception:  # noqa: BLE001
                    pass
                return False
            except Exception:  # noqa: BLE001
                pass
        if self._project_fallback is None:
            try:
                self._project_fallback = _OrderedProjectionWorker()
            except Exception:  # noqa: BLE001
                self._project_fallback = None
        if self._project_fallback is not None:
            accepted = self._project_fallback.submit(
                lambda: self._project_native(payload, snap, reason, started,
                                             generation))
            if not accepted:
                self._proj_drops += 1
                try:
                    self._rate_limited_projection_log()
                except Exception:  # noqa: BLE001
                    pass
            return accepted
        return False

    def cancel_projection(self, request_id=None, generation=None,
                          reason="cancelled"):
        """Cancel one in-flight projection explicitly.

        Returns ``"queued"`` (removed before it ran), ``"running"`` (token set,
        its late value suppressed) or ``None``. Used by close/emergency paths
        and by tests; a cancelled projection never applies and never claims
        completion.
        """
        mod = _async_module()
        if self._project is None or mod is None:
            return None
        if request_id is None and generation is not None:
            request_id = "proj-%d" % generation
        if request_id is None:
            request_id = self._last_proj_request_id
        if request_id is None:
            return None
        try:
            return self._project.cancel(request_id, reason=reason)
        except Exception:  # noqa: BLE001
            return None

    def _project_tick(self, payload, snap, reason=None, started=None,
                      generation=None):
        """Run the pure pulled projection on the worker thread."""
        inst = _instrumentation()
        if inst is not None and inst.is_enabled():
            started_proj = inst.now()
            try:
                view = self.ticker.project(payload, snap)
            except Exception as exc:  # noqa: BLE001
                try:
                    inst.record(
                        "ui_projection", count=1,
                        duration_ms=inst.duration_ms(started_proj, inst.now()),
                        meta={"state": "error",
                              "event": str(exc or "")[:120]})
                except Exception:  # noqa: BLE001
                    pass
                raise
            try:
                inst.record(
                    "ui_projection", count=1,
                    duration_ms=inst.duration_ms(started_proj, inst.now()),
                    meta={"reason": str(reason or "update")})
            except Exception:  # noqa: BLE001
                pass
            return view, reason, started
        return self.ticker.project(payload, snap), reason, started

    def _project_native(self, payload, snap, reason=None, started=None,
                        generation=None):
        """Fallback worker body: project then marshal the result to the UI."""
        try:
            value = self._project_tick(payload, snap, reason, started,
                                       generation)
        except BaseException as exc:  # noqa: BLE001
            self._dispatch_to_ui(
                lambda: self._on_projection_error(exc, None,
                                                  generation=generation))
            return
        self._dispatch_to_ui(
            lambda: self._on_projection_done(value, None,
                                             generation=generation))

    def _on_projection_done(self, value, handle, generation=None):
        """Result of one projection, already marshalled onto the UI thread."""
        if self.stop:
            return
        gen = generation if generation is not None else (
            getattr(handle, "generation", None) if handle is not None
            else None)
        if gen is not None and gen < self._last_committed_gen:
            # A stale result can never overwrite a committed newer frame and
            # never claims completion.
            self._proj_superseded += 1
            return
        if gen is not None:
            self._last_committed_gen = gen
        if not self._proj_ready:
            self._proj_ready = True
            _measure_startup("first_projection_ready")
            # A single bounded summary on the ready transition dismisses the
            # cold-start skeleton without waiting for the next 2 s tick.
            self._emit_pipeline()
        view, reason, started = value, None, None
        if isinstance(value, (tuple, list)) and len(value) == 3:
            view, reason, started = value
        self._on_projected_view(view, reason=reason, started=started)

    def _on_projection_error(self, exc, handle, generation=None):
        """A projection raised: fail closed to the neutral reset view.

        Only the *current* generation's failure resets the presentation; a
        stale failure from an older generation is suppressed so it can never
        wipe a newer committed view.
        """
        if self.stop:
            return
        gen = generation if generation is not None else (
            getattr(handle, "generation", None) if handle is not None
            else None)
        if gen is not None and gen < self._last_committed_gen:
            self._proj_superseded += 1
            return
        if gen is not None:
            self._last_committed_gen = gen
        self._proj_drops += 1
        self._reset_update_state()
        self._emit_view_text("null", revision=0, reason="projection_error",
                             started=None)
        try:
            self.logLine.emit(
                "control",
                f"[async] view projection failed; presentation reset "
                f"({type(exc).__name__}: {exc})\n", _bridge.PALETTE["bad"])
        except Exception:  # noqa: BLE001
            pass

    def _on_projection_cancelled(self, value, handle):
        """An explicit cancellation was observed (queued or late-running)."""
        if self.stop:
            return
        self._proj_cancelled += 1

    def _rate_limited_projection_log(self):
        now = time.monotonic()
        if now - self._last_proj_log_ts < 5.0:
            return
        self._last_proj_log_ts = now
        self.logLine.emit(
            "control",
            "[async] view projection queue full; a presentation frame was "
            "skipped (no chat or approval data was lost)\n",
            _bridge.PALETTE["warn"])

    def _on_projected_view(self, view, reason=None, started=None):
        """Apply one worker-projected view on the UI thread.

        Runs from the ordered projection worker's completion callback, which
        is marshalled onto the Qt UI thread. Only bridge-observable /
        coalescing state is mutated here; the expensive projection itself
        never runs on this thread.
        """
        if self.stop:
            return
        if not isinstance(view, dict):
            self._reset_update_state()
            self._emit_view_text("null", revision=0, reason=reason,
                                 started=started)
            return
        inst = _instrumentation()
        enabled = inst is not None and inst.is_enabled()
        meaningful = _bridge.is_meaningful(reason)

        safety_key = self._safety_key(view)
        if safety_key != self._last_safety_key:
            reason = "safety"
            meaningful = True
        self._last_safety_key = safety_key
        stable = _bridge.stable_projection(view)
        # Projected-view change detection (volatile animation fields stay in
        # the payload but are excluded from this equality check). Fingerprint
        # once: ``observe`` both classifies and advances the revision.
        changed, revision = self._view_tracker.observe(stable)
        coalescing = self._coalescer.has_pending
        if not changed and not meaningful and not coalescing:
            self._suppressed_count += 1
            self._instrument_suppressed(inst, enabled, reason, "view")
            return
        due = self._coalescer.offer(
            view, revision=revision, reason=reason, now_ms=self._now_ms())
        if due:
            self._emit_view_now(view, revision, reason, started=started)
        else:
            self._schedule_flush()

    def _instrument_suppressed(self, inst, enabled, reason, stage):
        if not enabled:
            return
        try:
            inst.record("ui_suppressed", count=1,
                        meta={"kind": str(stage),
                              "category": str(reason or "unchanged")})
        except Exception:  # noqa: BLE001
            pass

    def _on_observability_tick(self):
        self._emit_observability("periodic")

    def _emit_observability(self, source="periodic"):
        """Merge one bounded runtime summary into instrumentation and leave a
        single ``runtime_summary`` event. Summary-only (never per view); a
        no-op unless instrumentation is enabled. Never raises."""
        inst = _instrumentation()
        if inst is None or not inst.is_enabled():
            return None
        # Phase 4F: fold only the degraded-path delta since the last summary,
        # so the aggregate accumulates the true total without one event per
        # fallback attempt.
        degraded_delta = self._degraded_path_used - \
            self._degraded_path_used_emitted
        if degraded_delta > 0:
            self._degraded_path_used_emitted = self._degraded_path_used
        counts = {
            "proj_drops": self._proj_drops,
            "proj_superseded": self._proj_superseded,
            "proj_cancelled": self._proj_cancelled,
            "unchanged": self._unchanged_count,
            "suppressed": self._suppressed_count,
            "emitted": self._emitted_count,
            "project_ready": int(bool(self._proj_ready)),
        }
        if degraded_delta > 0:
            counts["degraded_path_used"] = degraded_delta
        for name, pool in (("work", self._work), ("project", self._project),
                           ("project_fallback", self._project_fallback)):
            if pool is None:
                continue
            try:
                st = pool.stats()
            except Exception:  # noqa: BLE001
                continue
            for key in ("queued", "running", "tracked", "tracked_cap",
                        "released", "evicted", "workers"):
                if key in st:
                    counts["%s_%s" % (name, key)] = st[key]
        levels = ["project_ready"]
        for name in ("work", "project", "project_fallback"):
            for key in ("queued", "running", "tracked", "tracked_cap",
                        "workers"):
                levels.append("%s_%s" % (name, key))
        try:
            merged = inst.report_runtime_counts(counts, phase=source,
                                                levels=levels)
        except Exception:  # noqa: BLE001
            return None
        if merged is None:
            return None
        try:
            inst.record("runtime_summary", stage="qt", phase=source,
                        count=len(merged), meta={"source": "qt",
                                                 "kind": str(source)})
        except Exception:  # noqa: BLE001
            pass
        return dict(merged)

    def _emit_pipeline(self):
        """Publish one bounded pipeline summary to QML (Phase 4E).

        Summary-only: a fixed 2 s cadence plus one emission when the first
        projection becomes ready (never per view/event). Reads fixed-size
        counters and the ordered projection pool stats; skips when the
        snapshot is unchanged; never raises. Introduces no instrumentation
        records, so the disabled-instrumentation path is fully inert.
        """
        if self.stop:
            return
        try:
            queued = running = 0
            if self._project is not None:
                try:
                    stats = self._project.stats()
                except Exception:  # noqa: BLE001
                    stats = None
                if isinstance(stats, dict):
                    queued = int(stats.get("queued", 0) or 0)
                    running = int(stats.get("running", 0) or 0)
            payload = json.dumps({
                "ready": int(bool(self._proj_ready)),
                "queued": queued,
                "running": running,
                "dropped": int(self._proj_drops),
                "cancelled": int(self._proj_cancelled),
                "superseded": int(self._proj_superseded),
            }, ensure_ascii=False, sort_keys=True)
            if payload == self._pipeline_last:
                return
            self._pipeline_last = payload
            self.pipelineJson.emit(payload)
        except Exception:  # noqa: BLE001
            return

    def _patch_wanted(self):
        """Deltas are only built when a consumer is actually connected."""
        try:
            return bool(self.receivers(self.viewPatchJson))
        except Exception:  # noqa: BLE001
            return True

    def _emit_view_now(self, view, revision, reason=None, started=None):
        envelope = self._build_envelope(view, revision)
        text = json.dumps(envelope, ensure_ascii=False)
        patch = None
        if self._patch_wanted():
            patch = _bridge.minimize_payload(
                view, self._last_stable_view,
                base_revision=self._last_patch_revision,
                revision=revision, generation=self._chat_generation)
            self._last_stable_view = _bridge.stable_projection(view)
        self._last_patch_revision = revision
        self._emitted_count += 1
        self._emit_view_text(text, revision=revision, reason=reason,
                             started=started, view=view, size_bytes=len(text))
        if patch is not None:
            try:
                self.viewPatchJson.emit(json.dumps(patch, ensure_ascii=False))
            except Exception:  # noqa: BLE001
                pass

    def _emit_view_text(self, text, *, revision, reason, started,
                        view=None, size_bytes=None):
        inst = _instrumentation()
        if inst is not None and inst.is_enabled():
            try:
                self._tick_seq += 1
                inst.record(
                    "ui_tick",
                    duration_ms=(inst.duration_ms(started, inst.now())
                                 if started is not None else 0.0),
                    size_bytes=(len(text) if size_bytes is None
                                else int(size_bytes)),
                    count=self._tick_seq,
                    meta={"revision": int(revision),
                          "phase": str(reason or "update"),
                          "state": str((view or {}).get("visual_state")
                                       if isinstance(view, dict) else "")})
            except Exception:  # noqa: BLE001
                pass
        self._last_view_text = text
        self.viewJson.emit(text)

    def _schedule_flush(self):
        try:
            if (self._timer_flush is not None
                    and not self._timer_flush.isActive()):
                self._timer_flush.start(
                    max(1, int(self._coalescer.interval_ms)))
        except Exception:  # noqa: BLE001
            pass

    @Slot()
    def _on_flush_timeout(self):
        pending = self._coalescer.flush(self._now_ms())
        if pending is None:
            if self._coalescer.has_pending:
                self._schedule_flush()
            return
        self._emit_view_now(pending["view"], pending["revision"],
                            pending.get("reason"))

    def _reset_update_state(self):
        """Drop any held update; safe on reset/reconnect/close."""
        try:
            self._coalescer.reset()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._view_tracker.reset()
        except Exception:  # noqa: BLE001
            pass
        self._last_input_sig = None
        self._last_stable_view = None
        self._last_safety_key = None
        self._last_patch_revision = 0
        # Any reset invalidates every in-flight projection: results or failures
        # delivered after a reset are stale and suppressed.
        self._last_committed_gen = max(self._last_committed_gen,
                                       self._view_gen)
        try:
            if self._timer_flush is not None:
                self._timer_flush.stop()
        except Exception:  # noqa: BLE001
            pass

    def _on_resource_tick(self):
        if self.stop:
            return
        def worker():
            try:
                result = self.command.resource_status()
                if not result.get("monitor_available"):
                    return
                if result.get("safe"):
                    self._unsafe_streak = 0
                    self._emergency_fired = False
                    return
                self._unsafe_streak += 1
                if self._emergency_fired:
                    return
                reasons = ", ".join(result.get("reasons", [])) or "unsafe"
                snap = result.get("snapshot", {})
                cpu = snap.get("cpu_percent", 0)
                mem = snap.get("memory_percent", 0)
                if self._unsafe_streak < 2:
                    self.logLine.emit(
                        "control",
                        f"[resource] resource warning — {reasons} "
                        f"(CPU {cpu:.1f}%, MEM {mem:.1f}%) at "
                        f"{_bridge.time_now()} — awaiting a second "
                        f"consecutive confirmation before stopping\n",
                        _bridge.PALETTE["warn"])
                    return
                self._emergency_fired = True
                self.logLine.emit(
                    "control",
                    f"[resource] RESOURCE SAFETY STOP — {reasons} "
                    f"(CPU {cpu:.1f}%, MEM {mem:.1f}%) at "
                    f"{_bridge.time_now()}\n", _bridge.PALETTE["bad"])
                self.emergency()
            except Exception as exc:  # noqa: BLE001
                self.logLine.emit(
                    "control", f"[resource] monitor unavailable: {exc}\n",
                    _bridge.PALETTE["warn"])
        self._submit_worker(worker)

    # ------------------------------------------------------------------
    # command slots (QML -> worker -> view signals)
    # ------------------------------------------------------------------
    @Slot(str, str)
    def enterCommand(self, page, cmd):
        kind = ("research" if cmd.lstrip().startswith(_bridge.RESEARCH_COMMANDS)
                else "processing")
        self._typing_timer.stop()
        self._set_activity(kind)
        def worker():
            try:
                out = self.command.local_command(cmd)
            except Exception as exc:  # noqa: BLE001
                out = f"Command error: {exc}"
            color = (_bridge.PALETTE["bad"]
                     if str(out).strip().startswith("Command error")
                     else _bridge.PALETTE["ink"])
            self.logLine.emit(
                page, f"[{_bridge.time_now()}] ❯ {cmd}\n{out}\n\n", color)
            self._set_activity("idle")
        self._submit_worker(worker)

    @Slot(str, str)
    def presenceAction(self, action, page="control"):
        def worker():
            out = self.command.presence_action(action)
            self.logLine.emit(
                page, f"[{_bridge.time_now()}] ❯ presence {action}\n{out}\n\n",
                _bridge.PALETTE["ink"])
            self._refresh_settings_view()
        self._submit_worker(worker)

    @Slot()
    def emergency(self):
        detail = self.command.emergency()
        self.logLine.emit(
            "control", f"[{_bridge.time_now()}] ❯ EMERGENCY STOP\n{detail}\n",
            _bridge.PALETTE["bad"])
        if self._chat is not None:
            try:
                self._chat.close(grace=2.0)
            except Exception:  # noqa: BLE001
                pass
        self.chat_p = None
        self.chatOnline.emit(False)
        # Reset is authoritative and immediate: drop any held/coalesced update
        # so a stale pre-emergency view can never be flushed afterwards.
        self._reset_update_state()
        self._last_view_text = json.dumps(None)
        self.viewJson.emit(json.dumps(None))

    # -- settings -----------------------------------------------------------
    @Slot()
    def refreshSettings(self):
        self._refresh_settings_view()

    @Slot()
    def refreshTick(self):
        self._refresh_view()

    def _refresh_settings_view(self):
        def worker():
            snap = self.command.settings_snapshot()
            self.settingsJson.emit(json.dumps(snap, ensure_ascii=False))
        self._submit_worker(worker)

    @Slot(str, str)
    def applyCache(self, cap, ttl):
        def worker():
            text, err = self.command.apply_cache(cap, ttl)
            color = _bridge.PALETTE["bad"] if err else _bridge.PALETTE["ink"]
            self.logLine.emit(
                "settings",
                f"[{_bridge.time_now()}] ❯ apply cache config\n{text}\n",
                color)
            self._refresh_settings_view()
        self._submit_worker(worker)

    @Slot()
    def clearCache(self):
        def worker():
            text, err = self.command.clear_cache()
            color = _bridge.PALETTE["bad"] if err else _bridge.PALETTE["warn"]
            self.logLine.emit(
                "settings",
                f"[{_bridge.time_now()}] ❯ clear cache\n{text}\n", color)
            self._refresh_settings_view()
        self._submit_worker(worker)

    # -- suggestions --------------------------------------------------------
    @Slot()
    def refreshSuggestions(self):
        def worker():
            pending = self.command.pending_suggestions()
            if isinstance(pending, dict) and "error" in pending:
                self.logLine.emit(
                    "settings",
                    f"[{_bridge.time_now()}] ❯ suggestion list read error: "
                    f"{pending['error']}\n", _bridge.PALETTE["bad"])
                pending = []
            self.suggestionsJson.emit(json.dumps(pending, ensure_ascii=False))
        self._submit_worker(worker)

    @Slot(str, str)
    def suggestionReview(self, suggestion_id, decision):
        def worker():
            text = self.command.review_suggestion(suggestion_id, decision)
            try:
                result = json.loads(text)
                status = result.get("status")
                color = (_bridge.PALETTE["ok"]
                         if status == "approved_pending_sandbox_and_regression"
                         else (_bridge.PALETTE["bad"]
                               if status == "rejected_by_user"
                               else _bridge.PALETTE["ink"]))
            except Exception:  # noqa: BLE001
                color = _bridge.PALETTE["bad"]
            self.logLine.emit(
                "settings",
                f"[{_bridge.time_now()}] ❯ suggestion {decision} "
                f"{suggestion_id}\n{text}\n", color)
            self.refreshSuggestions()
            self._refresh_settings_view()
        self._submit_worker(worker)

    # -- world model --------------------------------------------------------
    @Slot(str)
    def worldCompare(self, topic):
        topic = (topic or "").strip()
        cmd = ":world compare " + topic if topic else ":world compare"
        self.enterCommand("world", cmd)

    @Slot(str, str, str, str)
    def worldAdd(self, claim, source, conf, wtype):
        claim = (claim or "").strip()
        source = (source or "").strip()
        if not claim or not source:
            self.enterCommand("world", ":world add")
            return
        payload = (f":world add | {claim} | {source} | "
                   f"{conf} | {wtype}")
        self.enterCommand("world", payload)

    # -- tasks ----------------------------------------------------------------
    @Slot(str, str)
    def taskOp(self, kind, text):
        prefix = {"task add": "task add ", "task done": "task done ",
                  "task remove": "task remove "}.get(kind)
        if prefix is None:
            return
        text = (text or "").strip()
        if not text:
            return
        self.enterCommand("tasks", prefix + text)

    # -- thinking (mirrors MayaApp.show_thinking) ----------------------------
    @Slot(str)
    def thinkMap(self, text):
        def worker():
            try:
                from maya_pattern_mapping import render_pattern_map
                out = render_pattern_map(text)
            except Exception as exc:  # noqa: BLE001
                out = f"Pattern display error: {exc}"
            self.logLine.emit(
                "thinking",
                f"[{_bridge.time_now()}] ❯ patterns\n{out}\n\n",
                _bridge.PALETTE["ink"])
        self._submit_worker(worker)

    @Slot()
    def thinkInterests(self):
        def worker():
            try:
                from maya_learning import interest_summary
                out = interest_summary()
            except Exception as exc:  # noqa: BLE001
                out = f"Pattern display error: {exc}"
            self.logLine.emit(
                "thinking",
                f"[{_bridge.time_now()}] ❯ interests\n{out}\n\n",
                _bridge.PALETTE["ink"])
        self._submit_worker(worker)

    @Slot()
    def thinkEmerging(self):
        def worker():
            try:
                from maya_emerging_interests import emerging_interest_review
                out = emerging_interest_review()
            except Exception as exc:  # noqa: BLE001
                out = f"Pattern display error: {exc}"
            self.logLine.emit(
                "thinking",
                f"[{_bridge.time_now()}] ❯ emerging\n{out}\n\n",
                _bridge.PALETTE["ink"])
        self._submit_worker(worker)

    # -- close ---------------------------------------------------------------
    @Slot()
    def closeNow(self):
        # Final best-effort flush: a coalesced update is never lost on close.
        try:
            pending = self._coalescer.flush(self._now_ms(), force=True)
            if pending is not None:
                self._emit_view_now(pending["view"], pending["revision"],
                                    pending.get("reason"))
        except Exception:  # noqa: BLE001
            pass
        self._reset_update_state()
        self.stop = True
        if self._chat is not None:
            try:
                self._chat.close(grace=3.0)
            except Exception:  # noqa: BLE001
                pass
        self.chat_p = None
        if self._work is not None:
            try:
                # Cancel queued work, stop accepting, join the pool.
                self._work.shutdown(wait=True, timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
        if self._project is not None:
            try:
                # Same deterministic stop for the ordered projection worker;
                # its completion callbacks are already gated by ``self.stop``.
                self._project.shutdown(wait=True, timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
        if self._project_fallback is not None:
            try:
                self._project_fallback.shutdown(wait=True, timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
        # Final bounded runtime summary: captures the counter state after the
        # coalescer flush and worker join so a closing app is fully observable.
        self._emit_observability("closeNow")


def run_window(args=None, qapp=None):
    """Construct the Qt app/window and block until it closes."""
    app = qapp
    if app is None:
        app = QGuiApplication.instance() or QGuiApplication(sys.argv or [])
        app.setApplicationName("Maya")
        app.setApplicationVersion("local")
    try:
        from maya_identity import identity_version
        version = identity_version()
    except Exception:  # noqa: BLE001
        version = "local"
    app.setApplicationVersion(str(version))

    inst = _instrumentation()
    _measure_startup("bridge_ready")  # module import -> bridge ready

    engine_started = inst.now() if (inst is not None and inst.is_enabled()) \
        else None
    engine = QQmlApplicationEngine()
    controller = Controller()
    engine.rootContext().setContextProperty("ui", controller)
    engine.load(str((_QML_DIR / "Main.qml").resolve()))
    if engine_started is not None:
        try:
            inst.mark_startup(
                "qml_engine_load",
                duration_ms=inst.duration_ms(engine_started, inst.now()))
        except Exception:  # noqa: BLE001
            pass
    if not engine.rootObjects():
        controller.closeNow()
        raise RuntimeError("QML failed to load: no root object created")
    if inst is not None and inst.is_enabled():
        try:
            inst.mark_startup("main_window")
            root = engine.rootObjects()[0]
            if hasattr(root, "frameSwapped"):
                state = {"first": True}

                def _on_first_frame():
                    if state["first"]:
                        state["first"] = False
                        try:
                            inst.mark_startup("first_frame")
                        except Exception:  # noqa: BLE001
                            pass

                root.frameSwapped.connect(_on_first_frame)
        except Exception:  # noqa: BLE001
            pass

    # The QML window exposes onClosing -> ui.closeNow()
    def on_about_to_quit():
        controller.closeNow()
    app.aboutToQuit.connect(on_about_to_quit)

    app.setQuitOnLastWindowClosed(True)
    if os.environ.get("MAYA_QT_SMOKE") == "1":
        # Headless smoke test hook: quit shortly after a successful load.
        QTimer.singleShot(1200, app.quit)
    exit_code = app.exec()
    return exit_code