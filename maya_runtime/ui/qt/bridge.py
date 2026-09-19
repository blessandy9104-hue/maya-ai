"""Qt interface state bridge — pure Python, no Qt dependency.

Batch 8E: the presentation-only state layer for the PySide6/Qt Quick window.
It mirrors the exact tick pipeline used by the Tk interface (``maya_app``)
without touching any widget toolkit:

    state_snapshot(activity)
        -> cognitive_state.apply(core)          (visual_state / visual_label)
        -> PresenceEngine.tick(visual_state, raw)
        -> runtime_face_state(visual, meta, commands)
        -> build_visual_state(fs, meta, commands, semantic=cue)
        -> shape_math.project(vs, frame)        (authoritative projection)
    + the digest-verified ``[semantic] `` machine line (semantic_interpretation)

This module computes *view data only*: chips, live lines, status text and the
unit-space shape geometry consumed by the QML renderer. It never renders, never
invents state, has no randomness and reads no wall clock. Identical inputs give
byte-identical view dicts on every interpreter, so the Qt view can be validated
against the authoritative pipeline and replayed exactly like the Tk snapshot.

The only thing here that performs IO is ``CommandBridge`` (local commands,
presence controller, emergency stop, settings/cache/suggestions). Those mirror
the ``maya_app`` helpers and are intentionally thin wrappers around the same
backend modules; Qt calls them from worker threads.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent

CHILD_ENV = dict(os.environ)
CHILD_ENV["PYTHONIOENCODING"] = "utf-8"
CHILD_ENV["MAYA_SEMANTIC_BRIDGE"] = "1"


class OrderedProjectionWorker:
    """Single-daemon-thread, bounded FIFO view-projection worker.

    Pure (no Qt): the fallback path the controller uses when
    :class:`maya_async.BoundedExecutor` is unavailable. Preserves the ordering
    and non-blocking, bounded backpressure contract of the primary executor: at
    most ``max_queue`` projections wait and a full queue drops the
    *presentation* frame (never chat/approval data, which flows on separate
    channels).
    """

    def __init__(self, max_queue=8, name="maya-proj-fallback"):
        self.max_queue = max(1, int(max_queue))
        self.name = str(name)
        self._queue = collections.deque()
        self._cond = threading.Condition()
        self._stopping = False
        self._drops = 0
        self._thread = threading.Thread(target=self._loop, name=self.name,
                                        daemon=True)
        self._thread.start()

    def submit(self, fn):
        """Queue ``fn``; False (drop) when full or after shutdown."""
        if not callable(fn):
            return False
        with self._cond:
            if self._stopping:
                return False
            if len(self._queue) >= self.max_queue:
                self._drops += 1
                return False
            self._queue.append(fn)
            self._cond.notify()
        return True

    def shutdown(self, *, wait=True, timeout=2.0):
        """Stop accepting work, cancel queued plans, join the thread."""
        with self._cond:
            self._stopping = True
            self._queue.clear()
            self._cond.notify_all()
        if wait:
            self._thread.join(max(0.0, float(timeout)))

    def alive_workers(self):
        return 1 if self._thread.is_alive() else 0

    def _loop(self):
        while True:
            with self._cond:
                while not self._queue and not self._stopping:
                    self._cond.wait()
                if not self._queue:
                    return  # stopping and drained
                fn = self._queue.popleft()
            try:
                fn()
            except Exception:  # noqa: BLE001 - a projection never kills us
                pass

# Palette shared with the QML Theme.qml component (mirrors the Tk ``C`` map).
PALETTE = {
    "bg": "#0a0e1a",
    "panel": "#101629",
    "panel2": "#161d33",
    "card": "#0d1322",
    "field": "#0b1020",
    "edge": "#25305a",
    "edge2": "#1b2340",
    "accent": "#6d7cff",
    "accent2": "#9a8cff",
    "ink": "#e7ebfa",
    "muted": "#8a93b8",
    "dim": "#5b6488",
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "bad": "#ff5c7a",
    "cyan": "#38bdf8",
}

SHAPE_COLORS = {
    "core": "#5884d8",
    "core_dim": "#3a4f8f",
    "ring": "#d8b46c",
    "pointer": "#bedca0",
    "bg": "#101218",
}

ACTIVITY_KEYS = ("idle", "processing", "listening", "research")
RESEARCH_COMMANDS = (":research", ":world", ":income", ":evidence", ":focus", ":review")
WORLD_TYPES = ["fact", "historical_record", "observation", "report"]
CONFIDENCES = ["low", "medium", "high"]

_TAU = 6.283185307179586


def _float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _color(state_on, ok="#00ff00", muted="#888888"):
    return {"value": state_on, "color": ok if state_on else muted}


# ----------------------------------------------------------------------
# deterministic change detection / coalescing (pure, no Qt, injectable clock)
# ----------------------------------------------------------------------
#
# The Qt controller re-sends a full tick view on every status/resource tick.
# Most of those ticks are identical, and the consumer (Main.qml) then rebuilds
# every model from scratch. The helpers below let the controller detect real
# change and coalesce redundant ticks *without* ever hiding a meaningful event.
# They are pure functions/objects: no Qt, no wall clock, deterministic equality,
# and they never mutate the data they are given.

#: View fields that change on every tick for animation/geometry reasons only
#: and are not part of the meaningful (visible or contract) surface. They are
#: still present in every emitted payload; they are excluded only from *change
#: detection*, so a tick that changes nothing else is not re-sent.
VOLATILE_VIEW_FIELDS = frozenset({
    "frame", "shape", "ring", "pointer", "face", "face_digest",
})

#: Reasons that must never be delayed, merged or dropped by coalescing:
#: approvals, refusals/denials, cancellation, timeout, failure, completion,
#: safety-state transitions and user-visible conversational responses.
MEANINGFUL_EVENTS = frozenset({
    "approval", "denial", "refusal", "cancellation", "timeout", "failure",
    "completion", "safety", "conversation",
})


def is_meaningful(reason):
    """True when ``reason`` names an event coalescing must never suppress."""
    return reason in MEANINGFUL_EVENTS


def canonical(obj):
    """Deterministic nested form with sorted keys. Never mutates ``obj``."""
    if isinstance(obj, dict):
        return {str(k): canonical(v)
                for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [canonical(v) for v in obj]
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    return str(obj)


def canonical_json(obj):
    """Canonical JSON text (sorted, compact) used for deterministic equality."""
    return json.dumps(canonical(obj), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def fingerprint_text(obj):
    """Cheap deterministic JSON text for already-JSON-native structures.

    Views/payloads are built from JSON-native values with string keys, so a
    direct ``json.dumps`` is deterministic and avoids rebuilding the whole
    nested object graph (``canonical``) on every tick. Falls back to
    ``canonical_json`` for anything ``json`` cannot sort or serialize.
    """
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)
    except Exception:  # noqa: BLE001 - unusual keys/values: full canonical form
        return canonical_json(obj)


def stable_projection(view, exclude=VOLATILE_VIEW_FIELDS):
    """A copy of ``view`` without volatile fields (or ``None``)."""
    if not isinstance(view, dict):
        return None
    return {k: v for k, v in view.items() if k not in exclude}


def view_fingerprint(view):
    """Stable hash of the meaningful projection of one view dict."""
    return hashlib.sha256(
        fingerprint_text(stable_projection(view)).encode("utf-8")).hexdigest()


def input_signature(payload, state=None):
    """Deterministic signature of a tick payload plus ticker-held input state."""
    return fingerprint_text({"payload": payload, "state": state})


def changed_keys(previous, current):
    """Top-level keys whose (deep, canonical) value differs, order-stable."""
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return sorted({str(k) for k in (previous or [])}
                      | {str(k) for k in (current or [])})
    keys = set(previous) | set(current)
    return sorted(str(k) for k in keys
                  if canonical(previous.get(k)) != canonical(current.get(k)))


def minimize_payload(view, previous, *, base_revision=0, revision=1,
                     generation=0):
    """Versioned delta for consumers that opt in. ``None`` when unchanged.

    Additive: the existing consumer still receives a full snapshot. The view
    carries no raw trust records or secret material.
    """
    changed = changed_keys(previous, view)
    if not changed:
        return None
    return {
        "revision": int(revision),
        "base_revision": int(base_revision),
        "generation": int(generation),
        "changed": changed,
        "patch": {key: (view.get(key) if isinstance(view, dict) else None)
                  for key in changed},
    }


#: Key fragments that would indicate secret/trust-sensitive material leaking
#: into an ordinary payload. Presentation payloads never contain these.
_SENSITIVE_MARKERS = ("secret", "password", "passwd", "token", "api_key",
                      "apikey", "credential", "private_key")


def payload_is_sanitized(obj):
    """True when no key in ``obj`` looks secret/trust-sensitive (recursive)."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            name = str(key).lower()
            if any(marker in name for marker in _SENSITIVE_MARKERS):
                return False
            if not payload_is_sanitized(value):
                return False
        return True
    if isinstance(obj, (list, tuple)):
        return all(payload_is_sanitized(v) for v in obj)
    return True


class ChangeTracker:
    """Bounded deterministic change detection + monotonic revisioning.

    Retains only the last fingerprint; equality is canonical/deep, never
    object identity.
    """

    def __init__(self):
        self._fingerprint = None
        self._revision = 0
        self._changed = 0
        self._unchanged = 0

    @property
    def revision(self):
        return self._revision

    @property
    def fingerprint(self):
        return self._fingerprint

    def classify(self, obj):
        fingerprint = fingerprint_text(obj)
        if self._fingerprint is None:
            return "first"
        return "unchanged" if fingerprint == self._fingerprint else "changed"

    def commit(self, obj):
        changed, revision = self.observe(obj)
        return revision

    def observe(self, obj):
        """Fingerprint once; return ``(changed, revision)``."""
        fingerprint = fingerprint_text(obj)
        changed = fingerprint != self._fingerprint
        self._fingerprint = fingerprint
        if changed:
            self._revision += 1
            self._changed += 1
        else:
            self._unchanged += 1
        return changed, self._revision

    def reset(self):
        self._fingerprint = None
        self._revision = 0
        self._changed = 0
        self._unchanged = 0

    def stats(self):
        return {"revision": self._revision, "changed": self._changed,
                "unchanged": self._unchanged}


class UpdateCoalescer:
    """Bounded, deterministic coalescing of redundant bridge ticks.

    Semantics:
    * the first observation is always due;
    * meaningful events (``reason`` in :data:`MEANINGFUL_EVENTS`) are always
      due immediately and clear any held update;
    * a non-meaningful change is due immediately when the previous emit is at
      least ``interval_ms`` old; otherwise it is held as the single *latest*
      pending update and becomes due when the interval elapses.
    Bounded: at most one pending update is retained.
    """

    def __init__(self, interval_ms=50.0):
        self.interval_ms = max(0.0, float(interval_ms))
        self._last_emit_ms = None
        self._pending = None
        self._due_at = None

    @property
    def has_pending(self):
        return self._pending is not None

    @property
    def pending(self):
        return self._pending

    def reset(self):
        self._last_emit_ms = None
        self._pending = None
        self._due_at = None

    def offer(self, view, *, revision, reason=None, now_ms):
        """Record a new view; True when it must be emitted now."""
        meaningful = is_meaningful(reason)
        if (self._last_emit_ms is None or meaningful
                or now_ms - self._last_emit_ms < 0
                or now_ms - self._last_emit_ms >= self.interval_ms):
            self._pending = None
            self._due_at = None
            self._last_emit_ms = now_ms
            return True
        self._pending = {"view": view, "revision": int(revision),
                         "reason": reason}
        if self._due_at is None:
            self._due_at = self._last_emit_ms + self.interval_ms
        return False

    def due(self, now_ms):
        return (self._pending is not None and self._due_at is not None
                and now_ms >= self._due_at)

    def flush(self, now_ms, force=False):
        """Return the pending update once due (or when ``force``), else ``None``."""
        if not force and not self.due(now_ms):
            return None
        if self._pending is None:
            return None
        pending = self._pending
        self._pending = None
        self._due_at = None
        self._last_emit_ms = now_ms
        return pending

    def stats(self):
        return {"has_pending": self.has_pending,
                "interval_ms": self.interval_ms}


# Student-facing vocabulary for the redesigned core orb. Presentation only:
# these labels never change authority, capability or state; the authoritative
# nine-state model lives in ``maya_intelligence_core``. Constructed for
# readability (mint = ready, electric = thinking, gold = insight/done,
# red = needs attention), paired with a text label so colour is never the
# only signal.
STUDENT_STATUS = {
    "idle": ("Ready", "mint", "Maya is awake and ready."),
    "observing": ("Listening", "electric", "Maya is listening."),
    "reasoning": ("Thinking", "electric", "Maya is thinking it through."),
    "approval": ("Needs your OK", "gold",
                 "Maya is waiting for your OK before doing anything."),
    "acting": ("Working", "electric",
               "Maya is working on a permitted, bounded step."),
    "verifying": ("Checking", "electric", "Maya is double-checking the result."),
    "complete": ("All done", "gold", "Maya finished and verified that."),
    "unavailable": ("Paused", "muted",
                    "Maya is paused - she has no authority data to act on."),
    "error": ("Something's wrong", "red",
              "Something is wrong; Maya is not acting."),
}


def _pending_summary(rows):
    if not rows:
        return "Nothing needs your approval right now."
    try:
        from maya_pending import human_summary
        return human_summary(rows)
    except Exception:  # noqa: BLE001 - presentation layer never breaks the view
        return "Something needs your approval."


def student_view(core, resources, pending=None):
    """Pure, additive student-facing projection of the core view.

    Read-only and deterministic: it never changes authority, state or
    capability. Any unknown or missing core resolves to the muted "Paused"
    label, so a failure can never be shown as Ready.

    ``pending`` is an optional list of pending-validation items produced by
    the orchestration layer. It is surfaced additively so a chat surface can
    offer approve/deny/cancel/retry controls instead of hiding the queue.
    """
    state = core.get("state") if isinstance(core, dict) else None
    label, tone, detail = STUDENT_STATUS.get(
        state, ("Paused", "muted", "Maya is paused."))
    healthy = bool(isinstance(core, dict)
                   and not core.get("implies_failure")
                   and resources == "safe")
    try:
        from maya_pending import surface as _pending_surface
        pending_rows = _pending_surface(pending)
    except Exception:  # noqa: BLE001 - presentation layer never breaks the view
        pending_rows = [dict(item) for item in (pending or [])
                        if isinstance(item, dict)]
    open_rows = [item for item in pending_rows
                 if item.get("status") == "pending"]
    return {
        "state": state if state in STUDENT_STATUS else "unavailable",
        "status_label": label,
        "status_tone": tone,
        "status_detail": detail,
        "healthy": healthy,
        "core_legend": [
            {"tone": "mint", "text": "Ready"},
            {"tone": "electric", "text": "Thinking"},
            {"tone": "gold", "text": "All done"},
            {"tone": "red", "text": "Needs attention"},
        ],
        "pending": pending_rows,
        "pending_open": len(open_rows),
        "human_summary": _pending_summary(pending_rows),
    }



def ring_points_unit(projected, n=24):
    """Sample the orbit ring polyline in unit space (matches the Tk renderer).

    The Tk renderer produces exactly this 24-point ellipse from the same
    ``ProjectedShape`` parameters and the same phase formula; QML only draws
    the points it is given. Pure function of the projection.
    """
    pts = []
    for i in range(int(n)):
        theta = projected["ring_phase"] + _TAU * int(i) / int(n)
        pts.append({
            "x": projected["cx"] + projected["ring_rx"] * math.cos(theta),
            "y": projected["cy"] + projected["ring_ry"] * math.sin(theta),
        })
    return pts


def pointer_geometry(projected):
    """Unit-space pointer segment (mirrors the Tk canvas coords)."""
    if projected["pointer_len"] > 0:
        return {
            "visible": True,
            "x1": projected["cx"],
            "y1": projected["cy"],
            "x2": projected["cx"] + projected["pointer_dx"] * projected["pointer_len"],
            "y2": projected["cy"] + projected["pointer_dy"] * projected["pointer_len"],
        }
    return {"visible": False,
            "x1": projected["cx"], "y1": projected["cy"],
            "x2": projected["cx"], "y2": projected["cy"]}


def derive_face_metadata(snapshot, commands=None, visual="sleeping"):
    """Faithful copy of ``maya_app._derive_face_metadata`` (pure)."""
    meta = {
        "visual_state": str(visual or "sleeping"),
        "emotion": str(snapshot.get("expression_signal") or "neutral"),
        "confidence": 0.55 if snapshot.get("resources") == "safe" else 0.20,
        "attention": 0.0,
        "thinking": 0.0,
        "breath": 0.40,
        "glow_intensity": 0.15,
        "scan_activity": 0.20,
    }
    if commands:
        for key in ("eye_focus", "neural_activity", "glow_intensity",
                    "particle_density", "breath", "gaze_x", "gaze_y"):
            if key in commands:
                meta[key] = commands[key]
    if snapshot.get("resources") != "safe":
        meta["preset"] = "error"
    return meta


class UiTicker:
    """Owns the tick counters and latest validated semantic cue.

    Deterministic view generator for the Qt window. No Qt, no widget toolkit,
    no randomness, no wall clock.
    """

    def __init__(self):
        self._shape_frame = 0
        self._latest_semantic = None
        self._face_model = None
        self._face_ok = False
        self._pending_items = []

    def set_pending(self, items):
        """Replace the actionable pending set (presentation only, no writes)."""
        self._pending_items = [dict(item) for item in (items or [])
                               if isinstance(item, dict)]

    # -- semantic channel ---------------------------------------------------

    def read_semantic_line(self, text):
        """Digest-verify one ``[semantic] `` machine line -> cue or None."""
        from maya_identity.embodiment.semantic_interpretation import from_line
        cue = from_line(text) if isinstance(text, str) else None
        if cue is not None:
            self._latest_semantic = cue
        return cue

    def set_semantic(self, cue):
        self._latest_semantic = cue

    @property
    def latest_semantic(self):
        return self._latest_semantic

    def state_signature(self):
        """Deterministic signature of ticker-held input state.

        Lets the controller skip re-projecting an unchanged backend payload
        while still reacting the instant the semantic cue, pending set or face
        model changes. Canonical/deep equality; never object identity.
        """
        semantic = (self._latest_semantic.as_dict()
                    if self._latest_semantic is not None else None)
        return canonical_json({
            "semantic": semantic,
            "pending": self._pending_items,
            "face_ok": self._face_ok,
        })

    def snapshot_input(self):
        """Detached, deterministic copy of the UI-held inputs that feed a tick.

        Safe to hand to another thread: the projection worker reads *only*
        this snapshot and never the live ticker, so the authoritative model
        is advanced exactly once, on the UI thread, via :meth:`advance_frame`.
        The face model reference is intentionally shared (it is read-only
        after construction and deterministic per visitor).
        """
        semantic = (self._latest_semantic.as_dict()
                    if self._latest_semantic is not None else None)
        return {
            "shape_frame": int(self._shape_frame),
            "semantic": semantic,
            "pending": [dict(item) for item in self._pending_items],
            "face_model": self._face_model,
            "face_ok": bool(self._face_ok),
        }

    def advance_frame(self):
        """Optimistically advance the animation frame on the UI thread.

        Returns the new frame. Calling this on the UI thread keeps the frame
        counter authoritative on a single thread while the projection worker
        computes the view for the frame captured in its own snapshot.
        """
        self._shape_frame += 1
        return self._shape_frame

    # -- authoritative tick pipeline ---------------------------------------

    def make_tick_payload(self, activity="idle"):
        """Mirror ``maya_app._make_tick_payload``: snapshot + cognitive state."""
        from maya_identity import cognitive_state
        from maya_state_signals import snapshot as state_snapshot
        activity = activity if activity in ACTIVITY_KEYS else "idle"
        snap = state_snapshot(activity=activity)
        core = {
            "service": snap["presence"],
            "learning": snap["learning"],
            "presence": snap["raw"]["presence_mode"],
            "processing": snap["activity"] == "processing",
            "listening": snap["activity"] == "listening",
            "research": snap["activity"] == "research",
            "activity": snap["activity"],
            "conversation": snap["conversation"],
            "resources": snap["resources"],
        }
        return {**snap, **cognitive_state.apply(core)}

    def apply_tick_snapshot(self, snapshot):
        """Turn a tick snapshot into the pure Qt view dict (or None).

        ``None`` input (startup/emergency reset) produces the neutral reset
        view exactly like the Tk ``_apply_tick`` ``None`` branch.
        """
        if not isinstance(snapshot, dict):
            return None
        raw = snapshot.get("raw", {}) or {}
        service = str(raw.get("service") or "unknown")
        learning = str(snapshot.get("learning") or "off")
        presence_mode = str(raw.get("presence_mode") or "off")
        visual = str(snapshot.get("visual_state") or "sleeping")
        resources = str(snapshot.get("resources") or "safe")

        from maya_identity.embodiment import PresenceEngine
        from maya_identity.embodiment.shape_math import project
        from maya_identity.embodiment.visual_state import build_visual_state
        from maya_runtime.face_drive import (
            drive_digest, runtime_face_state,
        )

        commands = PresenceEngine().tick(visual_state=visual, signals=raw)
        meta = derive_face_metadata(snapshot, commands, visual)
        fs = runtime_face_state(visual=visual, meta=meta, commands=commands)
        vs = build_visual_state(fs, meta, commands,
                                semantic=self._latest_semantic)
        self._shape_frame += 1
        projected = project(vs, self._shape_frame).as_dict_safe()

        awake = visual in ("awake", "processing", "listening", "research")
        extra = dict(fs.extra or {})

        # Canonical face payload (Maya Batch 8M): the vector-face renderer is
        # the single presentation authority for the Qt face surface. Built
        # from the same authoritative FaceState/VisualState this tick already
        # produced; contains geometry, expression and digest only - it never
        # defines identity and QML only paints the points it is given.
        from maya_identity.vector_face import (
            anchors_for_face_extra,
            build_canonical_vector_face,
            render_face_commands,
            to_qml_payload,
            validate_canonical_face,
            validate_render_commands,
        )
        if self._face_model is None:
            model = build_canonical_vector_face()
            model_ok, _model_reasons = validate_canonical_face(model)
            self._face_model = model if model_ok else None
            self._face_ok = model_ok
        face_payload = None
        if self._face_model is not None:
            extra2 = dict(extra)
            extra2["attention"] = getattr(vs, "attention", None)
            extra2["activity"] = getattr(vs, "activity", None)
            extra2["focus"] = getattr(vs, "focus", None)
            extra2["curiosity"] = getattr(vs, "curiosity", None)
            expr = anchors_for_face_extra(extra2)
            rendered = render_face_commands(self._face_model, expr,
                                            frame=self._shape_frame)
            rendered_ok, _rendered_reasons = validate_render_commands(rendered)
            if rendered_ok:
                payload = to_qml_payload(self._face_model, expr,
                                         frame=self._shape_frame)
                face_payload = payload if payload.get("surface") else None

        core = None
        try:
            from maya_intelligence_core import runtime_core_view
            core = runtime_core_view(
                activity=str(snapshot.get("activity") or "idle"),
                resources=snapshot.get("resources"),
            )
        except Exception:  # noqa: BLE001 - presentation layer never breaks the tick
            core = None

        live_lines = [
            f"presence    : {snapshot.get('presence', 'unknown')}",
            f"activity    : {snapshot.get('activity', 'idle')}",
            f"state       : {visual}",
            f"learning    : {learning}",
            f"conversation: {snapshot.get('conversation', 'idle')}",
            f"expression  : {snapshot.get('expression_signal', 'calm')}",
            f"resources   : {resources}",
        ]
        return {
            "service": service,
            "service_color": "#4ade80" if service == "awake" else "#8a93b8",
            "learning": learning,
            "learning_color": "#4ade80" if learning == "on" else "#8a93b8",
            "presence": presence_mode,
            "presence_color": "#fbbf24" if presence_mode != "off" else "#8a93b8",
            "resources": resources,
            "resources_color": "#4ade80" if resources == "safe" else "#fbbf24",
            "activity": snapshot.get("activity", "idle"),
            "conversation": snapshot.get("conversation", "idle"),
            "expression": snapshot.get("expression_signal", "calm"),
            "visual_state": visual,
            "visual_label": str(snapshot.get("visual_label") or ""),
            "awake": awake,
            "live_lines": live_lines,
            "shape": projected,
            "ring": ring_points_unit(projected),
            "pointer": pointer_geometry(projected),
            "shape_colors": dict(SHAPE_COLORS),
            "frame": self._shape_frame,
            "visual": vs.as_dict(),
            "face": face_payload,
            "face_anchor": str(extra.get("anchor") or "neutral"),
            "face_aura": _float(extra.get("aura"), 0.5),
            "face_digest": drive_digest(fs),
            "core": core,
            "pending": list(self._pending_items),
            "ui": student_view(core, resources, self._pending_items),
            "semantic": (self._latest_semantic.as_dict()
                         if self._latest_semantic is not None else None),
        }

    def project(self, payload, snap):
        """Pure, additive, off-UI-thread projection of one tick payload.

        Produces exactly the view :meth:`apply_tick_snapshot` would produce
        for the same ticker state, but reads every UI-held input (semantic
        cue, pending set, face model, animation frame) from the *detached*
        ``snap`` captured by :meth:`snapshot_input` and never mutates lived
        ticker state. The animation frame is ``snap["shape_frame"] + 1``,
        matching the frame ``advance_frame`` left on the UI thread when the
        delivery was scheduled.

        ``None``/non-dict payloads resolve to ``None`` exactly like
        :meth:`apply_tick_snapshot` (``None`` is the neutral reset signal).

        Thread-safety: safe to call from any thread; the ticker is only ever
        reached through ``snap``.
        """
        if not isinstance(snap, dict):
            return None
        if not isinstance(payload, dict):
            return None
        frame = int(snap.get("shape_frame", 0)) + 1
        semantic = snap.get("semantic")
        pending = snap.get("pending") or []
        face_model = snap.get("face_model")
        face_ok = bool(snap.get("face_ok"))
        raw = payload.get("raw", {}) or {}
        service = str(raw.get("service") or "unknown")
        learning = str(payload.get("learning") or "off")
        presence_mode = str(raw.get("presence_mode") or "off")
        visual = str(payload.get("visual_state") or "sleeping")
        resources = str(payload.get("resources") or "safe")

        from maya_identity.embodiment import PresenceEngine
        from maya_identity.embodiment.shape_math import project
        from maya_identity.embodiment.visual_state import build_visual_state
        from maya_runtime.face_drive import (
            drive_digest, runtime_face_state,
        )

        commands = PresenceEngine().tick(visual_state=visual, signals=raw)
        meta = derive_face_metadata(payload, commands, visual)
        fs = runtime_face_state(visual=visual, meta=meta, commands=commands)
        from maya_identity.embodiment.semantic_interpretation import (
            from_dict as _semantic_from_dict,
        )
        vs = build_visual_state(
            fs, meta, commands,
            semantic=_semantic_from_dict(semantic))
        projected = project(vs, frame).as_dict_safe()

        awake = visual in ("awake", "processing", "listening", "research")
        extra = dict(fs.extra or {})

        # Canonical face payload (Maya Batch 8M): the vector-face renderer is
        # the single presentation authority for the Qt face surface. Built
        # from the same authoritative FaceState/VisualState this tick already
        # produced; contains geometry, expression and digest only - it never
        # defines identity and QML only paints the points it is given.
        from maya_identity.vector_face import (
            anchors_for_face_extra,
            build_canonical_vector_face,
            render_face_commands,
            to_qml_payload,
            validate_canonical_face,
            validate_render_commands,
        )
        if face_model is None:
            cand = build_canonical_vector_face()
            cand_ok, _cand_reasons = validate_canonical_face(cand)
            face_model = cand if cand_ok else None
            face_ok = cand_ok
        face_payload = None
        if face_model is not None:
            extra2 = dict(extra)
            extra2["attention"] = getattr(vs, "attention", None)
            extra2["activity"] = getattr(vs, "activity", None)
            extra2["focus"] = getattr(vs, "focus", None)
            extra2["curiosity"] = getattr(vs, "curiosity", None)
            expr = anchors_for_face_extra(extra2)
            rendered = render_face_commands(face_model, expr, frame=frame)
            rendered_ok, _rendered_reasons = validate_render_commands(rendered)
            if rendered_ok:
                payload_face = to_qml_payload(face_model, expr, frame=frame)
                face_payload = (
                    payload_face if payload_face.get("surface") else None)

        core = None
        try:
            from maya_intelligence_core import runtime_core_view
            core = runtime_core_view(
                activity=str(payload.get("activity") or "idle"),
                resources=payload.get("resources"),
            )
        except Exception:  # noqa: BLE001 - presentation layer never breaks the tick
            core = None

        live_lines = [
            f"presence    : {payload.get('presence', 'unknown')}",
            f"activity    : {payload.get('activity', 'idle')}",
            f"state       : {visual}",
            f"learning    : {learning}",
            f"conversation: {payload.get('conversation', 'idle')}",
            f"expression  : {payload.get('expression_signal', 'calm')}",
            f"resources   : {resources}",
        ]
        return {
            "service": service,
            "service_color": "#4ade80" if service == "awake" else "#8a93b8",
            "learning": learning,
            "learning_color": "#4ade80" if learning == "on" else "#8a93b8",
            "presence": presence_mode,
            "presence_color": "#fbbf24" if presence_mode != "off" else "#8a93b8",
            "resources": resources,
            "resources_color": "#4ade80" if resources == "safe" else "#fbbf24",
            "activity": payload.get("activity", "idle"),
            "conversation": payload.get("conversation", "idle"),
            "expression": payload.get("expression_signal", "calm"),
            "visual_state": visual,
            "visual_label": str(payload.get("visual_label") or ""),
            "awake": awake,
            "live_lines": live_lines,
            "shape": projected,
            "ring": ring_points_unit(projected),
            "pointer": pointer_geometry(projected),
            "shape_colors": dict(SHAPE_COLORS),
            "frame": frame,
            "visual": vs.as_dict(),
            "face": face_payload,
            "face_anchor": str(extra.get("anchor") or "neutral"),
            "face_aura": _float(extra.get("aura"), 0.5),
            "face_digest": drive_digest(fs),
            "core": core,
            "pending": list(pending),
            "ui": student_view(core, resources, pending),
            "semantic": (semantic
                         if isinstance(semantic, dict) else None),
        }


class CommandBridge:
    """Thin, faithful wrappers around Maya's own action helpers.

    Mirrors ``maya_app`` methods (run_command / run_presence / do_emergency /
    settings_* / world_* / task_op / suggestion_review). IO happens in the
    caller's thread; Qt invokes these from worker threads and forwards the
    text results to the view.
    """

    @staticmethod
    def local_command(cmd):
        """Run one deterministic local command (may need the LLM for chat)."""
        import maya_chat
        result = maya_chat.maya_local_command(cmd)
        if result is None:
            return "No local command matched."
        return result

    @staticmethod
    def presence_action(action, timeout=12):
        import subprocess as _sp
        try:
            proc = _sp.run(
                [sys.executable, str(ROOT / "presence.py"), action],
                cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", timeout=timeout, env=CHILD_ENV,
            )
            return (proc.stdout + proc.stderr).strip() \
                or f"presence {action} completed"
        except Exception as exc:  # noqa: BLE001 - same guard as maya_app
            return f"Presence controller error: {exc}"

    @staticmethod
    def emergency():
        """Emergency stop + presence stop. Returns the detail text."""
        from maya_safety_monitor import emergency_stop
        try:
            stop = emergency_stop("GUI emergency stop")
        except Exception as exc:  # noqa: BLE001
            stop = {"error": str(exc)}
        reason = stop.get("reason") if isinstance(stop, dict) else None
        err = stop.get("error") if isinstance(stop, dict) else None
        detail = f" (marker write error: {err})" if err else ""
        return (f"Emergency stop triggered: {reason or 'manual emergency stop'} "
                f"at {time_now()}{detail}")
    # -- settings (mirrors MayaApp.refresh_settings + settings_*) ----------

    @staticmethod
    def settings_snapshot():
        import maya_service
        try:
            pid = maya_service.running_pid()
            service = f"awake (pid {pid})" if pid else "asleep"
        except Exception:  # noqa: BLE001
            pid, service = None, "unknown"
        try:
            policy = json.loads(
                (ROOT / "maya_app_control_policy.json").read_text(encoding="utf-8")) \
                if (ROOT / "maya_app_control_policy.json").exists() else {}
            owner_enabled = bool(policy.get("owner_control_enabled"))
        except Exception:  # noqa: BLE001
            owner_enabled = None
        try:
            from maya_identity import load_engine_config
            voice_enabled = bool(load_engine_config("voice").get("enabled"))
        except Exception:  # noqa: BLE001
            voice_enabled = None
        try:
            status = json.loads(
                (ROOT / "presence_status.json").read_text(encoding="utf-8"))
            presence_mode = status.get("mode", "unknown")
        except Exception:  # noqa: BLE001
            presence_mode = "unknown"
        stop_active = (ROOT / "PRESENCE_STOP").exists()
        cache = CommandBridge.cache_status()
        try:
            import maya_web_research
            cache_fields = (maya_web_research.CACHE_MAX_ENTRIES,
                            maya_web_research.CACHE_TTL_DAYS)
        except Exception:  # noqa: BLE001
            cache_fields = (None, None)
        return {
            "service": (service, "#4ade80" if pid else "#8a93b8"),
            "presence_mode": (presence_mode,
                              "#fbbf24" if presence_mode == "on" else "#8a93b8"),
            "stop": ("ACTIVE" if stop_active else "clear",
                     "#ff5c7a" if stop_active else "#4ade80"),
            "owner": (("enabled" if owner_enabled else "disabled") if owner_enabled is not None else "read error",
                      "#fbbf24" if owner_enabled else "#8a93b8"),
            "voice": (("enabled" if voice_enabled else "disabled") if voice_enabled is not None else "read error",
                      "#4ade80" if voice_enabled else "#8a93b8"),
            "cache_text": cache["text"],
            "cache_cap": cache_fields[0],
            "cache_ttl": cache_fields[1],
        }

    @staticmethod
    def cache_status():
        try:
            import maya_web_research
            cap = maya_web_research.CACHE_MAX_ENTRIES
            ttl = maya_web_research.CACHE_TTL_DAYS
            path = maya_web_research.CACHE_FILE
            rows = len(maya_web_research._read_cache())  # noqa: SLF001
            size = path.stat().st_size if path.exists() else 0
            cap_bytes = maya_web_research.CACHE_MAX_BYTES
            text = (f"rows: {rows}   file: {size} B   cap {cap} entries / "
                    f"{cap_bytes // (1024 * 1024)} MB / {ttl} day staleness")
        except Exception as exc:  # noqa: BLE001
            text = f"cache status unavailable: {exc}"
        return {"rows": rows, "size": size, "text": text}

    @staticmethod
    def apply_cache(cap_raw, ttl_raw):
        try:
            cap, ttl = int(cap_raw), int(ttl_raw)
        except (TypeError, ValueError):
            return ("entry cap and staleness days must be integers", True)
        if cap < 1 or ttl < 1 or cap > 10000 or ttl > 3650:
            return ("values out of range (cap 1-10000, days 1-3650)", True)
        try:
            import maya_web_research
            old_cap = maya_web_research.CACHE_MAX_ENTRIES
            old_ttl = maya_web_research.CACHE_TTL_DAYS
            maya_web_research.CACHE_MAX_ENTRIES = cap
            maya_web_research.CACHE_TTL_DAYS = ttl
            text = f"entries: {old_cap} -> {cap}   staleness: {old_ttl} -> {ttl} days"
            return (text, False)
        except Exception as exc:  # noqa: BLE001
            return (f"apply cache config error: {exc}", True)

    @staticmethod
    def clear_cache():
        try:
            import maya_web_research
            path = maya_web_research.CACHE_FILE
        except Exception as exc:  # noqa: BLE001
            return ("cache modules unavailable", True)
        if not path.exists():
            return ("no research cache file present; nothing to clear", False)
        try:
            rows = len(maya_web_research._read_cache())  # noqa: SLF001
            size = path.stat().st_size if path.exists() else 0
            path.unlink(missing_ok=True)
            return (f"research cache deleted: {rows} rows, {size} B removed", False)
        except Exception as exc:  # noqa: BLE001
            return (f"cache clear error: {exc}", True)

    @staticmethod
    def pending_suggestions():
        try:
            import maya_suggestion_review
            return maya_suggestion_review.pending_suggestions()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @staticmethod
    def review_suggestion(suggestion_id, decision):
        try:
            import maya_suggestion_review
            return json.dumps(maya_suggestion_review.review_suggestion(
                suggestion_id, decision), ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            return f"review error: {exc}"

    # -- resource monitor (mirrors MayaApp.monitor_resources) --------------

    @staticmethod
    def resource_status():
        from maya_safety_monitor import status as resource_status
        return resource_status()


def time_now():
    import time as _time
    return _time.strftime('%H:%M:%S')