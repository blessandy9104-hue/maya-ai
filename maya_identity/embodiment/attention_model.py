"""Attention model — gaze and focus direction for the embodiment layer.

Purely presentational math: tracks a normalized focus point and a smooth gaze
direction. It does not create intelligence and represents state only.
"""
from __future__ import annotations

from ..wireframe.math_coordinator import MATH_AGENT
from ..wireframe import presentation_math as PresentationMath

_DEFAULT = (0.5, 0.42)


class AttentionModel:
    def __init__(self, x=None, y=None, attract=0.12):
        self.x, self.y = (float(x) if x is not None else _DEFAULT[0],
                          float(y) if y is not None else _DEFAULT[1])
        self.attract = attract
        self.x = PresentationMath.clip(self.x)
        self.y = PresentationMath.clip(self.y)

    def update(self, x=None, y=None, intensity=None):
        if x is not None:
            # focus is a pattern-driven state change: the gaze settles toward
            # the target through exp_smooth, grounded by the Math Coordination
            # Agent (never a raw increment).
            self.x = PresentationMath.clip(
                MATH_AGENT.pattern_state(self.x, x, self.attract))
        if y is not None:
            self.y = PresentationMath.clip(
                MATH_AGENT.pattern_state(self.y, y, self.attract))
        if intensity is not None:
            self.intensity = PresentationMath.clip(intensity)
        return self.snapshot()

    def drift(self, dx=0.0, dy=0.0):
        self.update(x=self.x + dx, y=self.y + dy)

    def decay(self, step=1.0):
        k = 1.0 - PresentationMath.decay_alpha(step)
        self.x = PresentationMath.clip(
            MATH_AGENT.pattern_state(self.x, _DEFAULT[0], 1.0 - k))
        self.y = PresentationMath.clip(
            MATH_AGENT.pattern_state(self.y, _DEFAULT[1], 1.0 - k))

    def focus_point(self):
        return (self.x, self.y)

    def gaze(self):
        return {
            "gaze_x": PresentationMath.clip(
                PresentationMath.remap_centered(self.x, 0.5), -1.0, 1.0),
            "gaze_y": PresentationMath.clip(
                PresentationMath.remap_centered(self.y, _DEFAULT[1]), -1.0, 1.0),
        }

    def snapshot(self):
        snap = self.gaze()
        snap["x"] = self.x
        snap["y"] = self.y
        snap["intensity"] = getattr(self, "intensity", 0.5)
        return snap