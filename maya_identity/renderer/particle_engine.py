"""Particle engine — deterministic holographic particle field.

Particles exist only as visual motion. They are seeded from Maya's geometry
seed so the same presence is generated every time, and they express states via
density / speed / brightness multipliers from the active expression.
"""
from __future__ import annotations

import random


class ParticleField:
    def __init__(self, seed: int, count: int, bounds=(0.12, 0.88, 0.08, 0.9)):
        self.rng = random.Random(seed)
        self.count = count
        self.bounds = bounds
        self.parts = [self._spawn() for _ in range(count)]

    def _spawn(self):
        x0, x1, y0, y1 = self.bounds
        return {
            "x": self.rng.uniform(x0, x1),
            "y": self.rng.uniform(y0, y1),
            "vx": self.rng.uniform(-0.004, 0.004),
            "vy": self.rng.uniform(-0.003, 0.003),
        }

    def step(self, mult: float = 1.0):
        x0, x1, y0, y1 = self.bounds
        for p in self.parts:
            p["x"] += p["vx"] * mult
            p["y"] += p["vy"] * mult
            if p["x"] < x0:
                p["x"], p["vx"] = x0, abs(p["vx"])
            elif p["x"] > x1:
                p["x"], p["vx"] = x1, -abs(p["vx"])
            if p["y"] < y0:
                p["y"], p["vy"] = y0, abs(p["vy"])
            elif p["y"] > y1:
                p["y"], p["vy"] = y1, -abs(p["vy"])

    def draw(self, canvas, px, py, density=1.0, brightness=1.0,
             palette=None, radius=1.2):
        palette = palette or ("#38bdf8", "#2543a8", "#5b6488")
        n = max(4, int(self.count * max(0.05, density)))
        scale_r = max(0.6, radius * brightness)
        for p in self.parts[:n]:
            x, y = px(p["x"]), py(p["y"])
            color = palette[int(p["x"] * 997 + p["y"] * 131) % len(palette)]
            canvas.create_oval(x - scale_r, y - scale_r, x + scale_r, y + scale_r,
                               outline="", fill=color)