"""Headless runtime face renderer — the deterministic raster path (Batch 8b).

Renders *any* bounded FaceState — not just the canonical neutral preset —
through the same painter's-order pipeline as the Batch 8a canonical raster:
the identity field colour, the depth-graded material engine, the pinhole
projection of ``MeshProjector``, the blurred halo and the neural sparkle.
The renderer is a display of the canonical face, never a second facial-truth
source: all geometry comes from the FaceState's canonical pose.

``aura`` is the only scene parameter (neural-activity glow): it scales the
halo gain, the sparkle strength, and the deep-field ring intensity without
touching the pose or the face materials. Each scale is a multiplication by
``aura``, so ``aura = 1.0`` is *exactly* the Batch 8a frame: the neutral
render reproduces ``maya_face_canonical.png`` byte-for-byte (same zlib level-0
PNG writer), which the test suite pins by SHA-256.

Determinism: no randomness, no wall-clock, pure ``zlib``/``struct`` PNG
writer, integer-safe tracing — identical bytes across runs and interpreters.
"""
from __future__ import annotations

import hashlib
import math
import struct
import zlib
from dataclasses import dataclass, field

from maya_identity.wireframe.mesh_model import get_mesh
from maya_identity.wireframe.render3d import _hex_to_rgb
from .render_canonical_face import (
    DEFAULT_MATERIALS,
    FIELD,
    GLOW_SOFT,
    NEURAL,
    _blur_rgb,
    _clamp255,
    _compose,
    _compose_steps,
    _composite_to_rgba,
    _soft,
    _stamp_radial,
    _stamp_segment,
)

SUPERSAMPLE = 2


def _aura_bg(size, intensity=1.0):
    """Deep-night field with neural rings, scaled by ``intensity``.

    Byte-identical to ``render_canonical_face._aura_bg`` at ``intensity=1.0``
    (the pixel loop is the original; only the ring/gradient weight ``t`` is
    multiplied by ``intensity``, and ``t * intensity == t`` for 1.0).
    """
    buf = bytearray(size * size * 3)
    cx = cy = size // 2
    r_out = 0.44 * size
    w_out = 0.018 * size
    r_in = 0.31 * size
    w_in = 0.008 * size
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.hypot(dx, dy)
            r, g, b = FIELD
            a_out = _soft(d, r_out * 2, r_out * 0.9) * 0.13
            ring_out = _soft(abs(d - r_out), w_out, w_out * 2.0)
            ring_in = _soft(abs(d - r_in), w_in, w_in * 2.0)
            t = a_out * 0.5 + ring_out * 0.55 + ring_in * 0.5
            t = t * intensity
            r += (GLOW_SOFT[0] - r) * t * 0.35
            g += (GLOW_SOFT[1] - g) * t * 0.35
            b += (GLOW_SOFT[2] - b) * t * 0.45
            i = (y * size + x) * 3
            buf[i] = _clamp255(r)
            buf[i + 1] = _clamp255(g)
            buf[i + 2] = _clamp255(b)
    return buf


def _canonical_soft(distance, thickness, softness):
    return max(0.0, min(1.0, 1.0 - (distance - thickness / 2.0)
                        / max(1.0, softness)))


@dataclass(frozen=True)
class RenderedFace:
    """One deterministic raster frame of the canonical face."""

    size: int
    rgba: bytes
    pose_digest: str
    frame_digest: str
    aura: float
    channels: dict
    tags: tuple = ()
    semantic: str | None = None
    _png_cache: bytes | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if len(self.rgba) != self.size * self.size * 4:
            raise ValueError(
                f"rgba length {len(self.rgba)} != {self.size * self.size * 4}")

    def png_bytes(self) -> bytes:
        if self._png_cache is None:
            object.__setattr__(self, "_png_cache", _png_bytes(self.size,
                                                              self.rgba))
        return self._png_cache

    def sha256(self) -> str:
        return hashlib.sha256(self.png_bytes()).hexdigest()

    def to_render_frame(self):
        from maya_runtime.rendering import RenderFrame
        return RenderFrame(
            channels=dict(self.channels),
            mesh=(),
            tags=("rendered_face", "pose:" + self.pose_digest[:24],
                  "size:" + str(self.size), "aura:" + str(self.aura),
                  "semantic:" + str(self.semantic), *self.tags),
        )

    def ascii_digest(self):
        return {
            "size": self.size,
            "pose_digest": self.pose_digest,
            "frame_digest": self.frame_digest,
            "png_sha256": self.sha256(),
            "aura": self.aura,
            "semantic": self.semantic,
            "channels": {k: round(float(v), 9) for k, v in self.channels.items()},
        }


def _png_bytes(size, rgba):
    """Byte-exact copy of the canonical level-0 PNG writer."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + bytes(rgba[y * size * 4:(y + 1) * size * 4])
                   for y in range(size))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 0))
    png += chunk(b"IEND", b"")
    return png


def render_face_frame(fs, size: int = 512, aura: float = 1.0,
                      materials: dict | None = None) -> RenderedFace:
    """Deterministic raster of any canonical FaceState.

    At ``size=512, aura=1.0`` with the neutral FaceState this reproduces the
    Batch 8a master exactly (``raw_sha256 a7fcfbe4…`` / PNG
    ``27d37840…``). ``aura`` stays in [0, 1]; materials default to the
    canonical set and never move the face pose.
    """
    size = int(size)
    aura = min(1.0, max(0.0, float(aura)))
    ss = SUPERSAMPLE
    N = size * ss

    mesh = get_mesh()
    pose = fs.pose
    if len(pose) != mesh.vertex_count():
        raise ValueError(
            f"pose vertex count {len(pose)} != mesh {mesh.vertex_count()}")

    projector = __import__("maya_identity.wireframe.render3d",
                           fromlist=["MeshProjector"]).MeshProjector(N)
    px, py = projector.project(pose, mesh.vertex_count())
    engine = __import__("maya_identity.wireframe.render3d",
                        fromlist=["MaterialEngine"]).MaterialEngine("#0b1020")
    engine.clear_cache()

    core = bytearray(N * N * 3)
    regions = mesh.edge_region
    verts = pose
    edge_count = mesh.edge_count()
    mats = dict(DEFAULT_MATERIALS)
    if materials:
        mats.update(materials)
    edge_thickness = __import__("maya_identity.wireframe.render3d",
                                fromlist=["edge_thickness"]).edge_thickness
    for idx in range(edge_count):
        a, b = mesh.edges[idx]
        region = regions[idx] if idx < len(regions) else "default"
        za, zb = verts[a][2], verts[b][2]
        zmid = 0.5 * (za + zb)
        bucket = engine.bucket(zmid)
        hexcol = engine.edge_color(region, mats, bucket, z=zmid)
        colour = _hex_to_rgb(hexcol)
        width = max(1, edge_thickness(zmid, N))
        _stamp_segment(core, px[a], py[a], px[b], py[b], width, colour,
                       N, size=ss)

    glow_core = _blur_rgb(core, N, 4)
    nebula = _compose_steps(core, glow_core, N, 0.55 * aura)
    field = _aura_bg(N, intensity=aura)
    sparkle = bytearray(N * N * 3)
    for name, rad in (("iris_l", 0.022), ("iris_r", 0.022),
                      ("nose_tip", 0.010)):
        idx = mesh.landmarks.get(name)
        if idx is not None:
            _stamp_radial(sparkle, N, px[idx], py[idx], N * rad, NEURAL,
                          0.8 * aura)
    buf = _compose(field, nebula, sparkle, N)
    rgba = _composite_to_rgba(buf, N, size)

    channels = fs.channel_state()
    return RenderedFace(
        size=size,
        rgba=bytes(rgba),
        pose_digest=fs.signature,
        frame_digest=hashlib.sha256(bytes(rgba)).hexdigest(),
        aura=aura,
        channels=dict(sorted(channels.items())),
        tags=("canonical_color", "v:" + fs.version),
        semantic=None,
    )


def render_semantic_frame(name: str, size: int = 512, aura: float | None = None):
    """Convenience: render a bounded semantic face state.

    Uses ``aura`` verbatim (defaults to the state's spec value). Zero
    runtime state is created; the state is a pure function of ``name``.
    """
    from maya_identity.wireframe.face_semantics import (
        build_semantic_face_state,
    )
    fs = build_semantic_face_state(name)
    aura_v = aura if aura is not None else float(fs.extra.get("aura", 0.5))
    face = render_face_frame(fs, size=size, aura=aura_v)
    object.__setattr__(face, "semantic", name)
    return face


def downsample_rgba(rgba: bytes, src_size: int, dst_size: int) -> bytes:
    """Deterministic alpha-weighted box downscale (canonical variant path)."""
    from .render_canonical_face import _box_downsample
    return bytes(_box_downsample(rgba, src_size, dst_size))