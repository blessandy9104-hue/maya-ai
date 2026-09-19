"""Analytic human facial mesh for the wireframe face.

The neutral mesh is generated deterministically as a wrap-around 3D head:
horizontal cross-section loops (crown to shoulders) lofted into a dense,
feature-clustered wireframe surface, plus recessed orbital globes, lidded
eyes with irises and pupils, a true nasal ball with alar wings and nostril
openings, a mouth with an oral cavity, protruding ears, and a tapering
neck. Every vertex is tagged with a region and rig parameters so the
expression controller can deform it analytically. No randomness, no image
assets, no static scans.
"""
from __future__ import annotations

import math

MODEL_VERSION = "1.0.0"

N_U = 44
N_V = 70

# Vertical cross-section profile, from crown (top) to shoulders (bottom).
# Each entry is (y, half_width, front_depth, back_depth).
_PROFILE = [
    (1.20, 0.58, 0.15, -0.15),
    (1.05, 0.66, 0.30, -0.30),
    (0.90, 0.73, 0.42, -0.38),
    (0.74, 0.79, 0.52, -0.44),
    (0.62, 0.80, 0.56, -0.47),
    (0.52, 0.78, 0.58, -0.47),
    (0.44, 0.79, 0.60, -0.46),
    (0.34, 0.80, 0.60, -0.46),
    (0.26, 0.84, 0.60, -0.46),
    (0.16, 0.92, 0.61, -0.46),
    (0.04, 0.90, 0.63, -0.48),
    (-0.02, 0.87, 0.66, -0.50),
    (-0.10, 0.86, 0.68, -0.50),
    (-0.20, 0.82, 0.66, -0.49),
    (-0.30, 0.78, 0.64, -0.48),
    (-0.40, 0.82, 0.64, -0.48),
    (-0.50, 0.84, 0.63, -0.46),
    (-0.60, 0.72, 0.70, -0.44),
    (-0.68, 0.60, 0.72, -0.42),
    (-0.76, 0.60, 0.58, -0.40),
    (-0.86, 0.66, 0.42, -0.40),
    (-0.98, 0.76, 0.32, -0.42),
    (-1.12, 0.94, 0.20, -0.50),
    (-1.30, 1.08, 0.12, -0.55),
]

_EYE_YC = 0.34
_EYE_XC = 0.40

# Feature bands used for row/column clustering so the mesh is denser where
# facial anatomy changes quickly (scan-style topology).
_FEATURE_Y = [
    (0.56, 22.0, 0.055),
    (0.40, 20.0, 0.075),
    (0.34, 20.0, 0.060),
    (0.02, 26.0, 0.085),
    (-0.05, 20.0, 0.070),
    (-0.31, 24.0, 0.055),
    (-0.47, 18.0, 0.055),
    (-0.63, 16.0, 0.065),
    (-0.28, 8.0, 0.14),
]


def _smoothstep(t):
    t = max(0.0, min(1.0, float(t)))
    return t * t * (3.0 - 2.0 * t)


def _knot(t, pts):
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= t <= x1:
            u = _smoothstep((t - x0) / (x1 - x0)) if x1 > x0 else 0.0
            return y0 + (y1 - y0) * u
    return pts[-1][1]


def _gauss(v, center, width):
    d = (v - center) / width
    return math.exp(-d * d)


def _distribute(n, lo, hi, wfn):
    """Return n-1 interior samples clustered where wfn(value) is high."""
    steps = 2400
    accs = [0.0]
    acc = 0.0
    for k in range(1, steps + 1):
        t = lo + (hi - lo) * (k / steps)
        acc += max(1e-6, wfn(t))
        accs.append(acc)
    total = accs[-1]
    out = []
    for i in range(1, n):
        goal = total * i / (max(1, n - 1))
        lo_k, hi_k = 0, steps
        while lo_k < hi_k:
            mid = (lo_k + hi_k) // 2
            if accs[mid] < goal:
                lo_k = mid + 1
            else:
                hi_k = mid
        out.append(lo + (hi - lo) * (lo_k / steps))
    return out


def _ydetail(y):
    d = 8.0
    for cy, amp, cw in _FEATURE_Y:
        d += amp * _gauss(y, cy, cw)
    return d


def _ys(n):
    out = _distribute(n, _PROFILE[0][0], _PROFILE[-1][0], _ydetail)
    return [float(v) for v in out]


def _us(n):
    """Columns clustered near the front midline and the two temple sides."""
    detail = [
        (0.25, 26.0, 0.055),
        (0.005, 10.0, 0.050),
        (0.50, 12.0, 0.070),
        (0.75, 4.0, 0.070),
    ]

    def w_u(t):
        d = 6.0
        for cu, amp, cw in detail:
            d += amp * _gauss(t, cu, cw)
        return d

    return [t for t in _distribute(n + 1, 0.0, 1.0, w_u) if 0.0 < t < 1.0][:n]


def _profile_at(y):
    lo, hi = _PROFILE[0][0], _PROFILE[-1][0]
    y = max(hi, min(lo, float(y)))
    for i in range(len(_PROFILE) - 1):
        y0, w0, f0, b0 = _PROFILE[i]
        y1, w1, f1, b1 = _PROFILE[i + 1]
        if y0 >= y >= y1:
            t = _smoothstep((y - y0) / (y1 - y0)) if y1 != y0 else 0.0
            return (w0 + (w1 - w0) * t,
                    f0 + (f1 - f0) * t,
                    b0 + (b1 - b0) * t)
    return _PROFILE[-1][1], _PROFILE[-1][2], _PROFILE[-1][3]


def _wrap_point(u, y):
    """Base wrap position for column u and row y (front loop, full head)."""
    rx, zf, zb = _profile_at(y)
    phi = 2.0 * math.pi * u
    x = rx * math.cos(phi)
    zc = (zf + zb) * 0.5
    dz = (zf - zb) * 0.5
    z = zc + dz * math.sin(phi)
    return x, y, z


def _z_delta(x, y):
    """Anatomical depth displacement over the wrap surface."""
    z = 0.0
    ax = abs(x)
    z += 0.10 * _gauss(y, 0.56, 0.055) * _gauss(x, 0.0, 0.52)          # brow ridge
    z += 0.045 * _gauss(y, 0.80, 0.14) * _gauss(x, 0.0, 0.42)          # frontal eminence
    z -= 0.060 * _gauss(y, 0.34, 0.13) * (
        _gauss(x, -_EYE_XC, 0.15) + _gauss(x, _EYE_XC, 0.15))          # orbital hollows
    z -= 0.035 * _gauss(y, 0.28, 0.07) * (
        _gauss(x, -_EYE_XC, 0.17) + _gauss(x, _EYE_XC, 0.17))          # tear-trough + upper cheek recess
    z -= 0.045 * _gauss(y, 0.36, 0.10) * _gauss(ax, 0.80, 0.16)        # temple hollows
    z += 0.075 * _gauss(y, 0.14, 0.14) * _gauss(ax, 0.70, 0.14)        # cheekbones
    z += 0.030 * _gauss(y, 0.14, 0.10) * _gauss(ax, 0.92, 0.10)        # zygomatic arch
    z -= 0.045 * _gauss(y, 0.03, 0.16) * _gauss(ax, 0.48, 0.13)        # lower cheek hollow
    z -= 0.050 * _gauss(ax, 0.47, 0.09) * _gauss(y, -0.02, 0.12)        # nasolabial grooves
    # nose: bridge, dorsal, ball, alar wings
    nose = 0.30 * _gauss(y, -0.02, 0.16) * _gauss(x, 0.0, 0.135)
    nose += 0.16 * _gauss(y, 0.22, 0.16) * _gauss(x, 0.0, 0.095)       # bridge
    z += nose * _smoothstep(1.0 - ax / 0.34)
    z += 0.10 * _gauss(y, -0.02, 0.09) * _gauss(ax, 0.24, 0.055)        # alar wings
    z -= 0.03 * _gauss(y, 0.52, 0.03) * _gauss(x, 0.0, 0.04)            # glabella dip
    # lips, philtrum, chin
    z += 0.055 * _gauss(y, -0.245, 0.045) * _gauss(x, 0.0, 0.17)       # upper lip
    z -= 0.012 * _gauss(y, -0.245, 0.045) * _gauss(x, 0.0, 0.05)       # cupid's bow notch
    z += 0.060 * _gauss(y, -0.375, 0.050) * _gauss(x, 0.0, 0.155)      # lower lip
    z -= 0.085 * _gauss(y, -0.315, 0.030) * (1.0 - 0.35 * ax / 0.28)   # mouth opening trench
    z -= 0.050 * _gauss(y, -0.475, 0.040) * _gauss(x, 0.0, 0.24)       # chin crease
    z += 0.035 * _gauss(y, -0.12, 0.055) * (
        _gauss(x, 0.062, 0.030) + _gauss(x, -0.062, 0.030))            # philtrum columns
    z += 0.050 * _gauss(y, -0.62, 0.085) * _gauss(x, 0.0, 0.16)        # chin ball
    z += 0.020 * _gauss(y, -0.50, 0.15) * _gauss(ax, 0.70, 0.10)       # masseter / jaw angle
    if y < -0.75:
        under = (-0.75 - y) / 0.12
        z -= 0.16 * _smoothstep(under)                                 # under-chin recession
    return z


def _wrap_region(y, x):
    if y > 0.94:
        return "scalp"
    if y > 0.62:
        return "forehead"
    if y > 0.50:
        if abs(x) > 0.62:
            return "temple_l" if x < 0 else "temple_r"
        return "brow_l" if x < 0 else "brow_r"
    if y > 0.16:
        if abs(x) > 0.60:
            return "temple_l" if x < 0 else "temple_r"
        return "cheek_l" if x < 0 else "cheek_r"
    if y > -0.16:
        if abs(x) < 0.34:
            return "nose"
        return "cheek_l" if x < 0 else "cheek_r"
    if y > -0.44:
        if abs(x) < 0.30:
            return "mouth"
        return "cheek_l" if x < 0 else "cheek_r"
    if y > -0.72:
        if abs(x) < 0.36:
            return "chin"
        return "jaw_l" if x < 0 else "jaw_r"
    if y > -0.90:
        return "jaw_l" if x < 0 else "jaw_r"
    return "neck"


class Mesh:
    """Vertex/edge model with region membership, landmarks, and rig params."""

    def __init__(self):
        self.verts = []
        self.vpar = []
        self.edges = []
        self.regions = {}
        self.landmarks = {}
        self.edge_region = []
        self.version = MODEL_VERSION

    def add_vertex(self, pos, region, params=None):
        self.verts.append((float(pos[0]), float(pos[1]), float(pos[2])))
        self.vpar.append(params or {})
        self.regions.setdefault(region, []).append(len(self.verts) - 1)
        return len(self.verts) - 1

    def add_edge(self, a, b, region):
        self.edges.append((int(a), int(b)))
        self.edge_region.append(region)

    def set_landmark(self, name, index):
        self.landmarks[name] = int(index)

    def vertex_count(self):
        return len(self.verts)

    def edge_count(self):
        return len(self.edges)


def _build_wrap(m, ys, us):
    """Loft the cross-section loops into the wrap surface + anatomy deltas."""
    ids = {}
    for j, y in enumerate(ys):
        tag_jaw = clamp01_s((-0.16 - y) / 0.55)
        tag_neck = 1.0 if y < -0.88 else (0.55 if y < -0.76 else 0.35)
        for i, u in enumerate(us):
            x, _, z = _wrap_point(u, y)
            z += _z_delta(x, y)
            region = _wrap_region(y, x)
            lidx = None
            if y > -0.27 and y < -0.15:
                lidx = 1 if y < -0.205 else -1
            params = {
                "region": region,
                "row": j,
                "jcol": i,
                "u": u,
                "jaw_w": tag_jaw if region not in ("neck",) else tag_neck,
            }
            if lidx is not None and abs(x) < 0.30:
                params["lip"] = lidx
            idx = m.add_vertex((x, y, z), region, params)
            ids[(j, i)] = idx
    return ids


def clamp01_s(x):
    return max(0.0, min(1.0, float(x)))


def _add_wrap_edges(m, ids, us, tri_rows):
    n_j = len(tri_rows)
    n_i = len(us)
    for j in range(n_j):
        for i in range(n_i):
            a = ids[(j, i)]
            b = ids[(j, (i + 1) % n_i)]
            m.add_edge(a, b, "skin")
            if j + 1 < n_j:
                m.add_edge(a, ids[(j + 1, i)], "skin")
    for j in range(n_j - 1):
        if not tri_rows[j] and not tri_rows[j + 1]:
            continue
        for i in range(n_i - 1):
            a = ids[(j, i)]
            c = ids[(j + 1, i + 1)]
            if (j + 1) % 2 == i % 2 or tri_rows[j]:
                m.add_edge(a, c, "scan")


def _tri_rows(ys):
    return [
        0.02 < y < 0.72 or -0.52 < y < -0.20 or (0.86 > y > 0.70)
        for y in ys
    ]


def _add_eye(m, sign, ys, us):
    """Recessed orbital globe + lids + iris + pupil for one eye."""
    region = "l" if sign < 0 else "r"
    eid = 0 if sign < 0 else 1
    ecx = sign * _EYE_XC
    ecy = _EYE_YC
    tilt = sign * 0.16
    socket_surface = None
    for j, y in enumerate(ys):
        for i, u in enumerate(us):
            if not (0.0 < u < 0.5):
                continue
            x, _, z = _wrap_point(u, y)
            if abs(x - ecx) < 0.11 and abs(y - ecy) < 0.09:
                z += _z_delta(x, y)
                socket_surface = z
    if socket_surface is None:
        socket_surface = 0.55
    globe_z = socket_surface - 0.055
    gx, gy = 0.135, 0.105
    # orbital rim (sits on the face surface)
    rim = []
    for k in range(14):
        a = 2.0 * math.pi * k / 14
        lx, ly = 0.235 * math.cos(a), 0.165 * math.sin(a) * 0.78
        wx, wy = _rot(lx, ly, tilt)
        m.add_vertex((ecx + wx, ecy + wy, socket_surface + 0.012),
                     "socket_" + region,
                     {"eid": eid, "etype": "rim", "ex": lx, "ey": ly,
                      "tilt": tilt, "ecx": ecx, "ecy": ecy, "z": socket_surface})
        rim.append(len(m.verts) - 1)
    for k in range(14):
        m.add_edge(rim[k], rim[(k + 1) % 14], "socket")
    # lids (upper/lower arcs riding the socket)
    lid_top, lid_bot = [], []
    for k in range(9):
        a = 0.10 + (math.pi - 0.20) * k / 8
        lx, ly = 0.225 * math.cos(a), 0.150 * math.sin(a)
        wx, wy = _rot(lx, ly, tilt)
        m.add_vertex((ecx + wx, ecy + wy, socket_surface + 0.014),
                     "lid_top_" + region,
                     {"eid": eid, "etype": "lid", "vin": 1, "ex": lx, "ey": ly,
                      "tilt": tilt, "ecx": ecx, "ecy": ecy, "z": socket_surface})
        lid_top.append(len(m.verts) - 1)
    for k in range(9):
        a = math.pi + 0.10 + (math.pi - 0.20) * k / 8
        lx, ly = 0.225 * math.cos(a), 0.150 * math.sin(a)
        wx, wy = _rot(lx, ly, tilt)
        m.add_vertex((ecx + wx, ecy + wy, socket_surface + 0.010),
                     "lid_bot_" + region,
                     {"eid": eid, "etype": "lid", "vin": -1, "ex": lx, "ey": ly,
                      "tilt": tilt, "ecx": ecx, "ecy": ecy, "z": socket_surface})
        lid_bot.append(len(m.verts) - 1)
    for s in range(8):
        m.add_edge(lid_top[s], lid_top[s + 1], "lid")
        m.add_edge(lid_bot[s], lid_bot[s + 1], "lid")
    m.add_edge(lid_top[0], rim[0], "lid")
    m.add_edge(lid_top[-1], rim[7], "lid")
    m.add_edge(lid_bot[0], rim[7], "lid")
    m.add_edge(lid_bot[-1], rim[0], "lid")
    # globe shell (recessed front hemisphere: latitude/longitude wire grid)
    lat_rows = []
    for lk in range(6):
        lat = -0.9 + 0.36 * lk
        row = []
        for ln in range(9):
            lon = math.pi * ln / 8
            lx = gx * math.cos(lon) * math.cos(lat)
            ly = gy * math.sin(lat)
            wlx, wly = _rot(lx, ly, tilt)
            m.add_vertex((ecx + wlx, ecy + wly, globe_z + gx * 0.9 * math.sin(lon)),
                         "globe_" + region,
                         {"eid": eid, "etype": "globe", "ex": lx, "ey": ly,
                          "tilt": tilt, "ecx": ecx, "ecy": ecy, "z": globe_z})
            row.append(len(m.verts) - 1)
        lat_rows.append(row)
    for lk, row in enumerate(lat_rows):
        for s in range(len(row) - 1):
            m.add_edge(row[s], row[s + 1], "globe")
        if lk + 1 < len(lat_rows):
            for s in range(len(row)):
                m.add_edge(lat_rows[lk + 1][s], row[s], "globe")
    # iris + pupil (front of the globe)
    iris_front = globe_z + 0.02
    iris = []
    for k in range(12):
        a = 2.0 * math.pi * k / 12
        lx, ly = 0.082 * math.cos(a), 0.068 * math.sin(a)
        wlx, wly = _rot(lx, ly, tilt)
        m.add_vertex((ecx + wlx, ecy + wly, iris_front),
                     "iris_" + region,
                     {"eid": eid, "etype": "iris", "ex": lx, "ey": ly,
                      "tilt": tilt, "ecx": ecx, "ecy": ecy, "z": iris_front})
        iris.append(len(m.verts) - 1)
    for k in range(12):
        m.add_edge(iris[k], iris[(k + 1) % 12], "iris")
    pupil = []
    for k in range(8):
        a = 2.0 * math.pi * k / 8
        lx, ly = 0.045 * math.cos(a), 0.038 * math.sin(a)
        wlx, wly = _rot(lx, ly, tilt)
        m.add_vertex((ecx + wlx, ecy + wly, iris_front + 0.012),
                     "pupil_" + region,
                     {"eid": eid, "etype": "pupil", "ex": lx, "ey": ly,
                      "tilt": tilt, "ecx": ecx, "ecy": ecy, "z": iris_front + 0.012})
        pupil.append(len(m.verts) - 1)
    for k in range(8):
        m.add_edge(pupil[k], pupil[(k + 1) % 8], "pupil")
    ci = m.add_vertex((ecx, ecy, iris_front + 0.004), "iris_" + region,
                      {"eid": eid, "etype": "iris", "ex": 0.0, "ey": 0.0,
                       "tilt": tilt, "ecx": ecx, "ecy": ecy, "z": iris_front + 0.004})
    cp = m.add_vertex((ecx, ecy, iris_front + 0.016), "pupil_" + region,
                      {"eid": eid, "etype": "pupil", "ex": 0.0, "ey": 0.0,
                       "tilt": tilt, "ecx": ecx, "ecy": ecy, "z": iris_front + 0.016})
    m.set_landmark("iris_" + region, ci)
    m.set_landmark("pupil_" + region, cp)
    for k in range(0, 12, 3):
        m.add_edge(ci, iris[k], "spoke")
    for k in range(0, 8, 2):
        m.add_edge(cp, pupil[k], "spoke")
    for k in range(4):
        m.add_edge(iris[2 + k], pupil[k], "spoke")
    m.set_landmark("corner_inner_" + region, rim[0] if sign < 0 else rim[7])
    m.set_landmark("corner_outer_" + region, rim[7] if sign < 0 else rim[0])
    m.add_edge(lid_top[4], iris[0], "attach")
    m.add_edge(lid_bot[4], iris[6], "attach")


def _rot(lx, ly, tilt):
    c, s = math.cos(tilt), math.sin(tilt)
    return lx * c - ly * s, lx * s + ly * c


def _add_nostrils(m):
    """Nostril openings + alar wings under the nasal ball."""
    for sign in (-1, 1):
        region = "l" if sign < 0 else "r"
        cxs = sign * 0.27
        ring = []
        for k in range(8):
            a = math.pi * k / 7
            lx = 0.075 * math.cos(a) * 0.6
            ly = 0.022 * math.sin(a)
            m.add_vertex((cxs + lx, -0.035 + ly, 0.78),
                         "nostril_" + region,
                         {"eid": None, "etype": "nostril", "nst": sign,
                          "ex": lx, "ey": ly})
            ring.append(len(m.verts) - 1)
        for k in range(7):
            m.add_edge(ring[k], ring[k + 1], "nostril")
        cavity = []
        for k in range(5):
            a = math.pi * k / 4
            lx = 0.045 * math.cos(a) * 0.55
            ly = 0.014 * math.sin(a)
            m.add_vertex((cxs + lx, -0.030 + ly, 0.70),
                         "cavity", {"etype": "cavity"})
            cavity.append(len(m.verts) - 1)
        for k in range(4):
            m.add_edge(cavity[k], cavity[k + 1], "cavity")
        for k in range(4):
            m.add_edge(cavity[k], ring[k + 2], "cavity")


def _add_mouth(m):
    """Oral cavity recess (mouth opening) + cupid's-bow rim."""
    rim = []
    for k in range(12):
        a = 2.0 * math.pi * k / 12
        lx, ly = 0.235 * math.cos(a), 0.095 * math.sin(a)
        m.add_vertex((lx, -0.315 + ly, 0.535),
                     "mouth_inner",
                     {"etype": "mouth_rim", "ex": lx, "ey": ly,
                      "corner": 1.0 if abs(a - math.pi) < 0.6 or abs(a) < 0.6 else 0.0})
        rim.append(len(m.verts) - 1)
    for k in range(12):
        m.add_edge(rim[k], rim[(k + 1) % 12], "mouth")
    m.set_landmark("mouth_corner_l", rim[6])
    m.set_landmark("mouth_corner_r", rim[0])
    cavity = []
    for k in range(10):
        a = 2.0 * math.pi * k / 10
        lx, ly = 0.145 * math.cos(a), 0.055 * math.sin(a)
        m.add_vertex((lx, -0.315 + ly, 0.46),
                     "mouth_cavity",
                     {"etype": "cavity"})
        cavity.append(len(m.verts) - 1)
    for k in range(10):
        m.add_edge(cavity[k], cavity[(k + 1) % 10], "cavity")
    for k in range(6):
        m.add_edge(rim[k + 3], cavity[k + 2], "cavity")
    m.set_landmark("upper_lip_c", rim[3])
    m.set_landmark("lower_lip_c", rim[9])


def _build_ear_shell(m, sign):
    region = "l" if sign < 0 else "r"
    cx = sign * 1.02
    cy = 0.10
    pts = []
    for k in range(14):
        a = 2.0 * math.pi * k / 14
        lx, ly = 0.085 * math.cos(a), 0.21 * math.sin(a)
        x = cx + lx
        y = cy + ly
        z = 0.16 + 0.10 * math.cos(a) * (ly > -0.10)
        m.add_vertex((x, y, z), "ear_" + region,
                     {"etype": "ear", "es": sign})
        pts.append(len(m.verts) - 1)
    for k in range(14):
        m.add_edge(pts[k], pts[(k + 1) % 14], "ear")
    inner = []
    for k in range(7):
        a = math.pi * k / 6 - 0.5 + (math.pi * k // 6) * 0.0
        lx, ly = 0.038 * math.cos(a), 0.115 * math.sin(a)
        m.add_vertex((cx + lx, cy + ly, 0.21),
                     "ear_" + region, {"etype": "ear", "es": sign})
        inner.append(len(m.verts) - 1)
    for k in range(6):
        m.add_edge(inner[k], inner[k + 1], "ear")
    for k in range(5):
        m.add_edge(pts[2 + k], inner[k + 1], "ear")
    m.set_landmark("ear_" + region, pts[0])


def build_mesh():
    """Build and return the neutral 3D facial mesh (deterministic)."""
    m = Mesh()
    ys = _ys(N_V)
    us = _us(N_U)
    ids = _build_wrap(m, ys, us)
    _add_wrap_edges(m, ids, us, _tri_rows(ys))
    _add_eye(m, -1, ys, us)
    _add_eye(m, 1, ys, us)
    _add_nostrils(m)
    _add_mouth(m)
    _build_ear_shell(m, -1)
    _build_ear_shell(m, 1)
    _add_wrap_landmarks(m, ys, us, ids)
    return m


def _add_wrap_landmarks(m, ys, us, ids):

    def nearest(x, y, band=0.10):
        best, best_d = None, 1e9
        for j in range(len(ys)):
            for i in range(len(us)):
                vx, vy = m.verts[ids[(j, i)]][0], m.verts[ids[(j, i)]][1]
                if abs(vy - y) > band:
                    continue
                if m.verts[ids[(j, i)]][2] < 0.0:
                    continue
                d = (vx - x) ** 2 + (vy - y) ** 2
                if d < best_d:
                    best_d, best = d, ids[(j, i)]
        return best

    m.set_landmark("nose_tip", nearest(0.0, -0.01, 0.08))
    m.set_landmark("nose_root", nearest(0.0, 0.50, 0.08))
    m.set_landmark("brow_in_l", nearest(-0.22, 0.56, 0.06))
    m.set_landmark("brow_in_r", nearest(0.22, 0.56, 0.06))
    m.set_landmark("brow_out_l", nearest(-0.62, 0.56, 0.06))
    m.set_landmark("brow_out_r", nearest(0.62, 0.56, 0.06))


_MESH_CACHE = None


def get_mesh():
    global _MESH_CACHE
    if _MESH_CACHE is None:
        _MESH_CACHE = build_mesh()
    return _MESH_CACHE


if __name__ == "__main__":
    mesh = get_mesh()
    print(
        "wireframe mesh %s vertices=%d edges=%d regions=%d landmarks=%d"
        % (mesh.version, mesh.vertex_count(), mesh.edge_count(),
           len(mesh.regions), len(mesh.landmarks))
    )