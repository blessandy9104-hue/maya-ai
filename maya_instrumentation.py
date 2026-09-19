"""Read-only performance instrumentation for Maya (opt-in, bounded, content-free).

This module measures the *shape* of a turn -- phase timings, sizes, counters and
an ordering trace -- without ever observing message content, secrets, credentials
or identifying user data. Design guarantees:

* **Opt-in.** Off unless ``MAYA_INSTRUMENT`` is truthy or a caller explicitly
  calls :func:`enable`. Importing this module has no side effects.
* **Read-only.** Nothing here opens a file for writing, touches the network, or
  mutates Maya's state (trust, identity, memory, registries). It cannot change
  an orchestration outcome because every hook only reads values that the caller
  already computed.
* **Bounded.** Events, traces and terminal records live in fixed-size buffers;
  recording is an O(1) append under a short lock and performs no IO, so it can
  never block the UI thread on disk. Runtime flow counters are merged into a
  bounded key map (max ``MAX_RUNTIME_KEYS``) via :func:`report_runtime_counts`;
  that call is summary-only and never appends an event, so no caller can turn
  per-interaction work into per-interaction events.
* **Deterministic when asked.** The clock is injectable and defaults to
  :func:`time.perf_counter` (monotonic). Tests inject a counter/failing clock.

Correlation IDs are local and non-identifying: they are either Maya's own
``req-<12hex>`` request ids (derived from session + sequence, never from
message text) or a monotonically increasing ``op-######`` label this module
mints itself. Message content is never accepted by any recording entry point
(the ``meta`` mapping is allow-listed by key and truncated).
"""
from __future__ import annotations

import collections
import json
import os
import platform
import re
import sys
import threading
import time

_TOKEN_RE = re.compile(r"[^A-Za-z0-9._:\-]")

ENV_FLAG = "MAYA_INSTRUMENT"
DEFAULT_MAX_EVENTS = 512
DEFAULT_MAX_TRACES = 128
DEFAULT_MAX_TERMINALS = 128
DEFAULT_MAX_RUNTIME_KEYS = 64
_META_KEY_LIMIT = 16
_META_KEY_CHARS = 32
_META_STR_CHARS = 48

#: Upper bound on distinct runtime flow counter keys merged by
#: :func:`report_runtime_counts`. New keys past this cap are ignored, so the
#: aggregate stays bounded no matter how many callers report into it.
MAX_RUNTIME_KEYS = DEFAULT_MAX_RUNTIME_KEYS

#: Only these structural keys may appear in ``meta``. A caller can never smuggle
#: message content through meta: unknown keys are dropped, and values are
#: truncated. No reason/detail/text key is allowed.
META_ALLOWED = frozenset({
    "phase", "kind", "category", "source", "status", "state", "from", "to",
    "action", "attempt", "verified", "unchanged", "budget", "depth",
    "outcome_class", "item_count", "open_count", "total_count", "error",
    "frame", "interval_ms", "revision",
})

#: Startup phases measured by the Qt application (see ``app.py``).
STARTUP_PHASES = ("bridge_ready", "qml_engine_load", "main_window",
                  "first_frame", "first_input")

_settings = threading.RLock()
_LOCK = threading.RLock()
_ENABLED = False
_CLOCK = time.perf_counter
_MAX_EVENTS = DEFAULT_MAX_EVENTS
_MAX_TRACES = DEFAULT_MAX_TRACES
_MAX_TERMINALS = DEFAULT_MAX_TERMINALS
_SEQ = 0
_EVENTS = collections.deque(maxlen=DEFAULT_MAX_EVENTS)
_COUNTERS = collections.Counter()
#: Bounded runtime flow-key aggregate (``report_runtime_counts``). Purely
#: numeric; capped at MAX_RUNTIME_KEYS keys.
_RUNTIME_COUNTERS = {}
#: Last-seen metadata for that aggregate: ``phase`` (sanitized token), the
#: number of merge updates, and the clock reading of the latest update.
_RUNTIME_META = {"phase": None, "updates": 0, "last_at": 0.0}
_STARTUP = {}
_TRACES = collections.OrderedDict()
_TERMINALS = collections.OrderedDict()
_PROCESS_START = time.perf_counter()


# ----------------------------------------------------------------------
# enabling / configuration
# ----------------------------------------------------------------------

def _env_enabled():
    return str(os.environ.get(ENV_FLAG, "")).strip().lower() in (
        "1", "true", "yes", "on")


def is_enabled():
    """True when instrumentation is active (explicitly or via the env flag)."""
    return _ENABLED or _env_enabled()


def enable(clock=None, *, max_events=None, max_traces=None):
    """Turn instrumentation on (used by tests/benchmarks). Never raises."""
    global _ENABLED
    with _settings:
        _ENABLED = True
        if clock is not None:
            _set_clock(clock)
        if max_events is not None:
            _resize(max_events=max_events)
        if max_traces is not None:
            _resize(max_traces=max_traces)
    return is_enabled()


def disable():
    """Turn explicit instrumentation off (the env flag still wins)."""
    global _ENABLED
    with _settings:
        _ENABLED = False
    return _ENABLED


def configure(*, clock=None, max_events=None, max_traces=None):
    """Adjust clock/buffer sizes without changing the enabled state."""
    with _settings:
        if clock is not None:
            _set_clock(clock)
        if max_events is not None or max_traces is not None:
            _resize(max_events=max_events, max_traces=max_traces)
    return is_enabled()


def _set_clock(clock):
    global _CLOCK
    _CLOCK = clock if callable(clock) else time.perf_counter


def _resize(*, max_events=None, max_traces=None):
    global _MAX_EVENTS, _MAX_TRACES, _MAX_TERMINALS, _EVENTS
    if max_events is not None:
        _MAX_EVENTS = max(1, int(max_events))
        _EVENTS = collections.deque(_EVENTS, maxlen=_MAX_EVENTS)
    if max_traces is not None:
        _MAX_TRACES = max(1, int(max_traces))
        _MAX_TERMINALS = _MAX_TRACES
        while len(_TRACES) > _MAX_TRACES:
            _TRACES.popitem(last=False)
        while len(_TERMINALS) > _MAX_TERMINALS:
            _TERMINALS.popitem(last=False)


def reset():
    """Clear all buffers/counters. Keeps the enabled state and clock."""
    with _LOCK:
        _EVENTS.clear()
        _COUNTERS.clear()
        _STARTUP.clear()
        _TRACES.clear()
        _TERMINALS.clear()
        _RUNTIME_COUNTERS.clear()
        _RUNTIME_META.update({"phase": None, "updates": 0, "last_at": 0.0})


# ----------------------------------------------------------------------
# clock / durations
# ----------------------------------------------------------------------

def now():
    """Current clock reading, or ``None`` if the clock is unavailable."""
    try:
        return float(_CLOCK())
    except Exception:  # noqa: BLE001 - a broken clock must never propagate
        return None


def process_start():
    return _PROCESS_START


def elapsed_ms():
    """Milliseconds since this module was imported (process/module start)."""
    return duration_ms(_PROCESS_START, now())


def duration_ms(start, end):
    """Non-negative millisecond duration, or ``None`` if it cannot be trusted.

    Returns ``None`` when either endpoint is missing, when the values are not
    numeric, or when the clock went backwards (a non-monotonic reading is never
    reported as a bogus negative duration).
    """
    try:
        if start is None or end is None:
            return None
        delta = (float(end) - float(start)) * 1000.0
        if delta < 0:
            return None
        return round(delta, 4)
    except (TypeError, ValueError, OverflowError):
        return None


# ----------------------------------------------------------------------
# recording
# ----------------------------------------------------------------------

def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _token(value, limit):
    """A short opaque token: strips whitespace/punctuation so a value can never
    carry free-form content, and returns ``None`` when nothing is left."""
    try:
        cleaned = _TOKEN_RE.sub("", str(value))[:limit]
        return cleaned or None
    except Exception:  # noqa: BLE001
        return None


def _new_id(prefix):
    global _SEQ
    with _LOCK:
        _SEQ += 1
        seq = _SEQ
    return "%s-%06d" % (prefix, seq)


def _sanitize_meta(meta):
    if not isinstance(meta, dict):
        return None
    clean = {}
    for key, value in list(meta.items())[:_META_KEY_LIMIT]:
        name = str(key)[:_META_KEY_CHARS]
        if name not in META_ALLOWED:
            continue  # unknown/content-bearing key: dropped, never recorded
        if isinstance(value, bool) or isinstance(value, (int, float)):
            clean[name] = value
        elif value is None:
            clean[name] = None
        elif isinstance(value, str):
            clean[name] = value[:_META_STR_CHARS]
        # every other type is dropped
    return clean or None


def record(event, *, stage=None, request_id=None, outcome=None,
           duration_ms=None, size_bytes=None, count=None, phase=None,
           meta=None):
    """Append one content-free event. Returns the stored dict or ``None``.

    A no-op (returns ``None``) when disabled. Never raises, never blocks on IO.
    """
    if not is_enabled():
        return None
    try:
        name = _token(event, 48) or "event"
        entry = {"event": name}
        for field, value, limit in (("stage", stage, 32), ("phase", phase, 32),
                                    ("request_id", request_id, 32),
                                    ("outcome", outcome, 24)):
            token = _token(value, limit) if value is not None else None
            if token is not None:
                entry[field] = token
        for name, value in (("duration_ms", duration_ms),
                            ("size_bytes", size_bytes), ("count", count)):
            number = _num(value)
            if number is not None:
                entry[name] = number
        clean = _sanitize_meta(meta)
        if clean:
            entry["meta"] = clean
        with _LOCK:
            _EVENTS.append(entry)
        return dict(entry)
    except Exception:  # noqa: BLE001 - instrumentation never breaks a caller
        return None


class _NullSpan:
    __slots__ = ()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def finish(self, error=None):
        return None


_NULL_SPAN = _NullSpan()


class Span:
    """A no-op-when-disabled timing scope; records on ``finish``/``__exit__``."""

    __slots__ = ("_event", "_fields", "_start", "_ended")

    def __init__(self, event, fields):
        self._event = event
        self._fields = fields or {}
        self._start = now()
        self._ended = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.finish(error=(exc_type.__name__ if exc_type else None))
        return False  # never swallow the caller's exception

    def finish(self, error=None):
        if self._ended:
            return None
        self._ended = True
        fields = dict(self._fields)
        if error is not None:
            existing = fields.get("meta") or {}
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged["error"] = str(error)
            fields["meta"] = merged
        return record(self._event, duration_ms=duration_ms(self._start, now()),
                      **fields)


def span(event, **fields):
    """Time a scope; returns a :class:`Span` (or a shared null scope)."""
    if not is_enabled():
        return _NULL_SPAN
    return Span(event, fields)


# ----------------------------------------------------------------------
# startup
# ----------------------------------------------------------------------

def mark_startup(phase, *, duration_ms=None, at=None):
    """Record one startup phase timing (idempotent per phase call site)."""
    if not is_enabled():
        return None
    try:
        value = _num(duration_ms)
        if value is None:
            base = _PROCESS_START if at is None else at
            value = duration_ms_between(base, now())
        entry = {"duration_ms": value}
        with _LOCK:
            _STARTUP[str(phase)[:32]] = entry
        record("startup", phase=phase, duration_ms=value)
        return dict(entry)
    except Exception:  # noqa: BLE001
        return None


def duration_ms_between(start, end):
    return duration_ms(start, end)


def startup_report():
    with _LOCK:
        return {k: dict(v) for k, v in _STARTUP.items()}


# ----------------------------------------------------------------------
# request lifecycle
# ----------------------------------------------------------------------

_LIFECYCLE_SUCCESSORS = {
    "planning": ("validating", "executing", "awaiting_approval", "awaiting_user",
                 "cancelled", "refused", "error", "unavailable"),
    "validating": ("executing", "awaiting_approval", "awaiting_user",
                   "cancelled", "refused", "error"),
    "executing": ("verifying", "completed", "unavailable", "error", "refused",
                  "timeout", "cancelled"),
    "awaiting_approval": ("executing", "denied", "cancelled", "timeout",
                          "error"),
}


def trace_request(request, *, phase="submit"):
    """Derive a content-free lifecycle trace from a request dict.

    Only reads ``request`` (state, timestamps, counts); it never mutates the
    request and never records the request text. Returns the trace dict or None.
    """
    if not is_enabled() or not isinstance(request, dict):
        return None
    try:
        history = [entry for entry in (request.get("history") or [])
                   if isinstance(entry, dict)]
        ordered = [(str(entry.get("state")), entry.get("at"))
                   for entry in history]
        created = request.get("created_at")
        updated = request.get("updated_at")
        outcome = request.get("outcome")
        terminal = bool(request.get("terminal"))
        request_id = (_token(request.get("request_id"), 32)
                      or _new_id("op"))

        def phase_ms(state):
            tail = set(_LIFECYCLE_SUCCESSORS.get(state, ()))
            for index, (current, at) in enumerate(ordered):
                if current != state:
                    continue
                for later, later_at in ordered[index + 1:]:
                    if later in tail or later == outcome:
                        return duration_ms(at, later_at)
                return duration_ms(at, updated)
            return None

        trace = {
            "request_id": request_id,
            "phase": _token(phase, 16),
            "state": _token(request.get("state"), 24),
            "outcome": _token(outcome, 24) if outcome else None,
            "outcome_class": (_token(request.get("outcome_class"), 32)
                              if request.get("outcome_class") else None),
            "terminal": terminal,
            "attempts": int(request.get("attempts") or 0),
            "duplicate": bool(request.get("duplicate")),
            "planning_ms": phase_ms("planning"),
            "validation_ms": phase_ms("validating"),
            "execution_ms": phase_ms("executing"),
            "approval_wait_ms": phase_ms("awaiting_approval"),
            "total_ms": duration_ms(created, updated),
        }

        # Correlation is scoped to the concrete request: orchestrator instances
        # number requests independently, so the same id can legitimately name a
        # different request later. Keying on (id, created_at) keeps distinct
        # requests apart and makes a conflicting terminal outcome a true
        # violation of the *same* request.
        trace_key = (request_id, created)
        with _LOCK:
            _TRACES[trace_key] = trace
            while len(_TRACES) > _MAX_TRACES:
                _TRACES.popitem(last=False)
            if trace["duplicate"]:
                _COUNTERS["duplicate_requests"] += 1
            if trace["attempts"] > 1:
                _COUNTERS["retries"] += 1
            if trace["outcome"] == "timeout":
                _COUNTERS["timeouts"] += 1
            if terminal and trace["outcome"]:
                previous = _TERMINALS.get(trace_key)
                if previous is not None and previous != trace["outcome"]:
                    _COUNTERS["terminal_outcome_violations"] += 1
                    _EVENTS.append({
                        "event": "terminal_outcome_violation",
                        "request_id": request_id,
                        "outcome": trace["outcome"],
                    })
                else:
                    _TERMINALS[trace_key] = trace["outcome"]
                    while len(_TERMINALS) > _MAX_TERMINALS:
                        _TERMINALS.popitem(last=False)

        record("request_trace", request_id=request_id, stage=phase,
               outcome=trace["outcome"], duration_ms=trace["total_ms"],
               meta={"state": trace["state"], "attempt": trace["attempts"],
                     "outcome_class": trace["outcome_class"]})
        return trace
    except Exception:  # noqa: BLE001
        return None


def traces():
    with _LOCK:
        return [dict(t) for t in _TRACES.values()]


def pending_ages(items, *, reference):
    """Milliseconds each pending item has been open, against ``reference``.

    ``reference`` must come from the same clock the items were created with
    (the pending store's clock), otherwise the result is ``None``.
    """
    ages = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        ages.append(duration_ms(item.get("created_at"), reference))
    return ages


# ----------------------------------------------------------------------
# resource readings (best effort, read-only)
# ----------------------------------------------------------------------

def _rss_bytes():
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes as wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _PMC()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        ok = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters),
            counters.cb)
        return int(counters.WorkingSetSize) if ok else None
    try:
        import resource
        usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return usage if sys.platform == "darwin" else usage * 1024
    except Exception:  # noqa: BLE001
        return None


def _handle_count():
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetProcessHandleCount.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.GetProcessHandleCount.restype = ctypes.c_int
        value = ctypes.c_uint32(0)
        ok = kernel32.GetProcessHandleCount(
            kernel32.GetCurrentProcess(), ctypes.byref(value))
        return int(value.value) if ok else None
    try:
        return len(os.listdir("/proc/self/fd"))
    except Exception:  # noqa: BLE001
        return None


def resource_snapshot():
    """Best-effort CPU/memory/thread/handle readings; never raises."""
    snap = {"pid": None, "threads": None, "cpu_time_s": None,
            "rss_bytes": None, "handles": None}
    try:
        snap["pid"] = os.getpid()
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["threads"] = threading.active_count()
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["cpu_time_s"] = round(time.process_time(), 6)
    except Exception:  # noqa: BLE001
        pass
    try:
        rss = _rss_bytes()
        if rss is not None:
            snap["rss_bytes"] = rss
    except Exception:  # noqa: BLE001
        pass
    try:
        handles = _handle_count()
        if handles is not None:
            snap["handles"] = handles
    except Exception:  # noqa: BLE001
        pass
    return snap


# ----------------------------------------------------------------------
# inspection (on demand; never called on the hot path)
# ----------------------------------------------------------------------

def event_count():
    with _LOCK:
        return len(_EVENTS)


def trace_count():
    with _LOCK:
        return len(_TRACES)


def counters():
    with _LOCK:
        return dict(_COUNTERS)


def buffer_limits():
    return {"max_events": _MAX_EVENTS, "max_traces": _MAX_TRACES,
            "max_terminals": _MAX_TERMINALS,
            "max_runtime_keys": MAX_RUNTIME_KEYS}


def snapshot(include_events=True):
    """A JSON-safe, content-free view of everything recorded so far."""
    with _LOCK:
        data = {
            "enabled": is_enabled(),
            "process_start": _PROCESS_START,
            "limits": buffer_limits(),
            "counters": dict(_COUNTERS),
            "startup": {k: dict(v) for k, v in _STARTUP.items()},
            "traces": [dict(t) for t in _TRACES.values()],
            "runtime": {"meta": dict(_RUNTIME_META),
                        "counters": dict(_RUNTIME_COUNTERS)},
            "resources": resource_snapshot(),
            "event_count": len(_EVENTS),
            "trace_count": len(_TRACES),
        }
        if include_events:
            data["events"] = [dict(e) for e in _EVENTS]
    return data


def summary():
    with _LOCK:
        events = list(_EVENTS)
        data = {
            "event_counts": {},
            "counters": dict(_COUNTERS),
            "event_count": len(events),
            "trace_count": len(_TRACES),
        }
    for entry in events:
        name = entry.get("event")
        data["event_counts"][name] = data["event_counts"].get(name, 0) + 1
    return data


def report_runtime_counts(counts, *, phase=None, levels=()):
    """Merge numeric flow counters into the bounded runtime aggregate.

    Summary-only: this call never appends an event, so a caller can safely
    report once per window (poll interval, periodic tick, shutdown) without
    shaping the event stream. Keys are sanitized to safe tokens; non-numeric
    values and any key past the bounded key cap are ignored. Monotonic
    counters sum under the same key; keys named in ``levels`` (a current level
    such as queue depth, worker liveness or a ready flag) replace the stored
    value instead, so an absolute reading never accumulates. Returns a copy of
    the merged counters, or ``None`` when instrumentation is off or ``counts``
    is not a mapping.
    """
    if not is_enabled() or not isinstance(counts, dict):
        return None
    level_keys = frozenset(
        _token(key, _META_KEY_CHARS) for key in levels)
    with _LOCK:
        p = _token(phase, _META_STR_CHARS) if phase is not None else None
        if p is not None:
            _RUNTIME_META["phase"] = p
        for key, value in list(counts.items())[:MAX_RUNTIME_KEYS]:
            name = _token(key, _META_KEY_CHARS)
            if name is None:
                continue
            if name not in _RUNTIME_COUNTERS and \
                    len(_RUNTIME_COUNTERS) >= MAX_RUNTIME_KEYS:
                continue
            num = _num(value)
            if num is None:
                continue
            if name in level_keys:
                _RUNTIME_COUNTERS[name] = num
            else:
                _RUNTIME_COUNTERS[name] = _RUNTIME_COUNTERS.get(name, 0) + num
        _RUNTIME_META["updates"] += 1
        _RUNTIME_META["last_at"] = now() or 0.0
        return dict(_RUNTIME_COUNTERS)


def runtime_counters():
    """A copy of the merged runtime flow counters (``{}`` while disabled)."""
    with _LOCK:
        return dict(_RUNTIME_COUNTERS)


def runtime_meta():
    """A copy of the runtime aggregate metadata (phase/updates/last_at)."""
    with _LOCK:
        return dict(_RUNTIME_META)


def diagnostics():
    """A JSON-safe, content-free diagnostic snapshot for the verification
    sweep: enabled state, limits, module counters, buffer occupancy, startup
    phases, the bounded runtime aggregate and the current resource reading."""
    with _LOCK:
        data = {
            "enabled": is_enabled(),
            "limits": buffer_limits(),
            "counters": dict(_COUNTERS),
            "event_count": len(_EVENTS),
            "trace_count": len(_TRACES),
            "startup": {k: dict(v) for k, v in _STARTUP.items()},
            "runtime": {"meta": dict(_RUNTIME_META),
                        "counters": dict(_RUNTIME_COUNTERS)},
            "resources": resource_snapshot(),
        }
    return data


def to_json(include_events=True):
    return json.dumps(snapshot(include_events=include_events), sort_keys=True,
                      default=str)


# ----------------------------------------------------------------------
# CLI: environment summary + a tiny self-check (opt-in benchmark helper)
# ----------------------------------------------------------------------

def _environment():
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "env_flag": os.environ.get(ENV_FLAG),
    }


def main(argv=None):  # pragma: no cover - manual benchmark entry point
    enable()
    reset()
    started = now()
    record("self_check", duration_ms=0, meta={"kind": "baseline"})
    result = {
        "environment": _environment(),
        "self_check_ms": duration_ms(started, now()),
        "resources": resource_snapshot(),
        "summary": summary(),
    }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
