"""Bounded asynchronous execution for Maya.

A small, dependency-free worker pool with an explicit contract:

* **bounded** -- at most ``max_workers`` run concurrently and at most
  ``max_queue`` wait; submitting past the bound raises :class:`QueueFullError`
  so a caller can surface an explicit failure instead of silently dropping
  work;
* **cancellable** -- a cooperative :class:`CancelToken` plus queue removal, so
  queued work can be cancelled before it starts and running work can stop
  between attempts;
* **exception-transparent** -- a raising job never kills a worker; the error is
  captured on the handle and routed to ``on_error`` so callers can turn it into
  an explicit ``internal_error`` outcome;
* **deterministic shutdown** -- :meth:`BoundedExecutor.shutdown` cancels queued
  work, stops accepting work, joins every worker and suppresses any callback
  that would otherwise arrive after shutdown.

The pool computes nothing itself and imports no UI toolkit. A ``dispatcher``
callable can marshal completion callbacks onto an owning thread (the Qt UI
thread) without this module knowing about Qt.
"""
from __future__ import annotations

import collections
import threading
import time

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

_TERMINAL_STATES = (DONE, FAILED, CANCELLED)


class TaskCancelled(Exception):
    """Raised by cooperative work that observes a cancelled token."""


class QueueFullError(RuntimeError):
    """Raised when the bounded queue cannot accept another task."""


class CancelToken:
    """Thread-safe cooperative cancellation flag (single use per task)."""

    __slots__ = ("_event",)

    def __init__(self, cancelled=False):
        self._event = threading.Event()
        if cancelled:
            self._event.set()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self):
        return self._event.is_set()

    def raise_if_cancelled(self):
        if self._event.is_set():
            raise TaskCancelled("task cancelled")

    def __bool__(self):  # convenient for ``if token:``
        return self._event.is_set()


class TaskHandle:
    """Observable state for one submitted job."""

    __slots__ = ("task_id", "request_key", "request_id", "generation", "token",
                 "state", "result", "error", "cancel_reason", "submitted_at",
                 "started_at", "finished_at", "_on_done", "_on_error",
                 "_on_cancelled", "_fn", "_args", "_kwargs", "released",
                 "terminal_registered")

    def __init__(self, task_id, fn, args, kwargs, *, request_id, generation,
                 token, on_done, on_error, on_cancelled):
        self.task_id = task_id
        self.request_id = request_id
        self.generation = int(generation or 0)
        self.token = token if token is not None else CancelToken()
        self.state = QUEUED
        self.result = None
        self.error = None
        self.cancel_reason = ""
        self.submitted_at = None
        self.started_at = None
        self.finished_at = None
        self._on_done = on_done
        self._on_error = on_error
        self._on_cancelled = on_cancelled
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.released = False
        self.terminal_registered = False
        self.request_key = None

    @property
    def terminal(self):
        return self.state in _TERMINAL_STATES

    def cancel(self, reason=""):
        if reason and not self.cancel_reason:
            self.cancel_reason = str(reason)
        self.token.cancel()

    def snapshot(self):
        return {
            "task_id": self.task_id,
            "request_id": self.request_id,
            "generation": self.generation,
            "state": self.state,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancel_reason": self.cancel_reason,
            "error": (type(self.error).__name__ if self.error is not None
                      else None),
        }


def _default_dispatcher(callback):
    """Run the callback inline (the pool's own thread)."""
    callback()


class BoundedExecutor:
    """Fixed-size worker pool over a bounded FIFO queue."""

    def __init__(self, *, max_workers=2, max_queue=16, name="maya-async",
                 dispatcher=None, clock=None, max_tracked=4096,
                 release_terminal_refs=True):
        self.max_workers = max(1, int(max_workers))
        self.max_queue = max(1, int(max_queue))
        self.max_tracked = max(1, int(max_tracked))
        self._release_terminal_refs = bool(release_terminal_refs)
        self.name = str(name)
        self._clock = clock if callable(clock) else time.monotonic
        self._dispatcher = dispatcher if callable(dispatcher) else \
            _default_dispatcher
        self._cond = threading.Condition()
        self._queue = collections.deque()
        self._handles = {}
        self._by_request = {}
        self._terminal_order = collections.deque()
        self._workers = []
        self._stopping = False
        self._shutdown_done = False
        self._seq = 0
        self._stats = {
            "submitted": 0, "completed": 0, "failed": 0, "cancelled": 0,
            "rejected": 0, "cancelled_queued": 0, "dispatch_errors": 0,
            "dispatch_skipped": 0, "released": 0, "evicted": 0,
        }
        for index in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop, name="%s-%d" % (self.name, index),
                daemon=True)
            worker.start()
            self._workers.append(worker)

    # -- introspection ---------------------------------------------------
    def now(self):
        try:
            return float(self._clock())
        except Exception:  # noqa: BLE001
            return None

    def queued_count(self):
        with self._cond:
            return len(self._queue)

    def running_count(self):
        with self._cond:
            return sum(1 for h in self._handles.values() if h.state == RUNNING)

    def stats(self):
        with self._cond:
            data = dict(self._stats)
            data["queued"] = len(self._queue)
            data["running"] = sum(1 for h in self._handles.values()
                                  if h.state == RUNNING)
            data["tracked"] = len(self._handles)
            data["tracked_cap"] = self.max_tracked
            data["released"] = self._stats["released"]
            data["evicted"] = self._stats["evicted"]
            data["workers"] = len(self._workers)
            data["stopping"] = self._stopping
        return data

    def handle(self, request_id):
        with self._cond:
            return self._by_request.get(str(request_id))

    def run_on_dispatcher(self, callback):
        """Marshal ``callback`` onto the owning thread (best effort)."""
        if not callable(callback):
            return False
        with self._cond:
            stopping = self._stopping
        if stopping:
            with self._cond:
                self._stats["dispatch_skipped"] += 1
            return False
        try:
            self._dispatcher(callback)
            return True
        except Exception:  # noqa: BLE001
            with self._cond:
                self._stats["dispatch_errors"] += 1
            return False

    # -- submission ------------------------------------------------------
    def submit(self, fn, *args, request_id=None, generation=0,
               cancel_token=None, on_done=None, on_error=None,
               on_cancelled=None, **kwargs):
        if not callable(fn):
            raise TypeError("job must be callable")
        with self._cond:
            if self._stopping:
                raise RuntimeError("executor is shut down")
            if len(self._queue) >= self.max_queue:
                self._stats["rejected"] += 1
                raise QueueFullError(
                    "queue full (%d)" % self.max_queue)
            self._seq += 1
            task_id = "%s-%d" % (self.name, self._seq)
            handle = TaskHandle(
                task_id, fn, args, kwargs, request_id=request_id,
                generation=generation, token=cancel_token, on_done=on_done,
                on_error=on_error, on_cancelled=on_cancelled)
            handle.request_key = str(request_id) if request_id is not None \
                else task_id
            handle.submitted_at = self.now()
            self._queue.append(handle)
            self._handles[task_id] = handle
            self._by_request[handle.request_key] = handle
            self._stats["submitted"] += 1
            self._prune_terminal()
            self._cond.notify()
        return handle

    # -- cancellation ----------------------------------------------------
    def cancel(self, request_id, reason=""):
        """Cancel a tracked task.

        Returns ``"queued"`` when it was removed before running, ``"running"``
        when the token was set for cooperative stop, else ``None``.
        """
        with self._cond:
            handle = self._by_request.get(str(request_id))
            if handle is None or handle.state in _TERMINAL_STATES:
                return None
            if handle.state == QUEUED:
                if handle in self._queue:
                    self._queue.remove(handle)
                handle.state = CANCELLED
                handle.cancel_reason = str(reason or "cancelled_queued")
                handle.finished_at = self.now()
                self._stats["cancelled"] += 1
                self._stats["cancelled_queued"] += 1
                self._register_terminal(handle)
                self._cond.notify_all()
                return "queued"
            handle.cancel(reason)
            return "running"

    def cancel_all(self, reason=""):
        with self._cond:
            pending = [h for h in self._handles.values()
                       if h.state not in _TERMINAL_STATES]
        for handle in pending:
            self.cancel(handle.request_id or handle.task_id, reason=reason)

    # -- worker loop -----------------------------------------------------
    def _worker_loop(self):
        while True:
            with self._cond:
                while not self._queue and not self._stopping:
                    self._cond.wait()
                if not self._queue:
                    return  # stopping and drained
                handle = self._queue.popleft()
                if handle.state == CANCELLED:
                    continue
                handle.state = RUNNING
                handle.started_at = self.now()
            self._run(handle)

    def _run(self, handle):
        try:
            if handle.token.cancelled:
                self._settle_cancelled(handle)
                return
            result = handle._fn(*handle._args, **handle._kwargs)
            if handle.token.cancelled:
                # Late result from cancelled work: suppress the value entirely.
                self._settle_cancelled(handle, late=True)
                return
            with self._cond:
                handle.result = result
                handle.state = DONE
                handle.finished_at = self.now()
                self._stats["completed"] += 1
                self._register_terminal(handle)
            self._dispatch(handle._on_done, result, handle)
        except TaskCancelled:
            self._settle_cancelled(handle)
        except BaseException as exc:  # noqa: BLE001 - a job must never kill us
            with self._cond:
                handle.error = exc
                handle.state = FAILED
                handle.finished_at = self.now()
                self._stats["failed"] += 1
                self._register_terminal(handle)
            self._dispatch(handle._on_error, exc, handle)

    def _settle_cancelled(self, handle, late=False):
        with self._cond:
            handle.state = CANCELLED
            if not handle.cancel_reason:
                handle.cancel_reason = "late_result" if late else "cancelled"
            handle.finished_at = self.now()
            self._stats["cancelled"] += 1
            self._register_terminal(handle)
        self._dispatch(handle._on_cancelled, None, handle)

    def _dispatch(self, callback, value, handle):
        if callback is None:
            return
        with self._cond:
            if self._stopping:
                self._stats["dispatch_skipped"] += 1
                return
        try:
            self._dispatcher(lambda: callback(value, handle))
        except Exception:  # noqa: BLE001
            with self._cond:
                self._stats["dispatch_errors"] += 1

    # -- retention -------------------------------------------------------
    def _register_terminal(self, handle):
        """Record a terminal handle (caller must hold ``self._cond``)."""
        if handle.terminal_registered:
            return
        handle.terminal_registered = True
        self._terminal_order.append(handle)
        if self._release_terminal_refs:
            self._release_refs(handle)
        self._prune_terminal()

    def _release_refs(self, handle):
        handle._fn = None
        handle._args = None
        handle._kwargs = None
        handle.released = True
        self._stats["released"] += 1

    def _prune_terminal(self):
        """Drop oldest terminal handles past ``max_tracked`` (lock held)."""
        while len(self._handles) > self.max_tracked and self._terminal_order:
            handle = self._terminal_order.popleft()
            if not handle.terminal:
                self._terminal_order.appendleft(handle)
                break
            if self._handles.pop(handle.task_id, None) is not None and \
               self._by_request.get(handle.request_key) is handle:
                self._by_request.pop(handle.request_key, None)
            self._stats["evicted"] += 1

    # -- waiting / shutdown ---------------------------------------------
    def wait(self, request_id, timeout=5.0):
        """Block until a request's handle is terminal (test/join helper)."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        handle = self.handle(request_id)
        if handle is None:
            return None
        while not handle.terminal:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.005, remaining))
        return handle

    def shutdown(self, *, wait=True, timeout=10.0):
        """Deterministically stop: cancel queued work, reject new work, join.

        Returns a dict (the previous return was ``None``; existing callers
        never inspect it) with:

        - ``leftover_workers``: workers still alive after the join attempt
          (a worker blocked inside an uninterruptible job stays alive);
        - ``join_timeout``: True when the join deadline expired with at least
          one worker still alive, False once every worker has drained;
        - ``elapsed``: wall seconds spent inside this call;
        - ``workers``: the total worker count.

        Never hangs: every ``join`` carries only the remaining deadline.
        Queued work is cancelled, running work is token-cancelled, and
        ``submit`` keeps rejecting after shutdown. An already-shut-down
        executor returns the current leftover state immediately.
        """
        with self._cond:
            if not self._shutdown_done:
                self._stopping = True
                for handle in list(self._queue):
                    handle.state = CANCELLED
                    if not handle.cancel_reason:
                        handle.cancel_reason = "cancelled_shutdown"
                    handle.finished_at = self.now()
                    self._stats["cancelled"] += 1
                    self._stats["cancelled_queued"] += 1
                    self._register_terminal(handle)
                self._queue.clear()
                for handle in self._handles.values():
                    if handle.state not in _TERMINAL_STATES:
                        handle.token.cancel()
                self._cond.notify_all()
        started = time.monotonic()
        if wait:
            deadline = started + max(0.0, float(timeout))
            for worker in self._workers:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                worker.join(max(0.0, remaining))
        with self._cond:
            self._shutdown_done = True
            leftover = sum(1 for w in self._workers if w.is_alive())
        return {
            "leftover_workers": leftover,
            "join_timeout": bool(wait and leftover > 0),
            "elapsed": time.monotonic() - started,
            "workers": len(self._workers),
        }

    def alive_workers(self):
        return sum(1 for w in self._workers if w.is_alive())

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.shutdown()
        return False
