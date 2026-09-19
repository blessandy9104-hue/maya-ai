"""Hologram renderer and ProceduralFace widget — Maya's procedural visual body.

Maya's identity is the mathematical structure in ``geometry/``. This engine is
only the body she wears: it renders the same geometry every time, transforms it
per the active expression, and animates it from ``configuration/animation.json``.
Temporary symbols/overlays never modify identity.

Presentation surface only: it cannot execute commands, access private files,
modify memory, change permissions, or contact the intelligence core. It reacts
to the same validated read-only visual-state signals as every other surface.
"""
from __future__ import annotations

import math
import tkinter as tk

from .. import identity as _identity
from ..cognitive_state import normalize_visual_state
from ..visual_language import SymbolComposer
from ..visual_surface import FRAME_MS_DEFAULT, LoopTimer, VisualSurface
from ..wireframe.math_coordinator import MATH_AGENT
from ..wireframe import presentation_math as PresentationMath
from .geometry_renderer import GeometryRenderer
from .particle_engine import ParticleField

# The visual body applies a pattern-derived command to the frame as bounded,
# smoothed state changes: every command merge converges through the Math
# Coordination Agent (``pattern_state``, i.e. ``exp_smooth``) toward the
# target at a strong alpha. There are no raw ``max`` comparisons and no raw
# increments on the working expression.
COMMAND_MERGE_ALPHA = 0.9

STATE_TEXT = {
    "awake": "procedural presence · awake · aware",
    "processing": "procedural presence · processing · focused",
    "listening": "procedural presence · listening · attentive",
    "research": "procedural presence · research · analytical",
    "learning": "procedural presence · learning · integrating",
    "sleeping": "procedural presence · sleeping · dormant",
    "offline": "procedural presence · offline · inactive",
}

EXPRESSION_BY_STATE = {
    "awake": "idle",
    "processing": "processing",
    "listening": "listening",
    "research": "research",
    "learning": "learning",
    "sleeping": "sleeping",
    "offline": "sleeping",
}


class HologramRenderer:
    """Composites geometry + expression + particles into one holographic frame."""

    def __init__(self, canvas, size: int, bundle: dict, palette: dict,
                 effects: dict, anim: dict):
        self.c = canvas
        self.size = size
        self.pal = palette
        self.effects = effects
        self.anim = anim
        self.geom = GeometryRenderer(bundle)
        self.state = "sleeping"
        self.expr = _identity.load_expression("idle")
        self.particles = ParticleField(bundle["identity"].get("seed", 21098),
                                       int(effects.get("particles", {}).get("count", 200)))
        self._f = max(0.22, size / 176.0)  # quality scale
        # real-time expression engine — read-only toggles and command state
        _eg = _identity.load_engine_config("expression_engine")
        self._cfg_gaze = bool(_eg.get("gaze", {}).get("enabled", False))
        self._cfg_micro = bool(_eg.get("micro_expression", {}).get("enabled", False))
        self._cfg_breathing = bool(_eg.get("breathing", {}).get("enabled", False))
        self._cfg_neural = bool(_eg.get("neural_motion", {}).get("enabled", False))
        self._cfg_distortion = bool(_eg.get("holographic_distortion", {}).get("enabled", False))
        self._command = None
        self._eff_scale = None
        self._dist = 0.0
        self._micro_x = 0.0
        self._micro_y = 0.0
        self._composer = SymbolComposer()

    def set_command(self, command):
        """Accept a read-only visual command dict from the presence engine."""
        if command is None:
            self._command = None
            return
        if not isinstance(command, dict):
            return
        clean = {}
        for key in ("eye_focus", "neural_activity", "particle_density",
                    "glow_intensity", "micro", "breath", "distortion"):
            try:
                clean[key] = float(command.get(key, 0.0))
            except (TypeError, ValueError):
                clean[key] = 0.0
        clean["gaze_x"] = PresentationMath.clip(command.get("gaze_x", 0.0), -1.0, 1.0)
        clean["gaze_y"] = PresentationMath.clip(command.get("gaze_y", 0.0), -1.0, 1.0)
        clean["symbol_mode"] = str(command.get("symbol_mode", "none"))
        self._command = clean

    def set_state(self, state: str):
        self.state = normalize_visual_state(state)
        name = EXPRESSION_BY_STATE.get(self.state, "idle")
        expr = _identity.load_expression(name) or _identity.load_expression("idle")
        self.expr = expr

    # ----- coordinate mapping -----
    def px(self, x):
        return x * self.size

    def py(self, y):
        return y * self.size

    def _line(self, pts, color, width=1.0, smooth=True):
        flat = []
        for x, y in pts:
            flat.extend((self.px(x), self.py(y)))
        if len(flat) >= 4:
            kw = dict(fill=color, width=max(0.6, width * self._f), smooth=smooth,
                      splinesteps=12)
            self.c.create_line(*flat, **kw)

    def _dot(self, x, y, r, color):
        self.c.create_oval(self.px(x - r), self.py(y - r),
                           self.px(x + r), self.py(y + r), outline="", fill=color)

    def _ring(self, cx, cy, r, color, width=1.0):
        self.c.create_oval(self.px(cx - r), self.py(cy - r),
                           self.px(cx + r), self.py(cy + r),
                           outline=color, width=max(0.6, width * self._f))

    # ----- expression helpers -----
    def _scaled(self, x, y):
        s = self._eff_scale if self._eff_scale is not None else self.expr["geometry"]["scale"]
        return (0.5 + (x - 0.5) * s, 0.46 + (y - 0.46) * s)

    def _shift(self, pts, dx, dy):
        return [(x + dx, y + dy) for x, y in pts]

    def _ring_v(self, cx, cy, r, color, width=1.0, t=0.0, ripple=0.0):
        if ripple > 0:
            pts = []
            n = 36
            for i in range(n):
                a = 2 * math.pi * i / n
                rr = r * (1 + ripple * math.sin(t * 0.18 + i * 0.65))
                pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
            pts.append(pts[0])
            self._line(pts, color, width)
        else:
            self._ring(cx, cy, r, color, width)

    def _work_expr(self, t):
        """Frame-local working expression from the visual command (read-only)."""
        base = self.expr
        cmd = self._command or {}
        work = {
            "geometry": dict(base["geometry"]),
            "eyes": dict(base["eyes"]),
            "brows": dict(base["brows"]),
            "mouth": dict(base["mouth"]),
            "neural": dict(base["neural"]),
            "particles": dict(base["particles"]),
            "glow": dict(base["glow"]),
            "motion": dict(base.get("motion", {})),
            "halo": base.get("halo") or {},
            "double_ring": bool(base.get("double_ring", False)),
            "attention_arc": bool(base.get("attention_arc", False)),
            "symbols": list(base.get("symbols", [])),
        }
        eye = work["eyes"]
        if cmd.get("eye_focus") is not None:
            cur = eye.get("focus", 0.0) or 0.0
            eye["focus"] = MATH_AGENT.pattern_state(cur, cmd["eye_focus"],
                                                    COMMAND_MERGE_ALPHA)
        if self._cfg_gaze and cmd.get("gaze_x") is not None:
            cur = eye.get("iris_shift_x", 0.0) or 0.0
            target = PresentationMath.scale(cmd["gaze_x"], 0.04,
                                            lo=-0.5, hi=0.5)
            eye["iris_shift_x"] = MATH_AGENT.pattern_state(
                cur, target, COMMAND_MERGE_ALPHA)
        if self._cfg_gaze and cmd.get("gaze_y", 0) < 0:
            cur = eye.get("focus", 0.0) or 0.0
            target = PresentationMath.boost(cur, -cmd["gaze_y"], 0.10)
            eye["focus"] = MATH_AGENT.pattern_state(cur, target,
                                                    COMMAND_MERGE_ALPHA)
        if self._cfg_neural and cmd.get("neural_activity") is not None:
            cur = work["neural"].get("activity", 0.0) or 0.0
            work["neural"]["activity"] = MATH_AGENT.pattern_state(
                cur, cmd["neural_activity"], COMMAND_MERGE_ALPHA)
        if cmd.get("particle_density") is not None:
            cur = work["particles"].get("density", 0.0) or 0.0
            work["particles"]["density"] = MATH_AGENT.pattern_state(
                cur, PresentationMath.scale(cmd["particle_density"], 0.9),
                COMMAND_MERGE_ALPHA)
        if cmd.get("glow_intensity") is not None:
            cur = work["glow"].get("intensity", 0.0) or 0.0
            work["glow"]["intensity"] = MATH_AGENT.pattern_state(
                cur, cmd["glow_intensity"], COMMAND_MERGE_ALPHA)
        return work

    def _draw_primitives(self, prims, t):
        palmap = {
            "glow": self.pal.get("glow", "#6d7cff"),
            "neural": self.pal.get("neural", "#38bdf8"),
            "soft": self.pal.get("glow_soft", "#4d5bb5"),
            "dim": self.pal.get("dim", "#5b6488"),
            "ink": self.pal.get("ink", "#e7ebfa"),
        }
        for p in prims:
            color = palmap.get(p.get("color", "neural"), "#38bdf8")
            kind = p.get("type")
            if kind == "line":
                self._line(p["points"], color, p.get("width", 1.0))
            elif kind == "ring":
                self._ring_v(p["x"], p["y"], p["r"], color, p.get("width", 1.0),
                             t=t, ripple=self._dist)
            elif kind == "dot":
                self._dot(p["x"], p["y"], p.get("r", 0.004), color)
            elif kind == "arc":
                pts = []
                a0, a1 = math.radians(p["a0"]), math.radians(p["a1"])
                for i in range(10):
                    a = a0 + (a1 - a0) * i / 9
                    pts.append((p["x"] + p["r"] * math.cos(a), p["y"] + p["r"] * math.sin(a)))
                self._line(pts, color, p.get("width", 1.0))

    def _draw_pattern(self, t):
        if not self._command:
            return
        mode = self._command.get("symbol_mode", "none")
        if not mode or mode == "none":
            return
        intensity = PresentationMath.clip(
            float(self._command.get("glow_intensity", 0.6) or 0.6), 0.3, 1.0)
        prims = self._composer.primitives(mode, t=t, intensity=intensity)
        self._draw_primitives(prims, t)

    def _glow_color(self, key="core"):
        return self.expr["glow"].get(key) or self.pal.get("glow", "#6d7cff")

    def _halo_center(self):
        cy, r = self.geom.halo()
        return 0.5, cy, r

    # ----- symbols (temporary overlays; never identity) -----
    def _draw_symbols(self, t):
        for kind in self.expr.get("symbols", []):
            method = getattr(self, "_sym_" + kind, None)
            if method:
                method(t)

    def _sym_flow_sweep(self, t):
        for k in range(3):
            base = 0.5 + k * 0.06
            pts = []
            for i in range(8):
                x = 0.3 + 0.4 * i / 7
                y = 0.62 + 0.02 * math.sin(t * 0.2 + k + i * 0.6)
                pts.append((x, y + (base - 0.5) * 0.35))
            self._line(pts, self.pal.get("neural", "#38bdf8"), 1.0)

    def _sym_data_pattern(self, t):
        for r in range(5):
            for cidx in range(8):
                x = 0.26 + cidx * 0.07
                y = 0.2 + r * 0.045
                if int(x * 100 + t) % 3:
                    self._dot(x, y, 0.0035, self.pal.get("neural_soft", "#2543a8"))

    def _sym_coordinate_grid(self, t):
        c = self.pal.get("dim", "#5b6488")
        for i, x in enumerate((0.62, 0.68, 0.74, 0.8)):
            self._line([(x, 0.2), (x, 0.42)], c, 0.6)
        for i, y in enumerate((0.2, 0.27, 0.34, 0.42)):
            self._line([(0.62, y), (0.8, y)], c, 0.6)

    def _sym_ring_formation(self, t):
        cx, cy, r = self._halo_center()
        for k, rr in enumerate((r * 0.82, r * 0.76)):
            partial = []
            for i in range(12):
                a = math.radians(200 + i * 8) + t * 0.02
                partial.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
            self._line(partial, self.pal.get("neural", "#38bdf8"), 0.8)

    def _sym_node_integrate(self, t):
        cx, cy, r = self._halo_center()
        for k in range(5):
            a = math.radians(60 + k * 55)
            x = cx + r * 0.93 * math.cos(a)
            y = cy + r * 0.93 * math.sin(a) * 0.6
            self._dot(x, y, 0.006, self._glow_color())

    # ----- main render -----
    def render(self, t: int):
        c = self.c
        c.delete("all")
        # real-time expression engine: frame-local working expression (read-only)
        expr = self._work_expr(t) if self._command else self.expr
        pal = self.pal
        act = expr["neural"]["activity"]
        pulse = 0.5 + 0.5 * math.sin(t * 0.14 + self.geom.np["pulse"]["base_jitter"])
        glow_intensity = expr["glow"]["intensity"]

        # command-driven, config-gated presentational transforms
        if self._command:
            breath = PresentationMath.clip(self._command.get("breath") or 0.0)
            if self._cfg_breathing and breath > 0:
                base_s = expr["geometry"]["scale"]
                self._eff_scale = base_s * (1.0 + PresentationMath.scale(breath, 0.0035) * math.sin(t * 0.07))
            dist = PresentationMath.clip(self._command.get("distortion") or 0.0)
            self._dist = PresentationMath.scale(dist, 0.05) if self._cfg_distortion else 0.0
            if self._cfg_micro:
                micro = PresentationMath.clip(self._command.get("micro") or 0.0)
                self._micro_x = PresentationMath.scale(micro, 0.0022) * math.sin(t * 0.29)
                self._micro_y = PresentationMath.scale(micro, 0.0014) * math.cos(t * 0.23)
            else:
                self._micro_x = self._micro_y = 0.0
        else:
            self._eff_scale = None
            self._dist = 0.0
            self._micro_x = 0.0
            self._micro_y = 0.0

        core = self._glow_color("core")
        ring = self._glow_color("ring")
        font_color = pal.get("ink", "#e7ebfa")
        dimc = pal.get("dim", "#5b6488")

        # light field (ambient beams)
        if self.effects.get("light_field", {}).get("beams", 0):
            self._line([(0.5, 0.04), (0.14, 0.96)], dimc, 0.7)
            self._line([(0.5, 0.04), (0.86, 0.96)], dimc, 0.7)

        # holographic halo (multi-layer glow)
        cx, cy, hr = self._halo_center()
        hal = expr.get("halo", {})
        if hal.get("visible", True):
            lv = self.effects.get("glow", {}).get("levels", [0.5])
            layer_w = max(0, (len(lv) - 1))
            for k in range(layer_w, -1, -1):
                rr = hr + 0.01 * k + 0.5 * k / max(1, len(lv))
                self._ring_v(cx, cy, rr, ring, 2.0 + k * 0.8, t=t, ripple=self._dist)
            hw = 2.2
            self._ring_v(cx, cy, hr, ring, hw, t=t, ripple=self._dist)
            if expr.get("double_ring"):
                self._ring_v(cx, cy, hr * 1.06, self.pal.get("glow_soft", "#4d5bb5"),
                             0.8, t=t, ripple=self._dist)

        # face outline + glow layers (micro expression jitter, non-identity)
        outline = self.geom.face_outline()
        if self._micro_x or self._micro_y:
            outline = self._shift(outline, self._micro_x, self._micro_y)
        for k in range(self.effects.get("hologram", {}).get("layers", 1)):
            self._line([self._scaled(*p) for p in outline], core, 1.1 + k, smooth=True)
        self._line([self._scaled(*p) for p in outline], font_color, 1.3)

        # jaw + contours
        self._line([self._scaled(*p) for p in self.geom.jaw_arc()], dimc, 1.0)
        for pair in self.geom.mirrored_pairs("cheek_lines"):
            self._line([self._scaled(*p) for p in pair], dimc, 0.8)
        for pair in self.geom.mirrored_pairs("temple_braids"):
            self._line([self._scaled(*p) for p in pair], dimc, 0.8)

        # brows
        for pair in self.geom.brows(expr):
            self._line([self._scaled(*p) for p in pair], font_color, 1.1)

        # eyes (permanent geometry transformed by expression)
        for side, v in self.geom.eye_view(expr).items():
            upper, lower = self.geom.eye_paths(v)
            if v["open"] < 0.12:
                self._line([self._scaled(*p) for p in upper], font_color, 1.0)
            else:
                self._line([self._scaled(*p) for p in upper], font_color, 1.3)
                self._line([self._scaled(*p) for p in lower], font_color, 1.0)
                ix, iy = self._scaled(*v["iris"])
                ir = v["iris_r"]
                self._ring(ix, iy, ir * (1.0 + v["glow"] * 0.9), core, 1.2)
                self._ring(ix, iy, ir * 0.55 * (0.7 + v["glow"] * 0.6), core, 0.8)
                self._dot(ix, iy, v["pupil_r"], "#04060f")

        # nose
        nose = self.geom.nose()
        self._line([self._scaled(*p) for p in nose["bridge"]], font_color, 1.0)
        for alar in (nose["alar_left"], reversed(nose["alar_right"])):
            self._line([self._scaled(*p) for p in alar], font_color, 0.8)
        for nr in nose["nostrils"]:
            self._dot(*self._scaled(*nr), nose["nostril_r"], font_color)

        # mouth (single face, transformed)
        for curve in self.geom.mouth(expr):
            self._line([self._scaled(*p) for p in curve], font_color, 1.2)

        # signature features (permanent)
        sig = self.geom.signature()
        gem = sig["awareness_gem"]
        gx, gy = self._scaled(*gem["point"])
        self._dot(gx, gy, gem["radius"], core)
        ax, ay = self._scaled(*sig["axis_light"]["points"][0])
        bx, by = self._scaled(*sig["axis_light"]["points"][1])
        self._line([(ax, ay), (bx, by)], dimc, 0.7)
        for cp in (sig["cheek_points"]["left"], sig["cheek_points"]["right"]):
            self._dot(*self._scaled(*cp), sig["cheek_points"]["radius"],
                      self.pal.get("glow_soft", "#4d5bb5"))
        for cn in sig["neural_crown"]:
            self._dot(*self._scaled(*cn), 0.004, core)

        # neural network (state-driven activity, geometry unchanged)
        nodes = self.geom.neural_grid()
        edges = self.geom.neural_edges(nodes)
        for i, j in edges:
            egrad = 0.35 + 0.65 * act * pulse
            xi, yi = self._scaled(*nodes[i])
            xj, yj = self._scaled(*nodes[j])
            color = self._mix(pal.get("neural", "#38bdf8"), dimc, 1.0 - egrad)
            self.c.create_line(self.px(xi), self.py(yi), self.px(xj), self.py(yj),
                               fill=color, width=max(0.5, 0.9 * self._f))
        for x, y in nodes:
            jitter = 0.5 + 0.5 * math.sin(t * 0.25 + (x + y) * 12.0)
            bright = 0.30 + 0.70 * act * jitter
            color = self._mix(core, pal.get("bg", "#0a0e1a"), 1.0 - bright)
            self._dot(*self._scaled(x, y), self.geom.np["node_radius"] * (0.6 + bright),
                      color)

        # particles (motion from expression + effects)
        if self._f >= 0.5 or self.size <= 56:
            self.particles.step(expr["particles"]["speed"])
            self.particles.draw(
                self.c, self.px, self.py,
                density=expr["particles"]["density"] * (1.0 if self._f >= 0.5 else 0.35),
                brightness=expr["particles"]["brightness"],
                palette=(pal.get("neural", "#38bdf8"), pal.get("neural_soft", "#2543a8"),
                         pal.get("glow_soft", "#4d5bb5")),
                radius=1.1 * self._f,
            )

        # attention arc (listening focal indicator)
        if expr.get("attention_arc"):
            arc = []
            for i in range(8):
                a = math.radians(-72 + i * 9)
                arc.append((cx + hr * math.cos(a), cy + hr * math.sin(a)))
            self._line(arc, self.pal.get("neural", "#38bdf8"), 1.4)

        # temporary symbols
        self._draw_symbols(t)

        # visual language pattern overlay (temporary, never identity)
        self._draw_pattern(t)

    @staticmethod
    def _mix(hex1: str, hex2: str, w1: float):
        return PresentationMath.mix_color(hex1, hex2, w1)


class ProceduralFace(VisualSurface, tk.Canvas):
    """Maya's procedural digital body — read-only visual presence widget.

    Drop-in complement to the raster ``MayaFace``: same ``set_state`` /
    ``state`` / ``status_text`` contract, but rendered live from geometry.
    Both surfaces share the ``VisualSurface`` contract and drive their
    animation through the same ``LoopTimer`` (identical cadence, default
    80 ms).
    """

    def __init__(self, master, size=176, state="sleeping", bg=None, **kwargs):
        palette = _identity.get_appearance_config().get("palette", {})
        super().__init__(master, width=size, height=size,
                         bg=bg or palette.get("field", "#0b1020"),
                         highlightthickness=0, **kwargs)
        self.size = size
        self.idn = _identity.load_identity()
        anim = _identity.get_animation_config()
        effects = _identity.load_effects_config()
        bundle = _identity.load_geometry_bundle()
        self._renderer = HologramRenderer(self, size, bundle, palette, effects, anim)
        self.state = normalize_visual_state(state)
        self._renderer.set_state(self.state)
        self._frame_ms = max(16, int(anim.get("procedural_rendering", {}).get("frame_ms", FRAME_MS_DEFAULT)))
        self._motion_enabled = bool(anim.get("neural_motion", {}).get("enabled", True))
        self._tick = 0
        self._loop = LoopTimer(self, self._frame_ms, active=False)
        self._loop.attach(self._tick_frame)
        self._driver = None
        self._renderer.render(self._tick)
        if self._motion_enabled:
            self._loop.set_active(True)

    def _tick_frame(self):
        self._tick += 1
        if self._driver is not None:
            try:
                self.set_command(self._driver())
            except Exception:
                pass
        self._renderer.render(self._tick)
        self.update_idletasks()

    def destroy(self):
        self._loop.cancel()
        super().destroy()

    def set_state(self, state):
        self.state = normalize_visual_state(state)
        self._renderer.set_state(state)
        self._renderer.render(self._tick)

    def set_command(self, command):
        self._renderer.set_command(command)
        self._renderer.render(self._tick)

    def set_driver(self, driver):
        """Bind a callable that returns a visual command each tick."""
        self._driver = driver

    def is_placeholder(self):
        return False

    def status_text(self):
        return (f"{self.idn.get('canonical_name', 'Maya')} "
                f"v{self.idn.get('identity_version', '?')} · "
                f"geometry {self.idn.get('geometry_version', '0.0.0')}")

    def state_text(self):
        return STATE_TEXT.get(self.state, STATE_TEXT["sleeping"])


if __name__ == "__main__":
    root = tk.Tk()
    root.title("ProceduralFace preview")
    face = ProceduralFace(root, size=176, state="awake")
    face.pack(padx=12, pady=12)
    print(face.status_text())
    root.after(2500, root.destroy)
    root.mainloop()