"""Canonical Vector Face - identity-owned, deterministic vector face model.

The canonical vector face is a *representation* of Maya's established
identity (``geometry/`` + ``identity.json`` + wireframe semantics), never a
definition of it:

    Identity geometry value -> Vector feature -> Validation rule

Every coordinate derives from the identity authority above, carries
provenance (``source``), and is re-validated by ``validate_canonical_face``
before it may be presented. The renderer (``render.py``) consumes the model
and applies only bounded, approved expression effects.

Scope: the canonical neutral face only (head silhouette, symmetry, eye
placement, iris/pupil anchors, nose landmark, mouth landmark, and the
identity signature features). Style is minimal, deterministic,
technological, calm and clean - never photorealistic, never an imitation of
a person, never decorative randomness.

This layer cannot write to any system: it reads identity geometry and
returns pure data. Version changes require the explicit activation flow in
``activate_canonical_vector_face``.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

VECTOR_SCHEMA_VERSION = "1.0.0"
VECTOR_FACE_VERSION = "1.0.0"
RENDERER_VERSION = "1.0.0"

_EPS = 1e-9
_SEG_SEGMENTS = 16
_ARC_SAMPLES = 10
_EYE_SAMPLES = 7
_MOUTH_SAMPLES = 9

REQUIRED_FEATURES = frozenset({
    "head_silhouette", "jaw_arc",
    "brows_left", "brows_right",
    "cheek_lines_left", "cheek_lines_right",
    "temple_braids_left", "temple_braids_right",
    "eye_lens_left", "eye_lens_right",
    "eye_iris_left", "eye_iris_right",
    "eye_pupil_left", "eye_pupil_right",
    "nose_bridge", "nose_tip",
    "nose_alar_left", "nose_alar_right",
    "nostril_left", "nostril_right",
    "mouth_corners_left", "mouth_corners_right",
    "mouth_idle",
    "signature_awareness_gem", "signature_axis_light",
    "signature_cheek_point_left", "signature_cheek_point_right",
    "neural_crown",
})

REQUIRED_LANDMARKS = frozenset({
    "crown", "chin", "left_eye", "right_eye", "mouth",
    "iris_left", "iris_right", "nose_tip",
})

PAIR_FEATURES = (
    ("brows_left", "brows_right"),
    ("cheek_lines_left", "cheek_lines_right"),
    ("temple_braids_left", "temple_braids_right"),
    ("eye_lens_left", "eye_lens_right"),
    ("eye_iris_left", "eye_iris_right"),
    ("eye_pupil_left", "eye_pupil_right"),
    ("nose_alar_left", "nose_alar_right"),
    ("nostril_left", "nostril_right"),
    ("signature_cheek_point_left", "signature_cheek_point_right"),
)


def _f(x):
    return float(x)


def _pt(p) -> Tuple[float, float]:
    return (round(_f(p[0]), 12), round(_f(p[1]), 12))


def _num(x) -> str:
    return "%.12f" % round(_f(x), 12)


def _numxy(p) -> str:
    return "%s,%s" % (_num(p[0]), _num(p[1]))


def _parse_xy(text) -> Tuple[float, float]:
    if isinstance(text, (list, tuple)):
        return _pt(text)
    a, b = str(text).split()
    return _pt((a, b))


def mirror_x(x: float, axis: float = 0.5) -> float:
    return axis - (x - axis)


def mirror_pts(pts, axis: float = 0.5):
    return tuple((round(mirror_x(x, axis), 12), y) for (x, y) in pts)


def _quad_points(p0, p1, p2, n: int = _MOUTH_SAMPLES):
    pts = []
    for i in range(n):
        t = i / max(1, n - 1)
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def _closed_path(upper, lower):
    return tuple(upper) + tuple(reversed(lower))


def _lens_points(eyes: dict, side: str, open_: float = 1.0):
    """Closed eye lens path, mirroring the renderer's ``eye_view``/``eye_paths``."""
    sgn = -1.0 if side == "left" else 1.0
    outer_x = 0.5 + sgn * eyes["outer_x"]
    inner_x = 0.5 + sgn * eyes["inner_x"]
    level = eyes["level"]
    up = eyes["upper_lift"] * open_ + 0.002
    down = eyes["lower_sag"] * open_
    upper = []
    lower = []
    for i in range(_EYE_SAMPLES):
        t = i / max(1, _EYE_SAMPLES - 1)
        x = outer_x + (inner_x - outer_x) * t
        arc = math.sin(math.pi * t)
        upper.append((x, level - up * arc))
        lower.append((x, level + down * arc))
    return _closed_path(upper, lower)


@dataclass(frozen=True)
class VectorFeature:
    """One canonical vector face feature (pure geometry data)."""

    name: str
    kind: str
    points: Tuple[Tuple[float, float], ...]
    source: str
    radius: float = 0.0
    role: str = "identity"


@dataclass(frozen=True)
class CanonicalVectorFace:
    """The canonical neutral vector face, frozen after construction."""

    vector_schema_version: str
    face_version: str
    geometry_version: str
    identity_version: str
    renderer_version: str
    symmetry_axis: float
    symmetry_tolerance: float
    features: Tuple[VectorFeature, ...]
    landmarks: Dict[str, Tuple[float, float]]
    geometry_digest: str

    def feature_map(self) -> Dict[str, VectorFeature]:
        return {feat.name: feat for feat in self.features}


def _geometry_digest(face: CanonicalVectorFace) -> str:
    payload = {
        "schema": face.vector_schema_version,
        "face_version": face.face_version,
        "geometry_version": face.geometry_version,
        "identity_version": face.identity_version,
        "renderer_version": face.renderer_version,
        "symmetry": {
            "axis": _num(face.symmetry_axis),
            "tolerance": _num(face.symmetry_tolerance),
        },
        "features": [
            {
                "name": feat.name,
                "kind": feat.kind,
                "points": [_numxy(p) for p in feat.points],
                "radius": _num(feat.radius),
                "source": feat.source,
                "role": feat.role,
            }
            for feat in face.features
        ],
        "landmarks": {
            key: _numxy(value) for key, value in sorted(face.landmarks.items())
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_canonical_vector_face(
    bundle: Optional[dict] = None,
    identity_payload: Optional[dict] = None,
) -> CanonicalVectorFace:
    """Pure factory: derive the canonical vector face from identity authority.

    Every feature point is a direct function of ``geometry/`` values, so
    ``geometry(identity)`` is stable: the same identity version yields the
    same vector geometry. Right-side features follow the symmetry rule
    ("the renderer derives every right-side feature from the canonical
    left-side definition by mirroring about the axis").
    """
    if bundle is None:
        from maya_identity.identity import load_geometry_bundle
        bundle = load_geometry_bundle()
    if identity_payload is None:
        from maya_identity.identity import load_identity
        identity_payload = load_identity() or {}

    fs = bundle["facial_structure"]
    sym = bundle["symmetry"]
    axis = _f(sym.get("axis", 0.5))
    tolerance = _f(sym.get("tolerance", 0.004))

    identity_version = str(identity_payload.get("identity_version") or "")
    face_version = str(identity_payload.get("face_version") or "")
    geometry_version = str(identity_payload.get("geometry_version") or "")

    features: List[VectorFeature] = []

    def add(name, kind, pts, source, radius=0.0):
        features.append(VectorFeature(
            name, kind, tuple(_pt(p) for p in pts),
            source, round(_f(radius), 12)))

    outline = fs["face_outline"]
    silhouette = [
        (outline["cx"] + outline["rx"] * math.cos(2 * math.pi * i / _SEG_SEGMENTS),
         outline["cy"] + outline["ry"] * math.sin(2 * math.pi * i / _SEG_SEGMENTS))
        for i in range(_SEG_SEGMENTS)
    ]
    silhouette.append(silhouette[0])
    add("head_silhouette", "path", silhouette, "facial_structure#face_outline")

    jaw = fs["jaw"]
    r0, r1 = math.radians(jaw["theta_start"]), math.radians(jaw["theta_end"])
    jaw_pts = [
        (jaw["cx"] + jaw["rx"] * math.cos(r0 + (r1 - r0) * i / max(1, _ARC_SAMPLES - 1)),
         jaw["cy"] + jaw["ry"] * math.sin(r0 + (r1 - r0) * i / max(1, _ARC_SAMPLES - 1)))
        for i in range(_ARC_SAMPLES)
    ]
    add("jaw_arc", "path", jaw_pts, "facial_structure#jaw")

    brows_left = fs["brows"]["left"]
    add("brows_left", "path", brows_left, "facial_structure#brows.left")
    add("brows_right", "path", mirror_pts(brows_left, axis),
        "facial_structure#brows.left (mirrored about symmetry axis)")

    cheek_left = fs["cheek_lines"]["left"]
    add("cheek_lines_left", "path", cheek_left, "facial_structure#cheek_lines.left")
    add("cheek_lines_right", "path", mirror_pts(cheek_left, axis),
        "facial_structure#cheek_lines.left (mirrored about symmetry axis)")

    temple_left = fs["temple_braids"]["left"]
    add("temple_braids_left", "polyline", temple_left,
        "facial_structure#temple_braids.left")
    add("temple_braids_right", "polyline", mirror_pts(temple_left, axis),
        "facial_structure#temple_braids.left (mirrored about symmetry axis)")

    eyes = fs["eyes"]
    iris_left = (0.5 - eyes["spacing"], eyes["level"] + eyes["iris"]["y_offset"])
    iris_left = _pt(iris_left)
    iris_right = _pt((mirror_x(iris_left[0], axis), iris_left[1]))
    add("eye_lens_left", "path", _lens_points(eyes, "left", open_=1.0),
        "facial_structure#eyes (upper_lift/lower_sag/inner_x/outer_x)")
    add("eye_lens_right", "path", mirror_pts(_lens_points(eyes, "left", open_=1.0), axis),
        "facial_structure#eyes (mirrored about symmetry axis)")
    add("eye_iris_left", "circle", [iris_left], "facial_structure#eyes.spacing/iris",
        radius=eyes["iris"]["radius"])
    add("eye_iris_right", "circle", [iris_right], "facial_structure#eyes.spacing/iris",
        radius=eyes["iris"]["radius"])
    add("eye_pupil_left", "circle", [iris_left], "facial_structure#eyes.pupil",
        radius=eyes["pupil"]["radius"])
    add("eye_pupil_right", "circle", [iris_right], "facial_structure#eyes.pupil",
        radius=eyes["pupil"]["radius"])

    nose = fs["nose"]
    add("nose_bridge", "path", nose["bridge"], "facial_structure#nose.bridge")
    add("nose_tip", "anchor", [nose["tip"]], "facial_structure#nose.tip")
    add("nose_alar_left", "polyline", [_parse_xy(p) for p in nose["alar_curves"]["left"]],
        "facial_structure#nose.alar_curves.left")
    add("nose_alar_right", "polyline",
        [_parse_xy(p) for p in nose["alar_curves"]["right"]],
        "facial_structure#nose.alar_curves.right")
    add("nostril_left", "circle", [nose["nostrils"]["left"]],
        "facial_structure#nose.nostrils.left", radius=nose["nostrils"]["radius"])
    add("nostril_right", "circle", [nose["nostrils"]["right"]],
        "facial_structure#nose.nostrils.right", radius=nose["nostrils"]["radius"])

    mouth = fs["mouth"]
    lc = _pt(mouth["corners"]["left"])
    rc = _pt(mouth["corners"]["right"])
    uc = _pt(mouth["upper_control"])
    low_c = mouth["lower_control"]
    low = (low_c[0], low_c[1] + 0.0 * 0.02)
    upper = _quad_points(lc, uc, rc)
    lower = _quad_points(lc, low, rc)
    add("mouth_idle", "path", _closed_path(upper, lower),
        "facial_structure#mouth.corners/controls (closed curve, rest pose)")
    add("mouth_corners_left", "anchor", [lc], "facial_structure#mouth.corners.left")
    add("mouth_corners_right", "anchor", [rc], "facial_structure#mouth.corners.right")

    sig = fs["signature_features"]
    add("signature_awareness_gem", "circle", [sig["awareness_gem"]["point"]],
        "facial_structure#signature_features.awareness_gem",
        radius=sig["awareness_gem"]["radius"])
    add("signature_axis_light", "path",
        [_parse_xy(p) for p in sig["axis_light"]["points"]],
        "facial_structure#signature_features.axis_light")
    cp_left = sig["cheek_points"]["left"]
    add("signature_cheek_point_left", "circle", [cp_left],
        "facial_structure#signature_features.cheek_points.left",
        radius=sig["cheek_points"]["radius"])
    add("signature_cheek_point_right", "circle",
        [mirror_pts([cp_left], axis)[0]],
        "facial_structure#signature_features.cheek_points.left (mirrored)",
        radius=sig["cheek_points"]["radius"])
    add("neural_crown", "path", sig["neural_crown"],
        "facial_structure#signature_features.neural_crown")

    landmarks = {key: _pt(value) for key, value in fs["feature_anchors"].items()}
    landmarks["iris_left"] = iris_left
    landmarks["iris_right"] = iris_right
    landmarks["nose_tip"] = _pt(nose["tip"])

    preliminary = CanonicalVectorFace(
        vector_schema_version=VECTOR_SCHEMA_VERSION,
        face_version=face_version,
        geometry_version=geometry_version,
        identity_version=identity_version,
        renderer_version=RENDERER_VERSION,
        symmetry_axis=axis,
        symmetry_tolerance=tolerance,
        features=tuple(features),
        landmarks=landmarks,
        geometry_digest="",
    )
    return CanonicalVectorFace(
        vector_schema_version=VECTOR_SCHEMA_VERSION,
        face_version=face_version,
        geometry_version=geometry_version,
        identity_version=identity_version,
        renderer_version=RENDERER_VERSION,
        symmetry_axis=axis,
        symmetry_tolerance=tolerance,
        features=tuple(features),
        landmarks=dict(landmarks),
        geometry_digest=_geometry_digest(preliminary),
    )


def _authority_mirror_problems(fs: dict, axis: float, tolerance: float) -> List[str]:
    problems = []

    def as_points(value):
        if value and all(isinstance(v, (int, float)) for v in value):
            return [_pt(value)]
        out = []
        for item in value or []:
            out.append(_pt(item))
        return out

    def consistency(left_pts, right_pts, label):
        if not left_pts and not right_pts:
            return
        mirrored = [(_pt((mirror_x(a[0], axis), a[1])))[0:2] for a in left_pts]
        mirrored = [(_f(m[0]), _f(m[1])) for m in mirrored]
        right = [(_f(b[0]), _f(b[1])) for b in right_pts]

        def matched(a):
            best = None
            for b in right:
                delta = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
                if best is None or delta < best:
                    best = delta
            return best

        for a in mirrored:
            if matched(a) > tolerance + _EPS:
                problems.append(
                    "%s: mirrored-left point %s has no stored-right match"
                    % (label, (round(a[0], 9), round(a[1], 9))))
        for b in right:
            best = None
            for a in mirrored:
                delta = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
                if best is None or delta < best:
                    best = delta
            if best > tolerance + _EPS:
                problems.append(
                    "%s: stored-right point %s has no mirrored-left match"
                    % (label, b))

    sources = (
        ("brows", fs["brows"]),
        ("cheek_lines", fs["cheek_lines"]),
        ("temple_braids", fs["temple_braids"]),
        ("signature cheek_points", fs["signature_features"]["cheek_points"]),
        ("nose nostrils", fs["nose"]["nostrils"]),
    )
    for label, src in sources:
        left = as_points(src.get("left"))
        right = as_points(src.get("right"))
        if len(left) != len(right) and left and right:
            problems.append("%s: side point count mismatch" % label)
            continue
        consistency(left, right, label)

    consistency([_pt(fs["mouth"]["corners"]["left"])],
                [_pt(fs["mouth"]["corners"]["right"])],
                "mouth corners")

    return problems


def validate_canonical_face(
    face: CanonicalVectorFace,
    bundle: Optional[dict] = None,
    identity_payload: Optional[dict] = None,
):
    """Return ``(ok, reasons)`` for the canonical vector face.

    Validation is re-derivation, never trust: every check is recomputed from
    identity authority (the bundle auto-loads through the cached, read-only
    identity loader when not provided), so a drift in geometry or versions is
    reported rather than silently accepted.
    """
    ok = True
    reasons: List[str] = []

    def fail(message: str):
        nonlocal ok
        ok = False
        reasons.append(message)

    if not isinstance(face, CanonicalVectorFace):
        return False, ["not a CanonicalVectorFace"]
    if bundle is None:
        from maya_identity.identity import load_geometry_bundle
        bundle = load_geometry_bundle()
    if identity_payload is None:
        from maya_identity.identity import load_identity
        identity_payload = load_identity() or {}

    by_name = face.feature_map()
    for name in sorted(REQUIRED_FEATURES):
        if name not in by_name:
            fail("missing feature %s" % name)
    for key in sorted(REQUIRED_LANDMARKS):
        if key not in face.landmarks:
            fail("missing landmark %s" % key)

    for name in sorted(by_name):
        feat = by_name[name]
        for p in feat.points:
            if not (-_EPS <= p[0] <= 1.0 + _EPS and -_EPS <= p[1] <= 1.0 + _EPS):
                fail("feature %s point %s out of unit space" % (name, p))
        if feat.kind == "circle" and not (_EPS < feat.radius <= 1.0):
            fail("feature %s circle radius out of range" % name)

    for key in sorted(face.landmarks):
        point = face.landmarks[key]
        if not (-_EPS <= point[0] <= 1.0 + _EPS and
                -_EPS <= point[1] <= 1.0 + _EPS):
            fail("landmark %s %s out of unit space" % (key, point))

    for field in ("vector_schema_version", "face_version", "geometry_version",
                  "identity_version", "renderer_version"):
        if not str(getattr(face, field)).strip():
            fail("empty version field %s" % field)

    if identity_payload:
        for field in ("identity_version", "face_version", "geometry_version"):
            declared = str(identity_payload.get(field) or "")
            if declared and declared != str(getattr(face, field)):
                fail("version %s %r != declared %r" % (field, getattr(face, field), declared))

    for feature in PAIR_FEATURES:
        left = by_name.get(feature[0])
        right = by_name.get(feature[1])
        if left is None or right is None:
            fail("pair %s incomplete" % (feature,))
            continue
        if len(left.points) != len(right.points):
            fail("pair %s point count mismatch" % (feature,))
            continue
        mirrored = mirror_pts(left.points, face.symmetry_axis)
        for a, b in zip(mirrored, right.points):
            if abs(a[0] - b[0]) > face.symmetry_tolerance + _EPS or \
                    abs(a[1] - b[1]) > face.symmetry_tolerance + _EPS:
                fail("pair %s symmetry drift %s vs %s" % (feature, a, b))

    fs = bundle["facial_structure"]
    drift = _authority_mirror_problems(fs, face.symmetry_axis,
                                       face.symmetry_tolerance)
    reasons.extend(drift)
    if drift:
        ok = False

    anchors = fs["feature_anchors"]
    anchor_eyes = dict(anchors)
    if "left_eye" in anchors and "iris_left" in face.landmarks:
        dx = abs(face.landmarks["iris_left"][0] - _f(anchor_eyes["left_eye"][0]))
        dy = abs(face.landmarks["iris_left"][1] - _f(anchor_eyes["left_eye"][1]))
        if dx > face.symmetry_tolerance + _EPS or dy > face.symmetry_tolerance + _EPS:
            fail("iris_left drifts from feature_anchors.left_eye "
                 "(%s vs %s)" % (face.landmarks["iris_left"],
                                 tuple(anchor_eyes["left_eye"])))

    rebuilt = build_canonical_vector_face(bundle=bundle,
                                          identity_payload=identity_payload)
    if rebuilt.geometry_digest != face.geometry_digest:
        fail("geometry digest drift across rebuild")

    return ok, reasons


def activate_canonical_vector_face(
    feature_face: Optional[CanonicalVectorFace] = None,
    created_by: str = "operator",
    journal_path=None,
) -> dict:
    """Explicit activation: Implementation -> Validation -> Approval -> Activation.

    Activation is operator-only and never automatic. The journal write is the
    single approved mutation of ``identity_versions.jsonl`` by this layer;
    validation must pass before any record is written, and the record carries
    geometry version, renderer version and the validation summary. Tests pass
    a disposable ``journal_path``.
    """
    face = (feature_face if feature_face is not None
            else build_canonical_vector_face())
    ok, reasons = validate_canonical_face(face)
    record = {
        "event": "canonical_vector_face_established",
        "face_version": face.face_version,
        "vector_schema_version": face.vector_schema_version,
        "geometry_version": face.geometry_version,
        "identity_version": face.identity_version,
        "renderer_version": face.renderer_version,
        "symmetry": {
            "axis": _num(face.symmetry_axis),
            "tolerance": _num(face.symmetry_tolerance),
        },
        "geometry_digest": face.geometry_digest,
        "validation": {
            "ok": ok,
            "violations": len(reasons),
        },
        "created_by": created_by,
    }
    if not ok:
        return {"status": "validation_failed", "record": None, "reasons": reasons}
    if journal_path is None:
        try:
            from maya_identity.identity import VERSIONS_LOG
            journal_path = VERSIONS_LOG
        except Exception:
            return {"status": "log_unavailable", "record": record,
                    "reasons": ["identity_versions journal unavailable"]}
    try:
        with open(str(journal_path), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True,
                                    separators=(",", ":"),
                                    ensure_ascii=False) + "\n")
    except OSError as err:
        return {"status": "write_failed", "record": record,
                "reasons": ["journal write failed: %s" % err]}
    return {"status": "activated", "record": record, "journal": str(journal_path)}