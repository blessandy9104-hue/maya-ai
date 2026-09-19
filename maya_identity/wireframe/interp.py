"""Interpolation, clamping, and smoothing utilities for the wireframe face.

Pure math; no Tk dependency. Every primitive referenced here lives in the
``rig_math`` layer (Maya's mathematical cognition); this module re-exports
them and hosts the ``Smoother`` exponential low-pass driver, which advances
values with ``exp_smooth(current, target, lambda)``.
"""
from __future__ import annotations

from .rig_math import clamp01, clamp, lerp, smoothstep, exp_smooth


class Smoother:
    """Exponential low-pass smoother. Current values ease toward targets.

    Targets are set independently; ``step`` advances all values using
    ``rig_math.exp_smooth`` with a per-name easing constant (``lambda``).
    This gives the face its characteristic eased, non-jumpy motion.
    """

    def __init__(self, names, alpha=0.32):
        self.alpha = clamp01(alpha)
        self._alpha = {name: self.alpha for name in names}
        self._cur = {name: 0.0 for name in names}
        self._tgt = {name: 0.0 for name in names}

    def names(self):
        return list(self._cur.keys())

    def set_alpha(self, name, alpha):
        if name in self._cur:
            self._alpha[name] = clamp01(alpha)

    def set_target(self, name, value, immediate=False):
        if name not in self._cur:
            return
        v = clamp01(value)
        self._tgt[name] = v
        if immediate:
            self._cur[name] = v

    def set_targets(self, values, immediate=False):
        if not values:
            return
        for name, value in values.items():
            self.set_target(name, value, immediate=immediate)

    def set_all(self, values, immediate=False):
        for name in self._cur:
            self.set_target(name, 0.0, immediate=immediate)
        for name, value in values.items():
            self.set_target(name, value, immediate=immediate)

    def clear_targets(self, immediate=False):
        for name in self._cur:
            self.set_target(name, 0.0, immediate=immediate)

    def step(self):
        for name in self._cur:
            self._cur[name] = exp_smooth(
                self._cur[name], self._tgt[name], self._alpha[name])
        return self._cur

    def snapshot(self):
        return dict(self._cur)