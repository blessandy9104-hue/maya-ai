"""MayaWireframeFace — the 3D wireframe face Tk canvas widget.

Renders the dense anatomical analytic mesh via software projection with
expression deformation, depth-graded edge colouring, scan lines, ambient
particles, and glow. Matches the ``set_state``/``set_command``/
``is_placeholder``/``status_text`` contract of ProceduralFace so it can be
used as a drop-in replacement in maya_app.
"""
from __future__ import annotations

import time
import tkinter as tk

from .interp import clamp01, clamp, lerp
from .rig_math import (
    lift_luminance, project_scale, cycle_sweep, oscillate,
)
from .mesh_model import get_mesh, Mesh
from .expression_controller import (
    ExpressionController, ALL_CONTROLS, PRESETS, _STATE_TO_PRESET,
)
from .emotion_mapper import parse_metadata
from .speech_adapter import SpeechAdapter
from .render3d import (
    MeshProjector, MaterialEngine, edge_thickness, _mix_rgb, _hex_to_rgb,
    _rgb_to_hex, HEX_BG,
)


_STATE_TEXT = {
    "awake":     "wireframe presence — awake — aware",
    "processing":"wireframe presence — processing — focused",
    "listening": "wireframe presence — listening — attentive",
    "research":  "wireframe presence — research — analytical",
    "learning":  "wireframe presence — learning — integrating",
    "sleeping":  "wireframe presence — sleeping — dormant",
    "offline":   "wireframe presence — offline — inactive",
}

_DEFAULT_MATERIALS = {
    "wireframe_opacity": 0.85,
    "line_brightness": 0.72,
    "cyan_blue_balance": 0.55,
    "violet_diagnostic": 0.18,
    "eye_brightness": 0.95,
    "bloom": 0.35,
    "scan_intensity": 1.0,
    "particle_density": 0.50,
    "animation_speed": 1.0,
    "voice_pulse": 0.0,
}

_MATERIAL_KEYS = list(_DEFAULT_MATERIALS.keys())

_SENSOR_ALPHA = 0.28

_HEAVY_REGIONS = frozenset({"skin", "scan", "globe", "cavity", "neck"})
_KEY_REGIONS = frozenset({"iris", "pupil", "spoke", "nose", "brow", "lid"})


def _bump_small(hex_color, floor=110):
    """Lift far-edge fills at tiny sizes so the mesh stays legible.

    Keeps the cyan -> violet depth grade, but guarantees an absolute
    luminance floor (``rig_math.lift_luminance``: every channel lifted by
    the same clamped amount until the max channel reaches ``floor``) so
    jaw/neck/scalp silhouette lines don't vanish below the eye's threshold
    on a 48px header.
    """
    return _rgb_to_hex(*lift_luminance(_hex_to_rgb(hex_color), floor))


def _identity_status_text():
    try:
        from ..identity import load_identity
        idn = load_identity()
        return (f"{idn.get('canonical_name', 'Maya')} "
                f"v{idn.get('identity_version', '?')} · "
                f"geometry {idn.get('geometry_version', '0.0.0')}")
    except Exception:
        return "Maya wireframe · identity unavailable"


class MayaWireframeFace(tk.Canvas):
    """Maya's dense 3D wireframe face — Tk canvas presentation widget.

    Implements the same public API as ``ProceduralFace`` so it can be used
    as a drop-in replacement: ``set_state``, ``set_command``,
    ``is_placeholder``, ``status_text``, ``state_text``, ``set_driver``,
    ``set_metadata``, ``set_control``, ``set_material``, ``apply_preset``,
    ``set_reduced_motion``, ``pause``, ``resume``, ``snapshot``, ``destroy``.
    """

    FRAME_MS = 60
    MIN_PARTICLES = 8
    MAX_PARTICLES = 70

    def __init__(self, master, size=176, state="sleeping", bg=None, **kwargs):
        super().__init__(master, width=size, height=size,
                         bg=bg or HEX_BG, highlightthickness=0, **kwargs)
        self.size = int(size)
        self._bg_hex = bg or HEX_BG
        self._bg_rgb = _hex_to_rgb(self._bg_hex)
        self.mesh = get_mesh()
        self.state = str(state).lower().strip()
        if self.state not in _STATE_TEXT:
            self.state = "sleeping"

        self.projector = MeshProjector(size, self._bg_hex)
        self.materials = dict(_DEFAULT_MATERIALS)
        self.controller = ExpressionController(self.mesh)
        self.speech = SpeechAdapter()
        self.mat_engine = MaterialEngine(self._bg_hex)

        self._tick = 0
        self._loop_id = None
        self._driver = None
        self._t0 = time.monotonic()
        self._last_set_command = 0.0
        self._reduced_motion = False
        self._paused = False
        self._fill_dirty = False
        self._stated = False
        self._state_pose = None
        self._state_signature = None
        self._state_aura = 0.0

        self._draw_plan = []
        self._item_ids = []
        self._item_regions = []
        self._edge_bucket = []
        self._edge_z = []
        self._scan_id = None
        self._glow_ids = []
        self._nose_glow_id = None
        self._particle_ids = []
        self._particle_state = []

        self.controller.set_state_preset(self.state)
        self._rebuild()

    def _rebuild(self):
        self.delete("all")
        n = self.mesh.vertex_count()
        self.projector.set_size(self.size)
        px, py = self.projector.project(self.mesh.verts, n)

        self._build_draw_plan()
        self._item_ids = []
        self._item_regions = []
        self._edge_bucket = []
        self._edge_z = []
        regions = self.mesh.edge_region
        self.mat_engine.clear_cache()

        for idx in self._draw_plan:
            a, b = self.mesh.edges[idx]
            region = regions[idx] if idx < len(regions) else "default"
            zmid = lerp(self.mesh.verts[a][2], self.mesh.verts[b][2], 0.5)
            bucket = self.mat_engine.bucket(zmid)
            fill = self.mat_engine.edge_color(region, self.materials,
                                              bucket, z=zmid)
            if self.size < 100:
                fill = _bump_small(fill)
            width = edge_thickness(zmid, self.size)
            iid = self.create_line(
                px[a], py[a], px[b], py[b],
                fill=fill, width=width,
            )
            self._item_ids.append(iid)
            self._item_regions.append(region)
            self._edge_bucket.append(bucket)
            self._edge_z.append(zmid)

        self._build_particles()
        self._build_glow()
        self._build_scan()
        self._fill_dirty = False
        self._tick_loop()

    def _build_draw_plan(self):
        n_edges = self.mesh.edge_count()
        regions = self.mesh.edge_region
        if self.size < 100:
            plan = []
            kept = {}
            for i in range(n_edges):
                r = regions[i] if i < len(regions) else ""
                if r in _HEAVY_REGIONS:
                    k = kept.get(r, 0)
                    if k % 3 == 0:
                        plan.append(i)
                    kept[r] = k + 1
                elif r in _KEY_REGIONS:
                    k = kept.get(r, 0)
                    if k % 2 == 0:
                        plan.append(i)
                    kept[r] = k + 1
                else:
                    plan.append(i)
            self._draw_plan = plan
        elif self.size < 140:
            plan = []
            kept = {}
            for i in range(n_edges):
                r = regions[i] if i < len(regions) else ""
                if r in _HEAVY_REGIONS:
                    k = kept.get(r, 0)
                    if k % 2 == 0:
                        plan.append(i)
                    kept[r] = k + 1
                else:
                    plan.append(i)
            self._draw_plan = plan
        else:
            self._draw_plan = list(range(n_edges))

    def _build_particles(self):
        count = int(clamp(8 + 52 * self.materials["particle_density"],
                          self.MIN_PARTICLES, self.MAX_PARTICLES))
        anchors = []
        lm = self.mesh.landmarks
        for name in ("iris_l", "iris_r", "mouth_corner_l", "mouth_corner_r",
                     "nose_tip"):
            idx = lm.get(name)
            if idx is not None:
                anchors.append(self.mesh.verts[idx])
        if not anchors:
            anchors = [(0, 0.1, 0.2)]
        self._particle_state = []
        for i in range(count):
            phase = (i * 1.618033988749895) % 1.0
            speed = 0.35 + (i % 7) * 0.05
            if i % 3 == 0 and anchors:
                ax, ay, az = anchors[i % len(anchors)]
                spread = 0.12 + 0.10 * (i % 3)
                x = ax + ((i * 0.73) % 1.0 - 0.5) * spread * 2
                y = ay + ((i * 0.31) % 1.0 - 0.5) * spread * 2
                z = az + 0.02
            else:
                x = -0.95 + (i * 0.173) % 1.9
                y = -1.5 + (i * 0.217) % 2.6
                z = 0.05 + (i % 5) * 0.18
            cluster = i % 3 == 0
            self._particle_state.append(
                (phase, speed, x, y, z, cluster))
        self._particle_ids = []
        for _ in range(count):
            iid = self.create_line(0, 0, 0, 0,
                                   fill="#122840", width=1, tag="particle")
            self._particle_ids.append(iid)

    def _build_glow(self):
        self._glow_ids = []
        for _ in range(3):
            iid = self.create_oval(0, 0, 0, 0, outline="#0e1e32",
                                   width=1, tag="glow")
            self._glow_ids.append(iid)
        self._nose_glow_id = self.create_oval(0, 0, 0, 0,
                                              outline="#0e1e32", width=1,
                                              tag="glow")

    def _build_scan(self):
        self._scan_id = self.create_line(
            0, 0, self.size, 0, fill="#0a2a42", width=1, tag="scan")

    def _tick_loop(self):
        if self._paused:
            return
        try:
            self._tick += 1
            if self._stated:
                self._tick_stated()
            else:
                self._tick_legacy()
        except Exception:
            pass
        self._schedule()

    def _tick_stated(self):
        """Deterministic stated frame: the pose IS the FaceState pose.

        No wall clock, no blink, no particles/scan/glow, no controller
        easing — the face renders exactly the bounded state it was given.
        """
        pose = self._state_pose
        if pose is None or len(pose) != self.mesh.vertex_count():
            return
        n = len(pose)
        px, py = self.projector.project(pose, n)
        self._draw_edges(px, py, pose)

    def _tick_legacy(self):
        if self._driver is not None:
            try:
                self.set_command(self._driver())
            except Exception:
                pass
        t = time.monotonic() - self._t0
        pose = self.controller.compute_pose(t, reduced=self._reduced_motion)
        n = len(pose)
        px, py = self.projector.project(pose, n)
        self._draw_edges(px, py, pose)
        self._draw_particles(px, py, t)
        self._draw_scan(t)
        self._draw_glow(px, py)

    def _schedule(self):
        if self._paused:
            return
        ms = max(16, int(self.FRAME_MS / max(0.01, self.materials["animation_speed"])))
        self._loop_id = self.after(ms, self._tick_loop)

    def _draw_edges(self, px, py, pose):
        n = len(self._draw_plan)
        items = self._item_ids
        buckets = self._edge_bucket
        regions = self._item_regions
        ez = self._edge_z
        edges = self.mesh.edges
        mats = self.materials
        engine = self.mat_engine
        for k in range(n):
            a, b = edges[self._draw_plan[k]]
            zmid = lerp(pose[a][2], pose[b][2], 0.5)
            bk = engine.bucket(zmid)
            if bk != buckets[k]:
                buckets[k] = bk
                ez[k] = zmid
                try:
                    fill = engine.edge_color(regions[k], mats, bk, z=zmid)
                    if self.size < 100:
                        fill = _bump_small(fill)
                    self.itemconfigure(items[k], fill=fill)
                except Exception:
                    pass
            try:
                self.coords(items[k], px[a], py[a], px[b], py[b])
            except Exception:
                pass
        if self._fill_dirty:
            self._apply_fills()
            self._fill_dirty = False

    def _apply_fills(self):
        for k, iid in enumerate(self._item_ids):
            region = self._item_regions[k] if k < len(self._item_regions) else "default"
            bucket = self._edge_bucket[k] if k < len(self._edge_bucket) else 7
            zmid = self._edge_z[k] if k < len(self._edge_z) else 0.2
            fill = self.mat_engine.edge_color(region, self.materials,
                                              bucket, z=zmid)
            try:
                self.itemconfigure(iid, fill=fill)
            except Exception:
                pass

    def _draw_particles(self, px, py, t):
        if self._reduced_motion:
            return
        scan_act = self.materials.get("scan_activity", 0.5)
        s = self.projector._s
        cx = self.projector._cx
        cy = self.projector._cy
        voice = self.materials.get("voice_pulse", 0.0)
        n_p = min(len(self._particle_state), len(self._particle_ids))
        for i in range(n_p):
            phase, speed, bx, by, bz, cluster = self._particle_state[i]
            flicker = oscillate(t * speed * 6.0 + phase * 6.28, 0.5, 0.5)
            if cluster:
                flicker = oscillate(t * speed * 9.0 + phase * 6.28, 0.35, 0.65)
            bx2 = bx + oscillate(t * speed * 0.4 + phase * 6.28, 0.0, 0.015)
            py_p = cycle_sweep(by + oscillate(t * speed * 0.35 + phase * 6.28,
                                              0.0, 0.015), 1.0, 2.6, 1.3)
            inv = project_scale(bz)
            screen_x = cx + bx2 * s * inv
            screen_y = cy - py_p * s * inv
            scan_fade = clamp01(scan_act * 0.5 + voice * 0.2)
            opacity = clamp01(0.10 + scan_fade * 0.25) * (0.55 + 0.45 * flicker)
            c = _mix_rgb(self._bg_rgb, (0x28, 0x90, 0xc0), opacity)
            fill = _rgb_to_hex(*c)
            length = max(2, int(s * 0.04 * scan_fade))
            try:
                self.coords(self._particle_ids[i],
                            screen_x - length, screen_y,
                            screen_x + length, screen_y)
                self.itemconfigure(self._particle_ids[i], fill=fill)
            except Exception:
                pass

    def _draw_scan(self, t):
        if self._reduced_motion or self.materials.get("scan_intensity", 0.0) < 0.05:
            try:
                self.itemconfigure(self._scan_id, state="hidden")
            except Exception:
                pass
            return
        try:
            self.itemconfigure(self._scan_id, state="normal")
        except Exception:
            pass
        speed = self.materials.get("animation_speed", 1.0)
        scan_y = cycle_sweep(t, speed * 40.0, self.size + 40.0, 20.0)
        try:
            self.coords(self._scan_id, 0, scan_y, self.size, scan_y)
            opacity = clamp01(self.materials.get("scan_intensity", 0.5) * 0.35)
            c = _mix_rgb(self._bg_rgb, (0x28, 0x98, 0xd0), opacity)
            self.itemconfigure(self._scan_id, fill=_rgb_to_hex(*c))
        except Exception:
            pass

    def _draw_glow(self, px, py):
        if self._reduced_motion:
            return
        bloom = clamp01(self.materials.get("bloom", 0.35))
        if bloom < 0.05:
            return
        targets = []
        for name in ("iris_l", "iris_r"):
            idx = self.mesh.landmarks.get(name)
            if idx is not None and idx < len(px):
                targets.append((px[idx], py[idx]))
        for k, iid in enumerate(self._glow_ids):
            if k < len(targets):
                gx, gy = targets[k]
                r = max(3, int(self.size * 0.028 * bloom))
                c = _mix_rgb(self._bg_rgb, (0x20, 0x88, 0xc0), clamp01(bloom * 0.45))
                try:
                    self.coords(iid, gx - r, gy - r, gx + r, gy + r)
                    self.itemconfigure(iid, outline=_rgb_to_hex(*c),
                                       width=max(1, int(bloom * 2.5)))
                except Exception:
                    pass
            else:
                try:
                    self.itemconfigure(iid, state="hidden")
                except Exception:
                    pass
        nose_idx = self.mesh.landmarks.get("nose_tip")
        if nose_idx is not None and nose_idx < len(px) and self._nose_glow_id is not None:
            gx, gy = px[nose_idx], py[nose_idx]
            r = max(2, int(self.size * 0.012 * bloom))
            c = _mix_rgb(self._bg_rgb, (0x30, 0x9c, 0xd8), clamp01(bloom * 0.4))
            try:
                self.coords(self._nose_glow_id, gx - r, gy - r, gx + r, gy + r)
                self.itemconfigure(self._nose_glow_id, outline=_rgb_to_hex(*c),
                                   width=max(1, int(bloom * 1.8)))
            except Exception:
                pass
        else:
            try:
                self.itemconfigure(self._nose_glow_id, state="hidden")
            except Exception:
                pass

    def set_state(self, state):
        self.state = str(state).lower().strip()
        if self.state not in _STATE_TEXT:
            self.state = "sleeping"
        self.controller.set_state_preset(self.state)

    def set_command(self, command):
        self.controller.set_command(command)
        self._last_set_command = time.monotonic()

    def set_face_state(self, fs, aura=None):
        """Enter deterministic stated mode: render exactly ``fs.pose``.

        The face becomes the canonical FaceState — no wall clock, no blink,
        no eased particles/scan/glow. ``aura`` lifts the presentation bloom
        and line brightness (bounded); the pose is never touched.
        """
        pose = tuple(tuple(float(v) for v in row) for row in fs.pose)
        if len(pose) != self.mesh.vertex_count():
            raise ValueError(
                f"set_face_state pose has {len(pose)} vertices, mesh has "
                f"{self.mesh.vertex_count()}")
        self._state_pose = pose
        self._state_signature = str(fs.signature)
        self._state_aura = clamp01(
            float(aura) if aura is not None
            else float(fs.extra.get("aura", 0.0)))
        self._stated = True
        self.materials["bloom"] = clamp01(0.35 + self._state_aura * 0.15)
        self.materials["line_brightness"] = clamp01(
            0.72 + self._state_aura * 0.10)
        self.mat_engine.clear_cache()
        self._fill_dirty = True

    def clear_face_state(self):
        """Exit stated mode and restore the legacy free animation."""
        self._stated = False
        self._state_pose = None
        self._state_signature = None
        self._state_aura = 0.0
        self.materials["bloom"] = _DEFAULT_MATERIALS["bloom"]
        self.materials["line_brightness"] = _DEFAULT_MATERIALS["line_brightness"]
        self.mat_engine.clear_cache()
        self._fill_dirty = True

    def set_metadata(self, meta):
        controls, preset, warnings = parse_metadata(meta, self.state)
        self.controller.controls.set_targets(controls)
        if preset and preset != "neutral":
            self.controller.apply_preset(preset)

    def set_control(self, name, value):
        self.controller.controls.set_target(name, clamp01(value))

    def set_material(self, name, value):
        if name in self.materials:
            self.materials[name] = clamp01(value)
            self.mat_engine.clear_cache()
            self._fill_dirty = True

    def apply_preset(self, name):
        self.controller.apply_preset(name)

    def set_reduced_motion(self, enabled):
        self._reduced_motion = bool(enabled)

    def pause(self):
        self._paused = True
        if self._loop_id:
            try:
                self.after_cancel(self._loop_id)
            except Exception:
                pass
            self._loop_id = None

    def resume(self):
        if self._paused:
            self._paused = False
            self._schedule()

    def set_driver(self, driver):
        self._driver = driver

    def is_placeholder(self):
        return False

    def status_text(self):
        return _identity_status_text()

    def state_text(self):
        return _STATE_TEXT.get(self.state, _STATE_TEXT["sleeping"])

    def snapshot(self):
        return {
            "state": self.state,
            "tick": self._tick,
            "size": self.size,
            "reduced": self._reduced_motion,
            "paused": self._paused,
            "controls": self.controller.controls.snapshot(),
            "materials": dict(self.materials),
            "stated": self._stated,
            "state_signature": self._state_signature,
            "state_aura": self._state_aura,
        }

    def destroy(self):
        if self._loop_id is not None:
            try:
                self.after_cancel(self._loop_id)
            except Exception:
                pass
            self._loop_id = None
        super().destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("MayaWireframeFace preview")
    face = MayaWireframeFace(root, size=176, state="awake", bg=HEX_BG)
    face.pack(padx=12, pady=12)
    root.after(2500, root.destroy)
    root.mainloop()