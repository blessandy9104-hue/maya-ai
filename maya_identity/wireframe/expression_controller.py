"""Expression controller — deforms the neutral mesh per frame.

Follows the parametric baseline

    pose(t) = base_pose
            + Σ_k (control_k * weight_k)          → expression channel
            + viseme(t) * jaw_open                → viseme channel
            + smoothstep(emotion_intensity) * micro_motion

with the channels priority-blended per the rig model

    final_pose = 0.6 * expression_pose
               + 0.3 * viseme_pose
               + 0.1 * emotion_offset (micro)

Controls are clamped to [0, 1], ``jaw_open = clamp(amplitude * 1.2, 0, 1)``,
    and blink is eased with ``exp_smooth(blink_target, 0.12)``. Every equation
    is owned by the ``rig_math`` layer; anatomical detail (eye blink/gaze)
    is added on top of the blend at full strength. Semantic meaning is kept
    strictly separated: the eye aperture is driven only by blink/gaze (never
    by emotion/state), viseme is confined to the mouth/jaw (never the
    emotional rig), micro is computed by the agent within ``MICRO_AMP``, and
    all channel blending goes exclusively through ``rig_math.blend_pose``.
    Continues to never write identity files.
"""
from __future__ import annotations

import math

from .rig_math import (
    clamp01, oscillate,
    BLEND_E, BLEND_V, BLEND_M, BLINK_LAMBDA, JAW_GAIN,
)
from .math_coordinator import MATH_AGENT

EMOTION_CONTROLS = [
    "smile", "sadness", "anger", "surprise", "fear", "calm",
]
STATE_CONTROLS = [
    "attention", "tiredness", "blink", "speaking", "thinking",
    "uncertainty", "confidence",
]
VOICE_CONTROLS = ["voice_intensity"]
MATERIAL_CONTROLS = ["glow_intensity", "scan_activity"]
META_CONTROLS = ["gaze_x", "gaze_y", "breath", "tremor"]
ALL_CONTROLS = (
    EMOTION_CONTROLS + STATE_CONTROLS + VOICE_CONTROLS + MATERIAL_CONTROLS + META_CONTROLS
)

PRESETS = {
    "neutral":    {"calm": 0.3, "confidence": 0.4, "attention": 0.25},
    "idle":       {"calm": 0.15, "attention": 0.2},
    "listening":  {"attention": 0.60, "calm": 0.35, "confidence": 0.45, "smile": 0.08},
    "thinking":   {"thinking": 0.72, "uncertainty": 0.25, "attention": 0.35, "confidence": 0.30},
    "calm":       {"calm": 0.68, "attention": 0.22, "confidence": 0.40},
    "happy":      {"smile": 0.72, "calm": 0.38, "confidence": 0.52, "attention": 0.32},
    "sad":        {"sadness": 0.60, "calm": 0.16, "attention": 0.30, "confidence": 0.28, "tiredness": 0.10},
    "angry":      {"anger": 0.70, "attention": 0.62, "confidence": 0.50, "surprise": 0.08},
    "fear":       {"fear": 0.62, "attention": 0.52, "surprise": 0.28, "confidence": 0.08, "calm": 0.04},
    "concerned":  {"uncertainty": 0.48, "sadness": 0.22, "attention": 0.52, "tiredness": 0.14},
    "surprised":  {"surprise": 0.78, "attention": 0.48, "calm": 0.08, "fear": 0.12},
    "uncertain":  {"uncertainty": 0.68, "thinking": 0.38, "attention": 0.38, "sadness": 0.10, "confidence": 0.12},
    "speaking":   {"speaking": 0.58, "attention": 0.48, "confidence": 0.42, "calm": 0.28,
                   "voice_intensity": 0.38},
    "error":      {"uncertainty": 0.42, "sadness": 0.28, "attention": 0.58, "tiredness": 0.18,
                   "confidence": 0.08, "scan_activity": 0.85},
    "listening_deep": {"attention": 0.82, "thinking": 0.30, "confidence": 0.40},
}

_STATE_TO_PRESET = {
    "awake": "idle",
    "processing": "thinking",
    "listening": "listening",
    "research": "thinking",
    "learning": "thinking",
    "sleeping": "neutral",
    "offline": "neutral",
}

BLINK_LAMBDA = 0.12
JAW_GAIN = 1.2

JAW_REGIONS = {"jaw_l": 1.0, "jaw_r": 1.0, "chin": 0.92, "neck": 0.45}
CHEEK_REGIONS = {"cheek_l": 1.0, "cheek_r": 1.0, "jaw_l": 0.12, "jaw_r": 0.12}


class ExpressionController:
    """Stateful rig driver: advances smoothed controls and deforms pose."""

    def __init__(self, mesh, auto_blink: bool = True):
        from .interp import Smoother
        self._mesh = mesh
        self._auto_blink_enabled = bool(auto_blink)
        self._smoother = Smoother(ALL_CONTROLS, alpha=0.34)
        self._smoother.set_alpha("blink", BLINK_LAMBDA)
        self._posed = [(x, y, z) for x, y, z in mesh.verts]
        self._blink_next = 0
        self._blink_phase = 0
        self._last_gaze = (0.0, 0.0)
        self._micro_seed = [
            ((hash((round(x, 3), round(y, 3), round(z, 3))) & 0xFFFFFF) % 6283) / 1000.0
            for x, y, z in mesh.verts
        ]
        self._audit = False
        self._last_fields = None
        self._last_pose = None

    @property
    def controls(self):
        return self._smoother

    def set_state_preset(self, state_name):
        preset = _STATE_TO_PRESET.get(state_name, "neutral")
        self.apply_preset(preset)

    def apply_preset(self, name):
        vec = dict(PRESETS.get(name, PRESETS["neutral"]))
        self._smoother.set_targets(vec)

    def set_metadata(self, meta, fallback_visual="sleeping"):
        if not meta:
            self.set_state_preset(fallback_visual)
            return
        preset_name = str(
            meta.get("preset") or meta.get("emotion")
            or meta.get("emotionLabel") or ""
        ).strip().lower()
        if preset_name and preset_name in PRESETS:
            self.apply_preset(preset_name)
        mapped = _map_meta_to_controls(meta)
        self._smoother.set_targets(mapped)
        if meta.get("gaze_x") is not None or meta.get("gaze_y") is not None:
            gx = clamp01(meta.get("gaze_x", 0.5))
            gy = clamp01(meta.get("gaze_y", 0.5))
            self._smoother.set_target("gaze_x", gx)
            self._smoother.set_target("gaze_y", gy)

    def set_command(self, command):
        if not command:
            return
        attn = command.get("eye_focus")
        if attn is not None:
            self._smoother.set_target("attention", clamp01(attn))
        neural = command.get("neural_activity")
        if neural is not None:
            self._smoother.set_target("thinking", clamp01(neural))
        glow = command.get("glow_intensity")
        if glow is not None:
            self._smoother.set_target("glow_intensity", clamp01(glow))
        density = command.get("particle_density")
        if density is not None:
            self._smoother.set_target("scan_activity", clamp01(density))
        breath = command.get("breath")
        if breath is not None:
            self._smoother.set_target("breath", clamp01(breath))
        gx = command.get("gaze_x")
        gy = command.get("gaze_y")
        if gx is not None:
            self._smoother.set_target("gaze_x", clamp01((float(gx) + 1.0) / 2.0))
        if gy is not None:
            self._smoother.set_target("gaze_y", clamp01((float(gy) + 1.0) / 2.0))

    def compute_pose(self, t=0.0, reduced=False):
        if self._auto_blink_enabled:
            self._auto_blink()
        c = self._smoother.step()
        out = self._posed
        verts = self._mesh.verts
        vpar = self._mesh.vpar

        blink_target = clamp01(c["blink"])
        blink = blink_target
        lid_factor = (1.0 - blink * 0.96)

        gx = (c["gaze_x"] - 0.5) * 2.0
        gy = (c["gaze_y"] - 0.5) * 2.0
        self._last_gaze = (gx, gy)

        jaw = MATH_AGENT.jaw_envelope(c["speaking"], c["surprise"])
        viseme = MATH_AGENT.viseme_phase(t)
        mouth = jaw * viseme

        micro_amp = MATH_AGENT.emotion_gate(
            (c["smile"], c["sadness"], c["anger"],
             c["surprise"], c["fear"], c["calm"])
        )
        compose = MATH_AGENT.compose_vertex
        audit = self._audit
        fields = [] if audit else None
        for i in range(len(verts)):
            vx, vy, vz = verts[i]
            dv = vpar[i]
            ex, ey, ez = self._rig_expr(vx, vy, vz, dv, c)
            region = dv.get("region", "")
            etype = dv.get("etype")
            ux, uy, uz = 0.0, 0.0, 0.0
            if etype == "mouth_rim":
                uy = mouth * 0.030
            elif etype == "cavity":
                uz = mouth * 0.060
            elif dv.get("lip"):
                uy = mouth * (0.045 if dv["lip"] == 1 else -0.050)
            elif region in JAW_REGIONS:
                fa = JAW_REGIONS[region] * (0.25 + 0.75 * dv.get("jaw_w", 1.0))
                uy = -mouth * 0.30 * fa
                uz = -mouth * 0.05 * fa
            eid = dv.get("eid")
            jx = jy = jz = 0.0
            mx = my_ = mz = 0.0
            if eid is not None:
                jx, jy, jz = self._eye_rig(
                    eid, etype, dv, lid_factor, gx, gy, blink)
            elif micro_amp > 0.005:
                ph = self._micro_seed[i]
                mx, my_, mz = MATH_AGENT.micro_displacement(t, ph, micro_amp)
            if audit:
                fields.append(
                    (ex, ey, ez, ux, uy, uz, mx, my_, mz, jx, jy, jz)
                )
            dx, dy, dz = compose(
                (ex, ey, ez), (ux, uy, uz), (mx, my_, mz), (jx, jy, jz))
            out[i] = (vx + dx, vy + dy, vz + dz)

        if audit:
            self._last_fields = fields
            self._last_pose = tuple(tuple(v) for v in out)

        if not reduced:
            self._apply_breathing(out, c, t)
            self._apply_head(out, c, t)
        return out

    def _rig_expr(self, vx, vy, vz, dv, c):
        """Expression channel: emotions + brows + cheeks + nose + posture."""
        dx, dy, dz = 0.0, 0.0, 0.0
        region = dv.get("region", "")
        eid = dv.get("eid")

        if eid is not None:
            return dx, dy, dz

        if dv.get("etype") == "nostril":
            sgn = dv.get("nst", 1.0)
            dx += c["anger"] * 0.030 * sgn
            dx += c["surprise"] * 0.020 * sgn
            dy += c["surprise"] * 0.015
            return dx, dy, dz

        if dv.get("etype") == "mouth_rim":
            if dv.get("corner"):
                dy += c["smile"] * 0.150
                dz += c["smile"] * 0.020
                dy -= c["sadness"] * 0.120
                dy -= c["fear"] * 0.055
            else:
                dy += c["smile"] * 0.010
            return dx, dy, dz

        if "brow" in region:
            bst = -1.0 if "l" in region else 1.0
            base = c["surprise"] * 0.16 + c["fear"] * 0.10 + c["attention"] * 0.05
            base -= c["thinking"] * 0.02 + c["sadness"] * 0.03
            inner_bias = c["sadness"] * 0.06 - c["anger"] * 0.10
            asym = c["uncertainty"] * 0.05 * bst
            dy += base + inner_bias + asym

        if region == "nose":
            dy += c["surprise"] * 0.020 + c["fear"] * 0.012
            dy += c["sadness"] * 0.008

        if dv.get("lip"):
            lip = dv["lip"]
            if lip == 1:
                dy += c["smile"] * 0.030 - c["anger"] * 0.015
                dz += c["smile"] * 0.008
            else:
                dy -= c["sadness"] * 0.004

        if "cheek" in region:
            dy += c["smile"] * 0.038
            dz += c["smile"] * 0.016

        if region in JAW_REGIONS:
            fa = JAW_REGIONS[region] * (0.25 + 0.75 * dv.get("jaw_w", 1.0))
            dy += c["sadness"] * 0.012 * fa
            dy -= c["anger"] * 0.010 * fa

        return dx, dy, dz

    def _eye_rig(self, eid, etype, dv, lid_factor, gx, gy, blink):
        dx, dy, dz = 0.0, 0.0, 0.0
        ex = dv.get("ex", 0.0)
        ey = dv.get("ey", 0.0)

        if etype == "lid":
            close = 1.0 - lid_factor
            if dv.get("vin") == 1:
                dy = -close * max(0.0, ey) * 1.35
                dy -= blink * 0.015
            else:
                dy = close * max(0.0, -ey) * 0.45
            return dx, dy, dz

        if etype in ("iris", "pupil"):
            scale = 1.0 - blink * 0.55
            dx = ex * (scale - 1.0) + gx * 0.045
            dy = ey * (scale - 1.0) - gy * 0.032
            dz = -blink * 0.030
            if etype == "pupil":
                dx += gx * 0.010
                dy -= gy * 0.008
            return dx, dy, dz

        if etype == "globe":
            scl = 1.0 - blink * 0.06
            dx = ex * (scl - 1.0)
            dy = ey * (scl - 1.0) * 0.6
            return dx, dy, dz

        return dx, dy, dz

    def _auto_blink(self):
        self._blink_next -= 1
        if self._blink_next <= 0:
            c = self._smoother.snapshot()
            attention = c.get("attention", 0.3)
            confidence = c.get("confidence", 0.4)
            tiredness = c.get("tiredness", 0.0)
            interval = 120 + int(90 * (1.0 - attention) + 60 * (1.0 - confidence))
            if tiredness > 0.5:
                interval = int(interval * 0.65)
            self._blink_next = max(20, interval)
            self._blink_phase = 4.0
        if self._blink_phase > 0:
            self._smoother.set_target("blink", 1.0)
            self._blink_phase -= 1.0
        else:
            self._smoother.set_target("blink", 0.0)

    def _apply_breathing(self, out, c, t):
        bf = c["breath"]
        if bf < 0.01:
            return
        scale = 1.0 + oscillate(t * 0.08, 0.0, bf * 0.006)
        zscale = 1.0 + oscillate(t * 0.08 + 1.5, 0.0, bf * 0.004)
        neck_y = -1.10
        for i in range(len(out)):
            vx, vy, vz = out[i]
            dy_rel = max(0.0, vy - neck_y)
            factor = 1.0 - min(1.0, dy_rel / 2.3)
            out[i] = (
                vx,
                vy + dy_rel * (scale - 1.0) * factor * 0.6,
                vz + (zscale - 1.0) * vz * factor * 0.5,
            )

    def _apply_head(self, out, c, t):
        gaze_x = (c["gaze_x"] - 0.5) * 2.0
        gaze_y = (c["gaze_y"] - 0.5) * 2.0
        tilt = c["uncertainty"] * 0.09 - c["confidence"] * 0.02
        yaw = -gaze_x * 0.13
        pitch = -gaze_y * 0.09
        wobble = 0.0
        if c["thinking"] > 0.2:
            wobble = oscillate(t * 0.72, 0.0, c["thinking"] * 0.003)
        tired_droop = c["tiredness"] * 0.04
        pitch += tired_droop
        c_a, s_a = math.cos(tilt + wobble), math.sin(tilt + wobble)
        c_b, s_b = math.cos(yaw), math.sin(yaw)
        c_p, s_p = math.cos(pitch), math.sin(pitch)
        cy = -0.25
        for i in range(len(out)):
            vx, vy, vz = out[i]
            ry = vy - cy
            x1 = vx * c_a - ry * s_a
            y1 = vx * s_a + ry * c_a + cy
            x2 = x1 * c_b + vz * s_b
            z2 = -x1 * s_b + vz * c_b
            y3 = y1 * c_p - z2 * s_p
            z3 = y1 * s_p + z2 * c_p
            out[i] = (x2, y3, z3)


def _map_meta_to_controls(meta):
    controls = {}
    for key in EMOTION_CONTROLS + STATE_CONTROLS + VOICE_CONTROLS + MATERIAL_CONTROLS:
        val = meta.get(key)
        if val is not None:
            controls[key] = clamp01(val)
    alias_map = {
        "voice_intensity": "voice_intensity", "voiceIntensity": "voice_intensity",
        "glow_intensity": "glow_intensity", "glowIntensity": "glow_intensity",
        "scan_activity": "scan_activity", "scanActivity": "scan_activity",
        "tiredness": "tiredness", "fatigue": "tiredness",
        "attention": "attention", "eyeFocus": "attention",
        "thinking": "thinking", "thinkingAmount": "thinking", "neural": "thinking",
        "speaking": "speaking", "speakingAmount": "speaking",
        "confidence": "confidence", "intensity": "intensity",
    }
    for key, val in meta.items():
        mapped = alias_map.get(key)
        if mapped and mapped not in controls:
            controls[mapped] = clamp01(val)
    return controls