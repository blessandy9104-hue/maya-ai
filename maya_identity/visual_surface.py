"""VisualSurface — the shared contract for Maya's visual bodies.

The raster face (``MayaFace``) and the procedural face (``ProceduralFace``)
are two renderers of the same identity. They now share:

- one interface (``VisualSurface``) with a single state contract;
- one update driver (``LoopTimer``) so both surfaces use identical timing,
  cadence, and cleanup (default 80 ms, matched to the animation config).

This module owns no rendering; it only unifies the contract and the loop.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

FRAME_MS_DEFAULT = 80  # shared per-tick interval (animation default)


class VisualSurface(ABC):
    """Common interface every visual body must satisfy."""

    @abstractmethod
    def set_state(self, state):
        """Apply a normalized visual state."""

    @abstractmethod
    def set_command(self, command):
        """Accept a read-only visual command; surfaces without a live command
        channel ignore it."""

    @abstractmethod
    def state_text(self):
        ...

    @abstractmethod
    def status_text(self):
        ...

    @abstractmethod
    def is_placeholder(self):
        ...


class LoopTimer:
    """Single tkinter-safe periodic driver shared by all visual surfaces.

    Owns the ``after()`` / ``after_cancel()`` bookkeeping, never
    double-schedules, and ticks only while active, so both faces share the
    same cadence and cleanup semantics.
    """

    def __init__(self, widget, interval_ms=FRAME_MS_DEFAULT, active=False):
        self._widget = widget
        self.interval_ms = max(16, int(interval_ms))
        self._active = bool(active)
        self._tick_fn = None
        self._handle = None

    def attach(self, tick_fn):
        """Bind the callback run on every tick."""
        self._tick_fn = tick_fn

    def set_active(self, active):
        """Start or stop the loop. Cancels any pending tick when stopped."""
        was_active = self._active
        self._active = bool(active)
        if self._active and not was_active and self._handle is None:
            self._schedule()
        elif not self._active and self._handle is not None:
            self._cancel()

    def cancel(self):
        """Stop the loop and release the pending callback."""
        self.set_active(False)

    def _schedule(self):
        if self._active and self._handle is None:
            self._handle = self._widget.after(self.interval_ms, self._fire)

    def _fire(self):
        self._handle = None
        if not self._active:
            return
        if self._tick_fn is not None:
            self._tick_fn()
        self._schedule()

    def _cancel(self):
        if self._handle is not None:
            try:
                self._widget.after_cancel(self._handle)
            except Exception:
                pass
            self._handle = None