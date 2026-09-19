"""Renderer contract for the canonical vector face.

The renderer is a separate, pure consumer:

    Vector Face Model + Expression Anchors -> draw commands (payload)

It can never modify the canonical model, create expressions, or write to any
system. All effects it applies are bounded, documented amplitudes of the
verified expression anchors - the same amplitudes the existing presentation
math uses (``geometry_renderer``), so the vector output agrees with the
hologram presentation wherever they share a feature.

QML compatibility: the payload is plain JSON (unit-space commands); the QML
surface only paints the points it is given. The face never hands logic to
QML.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from .expression import VectorExpression, VISEMES_NAMES
from .vector_face import (
    CanonicalVectorFace,
    mirror_pts,
    _pt,
    _quad_points,
)

# Bounded presentation amplitudes (unit space), mirroring the existing
# presentation math so the vector face agrees with the hologram renderer.
MOUTH_OPEN_AMPLITUDE = 0.02    # geometry_renderer.mouth: open * 0.02
IRIS_GAZE_AMPLITUDE = 0.02     # geometry_renderer.eye_view: gaze shift * 0.02
IRIS_FOCUS_LIFT = 0.012        # geometry_renderer.eye_view: focus * 0.012
BROW_LIFT_AMPLITUDE = 0.006    # engaged-attention brow lift (documented)

_EPS = 1e-9


def _r12(value: float) -> float:
    return round(float(value), 12)


def _num(value: float) -> str:
    return "%.12f" % _r12(value)


def _sha256(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def render_face_commands(
    face: CanonicalVectorFace,
    expr: VectorExpression,
    frame: int = 0,
    bundle: Optional[dict] = None,
) -> dict:
    """Deterministically map the canonical face + anchors to draw commands.

    Identity features are emitted unchanged; only the bounded expression
    effects move presentation (lids via openness, iris via gaze/focus, brows
    via attention, mouth via the viseme ``open`` parameter confined to the
    mouth/jaw channel). ``frame`` is metadata only - there is no animation in
    this version, so the geometry of frame 0 equals every other frame.
    """
    if bundle is None:
        from maya_identity.identity import load_geometry_bundle
        bundle = load_geometry_bundle()
    fs = bundle["facial_structure"]
    eyes = fs["eyes"]
    by_name = face.feature_map()

    fx = face.symmetry_axis
    commands = []
    commands.append({"op": "clear"})
    commands.append({"op": "path", "points": by_name["head_silhouette"].points,
                     "stroke": "identity"})
    commands.append({"op": "path", "points": by_name["jaw_arc"].points,
                     "stroke": "identity"})
    commands.append({"op": "path", "points": by_name["nose_bridge"].points,
                     "stroke": "identity"})
    for name in ("temple_braids_left", "temple_braids_right",
                 "nose_alar_left", "nose_alar_right",
                 "neural_crown", "signature_axis_light"):
        commands.append({"op": "polyline", "points": by_name[name].points,
                         "stroke": "identity"})

    lift = expr.attention * BROW_LIFT_AMPLITUDE
    for name in ("brows_left", "brows_right"):
        moved = tuple((_r12(x), _r12(y - lift))
                      for (x, y) in by_name[name].points)
        commands.append({"op": "path", "points": moved, "stroke": "identity"})
    for name in ("cheek_lines_left", "cheek_lines_right"):
        commands.append({"op": "path", "points": by_name[name].points,
                         "stroke": "identity"})
    for name in ("signature_cheek_point_left",
                 "signature_cheek_point_right"):
        feat = by_name[name]
        commands.append({"op": "circle", "center": feat.points[0],
                         "radius": feat.radius, "fill": "identity"})

    for side, sgn in (("left", -1.0), ("right", 1.0)):
        outer_x = 0.5 + sgn * eyes["outer_x"]
        inner_x = 0.5 + sgn * eyes["inner_x"]
        level = eyes["level"]
        up = eyes["upper_lift"] * expr.openness + 0.002
        down = eyes["lower_sag"] * expr.openness
        upper = []
        lower = []
        for i in range(7):
            t = i / 6
            arc = math_sin_pi(t)
            x = outer_x + (inner_x - outer_x) * t
            upper.append((_r12(x), _r12(level - up * arc)))
            lower.append((_r12(x), _r12(level + down * arc)))
        lens = tuple(upper) + tuple(reversed(lower))
        commands.append({"op": "path", "points": lens, "stroke": "identity"})

        iris = by_name["eye_iris_left" if side == "left" else "eye_iris_right"]
        base = iris.points[0]
        cx = _r12(base[0] + expr.gaze_x * IRIS_GAZE_AMPLITUDE)
        cy = _r12(base[1] + expr.gaze_y * IRIS_GAZE_AMPLITUDE
                  - expr.focus * IRIS_FOCUS_LIFT)
        commands.append({"op": "circle", "center": (cx, cy),
                         "radius": iris.radius, "fill": "iris"})
        pupil = by_name["eye_pupil_left" if side == "left" else "eye_pupil_right"]
        commands.append({"op": "circle", "center": (cx, cy),
                         "radius": pupil.radius, "fill": "pupil"})

    for name in ("signature_awareness_gem", "nostril_left", "nostril_right"):
        feat = by_name[name]
        commands.append({"op": "circle", "center": feat.points[0],
                         "radius": feat.radius, "fill": "identity"})

    commands.append({"op": "anchor", "point": by_name["nose_tip"].points[0],
                     "stroke": "identity"})
    for name in ("mouth_corners_left", "mouth_corners_right"):
        commands.append({"op": "anchor", "point": by_name[name].points[0],
                         "stroke": "identity"})

    mouth = fs["mouth"]
    lc = _pt(mouth["corners"]["left"])
    rc = _pt(mouth["corners"]["right"])
    uc = _pt(mouth["upper_control"])
    low_c = mouth["lower_control"]
    open_amount = expr.mouth_open * MOUTH_OPEN_AMPLITUDE
    low = (low_c[0], _r12(low_c[1] + open_amount))
    lower = _quad_points(lc, low, rc)
    upper = _quad_points(lc, uc, rc)
    idle = tuple(upper) + tuple(reversed(lower))
    commands.append({"op": "path", "points": idle, "stroke": "mouth"})

    commands.append({"op": "glow", "value": expr.aura})

    payload = {
        "frame": int(frame),
        "commands": commands,
        "expression": expr.as_dict(),
        "versions": {
            "vector_schema_version": face.vector_schema_version,
            "face_version": face.face_version,
            "geometry_version": face.geometry_version,
            "identity_version": face.identity_version,
            "renderer_version": face.renderer_version,
        },
    }
    digest = _sha256({"frame": payload["frame"], "commands": commands,
                      "expression": payload["expression"],
                      "versions": payload["versions"]})
    return {"commands": commands, "frame": int(frame),
            "expression": expr.as_dict(), "versions": payload["versions"],
            "digest": digest}


def math_sin_pi(t: float) -> float:
    import math
    return math.sin(math.pi * t)


def validate_render_commands(rendered: dict):
    """Return ``(ok, reasons)`` - all draw data is bounded and deterministic."""
    ok = True
    reasons = []

    def fail(message):
        nonlocal ok
        ok = False
        reasons.append(message)

    if not isinstance(rendered, dict) or "commands" not in rendered:
        return False, ["not a rendered payload"]
    known_ops = {"clear", "path", "polyline", "circle", "anchor", "glow"}
    for cmd in rendered["commands"]:
        if cmd.get("op") not in known_ops:
            fail("unknown op %r" % cmd.get("op"))
            continue
        if cmd["op"] in ("path", "polyline"):
            for p in cmd["points"]:
                if not (-_EPS <= p[0] <= 1.0 + _EPS and
                        -_EPS <= p[1] <= 1.0 + _EPS):
                    fail("path point %s out of unit space" % (p,))
        elif cmd["op"] == "circle":
            c = cmd["center"]
            if not (-_EPS <= c[0] <= 1.0 + _EPS and
                    -_EPS <= c[1] <= 1.0 + _EPS):
                fail("circle center %s out of unit space" % (c,))
            if not (_EPS < cmd["radius"] <= 1.0):
                fail("circle radius out of range")
        elif cmd["op"] == "anchor":
            p = cmd["point"]
            if not (-_EPS <= p[0] <= 1.0 + _EPS and
                    -_EPS <= p[1] <= 1.0 + _EPS):
                fail("anchor %s out of unit space" % (p,))
        elif cmd["op"] == "glow":
            if not (-_EPS <= cmd["value"] <= 1.0 + _EPS):
                fail("glow value %r out of [0, 1]" % cmd["value"])
    if "digest" not in rendered:
        fail("no digest")
    return ok, reasons


def to_qml_payload(
    face: CanonicalVectorFace,
    expr: VectorExpression,
    frame: int = 0,
    bundle: Optional[dict] = None,
) -> dict:
    """A JSON-safe, deterministic payload a QML surface can paint directly.

    Points are plain ``[x, y]`` lists in unit space; there is no shape
    computation left for QML. The QML side only maps commands to its canvas.
    """
    rendered = render_face_commands(face, expr, frame=frame, bundle=bundle)
    surface = []
    for cmd in rendered["commands"]:
        serializable = dict(cmd)
        if "points" in serializable:
            serializable["points"] = [[round(x, 12), round(y, 12)]
                                      for (x, y) in serializable["points"]]
        if "center" in serializable:
            serializable["center"] = [round(serializable["center"][0], 12),
                                      round(serializable["center"][1], 12)]
        if "point" in serializable:
            serializable["point"] = [round(serializable["point"][0], 12),
                                     round(serializable["point"][1], 12)]
        surface.append(serializable)
    # The payload digest must recompute from the payload's own serialized
    # surface (12-place rounding erases float-repr noise the render-time
    # digest covered), so a holder can verify the payload without re-rendering.
    payload_digest = _sha256({"frame": int(frame), "surface": surface,
                              "expression": rendered["expression"],
                              "versions": rendered["versions"]})
    return {
        "schema": "maya/canonical-vector-face/1.0.0",
        "frame": rendered["frame"],
        "surface": surface,
        "expression": rendered["expression"],
        "versions": rendered["versions"],
        "digest": payload_digest,
    }