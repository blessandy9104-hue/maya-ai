"""MayaFace — Maya's visual embodiment (Visual Interface Layer).

Presents Maya's identity and current cognitive state. This widget is a pure
presentation surface:

- it cannot execute commands
- it cannot access privileged systems
- it cannot modify memory or security settings
- it cannot control Maya's intelligence

It only maps a validated visual state to an appearance. Animation is delegated
to the config-driven animation system (``maya_identity.animation``), never
hardcoded here.
"""
from __future__ import annotations

import hashlib
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import PhotoImage

from . import identity as _identity
from .animation import AnimationDriver
from .cognitive_state import normalize_visual_state
from .visual_surface import FRAME_MS_DEFAULT, LoopTimer, VisualSurface

PLACEHOLDER_BG = (24, 30, 55)
PLACEHOLDER_FG = "#9a8cff"

_SCALE_CACHE: dict = {}


def _fit_src(path: str, size: int) -> str:
    key = (path, size)
    cached = _SCALE_CACHE.get(key)
    if cached and Path(cached).exists():
        return cached
    target = max(16, size)
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGBA")
            if im.width <= target and im.height <= target:
                _SCALE_CACHE[key] = path
                return path
            ratio = target / max(im.width, im.height)
            new = (max(1, int(im.width * ratio)), max(1, int(im.height * ratio)))
            im = im.resize(new, Image.Resampling.LANCZOS)
            digest = hashlib.md5(f"{path}:{new}".encode("utf-8")).hexdigest()[:12]
            out = Path(tempfile.gettempdir()) / f"maya_face_scale_{digest}_{new[0]}x{new[1]}.png"
            im.save(out, format="PNG")
            _SCALE_CACHE[key] = str(out)
            return str(out)
    except Exception:
        _SCALE_CACHE[key] = path
        return path
RING = {
    "awake": "#6d7cff",
    "processing": "#9a8cff",
    "listening": "#38bdf8",
    "research": "#4d5bb5",
    "sleeping": "#2a3353",
    "offline": "#3a3f55",
}
STATE_TEXT = {
    "awake": "presence · awake · aware",
    "processing": "presence · processing · focused",
    "listening": "presence · listening · attentive",
    "research": "presence · research · analytical",
    "sleeping": "presence · sleeping · dormant",
    "offline": "presence · offline · inactive",
}


class MayaFace(VisualSurface, tk.Canvas):
    def __init__(self, master, size=176, state="sleeping", bg="#0a0e1a", **kwargs):
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, **kwargs)
        self.size = size
        self.state = normalize_visual_state(state)
        self.avatar = _identity.get_avatar_path()
        self.photo = None
        self.image_id = None
        self.ring_id = None
        self.animator = AnimationDriver(self)
        self._pulse_running = False
        self._pulse_n = 0
        self._loop = LoopTimer(self, FRAME_MS_DEFAULT, active=False)
        self._loop.attach(self._pulse_tick)
        self._load_image()
        self._draw_ring()
        if self.avatar.get("is_placeholder"):
            self._draw_badge()
        self.set_state(self.state)

    def _asset_for_size(self):
        size = self.size
        avatar = self.avatar
        if size >= 340:
            return avatar.get("portrait") or avatar.get("portrait_medium") or avatar.get("portrait_small")
        if size >= 200:
            return avatar.get("portrait_medium") or avatar.get("portrait") or avatar.get("portrait_small")
        if size >= 96:
            return avatar.get("portrait_small") or avatar.get("icon_png") or avatar.get("portrait")
        return avatar.get("icon_png") or avatar.get("portrait_small") or avatar.get("portrait")

    def _load_image(self):
        path = self._asset_for_size()
        if path is None:
            return
        src = _fit_src(str(path), self.size)
        self.photo = PhotoImage(file=src)
        self.image_id = self.create_image(self.size // 2, self.size // 2, image=self.photo)

    def _draw_ring(self):
        margin = max(2, int(self.size * 0.035))
        self.ring_id = self.create_oval(
            margin, margin, self.size - margin, self.size - margin,
            outline=RING["sleeping"], width=2,
        )

    def _draw_badge(self):
        pad = max(3, int(self.size * 0.02))
        box = tk.Frame(self, bg="#0a0e1a")
        bg = "#%02x%02x%02x" % PLACEHOLDER_BG
        self.badge = tk.Label(box, text="PLACEHOLDER", bg=bg, fg=PLACEHOLDER_FG,
                              font=("Segoe UI", max(6, int(self.size * 0.045)), "bold"), padx=8, pady=2)
        self.badge.pack()
        self.create_window(self.size // 2, self.size - max(14, int(self.size * 0.08)), window=box)

    def set_state(self, state):
        state = normalize_visual_state(state)
        self.state = state
        self.itemconfigure(self.ring_id, outline=RING.get(state, RING["sleeping"]))
        if state == "awake":
            self.itemconfigure(self.ring_id, width=3)
            self._start_pulse()
        elif state == "sleeping":
            self.itemconfigure(self.ring_id, width=2)
            self._stop_pulse()
        else:
            self.itemconfigure(self.ring_id, width=2)
            self._stop_pulse()

    def _start_pulse(self):
        if self._pulse_running:
            return
        self._pulse_running = True
        self._pulse_tick()          # immediate first tick (original cadence)
        self._loop.set_active(True)

    def _stop_pulse(self):
        self._pulse_running = False
        self._loop.set_active(False)

    def _pulse_tick(self):
        if not self._pulse_running or self.state != "awake":
            self._pulse_running = False
            self._loop.set_active(False)
            return
        self._pulse_n += 1
        self.animator.refresh_activity()

    def set_command(self, command):
        """Raster surface has no per-tick command channel; part of the
        shared ``VisualSurface`` contract. Commands are ignored so both
        surfaces expose the same interface."""

    def destroy(self):
        self._loop.cancel()
        super().destroy()

    def is_placeholder(self):
        return bool(self.avatar.get("is_placeholder"))

    def status_text(self):
        identity = _identity.load_identity()
        version = _identity.identity_version()
        base = (
            f"{identity.get('canonical_name', 'Maya')} "
            f"v{version[0]} · face {version[1]}"
        )
        if self.avatar.get("is_placeholder"):
            return base + " · PLACEHOLDER identity (canonical face pending)"
        return base

    def state_text(self):
        return STATE_TEXT.get(self.state, STATE_TEXT["sleeping"])


if __name__ == "__main__":
    root = tk.Tk()
    root.title("MayaFace preview")
    face = MayaFace(root, size=176, state="awake")
    face.pack(padx=12, pady=12)
    print(face.status_text())
    root.after(2500, root.destroy)
    root.mainloop()