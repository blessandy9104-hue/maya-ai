"""Independent FaceState oracle (fractions.Fraction + IEEE-754 double replica).

Replicates the *key equations* without importing any maya_identity runtime,
then compares against the runtime outputs to confirm identity.

Equations replicated (canonical):
- project_scale(z) = CAM_D / (CAM_D - z)
- zprime(z) = z / (1 + z/CAM_D)
- depth01(zp) = clamp01((zp - lo)/(hi - lo))
- jaw_envelope(speaking, surprise) = clamp01(max(clamp01(speaking), clamp01(surprise)*0.6)*JAW_GAIN)
- compose_vertex = blend_pose(e,u,m) + j   (per component)
- blend_pose = BLEND_E*e + BLEND_V*u + BLEND_M*m
"""
from __future__ import annotations

import math
import struct
from fractions import Fraction
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_REPO_STR = str(_REPO)

# Canonical constants (from rig_math / math_coordinator)
CAM_D = Fraction(5)
SHADE_LO = Fraction(-9, 10)     # -0.9
SHADE_HI = Fraction(4, 5)       # 0.80
BLEND_E = Fraction(6, 10)       # 0.6
BLEND_V = Fraction(3, 10)       # 0.3
BLEND_M = Fraction(1, 10)       # 0.1
JAW_GAIN = Fraction(6, 5)       # 1.2
POSE_EPSILON = Fraction(1, 1_000_000_000)  # 1e-9


def _clamp01(x: Fraction) -> Fraction:
    return max(Fraction(0), min(Fraction(1), x))


def fraction_project_scale(z: Fraction) -> Fraction:
    if z == CAM_D:
        raise ZeroDivisionError("project_scale pole at z=CAM_D")
    return CAM_D / (CAM_D - z)


def fraction_zprime(z: Fraction) -> Fraction:
    return z / (Fraction(1) + z / CAM_D)


def fraction_depth01(zp: Fraction, lo: Fraction = SHADE_LO,
                     hi: Fraction = SHADE_HI) -> Fraction:
    if lo == hi:
        return Fraction(1, 2)
    return _clamp01((zp - lo) / (hi - lo))


def fraction_jaw_envelope(speaking: Fraction, surprise: Fraction) -> Fraction:
    return _clamp01(
        _clamp01(max(_clamp01(speaking), _clamp01(surprise) * Fraction(3, 5)))
        * JAW_GAIN
    )


def fraction_blend_kernel(e: Fraction, u: Fraction, m: Fraction) -> Fraction:
    return BLEND_E * e + BLEND_V * u + BLEND_M * m


def fraction_compose_vertex(expression, viseme, micro, anatomical=(Fraction(0),)*3):
    (ex, ey, ez), (ux, uy, uz), (mx, my, mz), (jx, jy, jz) = (
        expression, viseme, micro, anatomical
    )
    return (
        fraction_blend_kernel(ex, ux, mx) + jx,
        fraction_blend_kernel(ey, uy, my) + jy,
        fraction_blend_kernel(ez, uz, mz) + jz,
    )


def fraction_project_landmark(x: Fraction, y: Fraction, z: Fraction,
                              size: Fraction) -> tuple:
    s = size * Fraction(36, 100)
    inv = fraction_project_scale(z)
    px = size / Fraction(2) + x * s * inv
    py = size / Fraction(2) - y * s * inv
    return (px / size, py / size)


def _double_project_scale(z: float) -> float:
    return 5.0 / (5.0 - z)


def _double_zprime(z: float) -> float:
    return z / (1.0 + z / 5.0)


def _double_depth01(zp: float) -> float:
    return max(0.0, min(1.0, (zp - (-0.9)) / (0.8 - (-0.9))))


def _double_jaw_envelope(speaking: float, surprise: float) -> float:
    def c(v):
        return max(0.0, min(1.0, v))
    return max(0.0, min(1.0, max(c(speaking), c(surprise) * 0.6) * 1.2))


def _double_blend_kernel(e, u, m):
    return 0.6 * e + 0.3 * u + 0.1 * m


def _double_compose_vertex(e, u, m, j=(0.0, 0.0, 0.0)):
    return tuple(
        _double_blend_kernel(a, b, c) + d
        for a, b, c, d in zip(e, u, m, j)
    )


def _approx_eq(a, b, tol=1e-9) -> bool:
    return abs(float(a) - float(b)) <= tol


def run_oracle(runtime_projections: dict, runtime_fields: list,
               runtime_pose: list, base_verts: list,
               landmarks: dict, mesh_vertex_count: int) -> dict:
    """Parity check: fraction oracle vs runtime outputs.

    ``runtime_projections`` — dict from ``face_state._landmark_projections``.
    ``runtime_fields`` — audit fields (list of 12-tuples).
    ``runtime_pose`` — list of (x,y,z) tuples.
    ``base_verts`` — list of (x,y,z) tuples (mesh.verts).
    ``landmarks`` — dict name->vertex index.
    """
    details = []

    # 1. compose_vertex parity for the first 5 audit fields
    compose_ok = True
    for i, f in enumerate(runtime_fields[:5]):
        ex, ey, ez, ux, uy, uz, mx, my, mz, jx, jy, jz = f
        runtime_delta = _double_compose_vertex(
            (ex, ey, ez), (ux, uy, uz), (mx, my, mz), (jx, jy, jz)
        )
        runtime_v = runtime_pose[i]
        base_v = base_verts[i]
        runtime_vx = tuple(base_v[k] + runtime_delta[k] for k in range(3))
        for k in range(3):
            if abs(runtime_v[k] - runtime_vx[k]) > 1e-9:
                compose_ok = False
                details.append({
                    "check": "compose_double_parity",
                    "vertex": i, "axis": k,
                    "runtime_pose": runtime_v[k],
                    "recomposed": runtime_vx[k],
                    "gap": abs(runtime_v[k] - runtime_vx[k]),
                })
                break

    # 2. fraction compose_vertex parity (exact rational arithmetic)
    fraction_parity_ok = True
    for i, f in enumerate(runtime_fields[:5]):
        ex, ey, ez, ux, uy, uz, mx, my, mz, jx, jy, jz = f
        fr_e = (Fraction(ex).limit_denominator(10**12),
                Fraction(ey).limit_denominator(10**12),
                Fraction(ez).limit_denominator(10**12))
        fr_u = (Fraction(ux).limit_denominator(10**12),
                Fraction(uy).limit_denominator(10**12),
                Fraction(uz).limit_denominator(10**12))
        fr_m = (Fraction(mx).limit_denominator(10**12),
                Fraction(my).limit_denominator(10**12),
                Fraction(mz).limit_denominator(10**12))
        fr_j = (Fraction(jx).limit_denominator(10**12),
                Fraction(jy).limit_denominator(10**12),
                Fraction(jz).limit_denominator(10**12))
        got = fraction_compose_vertex(fr_e, fr_u, fr_m, fr_j)
        base_v = base_verts[i]
        expected = tuple(
            Fraction(base_v[k]).limit_denominator(10**12) + got[k]
            for k in range(3)
        )
        for k in range(3):
            if abs(float(expected[k]) - runtime_pose[i][k]) > 1e-9:
                fraction_parity_ok = False
                details.append({
                    "check": "compose_fraction_parity",
                    "vertex": i, "axis": k,
                    "runtime": runtime_pose[i][k],
                    "fraction_float": float(expected[k]),
                })
                break

    # 3. landmark projection fraction + double parity
    proj_ok = True
    frac_size = Fraction(1000)
    for name in ["iris_l", "iris_r", "nose_tip", "mouth_corner_l",
                 "brow_in_l", "brow_out_r"]:
        if name not in landmarks:
            continue
        idx = landmarks[name]
        vx, vy, vz = runtime_pose[idx]
        fr_x = Fraction(vx).limit_denominator(10**12)
        fr_y = Fraction(vy).limit_denominator(10**12)
        fr_z = Fraction(vz).limit_denominator(10**12)
        fr_px, fr_py = fraction_project_landmark(fr_x, fr_y, fr_z, frac_size)
        fp = float(fr_px)
        fy = float(fr_py)

        dp = _double_project_scale(vz)
        ds = 1000.0 * 0.36
        dx = (0.5 + vx * ds * dp / 1000.0)
        dy = (0.5 - vy * ds * dp / 1000.0)
        runtime_proj = runtime_projections.get(name, {})
        rx = runtime_proj.get("x")
        ry = runtime_proj.get("y")
        if rx is not None and ry is not None:
            ok_x = _approx_eq(fp, rx, 1e-9)
            ok_y = _approx_eq(fy, ry, 1e-9)
            if not (ok_x and ok_y):
                proj_ok = False
                details.append({
                    "check": "projection_parity",
                    "landmark": name,
                    "runtime": (rx, ry),
                    "fraction_float": (fp, fy),
                    "double_direct": (dx, dy),
                })

    # 4. depth01 + project_scale chain parity at a fixed z
    z_test = Fraction(1)
    fp = fraction_project_scale(z_test)
    hp = _double_project_scale(1.0)
    depth_fp = fraction_depth01(fraction_zprime(z_test))
    depth_hp = _double_depth01(_double_zprime(1.0))
    chain_ok = _approx_eq(depth_fp, depth_hp, 1e-12) and _approx_eq(fp, hp, 1e-12)
    if not chain_ok:
        details.append({
            "check": "depth_chain_parity",
            "fraction": (float(fp), float(depth_fp)),
            "double": (hp, depth_hp),
        })

    # 5. jaw_envelope parity at sample inputs
    jaw_ok = True
    for sp, su in [(0.5, 0.0), (0.0, 0.7), (0.3, 0.3), (1.0, 1.0)]:
        fj = float(fraction_jaw_envelope(
            Fraction(sp).limit_denominator(100),
            Fraction(su).limit_denominator(100)
        ))
        dj = _double_jaw_envelope(sp, su)
        if abs(fj - dj) > 1e-12:
            jaw_ok = False
            details.append({
                "check": "jaw_envelope_parity",
                "inputs": (sp, su),
                "fraction": fj,
                "double": dj,
            })

    ok = compose_ok and fraction_parity_ok and proj_ok and chain_ok and jaw_ok
    return {
        "ok": ok,
        "compose_double_parity": compose_ok,
        "compose_fraction_parity": fraction_parity_ok,
        "projection_parity": proj_ok,
        "depth_chain_parity": chain_ok,
        "jaw_envelope_parity": jaw_ok,
        "details": details,
    }