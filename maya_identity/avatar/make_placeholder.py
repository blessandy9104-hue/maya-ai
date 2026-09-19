"""Generate Maya PLACEHOLDER avatar assets (layout only).

This tool renders a neutral indigo monogram ring. It is intentionally NOT a
face: Maya's official identity comes from the controlled reference pipeline
(prompts/portrait_generation.md) and must never be produced by this script.

Generated files:
- maya_face_placeholder.png      (portrait size, layout)
- maya_identity_placeholder.ico  (multi-size window icon)

The script never overwrites canonical assets. If a canonical file exists at the
destination it is left untouched.
"""
from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

AUTODIR = Path(__file__).resolve().parent
ROOT = AUTODIR.parent
PORTRAIT_SIZE = 512
ACCENT = (109, 124, 255)
GLOW_SOFT = (77, 91, 181)
BG = (10, 14, 26)


def seg_dist(px, py, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def soft(distance, thickness, softness):
    return max(0.0, min(1.0, 1.0 - (distance - thickness / 2.0) / max(1.0, softness)))


def overlay(acc, srca, colour):
    top = min(1.0, srca)
    if top <= 0:
        return
    r, g, b = acc[:3]
    a = acc[3]
    na = a + top * (1.0 - a)
    if na <= 0:
        acc[:] = (r, g, b, 0)
        return
    acc[:3] = (
        (colour[0] * top + r * a * (1.0 - top)) / na,
        (colour[1] * top + g * a * (1.0 - top)) / na,
        (colour[2] * top + b * a * (1.0 - top)) / na,
    )
    acc[3] = na


def render_portrait(cx, cy, size):
    buf = bytearray(size * size * 4)
    glyph = [
        (0.28, 0.32, 0.28, 0.72),
        (0.72, 0.32, 0.72, 0.72),
        (0.28, 0.32, 0.50, 0.72),
        (0.72, 0.32, 0.50, 0.72),
    ]
    glyph_w = 0.075 * size
    ring1_r = 0.40 * size
    ring1_w = 0.026 * size
    ring2_r = 0.31 * size
    ring2_w = 0.011 * size
    aura_r = 0.46 * size
    for y in range(size):
        for x in range(size):
            px = x - cx
            py = y - cy
            acc = [0.0, 0.0, 0.0, 0.0]
            d_aura = math.hypot(px, py)
            overlay(acc, soft(d_aura, aura_r * 2, aura_r * 0.8) * 0.18, GLOW_SOFT)
            d_ring1 = abs(math.hypot(px, py) - ring1_r)
            overlay(acc, soft(d_ring1, ring1_w, ring1_w * 1.6), ACCENT)
            d_ring2 = abs(math.hypot(px, py) - ring2_r)
            overlay(acc, soft(d_ring2, ring2_w, ring2_w * 1.6), GLOW_SOFT)
            d_glyph = min(seg_dist(px + cx, py + cy, ax * size, ay * size,
                                   bx * size, by * size) for ax, ay, bx, by in glyph)
            overlay(acc, soft(d_glyph, glyph_w, glyph_w * 1.8), ACCENT)
            if d_glyph < glyph_w * 0.55:
                overlay(acc, 0.35, (220, 232, 255))
            idx = (y * size + x) * 4
            buf[idx] = int(max(0, min(255, acc[0])))
            buf[idx + 1] = int(max(0, min(255, acc[1])))
            buf[idx + 2] = int(max(0, min(255, acc[2])))
            buf[idx + 3] = int(max(0, min(255, acc[3] * 255)))
    return buf


def write_png(path, size, rgba):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(rgba[y * size * 4:(y + 1) * size * 4]) for y in range(size))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def downsample(rgba, src, dst):
    out = bytearray(dst * dst * 4)
    scale = src / dst
    for y in range(dst):
        y0 = int(y * scale)
        y1 = min(src, y0 + max(1, int(scale)))
        for x in range(dst):
            x0 = int(x * scale)
            x1 = min(src, x0 + max(1, int(scale)))
            acc = [0, 0, 0, 0]
            n = 0
            for yy in range(y0, y1):
                row = yy * src * 4
                for xx in range(x0, x1):
                    i = row + xx * 4
                    alpha = rgba[i + 3]
                    acc[0] += rgba[i] * alpha
                    acc[1] += rgba[i + 1] * alpha
                    acc[2] += rgba[i + 2] * alpha
                    acc[3] += alpha
                    n += 1
            idx = (y * dst + x) * 4
            if acc[3] > 0:
                out[idx] = min(255, int(acc[0] / acc[3]))
                out[idx + 1] = min(255, int(acc[1] / acc[3]))
                out[idx + 2] = min(255, int(acc[2] / acc[3]))
            out[idx + 3] = min(255, int(acc[3] / n))
    return out


def bmp_for_ico(rgba, size):
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0)
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        row = y * size * 4
        for x in range(size):
            i = row + x * 4
            pixels += struct.pack("<BBBB", rgba[i + 2], rgba[i + 1], rgba[i], rgba[i + 3])
    and_stride = ((size + 31) // 32) * 4
    and_mask = b"\x00" * (and_stride * size)
    return header + bytes(pixels) + and_mask


def write_ico(path, sizes, rgba):
    body = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    data_blobs = []
    for size in sizes:
        small = downsample(rgba, PORTRAIT_SIZE, size)
        blob = bmp_for_ico(small, size)
        entry_dim = 0 if size >= 256 else size
        body += struct.pack("<BBBBHHII", entry_dim, entry_dim, 0, 0, 1, 32, len(blob), offset)
        data_blobs.append(blob)
        offset += len(blob)
    path.write_bytes(body + b"".join(data_blobs))


def main():
    import json
    import sys as _sys
    force = "--force" in _sys.argv[1:]
    render = json.loads((AUTODIR.parent / "configuration" / "appearance.json").read_text(encoding="utf-8"))
    avatar = render["avatar"]
    rgba = render_portrait(PORTRAIT_SIZE // 2, PORTRAIT_SIZE // 2, PORTRAIT_SIZE)
    jobs = []
    for key, name in avatar["placeholder_names"].items():
        size = {"portrait": 512, "portrait_medium": 256, "portrait_small": 128, "icon_png": 48}.get(key)
        if size is None:
            continue
        jobs.append((AUTODIR / name, size))
    for target, size in jobs:
        if target.exists() and not force:
            print(f"SKIP exists (canonical protection): {target.name}")
            continue
        small = downsample(rgba, PORTRAIT_SIZE, size)
        write_png(target, size, small)
        print(f"WROTE placeholder portrait {target.name}")
    icon = AUTODIR / avatar["placeholder_names"]["icon"]
    if icon.exists() and not force:
        print(f"SKIP exists (canonical protection): {icon.name}")
    else:
        write_ico(icon, avatar["ico_sizes"], rgba)
        print(f"WROTE placeholder icon {icon.name}")


if __name__ == "__main__":
    sys.exit(main())