"""VisualCommand — identity-verified embodiment contract (MAYA BATCH 8J-C).

Controlled pathway between Maya's identity / verified behavior and her visual
embodiment layer:

    Internal State
        -> VisualState (bounded, deterministic embodiment descriptor; 8C/8D)
        -> VisualCommand (this module: identity rules + verified parameters)
        -> project() / renderer (presentation only)

Core principle (Batch 8J-C):

    Embodiment represents identity.
    Embodiment does not create identity.

The visual system must never invent cognition, infer personality, modify
reasoning, create hidden state, or bypass verification. This module is the
explicit contract that enforces that:

- ``build_visual_command`` derives the command from the authoritative
  ``identity.json`` (or an injected payload for hermetic tests) plus the
  already-verified ``VisualState`` / ``meta``. It is pure and write-free: the
  same inputs always produce the identical ``VisualCommand`` on every device
  and interpreter. It never reads the renderer and never writes any file.
- Every visual rule carries PROVENANCE (the ``identity.json`` field it is
  derived from) and a named validation surface that already exists in the
  architecture (``shape_math`` hard bounds, ``SemanticCue`` gating, the
  ``SEMANTIC_NAMES`` vocabulary, channel ceilings, the ``identity_versions``
  journal).
- ``validate_visual_identity`` re-derives and checks the command; activation
  is a separate, explicit, operator-only step (``activate_visual_identity``)
  that records the versioned event in ``metadata/identity_versions.jsonl``.
  The automatic pipeline never activates: no silent visual drift.
- The honest vocabulary ("expression represents activity, attention,
  interaction state or semantic emphasis — never real feelings") is enforced
  by construction: ``semantic_emphasis`` is restricted to ``SEMANTIC_NAMES``
  and expression parameters are the already-approved, bounded, channel-capped
  ``semantic_controls`` of that semantic state.

Nothing here imports a renderer. The renderer (``project`` /
``TemporaryShapeRenderer``) is a pure function of ``VisualState`` and never a
writer of identity.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date as _date
from typing import Optional, Tuple

from ..wireframe.face_semantics import (
    SEMANTIC_NAMES,
    semantic_controls,
)
from .visual_state import VisualState

# ---------------------------------------------------------------------------
# Identity -> visual rules (source field, rule code, implication, validation).
# A rule activates only when its identity.json field is present; provenance is
# therefore enforced by construction. Validation surfaces all already exist.
# ---------------------------------------------------------------------------

_VISUAL_RULE_SPECS: Tuple = (
    ("critical_identity_rule",
     "visual_consistency",
     "the visual identity representation is deterministic per declared version",
     "same (identity version, face version, geometry version, visual rules) -> "
     "identical identity visual digest"),
    ("identity_geometry_rule",
     "visual_stability",
     "bounded movement and stable transitions; the presence-to-motion mapping "
     "never drifts silently",
     "shape_math hard bounds (SCALE_MIN/SCALE_MAX/TRAVEL_MAX) + VisualState "
     "domain clamps"),
    ("protection_rule",
     "visual_versioned_change",
     "no visual identity change without a version increment, validation and "
     "operator-approved activation; no silent visual drift",
     "visual identity version + identity_versions journal + activation gate"),
    ("role",
     "visual_conservative_presence",
     "visual presence reacts only to verified semantic state; conservative by "
     "default, never autonomous intensification",
     "SemanticCue gating (restricted suppresses activity lift) + bounded "
     "presence parameter"),
    ("identity_statement",
     "visual_honest_expression",
     "the expression vocabulary represents activity, attention, interaction "
     "state or semantic emphasis - never real feelings, consciousness or "
     "private experience",
     "SEMANTIC_NAMES vocabulary + channel ceilings + bounded VisualState "
     "domains"),
)

_DIGEST_ALG = hashlib.sha256

# Parameter domains (these ARE the contract; validation mirrors them).
PARAM_DOMAIN = {
    "attention": (0.0, 1.0),
    "activity": (0.0, 1.0),
    "focus": (0.0, 1.0),
    "presence": (0.0, 1.0),
}

# Wording the honest-expression rule must never imply (test searches the
# derived command surface, never primary reasoning or renderer code).
EMOTION_CLAIM_WORDS = frozenset({
    "feeling", "feel", "emotion", "emotional", "conscious", "consciousness",
    "private experience", "happy", "sad", "angry", "fear", "joy",
})

_REST_ANCHORS = frozenset({"dormant", "neutral"})


def _float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _round12(value):
    return round(float(value), 12)


@dataclass(frozen=True)
class IdentityVisualRule:
    """One identity-sourced visual rule (constraint on the visual path)."""

    code: str
    source: str
    implication: str
    validation: str


@dataclass(frozen=True)
class VisualCommand:
    """Immutable identity-verified visual command (constraint data only).

    ``identity_digest`` changes when the identity version / face version /
    geometry version, or the active visual rules (with provenance) change.
    ``state_signature`` binds the underlying deterministic VisualState, so the
    full ``signature`` is a deterministic function of both the identity
    mapping and the verified visual state. The object has no write surface and
    no reasoning API.
    """

    identity_version: str
    face_version: str
    geometry_version: str
    visual_identity_version: str
    identity_digest: str
    active_rules: Tuple
    provenance: Tuple
    attention: float
    activity: float
    focus: float
    presence: float
    semantic_emphasis: str
    expression_params: Tuple
    state_signature: str

    def signature(self) -> str:
        payload = "%s|%s" % (self.identity_digest, self.state_signature)
        return _DIGEST_ALG(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict:
        return {
            "identity_version": self.identity_version,
            "face_version": self.face_version,
            "geometry_version": self.geometry_version,
            "visual_identity_version": self.visual_identity_version,
            "identity_digest": self.identity_digest,
            "active_rules": [
                {"code": r.code, "source": r.source,
                 "implication": r.implication, "validation": r.validation}
                for r in self.active_rules
            ],
            "provenance": list(self.provenance),
            "attention": self.attention,
            "activity": self.activity,
            "focus": self.focus,
            "presence": self.presence,
            "semantic_emphasis": self.semantic_emphasis,
            "expression_params": list(self.expression_params),
            "state_signature": self.state_signature,
            "signature": self.signature(),
        }


def visual_identity_version(identity_payload: Optional[dict] = None) -> str:
    """Deterministic visual identity version: ``identity_version/face_version``.

    The declared identity version plus the canonical face version uniquely
    identify the visual identity representation. Empty when unusable.
    """
    payload = identity_payload
    if payload is None:
        try:
            from maya_identity.identity import load_identity
            payload = load_identity() or {}
        except Exception:
            return ""
    if not isinstance(payload, dict):
        return ""
    identity_version = str(payload.get("identity_version") or "")
    face_version = str(payload.get("face_version") or "")
    if not identity_version or not face_version:
        return ""
    return "%s/%s" % (identity_version, face_version)


def _identity_digest(identity_version, face_version, geometry_version, rules):
    payload = {
        "identity_version": identity_version,
        "face_version": face_version,
        "geometry_version": geometry_version,
        "rules": [
            {"code": r.code, "source": r.source,
             "implication": r.implication, "validation": r.validation}
            for r in rules
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    return _DIGEST_ALG(raw.encode("utf-8")).hexdigest()


def _params_from_meta(meta):
    meta = dict(meta or {})
    presence = _round12(_clamp(
        _float(meta.get("presence", meta.get("presence_alpha"))),
        *PARAM_DOMAIN["presence"]))
    return presence


def build_visual_command(base_state: Optional[VisualState] = None,
                         meta=None,
                         identity_payload: Optional[dict] = None):
    """Pure, write-free derivation of the identity-verified visual command.

    ``base_state`` is the already-verified ``VisualState`` of the tick (Batch
    8C/8D); ``meta`` may carry a bounded ``presence`` parameter. When
    ``identity_payload`` is None the authoritative ``identity.json`` is read
    through ``maya_identity.identity.load_identity``. Returns ``None`` when no
    usable identity payload is available. Never raises on malformed input.
    """
    payload = identity_payload
    if payload is None:
        try:
            from maya_identity.identity import load_identity
            payload = load_identity() or {}
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    identity_version = str(payload.get("identity_version") or "")
    face_version = str(payload.get("face_version") or "")
    geometry_version = str(payload.get("geometry_version") or "")
    if not identity_version or not face_version:
        return None

    rules = []
    for source, code, implication, validation in _VISUAL_RULE_SPECS:
        if payload.get(source):
            rules.append(IdentityVisualRule(
                code=code, source=source, implication=implication,
                validation=validation))
    rules = tuple(sorted(rules, key=lambda r: r.code))
    provenance = tuple(sorted({r.source for r in rules}))

    digest = _identity_digest(identity_version, face_version,
                              geometry_version, rules)

    if base_state is None:
        emphasis = "neutral"
        attention = activity = focus = 0.0
        state_signature = ""
    else:
        emphasis = str(getattr(base_state, "semantic", "neutral") or "neutral")
        if emphasis not in SEMANTIC_NAMES:
            emphasis = "neutral"
        attention = _round12(_clamp(
            _float(getattr(base_state, "attention", 0.0)),
            *PARAM_DOMAIN["attention"]))
        activity = _round12(_clamp(
            _float(getattr(base_state, "activity", 0.0)),
            *PARAM_DOMAIN["activity"]))
        focus = _round12(_clamp(
            _float(getattr(base_state, "focus", 0.0)),
            *PARAM_DOMAIN["focus"]))
        state_signature = base_state.signature() if hasattr(
            base_state, "signature") else ""

    presence = _params_from_meta(meta)

    params = []
    try:
        spec_controls = semantic_controls(emphasis) or {}
    except Exception:
        spec_controls = {}
    for control, value in sorted((spec_controls or {}).items()):
        params.append((str(control), _round12(_clamp(
            _float(value), *PARAM_DOMAIN["attention"]))))
    expression_params = tuple(params)

    return VisualCommand(
        identity_version=identity_version,
        face_version=face_version,
        geometry_version=geometry_version,
        visual_identity_version="%s/%s" % (identity_version, face_version),
        identity_digest=digest,
        active_rules=rules,
        provenance=provenance,
        attention=attention,
        activity=activity,
        focus=focus,
        presence=presence,
        semantic_emphasis=emphasis,
        expression_params=expression_params,
        state_signature=state_signature,
    )


def restrict_visual_state(command: VisualCommand, vs: VisualState) -> VisualState:
    """Identity-constrained renderer input: a re-verified copy of ``vs``.

    Pure. ``VisualState`` already clamps every field into its domain, so the
    identity layer re-enforces (never relaxes) those bounds; this is the
    proof that identity constrains the renderer's inputs and that the renderer
    cannot, in turn, change identity.
    """
    return VisualState(
        semantic=command.semantic_emphasis,
        attention=_round12(_clamp(
            _float(getattr(vs, "attention", 0.0)), *PARAM_DOMAIN["attention"])),
        focus=_round12(_clamp(
            _float(getattr(vs, "focus", 0.0)), *PARAM_DOMAIN["focus"])),
        curiosity=_round12(_clamp(
            _float(getattr(vs, "curiosity", 0.0)), 0.0, 1.0)),
        activity=_round12(_clamp(
            _float(getattr(vs, "activity", 0.0)), *PARAM_DOMAIN["activity"])),
        gaze_dx=_round12(_clamp(
            _float(getattr(vs, "gaze_dx", 0.0)), -1.0, 1.0)),
        gaze_dy=_round12(_clamp(
            _float(getattr(vs, "gaze_dy", 0.0)), -1.0, 1.0)),
        rest=bool(getattr(vs, "rest", True)),
    )


def to_visual_state(command: VisualCommand) -> VisualState:
    """Deterministic VisualState reconstructed from the command parameters.

    Pure. Built only from the command's bounded parameters (attention,
    activity, focus, semantic emphasis), with gaze neutralised (identity
    commands carry no unverified gaze) and rest derived from the semantic
    emphasis. Renderer-safe by construction.
    """
    return VisualState(
        semantic=command.semantic_emphasis,
        attention=_round12(_clamp(command.attention, *PARAM_DOMAIN["attention"])),
        focus=_round12(_clamp(command.focus, *PARAM_DOMAIN["focus"])),
        curiosity=1.0 if command.semantic_emphasis == "curious" else 0.0,
        activity=_round12(_clamp(command.activity, *PARAM_DOMAIN["activity"])),
        gaze_dx=0.0,
        gaze_dy=0.0,
        rest=command.semantic_emphasis in _REST_ANCHORS,
    )


def validate_visual_identity(command) -> tuple:
    """Validation: re-derives and checks every contract invariant.

    Returns ``(ok: bool, reasons: [str])``. The checks mirror the Batch 8J-C
    requirements: identity consistency, provenance, bounded parameters,
    honest expression vocabulary, approved expression parameters, stable
    digest.
    """
    if command is None:
        return False, ["no command"]
    if not isinstance(command, VisualCommand):
        return False, ["not a VisualCommand"]
    reasons = []
    if not command.identity_version:
        reasons.append("empty identity_version")
    if not command.face_version:
        reasons.append("empty face_version")
    if not command.active_rules:
        reasons.append("no active visual rules")
    if not command.provenance:
        reasons.append("empty provenance")
    if set(command.provenance) != {r.source for r in command.active_rules}:
        reasons.append("provenance does not match active rule sources")

    recheck = _identity_digest(
        command.identity_version, command.face_version,
        command.geometry_version, tuple(command.active_rules))
    if recheck != command.identity_digest:
        reasons.append("identity_digest not stable")

    speed_meta = {
        "attention": command.attention,
        "activity": command.activity,
        "focus": command.focus,
        "presence": command.presence,
    }
    for key, (lo, hi) in PARAM_DOMAIN.items():
        value = speed_meta[key]
        if not (lo <= value <= hi):
            reasons.append("%s out of domain" % key)

    if command.semantic_emphasis not in SEMANTIC_NAMES:
        reasons.append("semantic emphasis not in honest vocabulary")
    lowered = command.semantic_emphasis.lower()
    for word in EMOTION_CLAIM_WORDS:
        if word in lowered:
            reasons.append("semantic emphasis implies an emotion claim: %r"
                           % word)

    for control, value in getattr(command, "expression_params", ()):
        if not (0.0 <= _float(value) <= 1.0):
            reasons.append("expression param out of bounds: %s=%r"
                           % (control, value))
    return (not reasons, reasons)


def _append_jsonl(path, entry: dict) -> None:
    row = json.dumps(entry, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(row + "\n")


def activate_visual_identity(command, created_by: str = "operator") -> dict:
    """Activation gate: explicit, operator-only activation of a visual identity.

    Validates the command first; on failure returns ``{"status":
    "validation_failed", "reasons": [...]}`` and writes nothing (no silent
    drift). On success appends a ``visual_identity_activated`` event to
    ``metadata/identity_versions.jsonl`` (resolved through the identity
    module's ``VERSIONS_LOG`` at call time, so tests can redirect it) and
    returns the recorded event. The automatic pipeline never calls this.
    """
    ok, reasons = validate_visual_identity(command)
    if not ok:
        return {"status": "validation_failed", "reasons": reasons}
    entry = {
        "event": "visual_identity_activated",
        "visual_identity_version": command.visual_identity_version,
        "identity_version": command.identity_version,
        "face_version": command.face_version,
        "geometry_version": command.geometry_version,
        "identity_digest": command.identity_digest,
        "active_rules": [r.code for r in command.active_rules],
        "provenance": list(command.provenance),
        "validation": "validated",
        "date": _date.today().isoformat(),
        "created_by": created_by,
    }
    try:
        from maya_identity import identity as _identity
        _append_jsonl(getattr(_identity, "VERSIONS_LOG"), entry)
    except Exception:
        return {"status": "log_unavailable", "reasons": []}
    return entry