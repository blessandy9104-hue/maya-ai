"""3D-to-2D projection and material colouring for the wireframe face.

Software perspective projection with the depth-compression map

    Z' = Z / (1 + Z / CAM_D)

so the projection scale for a vertex is exactly the same factor that
compresses its depth. Depth-bucket shading is a continuous grade from
luminous cyan (nearest) to violet (far):

    color = lerp(cyan, violet, depth)
    depth = clamp01((Z' - Z_min) / (Z_max - Z_min))

Each edge also picks up an additive neon glow with falloff

    glow_intensity = exp(-Z' * 2.5)

and near-plane edges are drawn thicker via
``thickness = 1 + 2*(1 - Z')``. Every equation is owned by the ``rig_math``
layer; this module derives its behaviour from there.
No OpenGL, no WebGL — pure Python list math driving Tk canvas ``coords``
and ``itemconfigure`` calls.
"""
from __future__ import annotations

from .rig_math import (
    CAM_D, SHADE_LO, SHADE_HI, NB,
    zprime, zprime_inv, depth01, shade_of, thickness01, glow01,
    project_scale, boost_rgb,
    color_lerp,
    bucket_of, bucket_midpoint,
)
from .math_coordinator import (
    MATH_AGENT,
    JEWEL, PALETTE, BRIGHT_REGIONS, EYE_REGIONS, HIGHLIGHT_REGIONS,
    _rgb_to_hex,
)

HEX_BG = "#070d1a"
HEX_CYAN = "#63d9ff"
HEX_BLUE = "#2f8bf0"
HEX_VIOLET = "#8a7dff"
HEX_WHITE = "#d8f9ff"
HEX_DIM = "#0e2a4c"

# Material semantics (palette/jewel/regions) are owned by the Math
# Coordination Agent in math_coordinator.py; kept here only as public
# aliases for the renderer's API compatibility.
_JEWEL = JEWEL
_DEFAULT_PALETTE = PALETTE
_BRIGHT_REGIONS = BRIGHT_REGIONS
_EYE_REGIONS = EYE_REGIONS
_HIGHLIGHT_REGIONS = HIGHLIGHT_REGIONS


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(r))),
        max(0, min(255, int(g))),
        max(0, min(255, int(b))),
    )


def _mix_rgb(c1, c2, t):
    """Channel-wise lerp; callers clamp ``t`` into [0, 1]."""
    return color_lerp(c1, c2, t)


def edge_thickness(z, size):
    """Variable line width from ``thickness01``, capped for the canvas."""
    return MATH_AGENT.line_width(z, size)


class MeshProjector:
    """True perspective projector (pinhole camera at z = CAM_D)."""

    def __init__(self, size, bg_hex=HEX_BG):
        self.bg = _hex_to_rgb(bg_hex)
        self.set_size(size)

    def set_size(self, size):
        self.size = size
        s = size * 0.36
        self._s = s
        self._cx = size * 0.50
        self._cy = size * 0.50
        self._d = CAM_D
        self._px = [0.0] * 8000
        self._py = [0.0] * 8000
        self._pz = [0.0] * 8000

    def project(self, verts, n=None):
        if n is None:
            n = len(verts)
        if n > len(self._px):
            self._px = [0.0] * n
            self._py = [0.0] * n
            self._pz = [0.0] * n
        s = self._s
        cx = self._cx
        cy = self._cy
        px = self._px
        py = self._py
        pz = self._pz
        for i in range(n):
            x, y, z = verts[i]
            inv = project_scale(z)
            px[i] = cx + x * s * inv
            py[i] = cy - y * s * inv
            pz[i] = zprime(z)
        return px, py


class MaterialEngine:
    """Colour engine: region + materials + depth -> continuous line colour.

    Base grade is ``color = lerp(cyan, violet, depth)`` with depths derived
    from ``rig_math.zprime`` / ``rig_math.depth01``; region palettes
    modulate brightness, then an additive neon glow
    ``rig_math.glow01(Z')`` is blended in so the scan plane reads as the
    brightest zone.
    """

    def __init__(self, bg_hex=None):
        if bg_hex is None:
            bg_hex = HEX_BG
        self.bg = _hex_to_rgb(bg_hex)
        self._hex_cache = {}

    @staticmethod
    def bucket(z):
        return MATH_AGENT.depth_bucket(z)

    def edge_color(self, region, materials, bucket=None, z=None):
        if z is None:
            t = bucket_midpoint(bucket) if bucket is not None else 0.5
            zp = 0.0
        else:
            t = depth01(zprime(z))
            zp = zprime(z)
        if bucket is None:
            bucket = bucket_of(t)
        key = (region, bucket, int(round(t * NB)),
               materials.get("line_brightness", 0.72),
               materials.get("cyan_blue_balance", 0.55),
               materials.get("violet_diagnostic", 0.18),
               materials.get("eye_brightness", 0.95),
               materials.get("glow_intensity", 0.0))
        if key in self._hex_cache:
            return self._hex_cache[key]
        h = MATH_AGENT.compute_edge_color(region, materials, t, zp, self.bg)
        self._hex_cache[key] = h
        return h

    def highlight_color(self, region, materials, bucket=None, z=None):
        if z is None:
            z = 0.9 if bucket is None else zprime_inv(
                SHADE_LO + bucket_midpoint(bucket) * (SHADE_HI - SHADE_LO))
        h = self.edge_color(region, materials, bucket=bucket, z=z)
        r, g, b = _hex_to_rgb(h)
        return _rgb_to_hex(*boost_rgb((r, g, b), scale=1.25, offset=(28, 26, 28)))

    def clear_cache(self):
        self._hex_cache.clear()