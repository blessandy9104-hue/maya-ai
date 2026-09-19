"""Maya's visual language — symbols, patterns, and meaning.

Visual communication is expressed through geometric primitives, neural
structures, particle formations, and light movement — never generic floating
text. Patterns are temporary overlays; they never modify identity.
"""
from __future__ import annotations

import math

from ..identity import load_engine_config
from ..wireframe.math_coordinator import MATH_AGENT

_FOCALS = {
    "none": (0.5, 0.46),
    "center": (0.5, 0.46),
    "field": (0.5, 0.58),
    "crown": (0.5, 0.30),
    "network": (0.5, 0.50),
    "eyes": (0.5, 0.40),
    "gaze": (0.5, 0.42),
}


def _c(x, y):
    return {"x": x, "y": y}


class SymbolComposer:
    """Resolves a pattern mode into deterministic unit-space primitives."""

    def __init__(self, symbols=None, patterns=None, meanings=None):
        self.symbols = symbols if symbols is not None else load_engine_config("visual_symbols").get("symbols", {})
        self.patterns = patterns if patterns is not None else load_engine_config("visual_patterns").get("patterns", {})
        self.meanings = meanings if meanings is not None else load_engine_config("visual_meanings").get("meaning", {})

    def mode_for(self, activity_or_meaning: str) -> str:
        text = str(activity_or_meaning or "idle").strip().lower()
        if text in self.patterns:
            return text
        meaning = load_engine_config("visual_meanings").get("map", {})
        return meaning.get(text, "calm")

    def meaning_of(self, mode: str) -> str:
        return self.meanings.get(mode, "")

    def symbol_vector(self, mode: str) -> tuple:
        """Pattern signature: presence vector over the union of symbol names,
        used by the agent for pattern alignment."""
        pattern = self.patterns.get(mode) or self.patterns.get("calm") or {}
        names = sorted(pattern.get("symbols", []))
        return tuple(1.0 if name in names else 0.0
                     for name in sorted({n for p in self.patterns.values() if isinstance(p, dict)
                                         for n in p.get("symbols", [])}))

    def mode_similarity(self, mode_a: str, mode_b: str) -> float:
        """Pattern alignment between two modes (via the Math Coordination
        Agent): ``clamp01(dot(normalize(sig_a), normalize(sig_b)))``."""
        return MATH_AGENT.pattern_similarity(self.symbol_vector(mode_a),
                                             self.symbol_vector(mode_b))

    def transition(self, mode_a: str, mode_b: str, t: float = 0.5) -> tuple:
        """Pattern transition between two modes (via the Math Coordination
        Agent): ``lerp(sig_a, sig_b, clamp01(t))`` per dimension — the only
        allowed path from one interpreted pattern to another."""
        return tuple(MATH_AGENT.pattern_transition(a, b, t)
                     for a, b in zip(self.symbol_vector(mode_a),
                                     self.symbol_vector(mode_b)))

    def primitives(self, mode: str, t: float = 0.0, intensity: float = 1.0):
        intensity = MATH_AGENT.control(float(intensity))
        pattern = self.patterns.get(mode) or self.patterns.get("calm") or {}
        anchor = _FOCALS.get(pattern.get("focal", "field"), _FOCALS["field"])
        prims = []
        for name in pattern.get("symbols", []):
            symbol = self.symbols.get(name) or {}
            for shape in symbol.get("shapes", []):
                gen = getattr(self, "_shape_" + shape, None)
                if gen:
                    prims.extend(gen(anchor, intensity, t))
        return prims

    # ----- primitive builders -----
    @staticmethod
    def _line(pts, color="neural", width=1.0):
        return {"type": "line", "points": [[float(x), float(y)] for x, y in pts],
                "color": color, "width": float(width)}

    @staticmethod
    def _ring(cx, cy, r, color="glow", width=1.0):
        return {"type": "ring", "x": float(cx), "y": float(cy), "r": float(r),
                "color": color, "width": float(width)}

    @staticmethod
    def _arc(cx, cy, r, a0, a1, color="glow", width=1.0):
        return {"type": "arc", "x": float(cx), "y": float(cy), "r": float(r),
                "a0": float(a0), "a1": float(a1), "color": color, "width": float(width)}

    @classmethod
    def _dot(cls, x, y, r, color="neural"):
        return {"type": "dot", "x": float(x), "y": float(y), "r": float(r), "color": color}

    # ----- shapes -----
    def _shape_arcs_inward(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for i in range(3):
            r = 0.09 + i * 0.014
            a_mid = 180 + i * 12 + (t * 0.05) % 360
            out.append(self._arc(x, y, r, a_mid - 55, a_mid + 55, "glow", 1.1))
        return out

    def _shape_central_core(self, anchor, intensity, t):
        x, y = anchor
        return [self._dot(x, y, 0.006 + 0.002 * intensity, "glow"),
                self._ring(x, y, 0.045, "glow", 1.0)]

    def _shape_orbit_rings(self, anchor, intensity, t):
        x, y = anchor
        return [self._ring(x, y, 0.09 * (1 + 0.04 * math.sin(t * 0.1)), "neural", 0.8),
                self._ring(x, y, 0.115 * (1 - 0.04 * math.sin(t * 0.1)), "neural", 0.7)]

    def _shape_radial_spokes(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for i in range(8):
            a = math.radians(i * 45 + (t % 360))
            r = 0.05 + 0.03 * intensity
            out.append(self._line([(x, y), (x + r * math.cos(a), y + r * math.sin(a))], "neural", 0.8))
        return out

    def _shape_expanding_rings(self, anchor, intensity, t):
        x, y = anchor
        k = 0.5 + 0.5 * math.sin(t * 0.12)
        return [self._ring(x, y, 0.07 + 0.05 * k, "soft", 0.9),
                self._ring(x, y, 0.10 + 0.05 * k, "neural", 0.8)]

    def _shape_scatter_nodes(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for i in range(6):
            a = math.radians(i * 60 + (t % 360))
            r = 0.05 + (i % 3) * 0.02
            out.append(self._dot(x + r * math.cos(a), y + r * math.sin(a), 0.0035, "neural"))
        return out

    def _shape_growth_nodes(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for i in range(4):
            yy = y - 0.03 - i * 0.022
            r = 0.005 - i * 0.0008
            out.append(self._dot(x + math.sin(t * 0.1 + i) * 0.02, yy, max(0.002, r), "glow"))
        return out

    def _shape_tendril_arcs(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for s in (-1, 1):
            for i in range(2):
                cx = x + s * (0.06 + i * 0.01)
                r = 0.035
                a_mid = 180 + s * i * 18 + (t * 0.04) % 22
                out.append(self._arc(cx, y + s * 0.01 * i, r, a_mid - 40, a_mid + 40, "neural", 0.7))
        return out

    def _shape_link_lines(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for i in range(3):
            a = math.radians(20 + i * 30)
            r1, r2 = 0.04, 0.09
            p1 = (x + r1 * math.cos(a), y + r1 * math.sin(a))
            p2 = (x + r2 * math.cos(a + 0.5), y + r2 * math.sin(a + 0.5))
            out.append(self._line([p1, p2], "neural", 0.7))
        return out

    def _shape_rekindled_nodes(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for i in range(8):
            a = math.radians(i * 45)
            r = 0.075
            ppm = 1 if (i + int(t // 6)) % 3 else 0
            out.append(self._dot(x + r * math.cos(a), y + r * math.sin(a),
                                 0.0032 if ppm else 0.002, "glow" if ppm else "soft"))
        return out

    def _shape_pathway_links(self, anchor, intensity, t):
        x, y = anchor
        pts = []
        for i in range(5):
            a = -0.6 + i * 0.3
            pts.append((x + 0.07 * math.sin(a + (t * 0.03) % 0.4), y - 0.04 + i * 0.02))
        return [self._line(pts, "neural", 0.9)]

    def _shape_soft_glow_rings(self, anchor, intensity, t):
        x, y = anchor
        return [self._ring(x, y, 0.055, "soft", 2.4), self._ring(x, y, 0.075, "soft", 1.6)]

    def _shape_chevron_lines(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for s in (-1, 1):
            for i, dx in enumerate((0.015, 0.032)):
                out.append(self._line([(x + s * (0.02 + dx), y - 0.03),
                                       (x + s * dx, y),
                                       (x + s * (0.02 + dx), y + 0.03)], "glow", 1.0))
        return out

    def _shape_alert_arc(self, anchor, intensity, t):
        x, y = anchor
        return [self._arc(x, y - 0.03, 0.14, 200, 340, "glow", 1.4)]

    def _shape_pulse_ring(self, anchor, intensity, t):
        x, y = anchor
        k = 1 + 0.05 * math.sin(t * 0.25)
        return [self._ring(x, y, 0.12 * k, "glow", 1.1)]

    def _shape_grid_lines(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for dx in (-0.05, 0.0, 0.05):
            out.append(self._line([(x + dx, y - 0.06), (x + dx, y + 0.06)], "soft", 0.6))
        for dy in (0.0, 0.045):
            out.append(self._line([(x - 0.06, y + dy), (x + 0.06, y + dy)], "soft", 0.6))
        return out

    def _shape_anchor_dots(self, anchor, intensity, t):
        x, y = anchor
        out = [self._dot(x, y, 0.005, "glow")]
        for dx, dy in ((-0.05, -0.03), (0.05, -0.03), (-0.05, 0.03), (0.05, 0.03)):
            out.append(self._dot(x + dx, y + dy, 0.0025, "neural"))
        return out

    def _shape_boundary_arc(self, anchor, intensity, t):
        x, y = anchor
        return [self._arc(x, y, 0.11, 15, 165, "neural", 0.9)]

    def _shape_iris_arc(self, anchor, intensity, t):
        x, y = (0.5, 0.40)
        return [self._arc(x, y, 0.13, 180, 360, "glow", 1.0)]

    def _shape_sideline_arcs(self, anchor, intensity, t):
        out = []
        for s in (-1, 1):
            out.append(self._arc(0.5 + s * 0.17, 0.40, 0.045, 130, 320, "neural", 0.8))
        return out

    def _shape_wave_lines(self, anchor, intensity, t):
        x, y = anchor
        out = []
        for k in range(2):
            pts = []
            for i in range(9):
                xx = x - 0.14 + 0.035 * i
                pts.append((xx, y + k * 0.045 + 0.015 * math.sin(i * 0.9 + t * 0.13)))
            out.append(self._line(pts, "neural" if k == 0 else "soft", 0.8))
        return out

    def _shape_drift_particles(self, anchor, intensity, t):
        out = []
        for i in range(4):
            phase = (t * 0.05 + i * 0.8) % 1.0
            out.append(self._dot(0.3 + 0.5 * phase, 0.55 + 0.02 * math.sin(i + t * 0.1), 0.003, "neural"))
        return out

    def _shape_balanced_ring(self, anchor, intensity, t):
        x, y = anchor
        return [self._ring(x, y, 0.10, "dim", 1.0)]


if __name__ == "__main__":
    import json as _json
    composer = SymbolComposer()
    sample = composer.primitives("convergence", t=1.0, intensity=0.8)
    print(_json.dumps(sample, indent=2)[:1200])