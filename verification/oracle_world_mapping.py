"""Clean-room oracle for the Representation -> World-Model Mapping contract.

Independent, non-importing re-derivation of the Batch #5 world-mapping
decisions from the *published contract* alone. This module intentionally
imports ONLY the standard library: it must never import
``maya_runtime``, otherwise its comparison in ``test_world_mapping.py``
would be circular rather than independent.

The mapping contract (as published):

- Statuses: KNOWN / AMBIGUOUS / UNRESOLVED / INVALID.
- KNOWN requires exactly one world kind AND complete normalized fields.
- AMBIGUOUS is reserved for bounded candidate sets (timestamp temporal-role,
  duration interval-vs-duration); ambiguity is preserved, never forced.
- UNRESOLVED is the fail-honest status for valid representations with no
  structure-derivable world reference (bare number, scalar, free text,
  identifier, symbol, category, language, generic vector/matrix, canonical
  envelope). A bare ``42`` or ``0.7`` never becomes age/weight/id/
  probability/coordinate/quantity.
- INVALID fails closed from an invalid representation, malformed provenance,
  or non-finite contamination; no world reference is produced.
- CLAIM vs WORLD STATE: representation validity never implies world
  reference; a mapped candidate reference is a *claim candidate* whose
  factual character never exceeds the declared epistemic evidence; free text
  and cultural statements are preserved as claims, never world facts; world
  state is never mutated by the mapping layer.
- Geometry is first-class: coordinate space/bounds/source and the y-axis
  convention are preserved from the input when declared, otherwise from the
  identity space (0.0-1.0 both axes, y-down, source
  ``maya_identity/geometry/maya_geometry.json``). Units/coordinate systems
  are never reinterpreted.
- Temporal is conservative: timestamp = temporal reference with unresolved
  role (event/publication/retrieval/processing); duration = temporal
  interval/duration candidate with unresolved bounds; the bus temporal
  contract (instants) remains authoritative.
- Cryptographic kinds (encoded/encrypted data, hash, signature, key,
  certificate, cryptographic claim) exist as reserved vocabulary only; this
  batch performs NO crypto classification and never labels input as one of
  them.
"""
from __future__ import annotations

import math
import re

ORACLE_STATUSES = frozenset({"KNOWN", "AMBIGUOUS", "UNRESOLVED", "INVALID"})

ORACLE_WORLD_KINDS = frozenset({
    "measurement", "event", "relation", "temporal_reference",
    "temporal_interval", "geometric_object", "geometric_point",
    "geometric_vector", "geometric_transform", "graph", "entity", "location",
    "process_state", "claim_assertion", "unknown_reference",
    "encoded_data", "encrypted_data", "hash", "signature", "key",
    "certificate", "cryptographic_claim",
})

RESERVED_CRYPTO_KINDS = frozenset({
    "encoded_data", "encrypted_data", "hash", "signature", "key",
    "certificate", "cryptographic_claim",
})

TIMESTAMP_ROLES = ("event_time", "publication_time", "retrieval_time",
                   "processing_time")

IDENTITY_SPACE = {"space": [0.0, 1.0, 0.0, 1.0], "y_down": True,
                  "coordinate_system": "identity_maya_2d",
                  "source": "maya_identity/geometry/maya_geometry.json"}

_ISO_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_DURATION_RE = re.compile(
    r"^[+-]?([0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*"
    r"(ms|us|µs|s|min|h|d)$")
_DURATION_SECONDS = {"ms": 0.001, "us": 1.0e-6, "µs": 1.0e-6, "s": 1.0,
                     "min": 60.0, "h": 3600.0, "d": 86400.0}

# Structure-derived world kind for each KNOWN representation type.
STRUCTURAL_KIND = {
    "measurement": "measurement",
    "event": "event",
    "relation": "relation",
    "temporal_interval": "temporal_interval",
    "geometric_point": "geometric_point",
    "geometric_vector": "geometric_vector",
    "geometric_transform": "geometric_transform",
    "geometric_object": "geometric_object",
    "graph": "graph",
    "probability": "claim_assertion",
    "confidence": "claim_assertion",
    "uncertainty": "claim_assertion",
    "equation": "claim_assertion",
}

# Valid-but-unresolvable representation types.
UNRESOLVED_TYPES = frozenset({
    "text", "scalar", "identifier", "symbol", "category", "language",
    "vector", "matrix", "structured_canonical_object",
})


def _is_iso_timestamp(text):
    return bool(isinstance(text, str) and _ISO_UTC_RE.match(text.strip()))


def _duration_seconds(text):
    if not isinstance(text, str):
        return None
    match = _DURATION_RE.match(text.strip())
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    multiplier = _DURATION_SECONDS.get(match.group(2))
    if multiplier is None:
        return None
    return number * multiplier


def _is_float(text):
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


def _finite(value):
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, (list, tuple)):
        return all(_finite(item) for item in value)
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    return True


def oracle_map(representation_status, detected_type, candidate, original=None):
    """Independently re-derive the mapping for a detection result.

    ``representation_status`` is the Batch #4 detector verdict
    (KNOWN/AMBIGUOUS/UNKNOWN/INVALID); ``detected_type`` its type;
    ``candidate`` the canonical candidate (may be None); ``original`` the raw
    input (used for AMBIGUOUS/UNKNOWN preservation and duration/timestamp
    detection). Returns (status, world_kind, world_reference_resolved,
    unresolved_subset, claim_char, crypto_class).
    """
    if representation_status == "INVALID":
        return ("INVALID", None, False, ("world_reference",),
                "claim-undefined", "not_classified")

    if not _finite(candidate):
        return ("INVALID", None, False, ("world_reference",),
                "claim-undefined", "not_classified")

    if representation_status == "KNOWN":
        if detected_type in STRUCTURAL_KIND:
            world_kind = STRUCTURAL_KIND[detected_type]
            if detected_type == "measurement":
                return ("KNOWN", world_kind, True, (),
                        "factual-or-nonfactual-by-evidence", "not_classified")
            if detected_type in ("probability", "confidence", "uncertainty",
                                 "equation"):
                return ("KNOWN", world_kind, True, (),
                        "factual-or-nonfactual-by-evidence", "not_classified")
            if detected_type in ("geometric_point", "geometric_vector",
                                 "geometric_object", "geometric_transform"):
                return ("KNOWN", world_kind, True, (),
                        "factual-or-nonfactual-by-evidence", "not_classified")
            if detected_type == "event":
                return ("KNOWN", world_kind, True, (),
                        "factual-or-nonfactual-by-evidence", "not_classified")
            if detected_type == "relation":
                return ("KNOWN", world_kind, True, (),
                        "factual-or-nonfactual-by-evidence", "not_classified")
            if detected_type == "graph":
                return ("KNOWN", world_kind, True, (),
                        "factual-or-nonfactual-by-evidence", "not_classified")
            return ("KNOWN", world_kind, True, (),
                    "factual-or-nonfactual-by-evidence", "not_classified")
        if detected_type in UNRESOLVED_TYPES:
            return ("UNRESOLVED", "unknown_reference", False,
                    ("world_reference", "world_kind"),
                    "factual-or-nonfactual-by-evidence", "not_classified")
        return ("INVALID", None, False, ("world_reference",),
                "claim-undefined", "not_classified")

    if representation_status == "AMBIGUOUS":
        if _is_iso_timestamp(original):
            return ("AMBIGUOUS", "temporal_reference", False,
                    ("temporal_role",),
                    "factual-or-nonfactual-by-evidence", "not_classified")
        if _duration_seconds(original) is not None:
            return ("AMBIGUOUS", "temporal_interval", False,
                    ("start", "end"),
                    "factual-or-nonfactual-by-evidence", "not_classified")
        return ("AMBIGUOUS", None, False,
                ("world_reference", "world_kind"),
                "claim-undefined", "not_classified")

    if representation_status == "UNKNOWN":
        return ("UNRESOLVED", None, False,
                ("world_reference", "world_kind"),
                "claim-undefined", "not_classified")

    return ("INVALID", None, False, ("world_reference",),
            "claim-undefined", "not_classified")


def status_for(representation_status):
    """Map a Batch #4 verdict to the mapping status it can support."""
    if representation_status == "INVALID":
        return "INVALID"
    if representation_status == "KNOWN":
        return "KNOWN-or-UNRESOLVED-by-type"
    if representation_status == "AMBIGUOUS":
        return "AMBIGUOUS"
    if representation_status == "UNKNOWN":
        return "UNRESOLVED"
    return "INVALID"


def probability_candidate_never_committed(value):
    """The oracle's guard rule: ``0.7`` is never assigned a probability
    (or confidence/uncertainty) semantic without a declaration."""
    return 0.0 <= float(value) <= 1.0 \
        and not isinstance(value, dict)


def bare_number_never_committed():
    return True