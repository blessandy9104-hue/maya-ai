"""Bounded, cancellable owner of the ``maya_chat.py`` subprocess.

The Qt controller speaks to Maya's chat CLI through a persistent child process
(one line written to stdin, protocol lines read from stdout).  This module wraps
that child in an explicit lifecycle so the UI can keep it off its own thread and
so every turn has a correlation id, a generation, a deadline and exactly one
terminal outcome.

Guarantees:

* **Serialized turns** -- the child is a single blocking loop, so at most one
  turn is in flight; further turns wait in a bounded queue.
* **Bounded lifetime** -- an idle TTL and a hard maximum lifetime terminate the
  child when it is not needed, and the queue/worker count is finite.
* **Cooperative then forced termination** -- cancel/close first ask the child to
  leave (stdin close + grace) and only then escalate to ``terminate``/``kill``.
* **Stale safety** -- every stdout line carries the active turn's correlation id
  and generation; lines for a cancelled/superseded/timed-out turn are dropped.
* **Explicit outcomes** -- normal completion, cancellation, timeout, launch
  failure, crash, nonzero exit, malformed output and partial output are distinct;
  a reply is only reported as ``completed`` when the child actually produced one.
* **No leaks** -- reader/stderr/writer threads are owned here, joined on close,
  and the child is always reaped.

The module is intentionally UI-agnostic and pure-stdlib; it never writes files
and never touches trust artifacts.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

# -- terminal outcomes -------------------------------------------------------
COMPLETED = "completed"
CANCELLED = "cancelled"
TIMEOUT = "timeout"
LAUNCH_FAILED = "launch_failed"
CRASHED = "crashed"
NONZERO_EXIT = "nonzero_exit"
MALFORMED = "malformed"
PARTIAL = "partial"
CLOSED = "closed"
QUEUE_FULL = "queue_full"

TERMINAL_OUTCOMES = frozenset({
    COMPLETED, CANCELLED, TIMEOUT, LAUNCH_FAILED, CRASHED, NONZERO_EXIT,
    MALFORMED, PARTIAL, CLOSED, QUEUE_FULL,
})

REPLY_PREFIX = "Maya: "
GOODBYE_LINE = "Maya: Goodbye."
_FACE = "[face] "
_SEMANTIC = "[semantic] "
_PENDING = "[pending] "


def _noop(*_args, **_kwargs):
    return None


def _now():
    return time.monotonic()


class _Turn:
    __slots__ = (
        "request_id", "generation", "text", "timeout", "on_line", "on_done",
        "state", "reason", "reply", "returncode", "created_at", "deadline",
        "done", "delivered_lines", "reply_seen",
    )

    def __init__(self, request_id, generation, text, timeout, on_line, on_done):
        self.request_id = request_id
        self.generation = generation
        self.text = text
        self.timeout = timeout
        self.on_line = on_line
        self.on_done = on_done
        self.state = "queued"
        self.reason = ""
        self.reply = None
        self.returncode = None
        self.created_at = _now()
        self.deadline = None
        self.done = threading.Event()
        self.delivered_lines = 0
        self.reply_seen = False

    def meta(self):
        return {"request_id": self.request_id, "generation": self.generation}


class ChatProcessManager:
    """Own one ``maya_chat.py`` child with a bounded, cancellable turn queue."""

    def __init__(self, *, script=None, python=None, cwd=None, env=None,
                 idle_ttl=300.0, max_lifetime=1800.0, turn_timeout=120.0,
                 start_timeout=15.0, grace=2.0, kill_grace=1.0, max_queue=32,
                 poll=0.05, clock=_now, on_line=None, on_idle_line=None,
                 on_stderr=None, on_exit=None, name="maya-chat"):
        self._script = str(script or os.environ.get("MAYA_CHAT_SCRIPT")
                           or (_ROOT / "maya_chat.py"))
        self._python = str(python or sys.executable)
        self._cwd = str(cwd or _ROOT)
        self._env = dict(env) if env is not None else {
            **os.environ, "MAYA_FACE_LINES": "1"}
        self.idle_ttl = float(idle_ttl)
        self.max_lifetime = float(max_lifetime)
        self.turn_timeout = float(turn_timeout)
        self.start_timeout = float(start_timeout)
        self.grace = float(grace)
        self.kill_grace = float(kill_grace)
        self.max_queue = int(max_queue)
        self._poll = float(poll)
        self._clock = clock if callable(clock) else _now
        self._on_line = on_line or _noop
        self._on_idle_line = on_idle_line or _noop
        self._on_stderr = on_stderr or _noop
        self._on_exit = on_exit or _noop
        self.name = name

        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._queue = deque()
        self._turns = {}
        self._active = None
        self._proc = None
        self._process_started = None
        self._last_activity = None
        self._prelude = False
        self._closed = False
        self._threads = []
        self._launch_error = ""
        self._stats = {
            "submitted": 0, "completed": 0, "cancelled": 0, "timeout": 0,
            "failed": 0, "rejected": 0, "launched": 0, "terminated": 0,
            "killed": 0, "stale_suppressed": 0, "exited": 0, "duplicate": 0,
        }
        self._writer = threading.Thread(target=self._writer_loop,
                                        name=self.name + "-writer", daemon=True)

    # -- introspection ----------------------------------------------------
    @property
    def proc(self):
        return self._proc

    def pid(self):
        proc = self._proc
        return proc.pid if proc is not None and proc.poll() is None else None

    def alive(self):
        proc = self._proc
        return proc is not None and proc.poll() is None

    def stats(self):
        with self._lock:
            data = dict(self._stats)
            data["queued"] = len(self._queue)
            data["active"] = (self._active.request_id
                              if self._active is not None
                              and not self._active.done.is_set() else None)
            data["alive"] = self.alive()
            data["closed"] = self._closed
            return data

    def queued_count(self):
        with self._lock:
            return len(self._queue)

    def child_alive(self):
        """Number of live child processes owned here (0 or 1)."""
        return 1 if self.alive() else 0

    def threads_alive(self):
        workers = list(self._threads) + [self._writer]
        return sum(1 for t in workers if t.is_alive())

    # -- lifecycle --------------------------------------------------------
    def start(self):
        """Ensure the child is running; returns the live ``Popen`` or None."""
        with self._lock:
            if self._closed:
                return None
            proc = self._ensure_process_locked()
            if proc is not None:
                self._ensure_writer_locked()
            return proc

    def submit(self, text, *, request_id, generation=0, timeout=None,
               on_line=None, on_done=None):
        """Queue one turn.  Never blocks on the child; safe from any thread."""
        with self._lock:
            if self._closed:
                self._reject(request_id, generation, CLOSED, on_done)
                return {"request_id": str(request_id), "accepted": False,
                        "error": CLOSED}
            existing = self._turns.get(str(request_id))
            if existing is not None and not existing.done.is_set():
                # The original turn still owns this correlation id; rejecting
                # the duplicate must not deliver a competing result under it.
                self._stats["duplicate"] += 1
                self._stats["rejected"] += 1
                return {"request_id": str(request_id), "accepted": False,
                        "error": "duplicate", "terminal": False}
            if len(self._queue) >= self.max_queue:
                self._reject(request_id, generation, QUEUE_FULL, on_done)
                return {"request_id": str(request_id), "accepted": False,
                        "error": QUEUE_FULL}
            self._prune_locked()
            self._stats["submitted"] += 1
            turn = _Turn(str(request_id), int(generation), str(text),
                         float(self.turn_timeout if timeout is None else timeout),
                         on_line or self._on_line, on_done)
            self._turns[turn.request_id] = turn
            self._queue.append(turn.request_id)
            self._ensure_writer_locked()
            self._cv.notify_all()
            return {"request_id": turn.request_id, "accepted": True,
                    "generation": turn.generation}

    def turn(self, request_id):
        with self._lock:
            return self._turns.get(str(request_id))

    def cancel(self, request_id, *, reason="cancelled_by_user"):
        """Cancel a queued or running turn; returns ``queued``/``running``/None."""
        rid = str(request_id)
        running = False
        with self._lock:
            turn = self._turns.get(rid)
            if turn is None or turn.done.is_set():
                return None
            if turn is self._active and turn.state == "running":
                running = True
                self._finalize_locked(turn, CANCELLED,
                                      reason=reason or "cancelled_by_user")
            else:
                try:
                    self._queue.remove(rid)
                except ValueError:
                    pass
                self._finalize_locked(turn, CANCELLED,
                                      reason="cancelled_before_execution")
        if running:
            self._terminate(self.grace)
        return "running" if running else "queued"

    def close(self, *, grace=None):
        """Stop the child and drain every turn; idempotent."""
        wait = self.grace if grace is None else float(grace)
        with self._lock:
            if self._closed:
                return
            self._closed = True
            queued = [self._turns[rid] for rid in list(self._queue)
                      if rid in self._turns]
            self._queue.clear()
            active = self._active
            self._cv.notify_all()
        for turn in queued:
            self._finalize(turn, CANCELLED, reason="closed_before_execution")
        if active is not None and not active.done.is_set():
            self._finalize(active, CANCELLED, reason="closed_during_execution")
        self._terminate(wait)
        self._join_threads()
        with self._lock:
            self._active = None
            self._turns.clear()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.close()

    # -- internals --------------------------------------------------------
    def _reject(self, request_id, generation, outcome, on_done):
        self._stats["rejected"] += 1
        if callable(on_done):
            try:
                on_done({"outcome": outcome, "reason": outcome,
                         "request_id": str(request_id),
                         "generation": int(generation),
                         "terminal": outcome != "duplicate"})
            except Exception:  # noqa: BLE001 - a callback never breaks us
                pass

    def _prune_locked(self, keep=64):
        if len(self._turns) <= keep:
            return
        terminal = [rid for rid, t in self._turns.items()
                    if t.done.is_set() and t is not self._active]
        terminal.sort(key=lambda rid: self._turns[rid].created_at)
        for rid in terminal[:len(self._turns) - keep]:
            self._turns.pop(rid, None)

    def _finalize_locked(self, turn, outcome, *, reason="", reply=None,
                         returncode=None):
        if turn.done.is_set():
            return
        turn.state = outcome
        turn.reason = str(reason)
        if reply is not None:
            turn.reply = reply
        if returncode is not None:
            turn.returncode = returncode
        turn.done.set()
        counter = {COMPLETED: "completed", CANCELLED: "cancelled",
                   TIMEOUT: "timeout", QUEUE_FULL: "rejected"}.get(outcome)
        if counter is not None and counter in self._stats:
            self._stats[counter] += 1
        if outcome not in (COMPLETED, CANCELLED):
            self._stats["failed"] += 1
        on_done = turn.on_done
        if callable(on_done):
            try:
                on_done({"outcome": outcome, "reason": turn.reason,
                         "reply": turn.reply,
                         "request_id": turn.request_id,
                         "generation": turn.generation,
                         "returncode": turn.returncode, "terminal": True})
            except Exception:  # noqa: BLE001
                pass
        self._cv.notify_all()

    def _finalize(self, turn, outcome, *, reason="", reply=None,
                  returncode=None):
        with self._lock:
            self._finalize_locked(turn, outcome, reason=reason, reply=reply,
                                  returncode=returncode)

    def _ensure_writer_locked(self):
        if self._closed or self._writer.is_alive():
            return
        self._writer = threading.Thread(target=self._writer_loop,
                                        name=self.name + "-writer", daemon=True)
        self._writer.start()

    def _ensure_process_locked(self):
        proc = self._proc
        if proc is not None and proc.poll() is None:
            return proc
        self._proc = None
        self._threads = [t for t in self._threads if t.is_alive()]
        try:
            proc = subprocess.Popen(
                [self._python, "-u", self._script],
                env=self._env, cwd=self._cwd, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", bufsize=1,
            )
        except Exception as exc:  # noqa: BLE001 - launch failure is an outcome
            self._launch_error = "%s: %s" % (type(exc).__name__, exc)
            self._proc = None
            return None
        self._proc = proc
        self._process_started = self._clock()
        self._last_activity = self._process_started
        self._prelude = True
        self._stats["launched"] += 1
        reader = threading.Thread(target=self._reader_loop, args=(proc,),
                                  name=self.name + "-reader", daemon=True)
        err = threading.Thread(target=self._stderr_loop, args=(proc,),
                               name=self.name + "-stderr", daemon=True)
        reader.start()
        err.start()
        self._threads.extend([reader, err])
        return proc

    def _writer_loop(self):
        while True:
            turn = None
            with self._lock:
                if self._closed:
                    return
                if not self._queue:
                    self._enforce_lifetime_locked()
                    self._cv.wait(timeout=self._poll)
                    continue
                rid = self._queue.popleft()
                turn = self._turns.get(rid)
                if turn is None or turn.done.is_set():
                    continue
                proc = self._ensure_process_locked()
                if proc is None:
                    self._finalize_locked(
                        turn, LAUNCH_FAILED,
                        reason=self._launch_error or "launch_failed")
                    continue
                self._active = turn
                turn.state = "running"
                turn.deadline = self._clock() + turn.timeout
                self._last_activity = self._clock()
                try:
                    proc.stdin.write(turn.text + "\n")
                    proc.stdin.flush()
                except Exception as exc:  # noqa: BLE001 - pipe died mid-write
                    self._finalize_locked(
                        turn, CRASHED,
                        reason="stdin_error:%s" % type(exc).__name__)
                    self._handle_process_gone_locked(proc)
                    self._active = None
                    continue
            finished = turn.done.wait(turn.timeout)
            if not finished:
                self._finalize(turn, TIMEOUT, reason="turn_timeout")
                # the child is still blocked on this turn; free it (graceful
                # stdin close first, then bounded escalation) so the next turn
                # starts from a clean process.
                self._terminate(self.grace)
            with self._lock:
                self._active = None
                self._last_activity = self._clock()
                if not self.alive():
                    self._cv.notify_all()

    def _enforce_lifetime_locked(self):
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        now = self._clock()
        if (self.max_lifetime > 0 and self._process_started is not None
                and now - self._process_started > self.max_lifetime):
            self._terminate(self.grace)
            return
        if (self.idle_ttl > 0 and self._last_activity is not None
                and now - self._last_activity > self.idle_ttl):
            self._terminate(self.grace)

    def _reader_loop(self, proc):
        try:
            for line in proc.stdout:
                self._handle_line(proc, line)
        except Exception:  # noqa: BLE001 - a broken pipe ends the reader
            pass
        with self._lock:
            self._handle_process_gone_locked(proc)

    def _stderr_loop(self, proc):
        try:
            for line in proc.stderr:
                text = line.rstrip("\n")
                if text:
                    try:
                        self._on_stderr(text)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    def _handle_line(self, proc, line):
        stripped = line.strip()
        with self._lock:
            turn = self._active
            stale = turn is None or turn.done.is_set()
            if not stale and turn.state != "running":
                stale = True

            if not stale and line.startswith(REPLY_PREFIX) \
                    and stripped != GOODBYE_LINE:
                self._prelude = False
                if not stripped[len(REPLY_PREFIX):].strip():
                    self._finalize_locked(turn, MALFORMED,
                                          reason="empty_reply")
                else:
                    turn.reply_seen = True
                    self._deliver_locked(turn, "reply", line)
                    self._finalize_locked(turn, COMPLETED, reply=line,
                                          reason="subprocess_reply")
                return
            kind = None
            if line.startswith(_FACE):
                kind = "face"
            elif line.startswith(_SEMANTIC):
                kind = "semantic"
            elif line.startswith(_PENDING):
                kind = "pending"
            if kind is not None:
                if stale:
                    self._stats["stale_suppressed"] += 1
                    return
                self._prelude = False
                self._deliver_locked(turn, kind, line)
                return
            # Plain text: startup banner (prelude) and any unsolicited line an
            # idle process prints go to the idle channel; only text seen after
            # the process has emitted protocol traffic belongs to the turn.
            if stale or self._prelude:
                try:
                    self._on_idle_line(line)
                except Exception:  # noqa: BLE001
                    pass
            else:
                self._deliver_locked(turn, "text", line)

    def _deliver_locked(self, turn, kind, line):
        turn.delivered_lines += 1
        callback = turn.on_line
        if callable(callback):
            try:
                callback(kind, line, turn.meta())
            except Exception:  # noqa: BLE001 - a line callback never breaks us
                pass

    def _handle_process_gone_locked(self, proc):
        if self._proc is not proc:
            return
        self._proc = None
        self._stats["exited"] += 1
        try:
            returncode = proc.poll()
            if returncode is None:
                returncode = proc.wait(timeout=self.kill_grace)
        except Exception:  # noqa: BLE001
            returncode = None
        active = self._active
        if active is not None and not active.done.is_set() \
                and active.state == "running":
            if active.reply_seen:
                outcome, reason = CRASHED, "exited_after_reply"
            elif returncode not in (None, 0):
                outcome, reason = NONZERO_EXIT, "exit_%s" % returncode
            elif returncode == 0:
                outcome, reason = PARTIAL, "no_reply"
            else:
                outcome, reason = CRASHED, "exited_without_reply"
            self._finalize_locked(active, outcome, reason=reason,
                                  returncode=returncode)
        try:
            self._on_exit(returncode)
        except Exception:  # noqa: BLE001
            pass
        self._cv.notify_all()

    def _terminate(self, grace):
        """Cooperative stdin close, then bounded escalation to kill."""
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is not None:
            return
        self._stats["terminated"] += 1
        try:
            if proc.stdin is not None and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=max(0.0, grace))
            return
        except Exception:  # noqa: BLE001 - still running; escalate
            pass
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=max(0.0, self.kill_grace))
            return
        except Exception:  # noqa: BLE001
            pass
        self._stats["killed"] += 1
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=max(0.0, self.kill_grace))
        except Exception:  # noqa: BLE001
            pass

    def _join_threads(self, timeout=3.0):
        workers = list(self._threads) + [self._writer]
        for thread in workers:
            if thread is threading.current_thread() or not thread.is_alive():
                continue
            thread.join(timeout=timeout)
        self._threads = [t for t in self._threads if t.is_alive()]


__all__ = [
    "ChatProcessManager", "COMPLETED", "CANCELLED", "TIMEOUT",
    "LAUNCH_FAILED", "CRASHED", "NONZERO_EXIT", "MALFORMED", "PARTIAL",
    "CLOSED", "QUEUE_FULL", "TERMINAL_OUTCOMES", "REPLY_PREFIX",
]
