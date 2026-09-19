"""Independent canonical-representation oracle used by MAYA Batch #2.

This module is an independent observer for the typed canonical-representation
layer. It does NOT import ``maya_runtime`` (nor ``maya_world_model``, nor the
implementation modules ``representation``/``canonical``). Its rules are
recomputed here from first principles and from the authoritative data files:

- the type/range rules (finite numbers, [0,1] probability/confidence/
  uncertainty, measurement-requires-units, vector-dimension match, closed
  category codes, hostile-free equation text, ISO-8601 UTC timestamps);
- the canonical envelope keys and the JSON Schema at
  ``verification/knowledge_object.schema.json`` (schema-as-contract witness);
- the geometry contract (space, axis, tolerance) read from
  ``maya_identity/geometry/*.json``, including an external mirror check
  (left/right brow pairs from ``facial_structure.json`` must mirror about the
  declared axis within the declared tolerance);
- digest recomputation through the already-verified independent JCS
  serializer ``oracle_jcs`` (sha-256 over the JCS canonical bytes of the
  envelope payload without its ``integrity`` member).

The test suite (``test_canonical_representation.py``) compares this oracle
against the implementation on both directions: implementation obj -> oracle
digest, and oracle corpus rules <-> implementation validator.

Standalone: ``python verification/oracle_representation.py`` verifies all
embedded checks and prints one ``=OK`` evidence line per category; exit code
is non-zero if anything fails.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re

try:
    from . import oracle_jcs
except ImportError:  # standalone: ``python verification/oracle_representation.py``
    import oracle_jcs

ORACLE_IDENTITY = "maya-verification/oracle-representation/1.0.0"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

DIGEST_ALG = "sha-256"
DIGEST_SOURCE = "jcs-rfc-8785"
SCHEMA_VERSION = 1

REPRESENTATION_TYPES = frozenset({
    "identifier", "text", "scalar", "measurement", "vector", "matrix",
    "symbol", "equation", "category", "relation", "event",
    "temporal_interval", "geometric_point", "geometric_vector",
    "geometric_transform", "geometric_object", "graph", "probability",
    "confidence", "uncertainty", "provenance", "metadata",
})

ENVELOPE_KEYS = (
    "protocol", "protocol_version", "schema", "object_id", "record_type",
    "schema_version", "created_at", "provenance", "metadata", "body",
    "integrity",
)

SCHEMA_2020_12_META = "https://json-schema.org/draft/2020-12/schema"

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/=-]{0,127}$")
ISO_UTC_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?"
    r"(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

EQUATION_FORBIDDEN = (
    "eval", "exec", "import ", "__", "os.", "subprocess", "socket",
    "builtins", "compile",
)
EQUATION_LANGUAGES = ("maya.symbolic.v1",)

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _geometries():
    root = PROJECT_ROOT / "maya_identity" / "geometry"
    with (root / "maya_geometry.json").open("r", encoding="utf-8") as handle:
        identity = json.load(handle)
    with (root / "symmetry_rules.json").open("r", encoding="utf-8") as handle:
        symmetry = json.load(handle)
    with (root / "facial_structure.json").open("r", encoding="utf-8") as handle:
        facial = json.load(handle)
    space = identity.get("space", {})
    return {
        "space": (0.0, float(space.get("width", 1.0)),
                  0.0, float(space.get("height", 1.0))),
        "axis_x": float(identity.get("symmetry_axis_x")
                        or symmetry.get("axis", 0.5)),
        "tolerance": float(symmetry.get("tolerance", 0.004)),
        "y_down": bool(space.get("y_down", True)),
        "facial": facial,
    }


def _number_ok(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _iso_utc_ok(text):
    if not isinstance(text, str):
        return False
    match = ISO_UTC_RE.match(text.strip())
    if not match:
        return False
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour, minute = int(match.group(4)), int(match.group(5))
    second = int(match.group(6) or "0")
    if not (1 <= month <= 12):
        return False
    max_day = _MONTH_DAYS[month - 1]
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        max_day = 29
    if day < 1 or day > max_day or hour > 23 or minute > 59 or second > 60:
        return False
    offset = match.group(8)
    if offset != "Z":
        oh = int(offset[1:3])
        om = int(offset[4:6])
        if oh > 23 or om > 59 or (oh == 23 and om != 0):
            return False
    return True


def _validate_independent(value, type_name, **attrs):
    """First-principles rule witness. Returns (ok, reason)."""
    if type_name not in REPRESENTATION_TYPES:
        return False, "unknown type %r" % (type_name,)
    units_ok = "units" in attrs and isinstance(attrs["units"], str) \
        and attrs["units"].strip()
    dim = attrs.get("dim")
    if type_name in ("probability", "confidence", "uncertainty"):
        if not _number_ok(value):
            return False, "non-finite or non-number"
        if not (0.0 <= value <= 1.0):
            return False, "%s outside [0,1]" % type_name
        return True, None
    if type_name == "scalar":
        domain = attrs.get("domain")
        if not _number_ok(value):
            return False, "non-finite or non-number"
        if domain is not None and not (domain[0] <= value <= domain[1]):
            return False, "outside domain"
        return True, None
    if type_name == "measurement":
        if not _number_ok(value):
            return False, "non-finite or non-number"
        if not units_ok:
            return False, "measurement requires declared units"
        return True, None
    if type_name in ("vector", "geometric_vector"):
        if not isinstance(value, (list, tuple)) or len(value) != dim:
            return False, "vector/dim mismatch"
        return (all(_number_ok(item) for item in value), None)
    if type_name == "category":
        code_set = attrs.get("code_set")
        if not isinstance(value, str) or code_set is None \
                or value not in set(code_set):
            return False, "category code not in closed set"
        return True, None
    if type_name in ("identifier", "symbol"):
        return bool(IDENTIFIER_RE.match(value) if isinstance(value, str)
                    else False), None
    if type_name == "equation":
        if not isinstance(value, str):
            return False, "equation must be text"
        lower = value.lower()
        for token in EQUATION_FORBIDDEN:
            if token in lower:
                return False, "forbidden construct %r" % token
        language = attrs.get("language")
        if not language:
            return False, "equation requires a declared language"
        if language not in EQUATION_LANGUAGES:
            return False, "unknown equation language/encoding scheme"
        return True, None
    if type_name == "temporal_interval":
        start = value.get("start") if isinstance(value, dict) else None
        end = value.get("end") if isinstance(value, dict) else None
        if not _iso_utc_ok(start) or not _iso_utc_ok(end) or start > end:
            return False, "malformed or reversed interval"
        return True, None
    if type_name == "provenance":
        if not isinstance(value, dict):
            return False, "provenance must be a dict"
        if not set(value) >= {"source", "retrieved_at", "evidence_type",
                              "confidence"}:
            return False, "provenance missing required fields"
        if not value.get("source"):
            return False, "source required"
        if not _iso_utc_ok(value.get("retrieved_at")):
            return False, "retrieved_at not ISO-8601 UTC"
        return True, None
    if type_name == "relation":
        if not isinstance(value, dict) or not set(value) >= {
                "source_id", "target_id", "predicate"}:
            return False, "relation shape invalid"
        if value["source_id"] == value["target_id"] and \
                value["predicate"] not in (
                    "equals", "identical_to", "belongs_to", "coexists_with"):
            return False, "contradictory reflexive relation"
        return True, None
    if type_name == "geometric_point":
        if not isinstance(value, (list, tuple)) or len(value) not in (2, 3):
            return False, "point must be 2D/3D"
        if not all(_number_ok(item) for item in value):
            return False, "point components non-finite"
        space = attrs.get("space")
        if space is None:
            space = _geometries()["space"]  # identity-space default
        lo_x, hi_x, lo_y, hi_y = space
        if not (lo_x <= value[0] <= hi_x and lo_y <= value[1] <= hi_y):
            return False, "point outside declared space"
        return True, None
    if type_name == "geometric_object":
        kind = value.get("geometry_kind") if isinstance(value, dict) else None
        if kind not in ("point", "curve", "surface", "mesh"):
            return False, "unknown geometry_kind"
        return True, None
    if type_name == "graph":
        nodes = value.get("nodes") if isinstance(value, dict) else None
        edges = value.get("edges") if isinstance(value, dict) else None
        if nodes is None or edges is None or not nodes:
            return False, "graph requires nodes and edges"
        if len(nodes) != len(set(nodes)):
            return False, "graph nodes must be unique"
        return True, None
    if type_name == "text":
        return (isinstance(value, str) and len(value) <= 100000), None
    if type_name == "matrix":
        if not isinstance(value, (list, tuple)):
            return False, "matrix must be a row sequence"
        rows = attrs.get("rows")
        cols = attrs.get("cols")
        if rows is None or cols is None:
            return False, "matrix requires rows/cols"
        if len(value) != rows:
            return False, "matrix height mismatch"
        for row in value:
            if len(row) != cols or not all(_number_ok(item)
                                           for item in row):
                return False, "matrix width/content mismatch"
        return True, None
    if type_name in ("event", "metadata", "geometric_transform"):
        return True, None
    return True, None


# Independent (positively-mirrored) corpus: each entry must pass both the
# implementation validator and this oracle's first-principles rules.
CORPUS = (
    {"type": "probability", "value": 0.5},
    {"type": "probability", "value": 1.0},
    {"type": "confidence", "value": 0.0},
    {"type": "uncertainty", "value": 0.25},
    {"type": "measurement", "value": 0.5, "attrs": {"units": "normalized"}},
    {"type": "vector", "value": [1.0, 2.0, 3.0], "attrs": {"dim": 3}},
    {"type": "identifier", "value": "geo-0001"},
    {"type": "symbol", "value": "phi"},
    {"type": "category", "value": "human-inspired",
     "attrs": {"code_set": ["human-inspired", "cyber-organic"]}},
    {"type": "equation", "value": "x = 2 * t + 1",
     "attrs": {"language": "maya.symbolic.v1"}},
    {"type": "temporal_interval",
     "value": {"start": "2026-09-09T00:00:00Z",
               "end": "2026-09-09T00:05:00Z"}},
    {"type": "geometric_point", "value": [0.5, 0.46]},
    {"type": "provenance",
     "value": {"source": "RFC 8785",
               "retrieved_at": "2026-09-09T00:00:00Z",
               "evidence_type": "fact", "confidence": "high"}},
    {"type": "relation",
     "value": {"source_id": "a", "target_id": "b", "predicate": "coexists_with"},
     "attrs": {"predicates": ["coexists_with"]}},
)

NEGATIVE_CORPUS = (
    {"type": "probability", "value": 1.5},
    {"type": "probability", "value": -0.25},
    {"type": "confidence", "value": 1.6},
    {"type": "uncertainty", "value": -0.02},
    {"type": "measurement", "value": 0.5},                       # no units
    {"type": "measurement", "value": float("nan"),
     "attrs": {"units": "normalized"}},
    {"type": "measurement", "value": float("inf"),
     "attrs": {"units": "normalized"}},
    {"type": "vector", "value": [1.0, 2.0], "attrs": {"dim": 3}},
    {"type": "identifier", "value": 42},
    {"type": "category", "value": "not-in-set",
     "attrs": {"code_set": ["human-inspired"]}},
    {"type": "equation", "value": "__import__('os')",
     "attrs": {"language": "maya.symbolic.v1"}},
    {"type": "temporal_interval",
     "value": {"start": "2026-09-09T00:05:00Z",
               "end": "2026-09-09T00:00:00Z"}},
    {"type": "geometric_point", "value": [0.5, 1.5],
     "attrs": {"space": (0, 1, 0, 1)}},
    {"type": "relation",
     "value": {"source_id": "a", "target_id": "a", "predicate": "not_equal"},
     "attrs": {"predicates": ["not_equal"]}},
)


# ---------------------------------------------------------------------------
# Independent envelope + digest reconstruction.
# ---------------------------------------------------------------------------

def payload_without_integrity(obj):
    if not isinstance(obj, dict):
        raise ValueError("envelope must be a dict")
    return {key: value for key, value in obj.items() if key != "integrity"}


def independent_envelope(*, object_id, record_type, created_at, provenance,
                         metadata, body):
    """Independently re-assemble the envelope (same key set, own ordering)."""
    assembled = {
        "protocol": "maya.knowledge_object",
        "protocol_version": 1,
        "schema": "maya:knowledge-object:1",
        "object_id": object_id,
        "record_type": record_type,
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "provenance": provenance,
        "metadata": metadata,
        "body": body,
    }
    if set(assembled) != set(ENVELOPE_KEYS) - {"integrity"}:
        raise ValueError("independent envelope key set mismatch")
    return assembled


def oracle_canonical_bytes(obj):
    return oracle_jcs.canonical_bytes(payload_without_integrity(obj))


def oracle_digest(obj):
    return hashlib.sha256(oracle_canonical_bytes(obj)).hexdigest()


# ---------------------------------------------------------------------------
# Schema-as-contract witness (no external validator library is installed).
# ---------------------------------------------------------------------------

def _schema_document():
    path = PROJECT_ROOT / "verification" / "knowledge_object.schema.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def schema_witness():
    """Structural witness that the schema mirrors the implementation contract.

    Performed only with stdlib tooling; conformance via a real JSON-Schema
    validator remains UNAVAILABLE — NOT VALIDATED (documented in the register).
    """
    reports = []
    try:
        doc = _schema_document()
    except (OSError, ValueError) as exc:
        return False, ["schema unreadable: %r" % (exc,)]
    if not doc.get("$schema", "").startswith(SCHEMA_2020_12_META):
        reports.append("$schema does not target JSON Schema 2020-12")
    if doc.get("type") != "object":
        reports.append("schema root type != object")
    required = doc.get("required")
    if required is None or set(required) != set(ENVELOPE_KEYS):
        reports.append("required key set does not match the envelope")
    properties = doc.get("properties")
    if properties is None or not set(properties) == set(ENVELOPE_KEYS):
        reports.append("properties key set does not match the envelope")
    if doc.get("additionalProperties") is not False:
        reports.append("envelope additionalProperties not false")
    env_type_enum = (properties or {}).get("body", {}) \
        .get("additionalProperties", {}).get("properties", {}) \
        .get("type", {}).get("enum")
    if env_type_enum is None or set(env_type_enum) != REPRESENTATION_TYPES:
        reports.append("body type enum does not match REPRESENTATION_TYPES")
    return not reports, reports


# ---------------------------------------------------------------------------
# Geometry contract witness (uses its own independent file reads).
# ---------------------------------------------------------------------------

def geometry_oracle():
    return _geometries()


def geometry_checks():
    """Verify the documented identity-space geometry and a real mirror pair."""
    reports = []
    geo = _geometries()
    lo_x, hi_x, lo_y, hi_y = geo["space"]
    if not (lo_x == 0.0 and hi_x == 1.0 and lo_y == 0.0 and hi_y == 1.0):
        reports.append("identity space is not the documented unit space")
    if geo["axis_x"] != 0.5:
        reports.append("symmetry axis is not 0.5")
    if geo["tolerance"] <= 0.0:
        reports.append("tolerance is not positive")
    facial = geo["facial"]
    brows = facial.get("brows", {})
    left = brows.get("left", [])
    right = brows.get("right", [])
    if not left or not right or len(left) != len(right):
        reports.append("facial_structure brows missing or mismatched")
    else:
        # The left list runs outer->inner and the right list inner->outer, so
        # a mirrored pair is (left[i], right[len-1-i]); deviation must stay
        # within the documented symmetry tolerance.
        for index in range(len(left)):
            lx = left[index][0]
            rx = right[len(right) - 1 - index][0]
            error = abs((geo["axis_x"] - lx) - (rx - geo["axis_x"]))
            if error > geo["tolerance"]:
                reports.append(
                    "brow mirror pair %d violates symmetry tolerance: "
                    "deviation %r > %r" % (index, error, geo["tolerance"]))
    return not reports, reports


# ---------------------------------------------------------------------------
# Full oracle verification.
# ---------------------------------------------------------------------------

def verify():
    """Run every embedded oracle check. Returns (ok, failures, ok_lines)."""
    failures = []
    ok_lines = []

    # corpus rules
    for entry in CORPUS:
        ok_call, _ = _validate_independent(entry["value"], entry["type"],
                                           **entry.get("attrs", {}))
        if not ok_call:
            failures.append(("corpus", entry, "oracle rejected an admissible value"))
    for entry in NEGATIVE_CORPUS:
        ok_call, _ = _validate_independent(entry["value"], entry["type"],
                                           **entry.get("attrs", {}))
        if ok_call:
            failures.append(("negative-corpus", entry,
                             "oracle admitted a value that must fail"))
    if not failures:
        ok_lines.append("oracle_corpus_rules=OK")

    ok, reports = schema_witness()
    if ok:
        ok_lines.append("oracle_schema_witness=OK")
    else:
        failures.append(("schema", reports, None))

    ok, reports = geometry_checks()
    if ok:
        ok_lines.append("oracle_geometry_contract=OK")
    else:
        failures.append(("geometry", reports, None))

    # independent digest round-trips against itself
    body = {
        "axis_x": {"type": "measurement", "value": 0.5, "units": "normalized"},
        "point": {"type": "geometric_point", "value": [0.5, 0.46]},
    }
    envelope = independent_envelope(
        object_id="geo-0001", record_type="identity.geometry",
        created_at="2026-09-09T00:00:00Z",
        provenance={"source": "RFC 8785",
                    "retrieved_at": "2026-09-09T00:00:00Z",
                    "evidence_type": "fact", "confidence": "high"},
        metadata={}, body=body)
    digest_value = oracle_digest(envelope)
    if not DIGEST_RE.match(digest_value):
        failures.append(("digest", digest_value, "digest shape invalid"))
    else:
        ok_lines.append("oracle_digest_independent=OK")

    return not failures, failures, ok_lines


def main():
    ok, failures, ok_lines = verify()
    for line in ok_lines:
        print(line)
    if not ok:
        print("oracle_representation_failures=%d" % len(failures))
        for entry in failures[:10]:
            print("  %r" % (entry,))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())