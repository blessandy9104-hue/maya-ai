"""Deterministic canonical face raster (Batch 8a).

Renders the canonical geometric face that Maya wears — the neutral canonical
pose of the analytic wireframe mesh, depth-shaded with the runtime material
engine, projected by the same pinhole camera as the live widget — into the
official raster assets:

- avatar/maya_face_canonical.png      512x512 master (per pipeline contract)
- avatar/maya_face_canonical_256.png  256x256
- avatar/maya_face_canonical_128.png  128x128
- avatar/maya_face_canonical_48.png   48x48
- avatar/maya_face_canonical.ico      multi-size window icon (16..256)

Properties
----------
Deterministic
    No randomness, no wall-clock, no PIL for asset bytes. The pose comes from
    ``face_state.build_face_state`` (fixed preset, t=0.5, autoblink off); the
    projection and shading are the runtime's own MeshProjector/MaterialEngine.
    The PNG encoder is a pure ``zlib``/``struct`` writer, so the output bytes
    are byte-identical across interpreters and runs.

Identity-true
    The portrait IS the geometry: the same mesh edges, depth grade, and
    canonical pose that the live presence renders, on the identity field
    colour (#0b1020) with the appearance palette's glow accents. The renderer
    is the body Maya wears; this raster is one arbitrary frame of it.

Governance
    Output files never overwrite existing canonical assets unless ``--force``
    is given. Promotion never happens here: it is owned by
    ``identity.finalize_canonical_face`` after validation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import sys
import zlib
from pathlib import Path

_AVATAR_DIR = Path(__file__).resolve().parent
_PACKAGE = _AVATAR_DIR.parent

sys.path.insert(0, str(_PACKAGE.parent))

from maya_identity.wireframe.expression_controller import PRESETS  # noqa: E402
from maya_identity.wireframe.face_state import build_face_state  # noqa: E402
from maya_identity.wireframe.mesh_model import get_mesh  # noqa: E402
from maya_identity.wireframe.render3d import (  # noqa: E402
    MeshProjector, MaterialEngine, edge_thickness, _hex_to_rgb,
)

MASTER_SIZE = int(os.environ.get("MAYA_RENDER_MASTER_SIZE", "512"))
SUPERSAMPLE = 2

# Material set identical in value to the live widget's defaults (face3d), plus
# a luminous still: glow_intensity lifts additively through the depth grade.
DEFAULT_MATERIALS = {
    "wireframe_opacity": 0.85,
    "line_brightness": 0.72,
    "cyan_blue_balance": 0.55,
    "violet_diagnostic": 0.18,
    "eye_brightness": 0.95,
    "bloom": 0.50,
    "scan_intensity": 1.0,
    "particle_density": 0.50,
    "animation_speed": 1.0,
    "voice_pulse": 0.0,
    "glow_intensity": 0.40,
}

FIELD = _hex_to_rgb("#0b1020")
GLOW = (109, 124, 255)
GLOW_SOFT = (77, 91, 181)
NEURAL = (56, 189, 248)
INK = (231, 235, 250)


def _palette() -> dict:
    color = {}
    path = _PACKAGE / "configuration" / "appearance.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    pal = data.get("palette", {})
    for key, hexv in pal.items():
        h = hexv.lstrip("#")
        color[key] = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return color


def _clamp255(v):
    return int(max(0, min(255, v)))


def _write_png(path, size, rgba):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + bytes(rgba[y * size * 4:(y + 1) * size * 4])
                   for y in range(size))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    # Level 0 (stored DEFLATE blocks) so the PNG bytes are identical across
    # interpreters — zlib 1.3.1 and zlib-ng emit different compressed streams
    # at higher levels even for identical raw pixels.
    png += chunk(b"IDAT", zlib.compress(raw, 0))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)
    return png


# ---- segment rasterisation (deterministic integer tracing) ---------------

def _disc_mask(radius):
    """Small filled-disc offsets for round-capped strokes (radius in px)."""
    r = int(radius)
    if r < 1:
        r = 1
    mask = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r + 1:
                mask.append((dx, dy))
    return mask


_DISC_CACHE = {}


def _disc(r):
    rk = int(r)
    if rk not in _DISC_CACHE:
        _DISC_CACHE[rk] = _disc_mask(rk)
    return _DISC_CACHE[rk]


def _stamp_segment(core, px1, py1, px2, py2, width, colour, N, size=1):
    """Opaque round-capped line stamp (painter's order, like the Tk canvas).

    Stroke pixels overwrite earlier strokes, so dense mesh reads as crisp
    depth-coloured lines rather than a white blow-out.
    """
    r = _disc(max(1.0, width * size / 2.0))
    if not r:
        return core
    x0, y0 = int(px1), int(py1)
    x1, y1 = int(px2), int(py2)
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    cr, cg, cb = colour
    while True:
        if 0 <= x0 < N and 0 <= y0 < N:
            base = (y0 * N + x0) * 3
            for deld in r:
                xx = x0 + deld[0]
                yy = y0 + deld[1]
                if 0 <= xx < N and 0 <= yy < N:
                    i = base + (deld[1] * N + deld[0]) * 3
                    core[i] = cr
                    core[i + 1] = cg
                    core[i + 2] = cb
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return core


def _box_downsample(src, sw, dh):
    """Deterministic alpha-weighted box downscale (source RGBA bytes)."""
    sw = sw
    sh = sw
    out = bytearray(dh * dh * 4)
    scale = sw / dh
    for y in range(dh):
        y0 = int(y * scale)
        y1 = min(sw, y0 + max(1, int(scale)))
        for x in range(dh):
            x0 = int(x * scale)
            x1 = min(sw, x0 + max(1, int(scale)))
            acc = [0, 0, 0, 0]
            n = 0
            for yy in range(y0, y1):
                row = yy * sw * 4
                for xx in range(x0, x1):
                    i = row + xx * 4
                    a = src[i + 3]
                    acc[0] += src[i] * a
                    acc[1] += src[i + 1] * a
                    acc[2] += src[i + 2] * a
                    acc[3] += a
                    n += 1
            idx = (y * dh + x) * 4
            if acc[3] > 0:
                out[idx] = _clamp255(acc[0] / acc[3])
                out[idx + 1] = _clamp255(acc[1] / acc[3])
                out[idx + 2] = _clamp255(acc[2] / acc[3])
            out[idx + 3] = _clamp255(acc[3] / n)
    return out


# ---- convolution (bloom) --------------------------------------------------

def _box_blur_pass(buf, size, radius):
    """Separable box blur on a byte RGB buffer, in two sweeps (H then V)."""
    r = max(1, int(radius))
    work = bytearray(len(buf))
    w = size
    h = size
    row_len = w * 3
    # horizontal
    for y in range(h):
        base = y * row_len
        for c in range(3):
            total = 0
            for x in range(2 * r + 1):
                xi = min(w - 1, max(0, x - r))
                total += buf[base + xi * 3 + c]
            work[base + c] = _clamp255(total / (2 * r + 1))
            for x in range(1, w):
                x_in = x + r
                x_out = x - 1 - r
                total += buf[base + min(w - 1, x_in) * 3 + c]
                total -= buf[base + max(0, x_out) * 3 + c]
                work[base + x * 3 + c] = _clamp255(total / (2 * r + 1))
    # vertical
    out = bytearray(len(buf))
    for x in range(w):
        for c in range(3):
            total = sum(work[(min(h - 1, max(0, y)) * w + x) * 3 + c]
                        for y in range(-r, r + 1))
            out[x * 3 + c] = _clamp255(total / (2 * r + 1))
            for y in range(1, h):
                y_in = y + r
                y_out = y - 1 - r
                total += work[(min(h - 1, y_in) * w + x) * 3 + c]
                total -= work[(max(0, y_out) * w + x) * 3 + c]
                out[(y * w + x) * 3 + c] = _clamp255(total / (2 * r + 1))
    return out


def _soft(distance, thickness, softness):
    return max(0.0, min(1.0, 1.0 - (distance - thickness / 2.0) / max(1.0, softness)))


def _aura_bg(size):
    """Deep-night field with faint neural rings (deterministic)."""
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
            r += (GLOW_SOFT[0] - r) * t * 0.35
            g += (GLOW_SOFT[1] - g) * t * 0.35
            b += (GLOW_SOFT[2] - b) * t * 0.45
            i = (y * size + x) * 3
            buf[i] = _clamp255(r)
            buf[i + 1] = _clamp255(g)
            buf[i + 2] = _clamp255(b)
    return buf


def _stamp_radial(sparkle, size, x, y, radius, colour, strength):
    """Soft radial disc into an additive byte buffer."""
    r = int(radius)
    cr, cg, cb = colour
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d2 = dx * dx + dy * dy
            if d2 <= r * r + 1:
                xx = int(x) + dx
                yy = int(y) + dy
                if 0 <= xx < size and 0 <= yy < size:
                    falloff = (1.0 - math.sqrt(d2) / r) * strength
                    i = (yy * size + xx) * 3
                    sparkle[i] = _clamp255(sparkle[i] + cr * falloff)
                    sparkle[i + 1] = _clamp255(sparkle[i + 1] + cg * falloff)
                    sparkle[i + 2] = _clamp255(sparkle[i + 2] + cb * falloff)


def _compose(field, nebula, sparkle, master_size):
    buf = bytearray(master_size * master_size * 4)
    str3 = master_size * 3
    for y in range(master_size):
        for x in range(master_size):
            i3 = y * master_size + x
            i4 = i3 * 4
            i3b = i3 * 3
            r = field[i3b]
            g = field[i3b + 1]
            b = field[i3b + 2]
            nr = nebula[i3b]
            ng = nebula[i3b + 1]
            nb = nebula[i3b + 2]
            sr = sparkle[i3b]
            sg = sparkle[i3b + 1]
            sb = sparkle[i3b + 2]
            buf[i4] = _clamp255(r + nr + sr)
            buf[i4 + 1] = _clamp255(g + ng + sg)
            buf[i4 + 2] = _clamp255(b + nb + sb)
            buf[i4 + 3] = 255
    return buf


def _write_ico(path, sizes, rgba, src_size):
    body = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    data_blobs = []
    for size in sizes:
        small = _box_downsample(rgba, src_size, size)
        blob = _bmp_for_ico(small, size)
        entry_dim = 0 if size >= 256 else size
        body += struct.pack("<BBBBHHII", entry_dim, entry_dim, 0, 0, 1, 32,
                            len(blob), offset)
        data_blobs.append(blob)
        offset += len(blob)
    path.write_bytes(body + b"".join(data_blobs))


def _bmp_for_ico(rgba, size):
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         size * size * 4, 0, 0, 0, 0)
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        row = y * size * 4
        for x in range(size):
            i = row + x * 4
            pixels += struct.pack("<BBBB", rgba[i + 2], rgba[i + 1],
                                  rgba[i], rgba[i + 3])
    and_stride = ((size + 31) // 32) * 4
    and_mask = b"\x00" * (and_stride * size)
    return header + bytes(pixels) + and_mask


def build_core(master, ss=SUPERSAMPLE):
    """Return (core_rgb_float at master*ss, projected px/py, pose, mesh)."""
    N = master * ss
    mesh = get_mesh()
    fs = build_face_state(PRESETS["neutral"], t=0.5, mesh=mesh)
    pose = fs.pose

    projector = MeshProjector(N)
    px, py = projector.project(pose, mesh.vertex_count())
    engine = MaterialEngine("#0b1020")
    engine.clear_cache()

    core = bytearray(N * N * 3)
    regions = mesh.edge_region
    verts = pose
    edge_count = mesh.edge_count()
    materials = dict(DEFAULT_MATERIALS)
    for idx in range(edge_count):
        a, b = mesh.edges[idx]
        region = regions[idx] if idx < len(regions) else "default"
        za, zb = verts[a][2], verts[b][2]
        zmid = 0.5 * (za + zb)
        bucket = engine.bucket(zmid)
        hexcol = engine.edge_color(region, materials, bucket, z=zmid)
        colour = _hex_to_rgb(hexcol)
        width = max(1, edge_thickness(zmid, N))
        _stamp_segment(core, px[a], py[a], px[b], py[b], width, colour,
                       N, size=ss)
    return core, px, py, pose, mesh, fs


def render_assets(master=MASTER_SIZE, force=False, out_root=None):
    out_root = out_root or _AVATAR_DIR
    master = int(master)
    ss = SUPERSAMPLE
    N = master * ss

    core, px, py, pose, mesh, fs = build_core(master, ss)

    # glow: box-blur the painted core; merge at a modest halo gain
    glow_core = _blur_rgb(core, N, 4)
    nebula = _compose_steps(core, glow_core, N, 0.55)

    field = _aura_bg(N)
    sparkle = bytearray(N * N * 3)
    for name, rad in (("iris_l", 0.022), ("iris_r", 0.022),
                      ("nose_tip", 0.010)):
        idx = mesh.landmarks.get(name)
        if idx is not None:
            _stamp_radial(sparkle, N, px[idx], py[idx],
                          N * rad, NEURAL, 0.8)
    buf = _compose(field, nebula, sparkle, N)

    rgba = _composite_to_rgba(buf, N, master)
    master_png = _write_png(out_root / "maya_face_canonical.png", master,
                            rgba)
    sha = hashlib.sha256(master_png).hexdigest()

    variants = {
        "maya_face_canonical_256.png": 256,
        "maya_face_canonical_128.png": 128,
        "maya_face_canonical_48.png": 48,
    }
    for name, size in variants.items():
        small = _box_downsample(rgba, master, size)
        _write_png(out_root / name, size, small)

    ico_sizes = _icon_sizes()
    _write_ico(out_root / "maya_face_canonical.ico", ico_sizes, rgba, master)
    return {
        "master_size": master,
        "sha256": sha,
        "raw_sha256": hashlib.sha256(bytes(rgba)).hexdigest(),
    }


def _icon_sizes():
    path = _PACKAGE / "configuration" / "appearance.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [int(s) for s in data.get("avatar", {}).get("ico_sizes",
                                                       [16, 24, 32, 48, 64, 256])]


def _blur_rgb(core, N, radius):
    return _box_blur_pass(bytes(core), N, radius)


def _compose_steps(core, glow_core, N, gain):
    """Painted core merged with its additive blurred halo."""
    out = bytearray(N * N * 3)
    for i in range(N * N):
        i3 = i * 3
        out[i3] = _clamp255(core[i3] + glow_core[i3] * gain)
        out[i3 + 1] = _clamp255(core[i3 + 1] + glow_core[i3 + 1] * gain)
        out[i3 + 2] = _clamp255(core[i3 + 2] + glow_core[i3 + 2] * gain)
    return out


def _composite_to_rgba(buf, N, master):
    """Deterministic 4x box downsample of the composited full buffer."""
    return _box_downsample(bytes(buf), N, master)


def main():
    force = "--force" in sys.argv[1:]
    print("render_canonical_face: batch 8a canonical raster")
    names = ("maya_face_canonical.png",
             "maya_face_canonical_256.png",
             "maya_face_canonical_128.png",
             "maya_face_canonical_48.png",
             "maya_face_canonical.ico")
    existing = [n for n in names if (_AVATAR_DIR / n).exists()]
    if existing and not force:
        raise SystemExit(
            "canonical protection: existing assets are never overwritten "
            f"without --force: {', '.join(existing)}")
    report = render_assets(force=force)
    for name in names:
        p = _AVATAR_DIR / name
        print("WROTE", name, p.stat().st_size)
    print("MASTER_SHA256", report["sha256"])
    print("MASTER_RAW_SHA256", report["raw_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())