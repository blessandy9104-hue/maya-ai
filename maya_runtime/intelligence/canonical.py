"""Canonical knowledge-object foundation (MAYA Batch #2).

Wraps validated typed values (see ``representation``) in a deterministic,
machine-operable envelope with a declared schema, explicit type tags, units,
provenance, and an integrity digest over the RFC 8785 JCS canonical bytes.

Guarantees this layer provides:

- **Deterministic integrity**: the digest is ``SHA-256`` over the JCS
  canonical UTF-8 bytes of the envelope *without* the ``integrity`` member
  (no self-reference, no wall-clock, no RNG). Identical input yields an
  identical envelope and digest on every interpreter/device.
- **Fail-closed construction**: every body field must be a declared typed
  value that passes its contract; uncertified values are rejected, never
  clamped or reinterpreted.
- **Explicit semantic boundaries**: ``UNKNOWN``/``AMBIGUOUS`` detection
  regimes are returned as labels; they are never coerced to numeric or
  boolean values. ``probability``/``confidence``/``uncertainty`` are never
  silently interconverted.
- **Provenance always attached**: a knowledge object without provenance is
  refused (reusing the world-model evidence vocabulary).
- **Geometry reuse**: space/axis/tolerance are read from the authoritative
  ``maya_identity/geometry/*.json`` files, not re-declared here.
- **Translation with loss accounting**: whitelisted shape-preserving moves
  are reported with explicit loss metadata; anything outside the whitelist is
  refused so the semantic distinction is preserved.

The underlying RFC 8785 serializer is the verified ``jcs`` module (Batch #1);
``hashlib`` is used only through ``jcs.sha256``. No ``eval``/``exec`` call
exists in this module or its type system.
"""
from __future__ import annotations

import json
import pathlib

from . import jcs
from .representation import (
    REPRESENTATION_TYPES_ORDERED,
    RepresentationError,
    classify,
    validate,
    validate_iso8601_utc,
    validate_metadata,
    validate_provenance,
)

PROTOCOL = "maya.knowledge_object"
PROTOCOL_VERSION = 1
SCHEMA_ID = "maya:knowledge-object:1"
SCHEMA_VERSION = 1
DIGEST_ALG = "sha-256"
DIGEST_SOURCE = "jcs-rfc-8785"

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _PROJECT_ROOT / "verification" / "knowledge_object.schema.json"
_GEOMETRY_PATH = _PROJECT_ROOT / "maya_identity" / "geometry"
_GEO_IDENTITY = _GEOMETRY_PATH / "maya_geometry.json"
_GEO_SYMMETRY = _GEOMETRY_PATH / "symmetry_rules.json"

# Envelope members, in stable order (mirrors knowledge_object.schema.json).
ENVELOPE_KEYS = (
    "protocol", "protocol_version", "schema", "object_id", "record_type",
    "schema_version", "created_at", "provenance", "metadata", "body",
    "integrity",
)

ALLOWED_ALGORITHMS = frozenset({DIGEST_ALG})

# Translation whitelist. Anything not listed is refused, preserving the
# semantic distinctions the type system exists to protect.
_TRANSLATIONS = {
    ("scalar", "measurement"): {
        "requires": ("units",),
        "lossy": False,
        "losses": (),
        "notes": "unit context gained; value preserved",
    },
    ("measurement", "scalar"): {
        "requires": ("drop_units", "units"),
        "lossy": True,
        "losses": ("units dropped",),
        "notes": "unit semantics are lost; permitted only with an explicit "
                 "drop_units flag and preserved provenance",
    },
    ("identifier", "text"): {
        "requires": ("allow_identifier_to_text",),
        "lossy": True,
        "losses": ("identifier contract dropped",),
        "notes": "the identifier obligation is an adhesive label; converting "
                 "it to free text loses that contract",
    },
    ("vector", "geometric_vector"): {
        "requires": ("dim",),
        "lossy": False,
        "losses": (),
        "notes": "identical components; geometric context gained",
    },
    ("geometric_vector", "vector"): {
        "requires": ("dim",),
        "lossy": False,
        "losses": (),
        "notes": "identical components; geometric context dropped but value "
                 "preserved",
    },
}

# Records that may omit provenance would be listed here; this table is
# intentionally empty so every object carries provenance (fail closed).
PROVENANCE_EXEMPT = frozenset()

_GEOMETRY_CACHE = None


class CanonicalError(ValueError):
    """Raised when an object cannot be a canonical knowledge object."""


def _json_file(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise CanonicalError("cannot read authoritative JSON %s: %r"
                             % (path.name, exc))


def geometry_contract():
    """Canonical geometry contract, derived from the repo's authoritative
    ``maya_identity/geometry`` files (reused, never re-declared)."""
    global _GEOMETRY_CACHE
    if _GEOMETRY_CACHE is None:
        identity = _json_file(_GEO_IDENTITY)
        symmetry = _json_file(_GEO_SYMMETRY)
        space = identity.get("space", {})
        width = float(space.get("width", 1.0))
        height = float(space.get("height", 1.0))
        axis_x = float(identity.get("symmetry_axis_x")
                       or symmetry.get("axis", 0.5))
        tolerance = float(symmetry.get("tolerance", 0.004))
        y_down = bool(space.get("y_down", True))
        _GEOMETRY_CACHE = {
            "space": (0.0, width, 0.0, height),
            "axis_x": axis_x,
            "tolerance": tolerance,
            "y_down": y_down,
            "source_files": (
                "maya_identity/geometry/maya_geometry.json",
                "maya_identity/geometry/symmetry_rules.json",
            ),
        }
    return _GEOMETRY_CACHE


def schema_path():
    return _SCHEMA_PATH


def schema_present():
    return _SCHEMA_PATH.is_file()


def geometry_space():
    """(lo_x, hi_x, lo_y, hi_y) bounds for the identity space."""
    return geometry_contract()["space"]


def _copy_without_integrity(obj):
    if not isinstance(obj, dict):
        raise CanonicalError("knowledge object must be a dict envelope")
    return {key: value for key, value in obj.items() if key != "integrity"}


def payload(obj):
    """The envelope minus the ``integrity`` member (the digest input)."""
    return _copy_without_integrity(obj)


def _validate_envelope_shape(obj):
    if not isinstance(obj, dict):
        raise CanonicalError("knowledge object must be a dict envelope")
    if not set(obj) == set(ENVELOPE_KEYS):
        raise CanonicalError("envelope key set mismatch: %s"
                             % sorted(set(obj) ^ set(ENVELOPE_KEYS)))
    if obj.get("protocol") != PROTOCOL:
        raise CanonicalError("protocol %r != %r" % (obj.get("protocol"),
                                                    PROTOCOL))
    if obj.get("protocol_version") != PROTOCOL_VERSION:
        raise CanonicalError("protocol_version %r != %d"
                             % (obj.get("protocol_version"), PROTOCOL_VERSION))
    if obj.get("schema") != SCHEMA_ID:
        raise CanonicalError("schema %r != %r" % (obj.get("schema"), SCHEMA_ID))
    if obj.get("schema_version") != SCHEMA_VERSION:
        raise CanonicalError("schema_version %r; current supported version is "
                             "%d" % (obj.get("schema_version"), SCHEMA_VERSION))


# Attributes that carry semantics and must survive into the envelope (units,
# declared dimensions, closed code sets, geometry space, ...). Only JSON-safe
# forms are ever stored; sets/tuples are normalized deterministically.
PERSISTED_ATTRS = (
    "units", "dim", "rows", "cols", "precision", "domain", "language",
    "code_set", "predicates", "nodes", "event_types", "geometry_kind",
    "kind", "space", "tolerance",
)

# Representation types whose instances live in the identity space: when no
# explicit space is supplied at construction, the canonical space contract
# (read from maya_identity/geometry) is enforced by default.
SPACE_BOUND_TYPES = ("geometric_point", "geometric_object")


def _persist_attrs(attrs):
    out = {}
    for key in PERSISTED_ATTRS:
        if key in attrs:
            value = attrs[key]
            if isinstance(value, (set, frozenset)):
                value = sorted(value)
            elif isinstance(value, tuple):
                value = list(value)
            out[key] = value
    return out


def create(*, record_type, body, object_id=None, provenance=None,
           created_at=None, metadata=None):
    """Build a canonical knowledge object.

    ``body`` is a dict mapping field name to ``{"type": <type>, "value": <v>,
    **attrs}``. Every field and the envelope are validated; nothing invalid is
    admitted. ``object_id`` and ``created_at`` are supplied by the caller (this
    layer is deterministic and never reads a clock).
    """
    if object_id is None:
        raise CanonicalError("object_id is required (caller-supplied; "
                             "identifiers are never generated here)")
    if created_at is None:
        raise CanonicalError(
            "created_at is required (caller-supplied; this layer never reads "
            "a wall clock)")
    validate(object_id, "identifier")
    validate_iso8601_utc(created_at)
    if record_type in PROVENANCE_EXEMPT:
        raise CanonicalError(
            "PROVENANCE_EXEMPT must stay empty: every knowledge object "
            "carries provenance (fail closed)")
    validate(record_type, "identifier")
    if provenance is None:
        raise CanonicalError("provenance is required for every knowledge "
                             "object (fail closed)")
    validate_provenance(provenance)
    if metadata is not None:
        validate_metadata(metadata)

    validated_body = {}
    for field_name, declared in (body or {}).items():
        validate(field_name, "identifier")
        if not isinstance(declared, dict) or "type" not in declared \
                or "value" not in declared:
            raise CanonicalError("body field %r must be a typed value dict "
                                 "with type and value" % (field_name,))
        type_name = declared["type"]
        attrs = {k: v for k, v in declared.items() if k not in ("type", "value")}
        if type_name in SPACE_BOUND_TYPES and "space" not in attrs:
            attrs["space"] = geometry_space()
        validated_value = validate(declared["value"], type_name, **attrs)
        stored = {"type": type_name, "value": validated_value}
        stored.update(_persist_attrs(attrs))
        validated_body[field_name] = stored

    payload_dict = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "schema": SCHEMA_ID,
        "object_id": object_id,
        "record_type": record_type,
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "provenance": provenance,
        "metadata": metadata if metadata is not None else {},
        "body": validated_body,
    }
    obj = dict(payload_dict)
    obj["integrity"] = {
        "alg": DIGEST_ALG,
        "source": DIGEST_SOURCE,
        "digest": jcs.sha256(payload_dict),
        "bytes": len(jcs.canonical_bytes(payload_dict)),
    }
    return obj


def verify(obj):
    """Recompute the integrity digest of ``obj`` and compare.

    Returns ``{"integrity_ok": True, "alg": ..., "digest": ..., "bytes": ...}``
    on success; raises ``CanonicalError`` if the envelope is malformed or the
    digest does not match (corruption fails closed).
    """
    _validate_envelope_shape(obj)
    integrity = obj.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("alg") not in \
            ALLOWED_ALGORITHMS:
        raise CanonicalError("integrity member is malformed or uses an "
                             "unrecognized algorithm")
    candidate = integrity.get("digest")
    if not isinstance(candidate, str) or not candidate:
        raise CanonicalError("integrity digest is missing")
    recomputed = jcs.sha256(_copy_without_integrity(obj))
    if recomputed != candidate:
        raise CanonicalError("integrity digest mismatch: recorded %r, "
                             "recomputed %r" % (candidate, recomputed))
    declared_bytes = integrity.get("bytes")
    if declared_bytes is not None and declared_bytes != len(
            jcs.canonical_bytes(_copy_without_integrity(obj))):
        raise CanonicalError("integrity byte count does not match the "
                             "canonical payload size")
    return {"integrity_ok": True, "alg": DIGEST_ALG,
            "digest": recomputed, "bytes": integrity.get("bytes")}


def to_jcs(obj):
    """RFC 8785 canonical JSON text of the full envelope."""
    return jcs.canonicalize(obj)


def canonical_bytes(obj):
    """RFC 8785 canonical UTF-8 bytes of the full envelope."""
    return jcs.canonical_bytes(obj)


def digest(obj):
    """SHA-256 over the JCS canonical bytes of the envelope without its
    ``integrity`` member (the same input used at creation)."""
    return jcs.sha256(_copy_without_integrity(obj))


def detect(candidate, declared=None):
    """Representation detection: KNOWN / INVALID / AMBIGUOUS / UNKNOWN."""
    return classify(candidate, declared=declared)


def translate(value, from_type, to_type, *, units=None, context=None):
    """Admitted representation-translation with explicit loss accounting.

    Only the whitelist in ``_TRANSLATIONS`` is reachable. Every admitted move
    returns ``{"ok", "value", "to_type", "lossy", "losses", "notes"}``;
    anything outside the whitelist raises ``CanonicalError`` (the semantic
    distinction is preserved, never silently reinterpreted). The original
    value is never mutated and, where lossy, the loss is declared.
    """
    context = context or {}
    if (from_type, to_type) not in _TRANSLATIONS:
        raise CanonicalError(
            "translation %s -> %s is not admitted; the type system preserves "
            "that distinction" % (from_type, to_type))
    spec = _TRANSLATIONS[(from_type, to_type)]
    missing = [key for key in spec["requires"] if context.get(key, units) is
               None]
    if missing:
        raise CanonicalError("translation %s -> %s requires %s"
                             % (from_type, to_type, ", ".join(spec["requires"])))
    effective_units = context.get("units", units)
    effective_dim = context.get("dim")
    if from_type == "scalar" and to_type == "measurement":
        validate(value, to_type, units=effective_units)
    elif from_type == "measurement" and to_type == "scalar":
        validate(value, from_type, units=effective_units)
    elif from_type == "identifier" and to_type == "text":
        validate(value, from_type)
        validate(value, to_type)
    elif from_type == "vector" and to_type == "geometric_vector":
        validate(value, to_type, dim=effective_dim)
    elif from_type == "geometric_vector" and to_type == "vector":
        validate(value, to_type, dim=effective_dim)
    else:  # pragma: no cover - the whitelist above is exhaustive
        raise CanonicalError("translation %s -> %s not implemented"
                             % (from_type, to_type))
    return {
        "ok": True,
        "value": value,
        "to_type": to_type,
        "lossy": spec["lossy"],
        "losses": list(spec["losses"]),
        "notes": spec["notes"],
        "source_type": from_type,
    }


def semantic_preservation(a, b):
    """Loss metrics comparing two knowledge objects.

    Returns a dict of booleans: ``byte_equal`` (identical JCS bytes), 
    ``value_equal`` (identical integrity payloads), ``type_equal`` (identical
    type tags), ``structural_equal`` (identical key structures),
    ``semantic_equal`` (identical typed bodies and record identity), and
    ``provenance_preserved`` (identical provenance records). LOSSY translations
    are detectable here: a lossy move cannot have all flags True.
    """
    _validate_envelope_shape(a)
    _validate_envelope_shape(b)
    payload_a = _copy_without_integrity(a)
    payload_b = _copy_without_integrity(b)
    jcs_a = jcs.canonicalize(payload_a)
    jcs_b = jcs.canonicalize(payload_b)
    type_tags = lambda obj: tuple(sorted(
        (name, declared.get("type")) for name, declared in obj["body"].items()))
    return {
        "byte_equal": jcs_a == jcs_b,
        "value_equal": payload_a == payload_b,
        "type_equal": type_tags(a) == type_tags(b),
        "structural_equal": _structure(dict(a)) == _structure(dict(b)),
        "semantic_equal": a["body"] == b["body"]
                          and a["record_type"] == b["record_type"],
        "provenance_preserved": a["provenance"] == b["provenance"],
    }


def _structure(node):
    """Return the key structure of a JSON tree (no values)."""
    if isinstance(node, dict):
        return {key: _structure(item) for key, item in sorted(node.items())}
    if isinstance(node, (list, tuple)):
        return [_structure(item) for item in node]
    return None


def body_field_type(obj, field_name):
    """Return the declared type tag of one body field, or None."""
    declared = (obj or {}).get("body", {}).get(field_name)
    if not isinstance(declared, dict):
        return None
    return declared.get("type")


def types_used(obj):
    """Unique type tags used by a knowledge object's body, in stable order."""
    seen = []
    for name, declared in sorted((obj or {}).get("body", {}).items(),
                                 key=lambda item: item[0]):
        type_name = declared.get("type")
        if type_name not in seen:
            seen.append(type_name)
    return tuple(seen)


__all__ = (
    "PROTOCOL", "PROTOCOL_VERSION", "SCHEMA_ID", "SCHEMA_VERSION",
    "DIGEST_ALG", "ENVELOPE_KEYS", "ALLOWED_ALGORITHMS",
    "CanonicalError",
    "geometry_contract", "geometry_space", "schema_path", "schema_present",
    "payload", "create", "verify", "to_jcs", "canonical_bytes", "digest",
    "detect", "translate", "semantic_preservation", "body_field_type",
    "types_used",
)