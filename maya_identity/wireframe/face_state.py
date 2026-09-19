"""Canonical FaceState: deterministic, headless face snapshot.

Unifies the previously separate layers into ONE face:
  identity  ->  geometry (mesh_model)  ->  expression (rig_math + math_coordinator)
       ->  projection (render3d)      ->  renderer contract (RenderFrame)

Guarantees (headless, portable, deterministic):
- no ``random``, ``time.monotonic``, wall-clock, or interpreter-dependent values;
  blink/smoother sampling is disabled (``auto_blink=False``) for reproducible pose.
- poses are validated through the single arbiter ``MATH_AGENT.finalize``
  (pose assembly, per-channel ceilings, semantic channel separation).
- every projection and measurement is derived from the canonical mesh, so
  landmark fractions, channel states, and signatures are cross-device stable.

The Live widget continues to animate freely (auto-blink + wall clock) on top;
FaceState is the canonical analytic snapshot used by validation, the
intelligence bridge, and the numeric oracle.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .rig_math import (
    BLEND_E,
    BLEND_V,
    BLEND_M,
    blend_pose,
    clamp01,
    depth01,
    math_isclose,
    pose_near,
    POSE_EPSILON,
    zprime,
)
from .math_coordinator import (
    CHANNEL_MAX,
    CH_EXPRESSION,
    CH_VISEME,
    CH_MICRO,
    CH_ANATOMICAL,
    CHANNELS,
    MATH_AGENT,
)
from .mesh_model import MODEL_VERSION as MESH_MODEL_VERSION, get_mesh
from .expression_controller import ALL_CONTROLS, PRESETS, ExpressionController
from .render3d import MeshProjector

FACE_STATE_VERSION = "1.0.0"

# Independent 2D layout reference (y-down) -- geometry/facial_structure.json.
# Used ONLY for cross-frame landmark regression trips; the live canonical
# geometry is the 3D mesh (see Batch 7 report, cross-frame mapping section).
_EYES = "eyes"
_FEATURE_TOLERANCES = {
    "brow_level_y": 0.110,
    "eye_level_y": 0.090,
    "nose_tip_y": 0.080,
    "nose_tip_x": 0.030,
    "mouth_corner_y": 0.120,
    "mouth_corner_x_l": 0.090,
    "mouth_corner_x_r": 0.090,
    "eye_center_x_l": 0.170,
    "eye_center_x_r": 0.170,
}

_CANONICAL_LANDMARKS = (
    "iris_l",
    "iris_r",
    "pupil_l",
    "pupil_r",
    "corner_inner_l",
    "corner_inner_r",
    "corner_outer_l",
    "corner_outer_r",
    "brow_in_l",
    "brow_in_r",
    "brow_out_l",
    "brow_out_r",
    "nose_root",
    "nose_tip",
    "upper_lip_c",
    "lower_lip_c",
    "mouth_corner_l",
    "mouth_corner_r",
    "ear_l",
    "ear_r",
)


def _geometry_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "geometry"


def canonical_float(value: float) -> float:
    return round(float(value), 12)


def pose_digest(pose, namespace: str = "face_state") -> str:
    """Deterministic, endian-explicit digest over the posed mesh.

    ``<d`` little-endian IEEE-754 doubles are identical on every CPython
    platform, giving a portable frame identity across interpreters.
    """
    h = hashlib.sha256()
    h.update(namespace.encode("ascii"))
    for (x, y, z) in pose:
        for c in (x, y, z):
            h.update(struct.pack("<d", canonical_float(c)))
    return h.hexdigest()


def face_state_reference_fractions() -> dict:
    """Independent 2D layout fractions parsed from facial_structure.json."""
    path = _geometry_dir() / "facial_structure.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    brows_l = spec["brows"]["left"]
    brows_r = spec["brows"]["right"]
    brow_y = sum(p[1] for p in brows_l + brows_r) / (len(brows_l) + len(brows_r))
    anchors = spec["feature_anchors"]
    mouth = spec["mouth"]["corners"]
    nose = spec["nose"]
    return {
        "source": str(path.relative_to(_geometry_dir().parent)).replace("\\", "/"),
        "brow_level_y": round(brow_y, 6),
        "eye_level_y": float(spec[_EYES]["level"]),
        "eye_center_x_l": float(anchors["left_eye"][0]),
        "eye_center_x_r": float(anchors["right_eye"][0]),
        "eye_center_y_l": float(anchors["left_eye"][1]),
        "eye_center_y_r": float(anchors["right_eye"][1]),
        "nose_tip": (float(nose["tip"][0]), float(nose["tip"][1])),
        "nose_bridge_top_y": float(nose["bridge"][0][1]),
        "mouth_corner_x_l": float(mouth["left"][0]),
        "mouth_corner_x_r": float(mouth["right"][0]),
        "mouth_corner_y": float(mouth["left"][1]),
        "crown_y": float(anchors["crown"][1]),
        "chin_y": float(anchors["chin"][1]),
    }


def _landmark_projections(mesh, pose, projector) -> dict:
    px, py = projector.project(pose, mesh.vertex_count())
    proj = {}
    for name in _CANONICAL_LANDMARKS:
        if name not in mesh.landmarks:
            continue
        i = mesh.landmarks[name]
        zp = zprime(pose[i][2])
        proj[name] = {
            "x": canonical_float(px[i] / float(projector.size)),
            "y": canonical_float(py[i] / float(projector.size)),
            "z_mesh": canonical_float(pose[i][2]),
            "depth01": canonical_float(depth01(zp)),
        }
    return proj


def _avg(proj, names, key):
    vals = [proj[n][key] for n in names if n in proj]
    return round(sum(vals) / len(vals), 12) if vals else None


def measure(projections: dict) -> dict:
    """Feature measurements (unit fraction space, y top-down)."""
    eye = ("iris_l", "iris_r")
    brows = ("brow_in_l", "brow_in_r", "brow_out_l", "brow_out_r")
    mouth = ("mouth_corner_l", "mouth_corner_r", "upper_lip_c", "lower_lip_c")
    m = {
        "eye_level_y": _avg(projections, eye, "y"),
        "brow_level_y": _avg(projections, brows, "y"),
        "mouth_y": _avg(projections, mouth, "y"),
        "eye_center_x_l": projections.get("iris_l", {}).get("x"),
        "eye_center_x_r": projections.get("iris_r", {}).get("x"),
        "nose_tip": (
            projections.get("nose_tip", {}).get("x"),
            projections.get("nose_tip", {}).get("y"),
        ),
        "mouth_corner_x_l": projections.get("mouth_corner_l", {}).get("x"),
        "mouth_corner_x_r": projections.get("mouth_corner_r", {}).get("x"),
        "nose_tip_x": projections.get("nose_tip", {}).get("x"),
    }
    m["sym_eye_dx_l"] = round(abs(0.5 - m["eye_center_x_l"]), 12) if m["eye_center_x_l"] else None
    m["sym_eye_dx_r"] = round(abs(m["eye_center_x_r"] - 0.5), 12) if m["eye_center_x_r"] else None
    m["sym_eye_x_mismatch"] = round(abs(m["sym_eye_dx_l"] - m["sym_eye_dx_r"]), 12)
    m["sym_mouth_dx_l"] = round(abs(0.5 - m["mouth_corner_x_l"]), 12) if m["mouth_corner_x_l"] else None
    m["sym_mouth_dx_r"] = round(abs(m["mouth_corner_x_r"] - 0.5), 12) if m["mouth_corner_x_r"] else None
    return m


def cross_frame_report(projections: dict, reference: dict | None = None) -> dict:
    """Compare projected 3D landmark fractions to the 2D layout reference.

    The two bodies are different projections of the same face (2D stylized vs
    true-pinhole 3D), so equality is not asserted; documented per-feature
    tolerance bands trip the regression check. Every residual is published.
    """
    if reference is None:
        reference = face_state_reference_fractions()
    m = measure(projections)
    checks = {
        "brow_level_y": (m["brow_level_y"], reference["brow_level_y"]),
        "eye_level_y": (m["eye_level_y"], reference["eye_level_y"]),
        "nose_tip_y": (m["nose_tip"][1], reference["nose_tip"][1]),
        "nose_tip_x": (m["nose_tip"][0], reference["nose_tip"][0]),
        "mouth_corner_y": (m["mouth_y"], reference["mouth_corner_y"]),
        "mouth_corner_x_l": (m["mouth_corner_x_l"], reference["mouth_corner_x_l"]),
        "mouth_corner_x_r": (m["mouth_corner_x_r"], reference["mouth_corner_x_r"]),
        "eye_center_x_l": (m["eye_center_x_l"], reference["eye_center_x_l"]),
        "eye_center_x_r": (m["eye_center_x_r"], reference["eye_center_x_r"]),
    }
    residuals = {}
    violations = []
    for feature, (got, want) in checks.items():
        if got is None or want is None:
            residuals[feature] = None
            violations.append(feature)
            continue
        resid = round(abs(got - want), 12)
        residuals[feature] = resid
        tol = _FEATURE_TOLERANCES[feature]
        if resid > tol:
            violations.append(feature)

    # structural orderings in y (top-down): brow < eye < nose < mouth
    structure = {
        "brow_above_eye_ok": (
            m["brow_level_y"] is not None
            and m["eye_level_y"] is not None
            and m["brow_level_y"] < m["eye_level_y"]
        ),
        "eye_above_nose_ok": (
            m["eye_level_y"] is not None
            and m["nose_tip"][1] is not None
            and m["eye_level_y"] < m["nose_tip"][1]
        ),
        "nose_above_mouth_ok": (
            m["nose_tip"][1] is not None
            and m["mouth_y"] is not None
            and m["nose_tip"][1] < m["mouth_y"]
        ),
        "nose_centered_x_ok": (
            m["nose_tip_x"] is not None
            and abs(m["nose_tip_x"] - 0.5) <= 0.008
        ),
        "mouth_symmetric_ok": (
            m["sym_mouth_dx_l"] is not None
            and m["sym_mouth_dx_r"] is not None
            and abs(m["sym_mouth_dx_l"] - m["sym_mouth_dx_r"]) <= 0.004
        ),
    }
    structure_ok = all(structure.values())
    return {
        "reference": reference["source"],
        "measurements": m,
        "residuals": residuals,
        "tolerances": dict(_FEATURE_TOLERANCES),
        "structure": structure,
        "structure_ok": structure_ok,
        "within_tolerance": not violations,
        "violations": violations,
    }


def channel_state(fields) -> dict:
    """Per-channel maximum displacement magnitudes (round-trip stable)."""
    out = {CH_EXPRESSION: 0.0, CH_VISEME: 0.0, CH_MICRO: 0.0, CH_ANATOMICAL: 0.0}
    if not fields:
        return out
    for (ex, ey, ez, ux, uy, uz, mx, my, mz, jx, jy, jz) in fields:
        out[CH_EXPRESSION] = max(out[CH_EXPRESSION], abs(ex), abs(ey), abs(ez))
        out[CH_VISEME] = max(out[CH_VISEME], abs(ux), abs(uy), abs(uz))
        out[CH_MICRO] = max(out[CH_MICRO], abs(mx), abs(my), abs(mz))
        out[CH_ANATOMICAL] = max(out[CH_ANATOMICAL], abs(jx), abs(jy), abs(jz))
    return {k: round(v, 12) for k, v in out.items()}


def _eye_landmark_delta(lm_names, indices, base, posed):
    total = 0.0
    for name in lm_names:
        i = indices[name]
        bx, by, bz = base[i]
        qx, qy, qz = posed[i]
        total += abs(qx - bx) + abs(qy - by) + abs(qz - bz)
    return round(total / max(1, len(lm_names)), 12)


def blend_law_review(mesh=None, base=None) -> dict:
    """Quantitative review of the 0.6/0.3/0.1 blend law over canonical presets."""
    if mesh is None:
        mesh = get_mesh()
    if base is None:
        base = tuple(tuple(v) for v in mesh.verts)
    weights_ok = math_isclose(
        BLEND_E + BLEND_V + BLEND_M, 1.0, POSE_EPSILON
    )
    checks = {"weights_sum_ok": bool(weights_ok)}
    per_preset = {}
    for name in sorted(PRESETS):
        ctrl = ExpressionController(mesh, auto_blink=False)
        ctrl.controls.set_all(PRESETS[name], immediate=True)
        ctrl.controls.set_target("blink", 0.0, immediate=True)
        ctrl._audit = True
        pose = ctrl.compute_pose(0.5, reduced=True)
        fields = ctrl._last_fields
        st = channel_state(fields)
        max_delta = max(
            max(abs(pose[i][k] - base[i][k]) for k in range(3))
            for i in range(len(base))
        )
        per_preset[name] = {
            "channels": st,
            "max_delta": round(max_delta, 12),
            "bounded": all(
                st[c] <= CHANNEL_MAX[c] + 1e-9 for c in CHANNELS
            ),
            "neutral_preserved": (
                name != "neutral"
                or round(max_delta, 9) <= 0.12
            ),
        }
    bounded = all(p["bounded"] for p in per_preset.values())
    neutral_ok = all(
        p["neutral_preserved"] for n, p in per_preset.items() if n == "neutral"
    )

    # semantic separation: speaking/viseme must never move the eyes
    ctrl_silent = ExpressionController(mesh, auto_blink=False)
    ctrl_silent.controls.set_all(PRESETS["neutral"], immediate=True)
    ctrl_silent.controls.set_target("blink", 0.0, immediate=True)
    pose_silent = ctrl_silent.compute_pose(0.5, reduced=True)
    ctrl_talk = ExpressionController(mesh, auto_blink=False)
    ctrl_talk.controls.set_all(PRESETS["speaking"], immediate=True)
    ctrl_talk.controls.set_target("blink", 0.0, immediate=True)
    pose_talk = ctrl_talk.compute_pose(0.5, reduced=True)
    eye_delta = _eye_landmark_delta(
        ("iris_l", "iris_r", "corner_inner_l", "corner_inner_r"),
        mesh.landmarks,
        pose_silent,
        pose_talk,
    )
    mouth_delta = _eye_landmark_delta(
        ("mouth_corner_l", "mouth_corner_r", "upper_lip_c", "lower_lip_c"),
        mesh.landmarks,
        pose_silent,
        pose_talk,
    )
    speech_confined = eye_delta <= 1e-9 and mouth_delta > 1e-9

    # neutral symmetry: authored boundary must be exactly symmetric; pose-time
    # residual is bounded by the documented micro band (0.1 * micro amplitude).
    ctrl_n = ExpressionController(mesh, auto_blink=False)
    ctrl_n.controls.set_all(PRESETS["neutral"], immediate=True)
    ctrl_n.controls.set_target("blink", 0.0, immediate=True)
    pose_n = ctrl_n.compute_pose(0.5, reduced=True)
    lm = mesh.landmarks
    bx_r = base[lm["mouth_corner_r"]][0]
    bx_l = base[lm["mouth_corner_l"]][0]
    authored_symmetry_ok = math_isclose(bx_r, -bx_l, POSE_EPSILON)
    bn_x = base[lm["nose_tip"]][0]
    authored_nose_centered = abs(bn_x) <= POSE_EPSILON
    rx = pose_n[lm["mouth_corner_r"]][0]
    lx = pose_n[lm["mouth_corner_l"]][0]
    pose_symmetry_ok = abs(rx + lx) <= 0.005
    nx = pose_n[lm["nose_tip"]][0]
    pose_nose_ok = abs(nx) <= 0.002

    # dominance: expression energy > viseme energy for an emotional preset,
    # viseme overtakes expression for the speaking preset (speech is channel-capped).
    expr = per_preset["happy"]["channels"][CH_EXPRESSION]
    viseme = per_preset["happy"]["channels"][CH_VISEME]
    expression_dominance_ok = expr >= viseme

    micro = per_preset["neutral"]["channels"][CH_MICRO]
    micro_bounded_ok = micro <= CHANNEL_MAX[CH_MICRO] + 1e-9

    # audit-composition consistency sampled on the speaking preset (single call
    # so _last_fields / _last_pose are a matched pair)
    ctrl_a = ExpressionController(mesh, auto_blink=False)
    ctrl_a.controls.set_all(PRESETS["speaking"], immediate=True)
    ctrl_a.controls.set_target("blink", 0.0, immediate=True)
    ctrl_a._audit = True
    pose_a = ctrl_a.compute_pose(0.5, reduced=True)
    fields_a = ctrl_a._last_fields
    composition_ok = True
    for i, (ex, ey, ez, ux, uy, uz, mx, my, mz, jx, jy, jz) in enumerate(fields_a):
        exp_ = (
            base[i][0] + blend_pose(ex, ux, mx) + jx,
            base[i][1] + blend_pose(ey, uy, my) + jy,
            base[i][2] + blend_pose(ez, uz, mz) + jz,
        )
        if not all(
            pose_near(pose_a[i][k], exp_[k], POSE_EPSILON) for k in range(3)
        ):
            composition_ok = False
            break

    checks.update(
        {
            "channel_ceilings_ok": bool(bounded),
            "neutral_preserved_ok": bool(neutral_ok),
            "expression_dominance_ok": bool(expression_dominance_ok),
            "speech_confined_to_mouth_ok": bool(speech_confined),
            "micro_bounded_ok": bool(micro_bounded_ok),
            "neutral_symmetry_ok": bool(
                authored_symmetry_ok and authored_nose_centered
            ),
            "neutral_pose_symmetry_ok": bool(pose_symmetry_ok and pose_nose_ok),
            "audit_composition_ok": bool(composition_ok),
        }
    )
    return {
        "blend_weights": {
            "expression": BLEND_E,
            "viseme": BLEND_V,
            "micro": BLEND_M,
        },
        "checks": checks,
        "all_ok": all(checks.values()),
        "per_preset": per_preset,
    }


@dataclass(frozen=True)
class FaceState:
    version: str
    mesh_model_version: str
    controls: dict
    t: float
    reduced: bool
    pose: tuple
    fields: tuple
    audit: dict
    projections: dict
    signature: str
    extra: dict = field(default_factory=dict)

    def channel_state(self) -> dict:
        return channel_state(self.fields)

    def measure(self) -> dict:
        return measure(self.projections)

    def cross_frame_report(self, reference: dict | None = None) -> dict:
        return cross_frame_report(self.projections, reference=reference)

    def _flatten_round(self, value):
        return round(float(value), 9)

    def to_render_frame(self):
        """Renderer-contract snapshot. Lazily imports the renderer contract so
        the headless analytic layer never depends on the runtime package graph."""
        from maya_runtime.rendering import RenderFrame

        st = self.channel_state()
        channels = {k: self._flatten_round(v) for k, v in st.items()}
        tags = (
            "face_state",
            "id:" + self.signature[:24],
            "v:" + self.version,
            "mesh:" + self.mesh_model_version,
        )
        return RenderFrame(
            channels=channels,
            mesh=(),
            tags=tags,
        )

    def verify(self, reference: dict | None = None) -> dict:
        st = self.channel_state()
        bounded = all(st[k] <= CHANNEL_MAX[k] + 1e-9 for k in CHANNELS)
        cf = self.cross_frame_report(reference=reference)
        audit_ok = bool(self.audit.get("ok")) and bool(self.audit.get("pose_ok"))
        return {
            "version": self.version,
            "audit": self.audit,
            "audit_ok": audit_ok,
            "channel_state": st,
            "bounded": bounded,
            "cross_frame": cf,
            "face_state_ok": audit_ok and bounded and cf["structure_ok"],
        }


def build_face_state(
    controls: dict | None = None,
    t: float = 0.5,
    reduced: bool = True,
    mesh=None,
    size: int = 1000,
    reference: dict | None = None,
) -> FaceState:
    """Deterministic canonical snapshot of the face.

    ``controls`` defaults to the ``neutral`` preset (stateless: fresh
    controller, blink disabled, immediate targets, fixed ``t``).
    """
    if mesh is None:
        mesh = get_mesh()
    if controls is None:
        controls = PRESETS["neutral"]
    ctrl = ExpressionController(mesh, auto_blink=False)
    ctrl.controls.set_all(dict(controls), immediate=True)
    ctrl.controls.set_target("blink", 0.0, immediate=True)

    audit = MATH_AGENT.finalize(ctrl, t=t, reduced=reduced)
    pose = tuple(tuple(v) for v in ctrl._last_pose)
    fields = tuple(tuple(f) for f in ctrl._last_fields)

    projector = MeshProjector(size)
    projections = _landmark_projections(mesh, pose, projector)

    return FaceState(
        version=FACE_STATE_VERSION,
        mesh_model_version=mesh.MODEL_VERSION if hasattr(mesh, "MODEL_VERSION") else MESH_MODEL_VERSION,
        controls=dict(sorted(controls.items())),
        t=canonical_float(t),
        reduced=reduced,
        pose=pose,
        fields=fields,
        audit=audit,
        projections=projections,
        signature=pose_digest(pose),
    )


def identity_face_state_record(identity_path: str | Path | None = None) -> dict | None:
    """The ``face_state`` block declared in maya_identity/identity.json."""
    path = Path(identity_path or (_geometry_dir().parent / "identity.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("face_state")


def canonical_contract_ok(identity_path: str | Path | None = None) -> dict:
    """Live rig constants vs the identity record (the fixed-point referee).

    The identity record is the only file that is written once under approval;
    if the runtime blend law or channel ceilings drift (accidental or hostile),
    this check fails loudly so FaceState never certifies a corrupted rig.
    """
    rec = identity_face_state_record(identity_path=identity_path) or {}
    blend = rec.get("blend_law") or {}
    ceilings = rec.get("channel_ceilings") or {}
    checks = {
        "blend_expression_ok": math_isclose(blend.get("expression", -1.0), BLEND_E, POSE_EPSILON),
        "blend_viseme_ok": math_isclose(blend.get("viseme", -1.0), BLEND_V, POSE_EPSILON),
        "blend_micro_ok": math_isclose(blend.get("micro", -1.0), BLEND_M, POSE_EPSILON),
        "ceiling_expression_ok": math_isclose(ceilings.get(CH_EXPRESSION, -1.0), CHANNEL_MAX[CH_EXPRESSION], POSE_EPSILON),
        "ceiling_viseme_ok": math_isclose(ceilings.get(CH_VISEME, -1.0), CHANNEL_MAX[CH_VISEME], POSE_EPSILON),
        "ceiling_micro_ok": math_isclose(ceilings.get(CH_MICRO, -1.0), CHANNEL_MAX[CH_MICRO], POSE_EPSILON),
        "ceiling_anatomical_ok": math_isclose(ceilings.get(CH_ANATOMICAL, -1.0), CHANNEL_MAX[CH_ANATOMICAL], POSE_EPSILON),
    }
    return {
        "recorded": bool(rec),
        "checks": checks,
        "all_ok": bool(rec) and all(checks.values()),
    }


def identity_canonical_face(identity_path: str | Path | None = None) -> dict | None:
    path = Path(identity_path or (_geometry_dir().parent / "identity.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("canonical_face")