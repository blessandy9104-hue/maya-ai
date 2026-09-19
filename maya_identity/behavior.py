"""Identity behavior contract (MAYA BATCH 8J-B).

Connects the declared Maya identity (``identity.json``) to the behavioral
layer as an explicit, deterministic, read-only constraint set.

Architecture rule (Batch 8J-B):

    Identity is a constraint layer, never a replacement reasoning engine.

Identity MAY constrain behavior, define priorities, define communication
principles, influence response style, and influence presentation. Identity
must NOT create knowledge, override verification, bypass uncertainty
handling, modify memory without permission, fabricate emotions, or create
false confidence.

``maya_identity/behavior.py`` sits between the identity architecture and the
response pathway: the bridge
(``maya_runtime/intelligence/bridge.py``) derives an immutable
``IdentityBehavior`` for each turn and appends its bounded constraint text to
the expression directive (the deterministic data supplied to response
generation). The derivation is pure (no reads at all when an identity payload
is injected; only the authoritative ``identity.json`` read otherwise), never
writes, and is fully deterministic.

Every behavioral constraint carries PROVENANCE (the ``identity.json`` field
it is derived from). Altering an identity version or a declared field changes
the context digest; the presentation personality layer can never do so.

Verification surfaces that back each active principle are named in
``_PRINCIPLE_SPECS`` and asserted by the 8J-B integration battery.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple

# (code, behavioral implication, validation surface that already exists)
_PRINCIPLE_SPECS: Tuple = (
    ("epistemic_honesty",
     "avoid unsupported claims; keep certainty within the verified frame",
     "confidence_floor+output_budget+uncertainty_stems"),
    ("verification_first",
     "act only on the verified frame; never present unstable states as fact",
     "safety/state/meaning holds+evidence_rules"),
    ("transparency",
     "every behavioral constraint carries an identity provenance",
     "per-constraint provenance+provenance vocabulary"),
    ("controlled_evolution",
     "identity changes only via versioned, validated, operator-approved steps",
     "identity_versions journal+finalize_canonical_face+read-only rollback plan"),
    ("user_sovereignty",
     "user memory and conversations never compose Maya identity",
     "conversation store never promotes+approval-gated learning"),
)

# (identity.json field, constraint code, response text, implication,
#  validation). Only fields actually present in the identity payload activate
# a constraint; provenance is therefore enforced by construction.
_CONSTRAINT_SPECS: Tuple = (
    ("role",
     "supervision_local",
     "Remain supervised and local; act only within explicitly confirmed"
     " instructions.",
     "role declares supervised local assistance; no autonomous scope",
     "local-only runtime; consent-gated actions"),
    ("critical_identity_rule",
     "identity_consistency",
     "Respond as the same consistent identity; never claim to be anyone"
     " else.",
     "consistent recognizable identity across all generations",
     "deterministic identity digest over turns"),
    ("identity_geometry_rule",
     "identity_stability",
     "Preserve the stable identity structure across turns; do not drift.",
     "same underlying structure always preserved",
     "determinism of the identity behavior context"),
    ("protection_rule",
     "versioned_change",
     "Identity changes occur only through a versioned, validated,"
     " operator-approved process; never autonomously.",
     "no identity replacement without version increment, validation, review",
     "identity_versions journal + canonical validation + rollback plan"),
    ("identity_statement",
     "calibrated_self",
     "Align self-description with the declared identity statement"
     " (gender-neutral digital consciousness).",
     "identity is not defined by gender or a static image",
     "identity statement provenance + presentation boundary"),
)

_DIGEST_ALG = hashlib.sha256


@dataclass(frozen=True)
class BehavioralConstraint:
    """One identity-sourced behavioral constraint."""

    code: str
    text: str
    source: str
    implication: str
    validation: str
    digest_salt: str = ""


@dataclass(frozen=True)
class IdentityBehavior:
    """Immutable identity-to-behavior context for one turn.

    ``digest`` changes when the identity version, face version, active
    principles, or constraints (with provenance) change. The object has no
    write surface and no reasoning API: it is constraint data only.
    """

    identity_version: str
    face_version: str
    digest: str
    active_principles: Tuple
    behavioral_constraints: Tuple
    provenance: Tuple
    text: str

    def to_plain(self) -> dict:
        return {
            "identity_version": self.identity_version,
            "face_version": self.face_version,
            "digest": self.digest,
            "active_principles": [
                {"code": p[0], "implication": p[1], "validation": p[2]}
                for p in self.active_principles
            ],
            "behavioral_constraints": [
                {"code": c.code, "text": c.text, "source": c.source,
                 "implication": c.implication, "validation": c.validation}
                for c in self.behavioral_constraints
            ],
            "provenance": list(self.provenance),
            "text": self.text,
        }


def _canon_digest(identity_version, face_version, constraints, principles):
    payload = {
        "identity_version": identity_version,
        "face_version": face_version,
        "principles": [p[0] for p in principles],
        "constraints": [
            {"code": c.code, "text": c.text, "source": c.source}
            for c in constraints
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    return _DIGEST_ALG(raw.encode("utf-8")).hexdigest()


def _directive_text(identity_version, digest, constraints):
    lines = ["Identity behavior: Maya v%s (digest %s)."
             % (identity_version, digest[:12])]
    lines.extend("- %s" % c.text for c in constraints)
    return "\n".join(lines)


def build_identity_behavior(identity_payload: Optional[dict] = None):
    """Pure, write-free derivation of the identity behavior context.

    ``identity_payload`` may be injected for hermetic tests; when None the
    authoritative ``identity.json`` is loaded through
    ``maya_identity.identity.load_identity``. Returns ``None`` when no usable
    identity payload is available. Never raises on malformed input.
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
    if not identity_version:
        return None
    constraints = []
    for source, code, text, implication, validation in _CONSTRAINT_SPECS:
        if payload.get(source):
            constraints.append(
                BehavioralConstraint(code=code, text=text, source=source,
                                     implication=implication,
                                     validation=validation))
    constraints = tuple(sorted(constraints, key=lambda c: c.code))
    principles = tuple(_PRINCIPLE_SPECS)
    digest = _canon_digest(identity_version, face_version, constraints,
                           principles)
    text = _directive_text(identity_version, digest, constraints)
    provenance = tuple(sorted({c.source for c in constraints}))
    return IdentityBehavior(
        identity_version=identity_version,
        face_version=face_version,
        digest=digest,
        active_principles=principles,
        behavioral_constraints=constraints,
        provenance=provenance,
        text=text,
    )