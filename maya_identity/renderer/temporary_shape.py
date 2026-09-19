"""TemporaryShapeRenderer — the Batch 8C temporary geometric embodiment.

A Tk canvas that draws an abstract geometric core (orb + orbit ring + gaze
pointer) as a pure projection of ``VisualState`` at an explicit frame index.
It is deliberately NOT a face: no eyes, mouth, or decorative character
animation. Every movement is a deterministic function of Maya's validated
semantic state.

The renderer is downstream of the state pipeline — it computes nothing about
intelligence; it only draws. Swapping this renderer for a future
``MayaFaceRenderer`` changes nothing upstream of ``VisualState``.

Implements the shared ``VisualSurface`` contract (``set_state``,
``set_command``, ``state_text``, ``status_text``, ``is_placeholder``) plus the
tick-driver methods used by ``maya_app._apply_tick`` (``set_visual_state`` /
``set_face_state`` / ``set_metadata`` / ``snapshot``).
"""
from __future__ import annotations

import math
import tkinter as tk

from ..embodiment.shape_math import project as project_shape
from ..embodiment.visual_state import build_visual_state

_STATE_TEXT = {
    "sleeping": "dormant",
    "idle": "neutral",
    "awake": "attentive",
    "processing": "focused",
    "research": "focused",
    "learning": "focused",
    "listening": "listening",
    "neutral": "neutral",
    "active": "active",
    "curious": "curious",
}

_CORE = "#5884d8"
_CORE_DIM = "#3a4f8f"
_RING = "#d8b46c"
_POINTER = "#bedca0"
_BG = "#101218"


class TemporaryShapeRenderer(tk.Canvas):
    def __init__(self, parent, size=132, state="sleeping", bg=_BG):
        super().__init__(parent, width=size, height=size, bg=bg,
                         highlightthickness=0)
        self.size = size
        self._frame = 0
        self._vs = None
        self._last = None
        self._state = str(state).lower().strip()
        self._command = None
        self._metadata = {}
        self._ids = {}
        self._draw_placeholder()

    # -- Tick driver (maya_app._apply_tick) -------------------------------

    def set_visual_state(self, vs, frame=None):
        """Drive from a bounded VisualState at an explicit frame index.

        ``frame`` may be omitted in live UI (uses the internal tick counter,
        so identical call sequences replay identically); tests pass it
        explicitly for exact replay.
        """
        self._vs = vs
        if frame is None:
            self._frame += 1
        else:
            self._frame = int(frame)
        self._last = project_shape(vs, self._frame)
        self._redraw()

    def set_face_state(self, fs, aura=None):
        """Convert the driven FaceState into a VisualState and drive it.

        Implemented so the shared ``_apply_tick`` loop can treat this surface
        like the others; state derivation keeps the renderer downstream.
        """
        vs = build_visual_state(fs)
        self.set_visual_state(vs)

    # -- VisualSurface contract ------------------------------------------

    def set_state(self, state):
        self._state = str(state).lower().strip()
        if self._state not in _STATE_TEXT:
            self._state = "sleeping"

    def set_command(self, command):
        self._command = dict(command) if isinstance(command, dict) else None

    def set_metadata(self, meta):
        self._metadata = dict(meta or {})

    def state_text(self):
        return _STATE_TEXT.get(self._state, _STATE_TEXT["sleeping"])

    def status_text(self):
        if self._vs is None:
            return "shape: no state yet"
        return "shape: %s (att %.2f act %.2f fcs %.2f)" % (
            self._vs.semantic, self._vs.attention, self._vs.activity,
            self._vs.focus)

    def is_placeholder(self):
        return False

    def snapshot(self):
        return {
            "kind": "temporary_shape",
            "frame": self._frame,
            "visual": self._vs.as_dict() if self._vs is not None else None,
            "projected": self._last.as_dict_safe() if self._last is not None
            else None,
            "state": self._state,
            "size": self.size,
        }

    # -- deterministic drawing -------------------------------------------

    def _draw_placeholder(self):
        """A calm, stable placeholder circle before any state arrives."""
        c = self.size / 2.0
        r = self.size * 0.14
        self._ids["orb"] = self.create_oval(
            c - r, c - r, c + r, c + r, fill=_CORE_DIM, outline="")
        self._ids["ring"] = self.create_line(0, 0, 1, 1, fill=_RING, width=2)
        self._ids["pointer"] = self.create_line(0, 0, 0, 0, fill=_POINTER,
                                                width=2)

    def _px(self, value):
        return int(round(value * self.size))

    def _redraw(self):
        p = self._last
        if p is None:
            return
        size = self.size
        cx, cy = self._px(p.cx), self._px(p.cy)
        r = self._px(p.radius)

        # orb (roll is cosmetic on a sphere; the ring carries the attitude)
        self.coords(self._ids["orb"], cx - r, cy - r, cx + r, cy + r)
        self.itemconfigure(self._ids["orb"], fill=_CORE if not p.resting
                           else _CORE_DIM)

        # orbit ring as a sampled ellipse polyline (exact phase, deterministic)
        rx = p.ring_rx * size
        ry = p.ring_ry * size
        pts = []
        for i in range(24):
            theta = p.ring_phase + 6.283185307179586 * i / 24
            x = cx + rx * math.cos(theta)
            y = cy + ry * math.sin(theta)
            pts.extend((int(round(x)), int(round(y))))
        self.coords(self._ids["ring"], *pts)

        # pointer
        if p.pointer_len > 0:
            tx = self._px(p.cx + p.pointer_dx * p.pointer_len)
            ty = self._px(p.cy + p.pointer_dy * p.pointer_len)
            self.coords(self._ids["pointer"], cx, cy, tx, ty)
            self.itemconfigure(self._ids["pointer"], state="normal")
        else:
            self.coords(self._ids["pointer"], cx, cy, cx, cy)
            self.itemconfigure(self._ids["pointer"], state="hidden")