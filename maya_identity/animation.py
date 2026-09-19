"""Maya animation system.

This module is the single place that drives Maya's visual animation. It is
configuration-driven (``configuration/animation.json``) and never hardcoded
inside the GUI.

Phase 1: only the architecture runs here. Every capability (blink, breath,
gaze, micro-expression, voice sync) is gated by ``animation.capabilities.<name>``
(all ``false`` in phase 1). The driver emits a scalar ``activity`` pulse derived
from the visibility state, so Maya's presence feels alive without inventing new
facial geometry.

Decorators drawn here (``refresh_activity``) wrap the MayaFace canvas with a
thin luminous rim that all dynamic states can reuse. Holographic effects are
cosmetic only and always respect the appearance.json ``holographic_effects.enabled``
flag.
"""
from __future__ import annotations

import math
from pathlib import Path

from . import identity as _identity

ROOT = Path(__file__).resolve().parent
ANIMATION_FILE = ROOT / "configuration" / "animation.json"

ALLOWED = ("awake", "processing", "listening", "research", "sleeping", "offline")


def _anim() -> dict:
    return _identity.get_animation_config()


def installed_capabilities() -> frozenset:
    caps = _anim().get("capabilities", {})
    return frozenset(name for name, value in caps.items() if value)


def effective_state(raw: str) -> str:
    states = _anim().get("states", {})
    if raw in ALLOWED and raw in states:
        return raw
    return "sleeping"


class AnimationDriver:
    def __init__(self, face) -> None:
        self.face = face
        self.canvas = face.master if face else None
        self._speed = 1.0
        self._step = 0
        self._rim_group = "anim_rim"
        self._running = False

    def set_speed(self, speed: float) -> None:
        try:
            self._speed = max(0.1, min(3.0, float(speed)))
        except (TypeError, ValueError):
            self._speed = 1.0

    def glyph_status(self) -> str:
        caps = installed_capabilities()
        if not caps:
            return "arch"
        state = effective_state(getattr(self.face, "state", "sleeping"))
        return "arch|" + ",".join(sorted(caps)) + "|" + state

    def refresh_activity(self) -> bool:
        """Emit a single config-driven activity pulse (Scalar presence)."""
        caps = installed_capabilities()
        state = effective_state(getattr(self.face, "state", "sleeping"))
        glow = _anim().get("states", {}).get(state, {}).get("glow", "dim")
        if glow in ("none", "reduced") or not self.canvas:
            self._clear_rim()
            return False
        frame = int(self._step * self._speed)
        self._step += 1
        phase = (frame % 90) / 90.0
        breathe = 0.5 + 0.5 * math.sin(phase * 2 * math.pi)
        pulses = 0.45 + 0.35 * breathe
        self._draw_rim(pulses)
        return True

    def _clear_rim(self) -> None:
        if self.canvas:
            try:
                self.canvas.delete(self._rim_group)
            except Exception:
                pass

    def _draw_rim(self, pulses: float) -> None:
        if not self.canvas:
            return
        try:
            self._clear_rim()
            size = self.face.size if hasattr(self.face, "size") else 176
            cx = cy = 0.5 * size
            radius = 0.46 * size * pulses
            color = self._interpolate("#6d7cff", pulses)
            self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                    outline=color, width=1, tags=self._rim_group)
        except Exception:
            pass

    @staticmethod
    def _interpolate(hex_color: str, alpha: float) -> str:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        step = int(max(0.0, min(1.0, alpha)) * 255)
        dark = (10, 14, 26)
        return "#%02x%02x%02x" % (
            r + (dark[0] - r) * step // 255,
            g + (dark[1] - g) * step // 255,
            b + (dark[2] - b) * step // 255,
        )