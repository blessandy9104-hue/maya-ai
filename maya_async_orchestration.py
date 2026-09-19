"""Asynchronous orchestration driver for Maya's conversational turns.

This module wraps the pure, synchronous :class:`maya_orchestration.Orchestrator`
state machine with a bounded worker pool so planning, validation and execution
never block the caller (the Qt UI thread). It adds nothing to the trust or
approval model: the wrapped orchestrator still owns every state transition and
every terminal outcome. What this layer adds is *scheduling*:

* **bounded concurrency** -- work runs on :class:`maya_async.BoundedExecutor`;
  a queue that is full produces an explicit ``internal_error`` terminal outcome
  rather than silently dropping or unboundedly buffering a turn;
* **stable correlation** -- every turn is created with ``Orchestrator.begin``
  so its ``request_id`` exists before dispatch and can be cancelled;
* **ordering** -- results for a conversation are delivered in the order the
  operations were accepted, even when the underlying work finishes out of
  order;
* **generation / stale safety** -- each operation carries a generation; a late
  result from a cancelled, superseded or closed operation is suppressed;
* **cancellation** -- queued work is removed before it runs and running work is
  asked to stop cooperatively via a :class:`maya_async.CancelToken`; pending
  approval items are reconciled so a cancel can never leave a misleading open
  item;
* **deterministic shutdown** -- shutting down cancels queued work, asks running
  work to stop, joins every worker and suppresses any late delivery.

The module is dependency-free (no Qt) and imports only stdlib plus the pure
orchestration modules.
"""
from __future__ import annotations

import threading

import maya_async
from maya_async import BoundedExecutor, CancelToken, QueueFullError
from maya_orchestration import (
    AWAITING_APPROVAL,
    CANCELLED,
    ERROR,
    Orchestrator,
)

#: Terminal reason used when the bounded queue refused a turn.
REASON_QUEUE_FULL = "async_queue_full"
#: Terminal reason used when a session exceeded its in-flight bound.
REASON_SESSION_LIMIT = "session_inflight_limit"


class AsyncOrchestrator:
    """Schedules orchestrator turns off the caller's thread, in order."""

    def __init__(self, *, orchestrator=None, clock=None, max_workers=2,
                 max_queue=16, max_inflight_per_session=8, dispatcher=None,
                 executor=None, name="maya-orch"):
        self.orch = orchestrator if orchestrator is not None else \
            Orchestrator(clock=clock)
        self.max_inflight_per_session = max(1, int(max_inflight_per_session))
        self._executor = executor if executor is not None else BoundedExecutor(
            max_workers=max_workers, max_queue=max_queue, name=name,
            dispatcher=dispatcher, clock=clock)
        self._lock = threading.RLock()
        self._sessions = {}
        self._turns = {}
        self._stopping = False
        self._shutdown_done = False
        self._stats = {
            "turns_submitted": 0, "turns_duplicate": 0, "turns_rejected": 0,
            "resolves_submitted": 0, "cancelled_queued": 0,
            "cancelled_running": 0, "stale_suppressed": 0,
            "delivery_suppressed": 0, "delivered": 0, "updates": 0,
            "worker_errors": 0, "sessions_closed": 0,
        }

    # -- introspection ---------------------------------------------------
    def stats(self):
        with self._lock:
            data = dict(self._stats)
            data["open_turns"] = sum(1 for t in self._turns.values()
                                     if not t["terminal"])
            data["tracked_turns"] = len(self._turns)
            data["stopping"] = self._stopping
        data["executor"] = self._executor.stats()
        return data

    def pending_view(self):
        return self.orch.pending.surface()

    def request(self, request_id):
        return self.orch.log.get(request_id)

    def _session(self, session_id):
        key = str(session_id)
        session = self._sessions.get(key)
        if session is None:
            session = {
                "id": key,
                "next_order": 0,
                "cursor": 0,
                "buffer": {},
                "inflight": [],
                "closed": False,
            }
            self._sessions[key] = session
        return session

    def _new_order(self, session):
        order = session["next_order"]
        session["next_order"] += 1
        return order

    # -- submission ------------------------------------------------------
    def submit_turn(self, text, *, session_id="session1", classify=None,
                    execute=None, context=None, idempotency_key=None,
                    timeout_seconds=None, on_result=None, on_update=None,
                    on_cancelled=None, supersede_previous=False):
        """Accept a turn and dispatch it, returning an immediate snapshot."""
        with self._lock:
            if self._stopping:
                raise RuntimeError("async orchestrator is shut down")
            key = str(idempotency_key) if idempotency_key else None
            existing = self.orch.log.find_by_key(key) if key else None
            if existing is not None:
                snapshot = dict(existing)
                snapshot["duplicate"] = True
                snapshot["accepted"] = False
                self._stats["turns_duplicate"] += 1
                return snapshot

            session = self._session(session_id)
            if supersede_previous:
                self._supersede_locked(session)
            self._enforce_inflight_locked(session)

            request = self.orch.begin(
                text, session_id=session_id, modality="text",
                idempotency_key=key, timeout_seconds=timeout_seconds)
            request_id = request["request_id"]
            order = self._new_order(session)
            token = CancelToken()
            request["generation"] = order
            request["async_token"] = token

            turn = {
                "request_id": request_id,
                "session_id": session["id"],
                "generation": order,
                "base": order,
                "settled_once": False,
                "text": request.get("text"),
                "token": token,
                "result": dict(request),
                "state": request.get("state"),
                "terminal": bool(request.get("terminal")),
                "deliver": True,
                "on_result": on_result,
                "on_update": on_update,
                "on_cancelled": on_cancelled,
                "done": threading.Event(),
                "settled": threading.Event(),
            }
            self._turns[request_id] = turn
            self._stats["turns_submitted"] += 1

            if turn["terminal"]:
                # begin() already failed closed (e.g. invalid payload).
                self._settle_locked(turn, dict(request))
                turn["done"].set()
                ack = dict(request)
                ack["accepted"] = True
                ack["generation"] = order
                return ack

            session["inflight"].append(request_id)
            try:
                self._executor.submit(
                    self._drive, request, classify, execute, context, token,
                    request_id=request_id, generation=order,
                    on_done=lambda result, handle, rid=request_id:
                        self._on_settled(rid, result),
                    on_error=lambda exc, handle, rid=request_id:
                        self._on_worker_error(rid, exc),
                    on_cancelled=lambda _v, handle, rid=request_id:
                        self._on_settled(
                            rid, self.orch.log.get(rid) or {
                                "request_id": rid, "state": CANCELLED,
                                "outcome": CANCELLED, "terminal": True}))
            except QueueFullError:
                result = self.orch.fail(
                    request_id, REASON_QUEUE_FULL,
                    response=("I'm handling as many things as I safely can "
                              "right now, so I did not start that."))
                self._stats["turns_rejected"] += 1
                self._settle_locked(turn, result)
                ack = dict(result)
                ack["accepted"] = False
                ack["generation"] = order
                return ack

            ack = dict(request)
            ack["accepted"] = True
            ack["generation"] = order
            ack["queued"] = True
            return ack

    def _drive(self, request, classify, execute, context, token):
        try:
            return self.orch.drive(
                request, classify=classify, execute=execute, context=context,
                cancel_check=lambda: token.cancelled)
        except BaseException as exc:  # noqa: BLE001
            with self._lock:
                self._stats["worker_errors"] += 1
            return self.orch.fail(
                request["request_id"],
                "async_worker_exception:" + type(exc).__name__)

    # -- resolution / cancellation --------------------------------------
    def resolve_turn(self, request_id, decision, *, reason="", execute=None,
                     context=None, on_result=None, on_update=None,
                     on_cancelled=None):
        """Resolve an open turn (approve/deny/cancel/retry) off-thread."""
        with self._lock:
            if self._stopping:
                raise RuntimeError("async orchestrator is shut down")
            turn = self._turns.get(str(request_id))
            if turn is None:
                return {"request_id": str(request_id), "error": "unknown_turn"}
            if on_result is not None:
                turn["on_result"] = on_result
            if on_update is not None:
                turn["on_update"] = on_update
            if on_cancelled is not None:
                turn["on_cancelled"] = on_cancelled
            if not turn["terminal"]:
                turn["settled"].clear()
            self._stats["resolves_submitted"] += 1
            try:
                self._executor.submit(
                    self._resolve, request_id, decision, reason, execute,
                    context,
                    request_id="resolve:" + str(request_id),
                    on_done=lambda _v, _h, rid=str(request_id):
                        self._settle_locked_from_log(rid))
            except QueueFullError:
                return {"request_id": str(request_id),
                        "error": REASON_QUEUE_FULL}
        return {"request_id": str(request_id), "accepted": True}

    def _resolve(self, request_id, decision, reason, execute, context):
        return self.orch.resolve(request_id, decision, reason=reason,
                                 execute=execute, context=context)

    def cancel(self, request_id, *, reason="cancelled_by_user"):
        """Cancel a turn; returns ``"queued"``, ``"running"`` or ``None``."""
        rid = str(request_id)
        with self._lock:
            turn = self._turns.get(rid)
            if turn is None:
                return None
            token = turn["token"]
            token.cancel()
            self._reconcile_pending(rid, "cancel", reason)
            status = self._executor.cancel(rid, reason=reason)
            if status == "queued":
                result = self.orch.resolve(rid, "cancel", reason=reason)[0]
                if result is None:
                    result = self.orch.log.get(rid)
                self._stats["cancelled_queued"] += 1
                self._settle_locked(turn, result)
                return "queued"
            if status == "running":
                self._stats["cancelled_running"] += 1
                return "running"
            if turn["terminal"]:
                return None
            # Not tracked by the executor (e.g. already settled); fail closed.
            result = self.orch.resolve(rid, "cancel", reason=reason)[0]
            if result is not None:
                self._settle_locked(turn, result)
            return "queued"

    def supersede(self, request_id):
        """Mark a turn stale so its eventual result is not delivered."""
        rid = str(request_id)
        with self._lock:
            turn = self._turns.get(rid)
            if turn is None:
                return False
            turn["deliver"] = False
        self.cancel(rid, reason="superseded")
        return True

    def _supersede_locked(self, session):
        for rid in list(session["inflight"]):
            turn = self._turns.get(rid)
            if turn is not None and not turn["terminal"]:
                turn["deliver"] = False
                self.cancel(rid, reason="superseded")

    def _enforce_inflight_locked(self, session):
        live = [rid for rid in session["inflight"]
                if not (self._turns.get(rid) or {}).get("terminal")]
        session["inflight"] = live
        while len(live) >= self.max_inflight_per_session:
            freed = False
            for rid in list(live):
                if self._executor.cancel(rid, reason=REASON_SESSION_LIMIT) \
                        == "queued":
                    turn = self._turns.get(rid)
                    result = self.orch.resolve(
                        rid, "cancel", reason=REASON_SESSION_LIMIT)[0]
                    if turn is not None and result is not None:
                        self._stats["cancelled_queued"] += 1
                        self._settle_locked(turn, result)
                    live.remove(rid)
                    freed = True
                    break
            if not freed:
                break
        session["inflight"] = live

    def _reconcile_pending(self, request_id, decision, reason):
        request = self.orch.log.get(request_id)
        if request is None:
            return
        pending_id = request.get("pending_id")
        if pending_id:
            self.orch.pending.resolve(pending_id, decision,
                                      reason=reason or decision)

    def close_session(self, session_id):
        with self._lock:
            session = self._sessions.get(str(session_id))
            if session is None or session.get("closed"):
                return False
            session["closed"] = True
            self._stats["sessions_closed"] += 1
            rids = list(session["inflight"])
        for rid in rids:
            self.cancel(rid, reason="session_closed")
        return True

    # -- settlement / ordered delivery ----------------------------------
    def _on_settled(self, request_id, result):
        with self._lock:
            turn = self._turns.get(str(request_id))
            if turn is None:
                return
            if result is None:
                result = self.orch.log.get(str(request_id)) or {}
            self._settle_locked(turn, result)

    def _on_worker_error(self, request_id, exc):
        result = self.orch.fail(
            str(request_id),
            "async_worker_exception:" + type(exc).__name__)
        with self._lock:
            self._stats["worker_errors"] += 1
            turn = self._turns.get(str(request_id))
            if turn is not None:
                self._settle_locked(turn, result or {})

    def _settle_locked_from_log(self, request_id):
        result = self.orch.log.get(str(request_id))
        with self._lock:
            turn = self._turns.get(str(request_id))
            if turn is not None and result is not None:
                self._settle_locked(turn, result)

    def _settle_locked(self, turn, result):
        """Buffer a settle event and drain in-order deliveries (lock held)."""
        result = dict(result or {})
        turn["result"] = result
        turn["state"] = result.get("state")
        turn["terminal"] = bool(result.get("terminal"))
        request_id = turn["request_id"]
        session = self._sessions.get(turn["session_id"])
        if session is not None:
            session["inflight"] = [r for r in session["inflight"]
                                   if r != request_id]
        if session is None or session.get("closed") or self._stopping:
            self._stats["delivery_suppressed"] += 1
            turn["settled"].set()
            if turn["terminal"]:
                turn["done"].set()
            return
        if not turn["terminal"]:
            self._stats["updates"] += 1
        if turn.get("settled_once"):
            slot = self._new_order(session)
        else:
            slot = turn["base"]
            turn["settled_once"] = True
        session["buffer"][slot] = {
            "turn": turn, "result": result,
            "kind": "result" if turn["terminal"] else "update"}
        self._drain_locked(session)
        turn["settled"].set()
        if turn["terminal"]:
            turn["done"].set()

    def _drain_locked(self, session):
        deliveries = []
        while session["cursor"] in session["buffer"]:
            entry = session["buffer"].pop(session["cursor"])
            session["cursor"] += 1
            turn = entry["turn"]
            if not turn.get("deliver", True):
                self._stats["stale_suppressed"] += 1
                continue
            if entry["kind"] == "update":
                callback = turn.get("on_update")
            else:
                callback = turn.get("on_result")
                if entry["result"].get("outcome") == CANCELLED \
                        and turn.get("on_cancelled") is not None:
                    callback = turn["on_cancelled"]
            if callback is None:
                continue
            self._stats["delivered"] += 1
            deliveries.append((callback, entry["result"]))
        # Dispatch outside the lock to avoid re-entrancy deadlocks.
        for callback, result in deliveries:
            self._executor.run_on_dispatcher(
                _bind(callback, result))

    # -- lifecycle -------------------------------------------------------
    def wait(self, request_id, timeout=5.0, terminal=False):
        """Wait for the next settle (default) or the terminal outcome."""
        turn = self._turns.get(str(request_id))
        if turn is None:
            return None
        event = turn["done"] if terminal else turn["settled"]
        event.wait(max(0.0, float(timeout)))
        return turn["result"]

    def shutdown(self, *, wait=True, timeout=10.0):
        with self._lock:
            if self._shutdown_done:
                return
            self._stopping = True
            rids = [rid for rid, t in self._turns.items() if not t["terminal"]]
        for rid in rids:
            self.cancel(rid, reason="shutdown")
        self._executor.shutdown(wait=wait, timeout=timeout)
        with self._lock:
            self._shutdown_done = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.shutdown()
        return False


def _bind(callback, result):
    def _call():
        return callback(result)
    return _call


__all__ = ["AsyncOrchestrator", "REASON_QUEUE_FULL", "REASON_SESSION_LIMIT",
           "maya_async", "AWAITING_APPROVAL", "ERROR"]
