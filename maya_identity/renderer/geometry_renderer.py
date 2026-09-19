"""Geometry renderer — turns Maya's geometry definition into primitives.

Pure geometry: reads only ``geometry/`` definitions and the active expression
transform, and produces unit-space paths. It cannot read memory, execute
commands, or change any system outside the visual layer.
"""
from __future__ import annotations

import math


def mirror_x(x: float, axis: float = 0.5) -> float:
    return axis - (x - axis)


def mirror_polyline(pts, axis: float = 0.5):
    return [(mirror_x(x, axis), y) for (x, y) in reversed(pts)]


def sampling(n: int) -> list:
    return [i / max(1, n - 1) for i in range(n)]


class GeometryRenderer:
    """Resolves canonical geometry + expression deltas into unit-space paths.

    Symmetry is enforced here: every right-side feature is derived from the
    canonical left-side definition by mirroring about ``symmetry_axis_x``.
    """

    def __init__(self, bundle: dict):
        self.identity = bundle["identity"]
        self.fs = bundle["facial_structure"]
        self.sym = bundle["symmetry"]
        self.np = bundle["neural_pattern"]
        self.axis = float(self.sym.get("axis", 0.5))

    # ----- structural accessors (unit space) -----

    def face_outline(self):
        o = self.fs["face_outline"]
        pts = []
        seg = int(o["segments"])
        for i in range(seg):
            a = 2 * math.pi * i / seg
            pts.append((o["cx"] + o["rx"] * math.cos(a), o["cy"] + o["ry"] * math.sin(a)))
        return pts

    def jaw_arc(self):
        j = self.fs["jaw"]
        pts = []
        r0, r1 = math.radians(j["theta_start"]), math.radians(j["theta_end"])
        for i in range(10):
            a = r0 + (r1 - r0) * i / 9
            pts.append((j["cx"] + j["rx"] * math.cos(a), j["cy"] + j["ry"] * math.sin(a)))
        return pts

    def mirrored_pairs(self, feature_key: str):
        """Return ((left_pts, right_pts), ...) built from canonical left data."""
        item = self.fs[feature_key]
        if isinstance(item, dict) and "left" in item and "right" in item:
            left = item["left"]
            right = mirror_polyline(left, self.axis)
            return (left, right)
        return (item, mirror_polyline(item, self.axis))

    def brows(self, expr: dict):
        height = expr["brows"]["height"]
        slant = expr["brows"]["slant"]
        left = []
        mid = 0.39
        for (x, y) in self.fs["brows"]["left"]:
            left.append((x, y - height + slant * (x - mid)))
        return (left, mirror_polyline(left, self.axis))

    def eye_view(self, expr: dict) -> dict:
        e = self.fs["eyes"]
        E = expr["eyes"]
        open_ = max(0.06, 1.0 - E["lid"])
        result = {}
        for side, sgn in (("left", -1), ("right", 1)):
            outer_x = 0.5 + sgn * e["outer_x"]
            inner_x = 0.5 + sgn * e["inner_x"]
            mid = (inner_x + outer_x) / 2
            up = e["upper_lift"] * open_ + 0.002
            down = e["lower_sag"] * open_
            result[side] = {
                "outer": (outer_x, e["level"]),
                "inner": (inner_x, e["level"]),
                "mid": mid,
                "level": e["level"],
                "up": up,
                "down": down,
                "iris": (
                    mid + sgn * E["iris_shift_x"] * 0.02,
                    e["level"] + e["iris"]["y_offset"] - E["focus"] * 0.012,
                ),
                "iris_r": e["iris"]["radius"],
                "pupil_r": max(0.004, E["pupil"]),
                "glow": E["iris_glow"],
                "open": open_,
            }
        return result

    @staticmethod
    def eye_paths(v: dict):
        n = 7
        tx = [v["outer"][0] + (v["inner"][0] - v["outer"][0]) * t for t in sampling(n)]
        oy = v["outer"][1]
        iy = v["inner"][1]
        upper = []
        lower = []
        for i, x in enumerate(tx):
            t = sampling(n)[i]
            arc = math.sin(math.pi * t)
            upper.append((x, oy + (iy - oy) * t - v["up"] * arc))
            lower.append((x, oy + (iy - oy) * t + v["down"] * arc))
        return upper, lower

    def nose(self):
        fs = self.fs
        return {
            "bridge": fs["nose"]["bridge"],
            "tip": fs["nose"]["tip"],
            "alar_left": fs["nose"]["alar_curves"]["left"],
            "alar_right": fs["nose"]["alar_curves"]["right"],
            "nostrils": (
                fs["nose"]["nostrils"]["left"],
                fs["nose"]["nostrils"]["right"],
            ),
            "nostril_r": fs["nose"]["nostrils"]["radius"],
        }

    def mouth(self, expr: dict):
        m = self.fs["mouth"]
        open_ = expr["mouth"]["open"]
        lift = expr["mouth"]["lift"]
        lc = m["corners"]["left"]
        rc = m["corners"]["right"]
        uc = m["upper_control"]
        low = (m["lower_control"][0], m["lower_control"][1] + open_ * 0.02)

        def quad(p0, p1, p2, n=9):
            pts = []
            for t in sampling(n):
                x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
                y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
                pts.append((x, y - lift))
            return pts

        return quad(lc, uc, rc), quad(lc, low, rc)

    def neural_grid(self):
        g = self.np["grid"]
        nodes = []
        for r in range(g["rows"]):
            for c in range(g["cols"]):
                t = (c / max(1, g["cols"] - 1)) if g["cols"] > 1 else 0.5
                u = (r / max(1, g["rows"] - 1)) if g["rows"] > 1 else 0.5
                x = g["x0"] + (g["x1"] - g["x0"]) * t
                y = g["y0"] + (g["y1"] - g["y0"]) * u
                nodes.append([x, y])
        return nodes

    def neural_edges(self, nodes):
        radius = float(self.np["connection_radius"])
        edges = []
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                dx = nodes[i][0] - nodes[j][0]
                dy = nodes[i][1] - nodes[j][1]
                if dx * dx + dy * dy <= radius * radius:
                    edges.append((i, j))
        return edges

    def signature(self):
        return self.fs["signature_features"]

    def anchors(self) -> dict:
        return self.fs["feature_anchors"]

    def halo(self, radius=None):
        h = self.np["halo"]
        return (h.get("y_center", 0.46), radius if radius is not None else h.get("radius", 0.42))