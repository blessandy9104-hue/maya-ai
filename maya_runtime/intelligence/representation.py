"""Typed canonical representation foundation (MAYA Batch #2).

Every value Maya stores or exchanges is a *representation* of something, not
the thing itself. This module gives each admissible representation an explicit,
introspectable contract: what it is, what it may contain, its domain/range,
units, precision, and whether it is semantic or opaque. It never decides what
a value *means*; it only decides whether a value is a well-formed instance of
a declared representation type.

Fail-closed rules (enforced, never documented-away):

- ``UNKNOWN`` is never serialized as ``0``, ``AMBIGUOUS`` is never coerced to
  ``False``; detection returns a regime label and refuses to select a value.
- ``NaN``/``Infinity`` are invalid in every numeric type.
- An ``identifier`` is never a measurement; a ``category`` code is never a
  scalar; ``probability`` is never ``confidence`` is never ``uncertainty``
  (distinct type names, distinct contracts, no silent reinterpretation).
- Invalid values raise ``RepresentationError``; nothing is silently clamped,
  zeroed, or rounded. (The rendering ``FeatureEncoder`` may clamp for
  presentation; this layer documents representation, it does not bend it.)
- Symbolic/equation input is never ``eval``/``exec``'ed anywhere: it is stored
  as declared opaque text and hostile-looking constructs are rejected.
- Timestamps are supplied by callers as ISO-8601 UTC text and validated purely
  (this package bans ``time``/``datetime`` imports to stay deterministic).

Determinism contract: no randomness, no wall-clock, no hardware dependence.
Identifiers are caller-supplied (generation is nondeterministic and lives
outside the intelligence scope).

Stack discipline: stdlib-only; none of the forbidden imports
(random/time/datetime/tkinter/subprocess/socket) are reachable from here.
"""
from __future__ import annotations

import math
import re

from maya_world_model import ALLOWED_CONFIDENCE, ALLOWED_EVIDENCE_TYPES

REPRESENTATION_TYPES = frozenset({
    "identifier", "text", "scalar", "measurement", "vector", "matrix",
    "symbol", "equation", "category", "relation", "event",
    "temporal_interval", "geometric_point", "geometric_vector",
    "geometric_transform", "geometric_object", "graph", "probability",
    "confidence", "uncertainty", "provenance", "metadata",
})

# Preferred order for reports/logging (stable, not the frozenset).
REPRESENTATION_TYPES_ORDERED = (
    "identifier", "text", "scalar", "measurement", "vector", "matrix",
    "symbol", "equation", "category", "relation", "event",
    "temporal_interval", "geometric_point", "geometric_vector",
    "geometric_transform", "geometric_object", "graph", "probability",
    "confidence", "uncertainty", "provenance", "metadata",
)

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/=-]{0,127}$")
ISO_UTC_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?"
    r"(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$")

MAX_TEXT_LENGTH = 100000
MAX_EQUATION_LENGTH = 4096
MAX_DEPTH_VALUES = 64

# Registry of declared equation languages/encoding schemes. A symbol block with
# an unrecognized scheme is rejected (unknown encoding is never admitted).
EQUATION_LANGUAGES = frozenset({"maya.symbolic.v1"})

# Hostile constructs that are never admissible in symbolic input. This is an
# admission/limitation guard, not an execution boundary: the canonical layer
# never evaluates these strings in any interpreter.
EQUATION_FORBIDDEN_TOKENS = (
    "eval", "exec", "import ", "__", "os.", "subprocess", "socket",
    "builtins", "compile",
)

# Reflexive relations are admissible only for these predicates; any other
# predicate with source == target is a contradiction and is rejected.
REFLEXIVE_COMPATIBLE_PREDICATES = frozenset({
    "equals", "identical_to", "belongs_to", "coexists_with",
})

# Predicates that assert difference/opposition; pairing them with an identical
# subject/object is inherently contradictory.
CONTRADICTION_PREDICATES = frozenset({
    "not_equal", "conflicts_with", "opposes", "contradicts",
})

GEOMETRIC_KINDS = ("point", "curve", "surface", "mesh")
TRANSFORM_KINDS = ("translate", "rotate", "scale", "reflect", "compose")


class RepresentationError(ValueError):
    """Raised when a value is not a well-formed instance of a declared type."""


def _reject(why):
    raise RepresentationError(why)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject("expected a real number, got %s" % type(value).__name__)
    if not math.isfinite(value):
        _reject("non-finite number %r is not representable" % (value,))
    return True


def _numbers(seq):
    for item in seq:
        _number(item)
    return True


def _check_attrs(attrs, names, value):
    for name in names:
        if name not in attrs:
            _reject("%r requires attribute %r" % (type(value).__name__, name))


# ---------------------------------------------------------------------------
# ISO-8601 UTC timestamp validator (pure; no datetime import).
# ---------------------------------------------------------------------------

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def validate_iso8601_utc(text):
    """Validate an RFC 3339 timestamp (``YYYY-MM-DDTHH:MM[:SS][.fff]Z|±HH:MM``).

    Returns the input unchanged on success; raises ``RepresentationError`` on
    any structural or calendar error (including out-of-offset-range).
    """
    if not isinstance(text, str):
        _reject("timestamp must be a string, got %s" % type(text).__name__)
    match = ISO_UTC_RE.match(text.strip())
    if not match:
        _reject("timestamp %r is not ISO-8601/RFC 3339 (W3C form)" % (text,))
    year, month, day, hour, minute = (int(match.group(i)) for i in range(1, 6))
    second = int(match.group(6) or "0")
    offset = match.group(8)
    if not (1 <= month <= 12):
        _reject("month %d out of range" % month)
    max_day = _MONTH_DAYS[month - 1]
    if month == 2 and _leap(year):
        max_day = 29
    if not (1 <= day <= max_day):
        _reject("day %d out of range for month %d" % (day, month))
    if hour > 23:
        _reject("hour %d out of range" % hour)
    if minute > 59:
        _reject("minute %d out of range" % minute)
    if second > 60:
        _reject("second %d out of range" % second)
    if offset != "Z":
        sign, oh, om = offset[0], int(offset[1:3]), int(offset[4:6])
        if oh > 23 or om > 59 or (oh == 23 and om != 0):
            _reject("offset %r out of ISO-8601 range" % (offset,))
    return text


# ---------------------------------------------------------------------------
# Per-type validators (fail closed; raise RepresentationError).
# ---------------------------------------------------------------------------

def validate_identifier(value, **attrs):
    if not isinstance(value, str):
        _reject("identifier must be a string, got %s" % type(value).__name__)
    if not IDENTIFIER_RE.match(value):
        _reject("identifier %r violates the identifier pattern" % (value,))
    if value.endswith("__") and value.startswith("__"):
        _reject("dunder identifier %r is not permitted" % (value,))
    return value


def validate_text(value, **attrs):
    if not isinstance(value, str):
        _reject("text must be a string, got %s" % type(value).__name__)
    if len(value) > MAX_TEXT_LENGTH:
        _reject("text length %d exceeds %d" % (len(value), MAX_TEXT_LENGTH))
    for ch in value:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            _reject("lone surrogate U+%04X is not valid text" % code)
        if code < 0x20 and code not in (0x09, 0x0A, 0x0D):
            _reject("control character U+%04X is not valid text" % code)
    return value


def validate_scalar(value, domain=None, precision=None, **attrs):
    _number(value)
    if domain is not None:
        lo, hi = domain
        if not (lo <= value <= hi):
            _reject("scalar %r outside declared domain %s" % (value, domain))
    if precision is not None and (not isinstance(precision, int)
                                  or precision < 1):
        _reject("precision must be a positive integer")
    return value


def validate_measurement(value, units=None, domain=None, precision=None, **attrs):
    _number(value)
    if not units or not isinstance(units, str) or not units.strip():
        _reject("measurement requires declared units; a bare number is not "
                "a measurement (categorical codes carry no units)")
    if domain is not None:
        lo, hi = domain
        if not (lo <= value <= hi):
            _reject("measurement %r outside declared domain %s" % (value, domain))
    if precision is not None and (not isinstance(precision, int)
                                  or precision < 1):
        _reject("precision must be a positive integer")
    return value


def validate_vector(value, dim=None, **attrs):
    if dim is None or (not isinstance(dim, int)) or dim < 1:
        _reject("vector requires declared integer dim >= 1")
    if not isinstance(value, (list, tuple)):
        _reject("vector must be a sequence of numbers, got %s"
                % type(value).__name__)
    if len(value) != dim:
        _reject("vector has %d components; declared dim %d" % (len(value), dim))
    _numbers(value)
    return value


def validate_matrix(value, rows=None, cols=None, **attrs):
    if rows is None or cols is None:
        _reject("matrix requires declared rows and cols")
    if not isinstance(value, (list, tuple)) or len(value) != rows:
        _reject("matrix must be a row sequence of declared height %d" % rows)
    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) != cols:
            _reject("matrix row must be a sequence of declared width %d" % cols)
        _numbers(row)
    return value


def validate_symbol(value, **attrs):
    return validate_identifier(value)


def validate_equation(value, language=None, **attrs):
    if not isinstance(value, str):
        _reject("equation must be declared opaque text, got %s"
                % type(value).__name__)
    if not language or not isinstance(language, str) or not language.strip():
        _reject("equation requires a declared language (e.g. maya.symbolic.v1)")
    if language not in EQUATION_LANGUAGES:
        _reject("equation language/encoding scheme %r is unknown; valid "
                "schemes: %s" % (language, sorted(EQUATION_LANGUAGES)))
    if len(value) > MAX_EQUATION_LENGTH:
        _reject("equation length %d exceeds %d" % (len(value),
                                                   MAX_EQUATION_LENGTH))
    lower = value.lower()
    for token in EQUATION_FORBIDDEN_TOKENS:
        if token in lower:
            _reject("equation contains forbidden construct %r; symbolic input "
                    "is never evaluated" % (token,))
    for ch in value:
        code = ord(ch)
        if code < 0x20 and code not in (0x09, 0x0A, 0x0D):
            _reject("control character U+%04X in equation" % code)
    return value


def validate_category(value, code_set=None, **attrs):
    if not isinstance(value, str):
        _reject("category code must be a string; a bare number is never a "
                "categorical code")
    if code_set is None:
        _reject("category requires a declared closed code_set")
    if not isinstance(code_set, (list, tuple, set, frozenset)):
        _reject("code_set must be a collection")
    if value not in code_set:
        _reject("category code %r is not in the declared code_set" % (value,))
    return value


def validate_relation(value, predicates=None, nodes=None, **attrs):
    if not isinstance(value, dict):
        _reject("relation must be a dict with source_id/target_id/predicate")
    if not set(value) >= {"source_id", "target_id", "predicate"}:
        _reject("relation requires source_id, target_id, predicate")
    validate_identifier(value["source_id"])
    validate_identifier(value["target_id"])
    if not isinstance(value["predicate"], str) or not value["predicate"]:
        _reject("relation predicate must be a non-empty string")
    if predicates is None:
        _reject("relation requires a declared predicate universe")
    if value["predicate"] not in predicates:
        _reject("predicate %r is not in the declared universe" % value["predicate"])
    reflexive = value["source_id"] == value["target_id"]
    if reflexive and value["predicate"] not in REFLEXIVE_COMPATIBLE_PREDICATES:
        _reject("contradictory relation: %r is reflexive but predicate %r "
                "asserts otherwise"
                % (value["source_id"], value["predicate"]))
    if value["predicate"] in CONTRADICTION_PREDICATES and \
            value["source_id"] == value["target_id"]:
        _reject("contradictory relation: identical endpoints with predicate %r"
                % value["predicate"])
    if nodes is not None:
        for endpoint in (value["source_id"], value["target_id"]):
            if endpoint not in nodes:
                _reject("relation references undefined node %r" % endpoint)
    return value


def validate_event(value, event_types=None, **attrs):
    if not isinstance(value, dict):
        _reject("event must be a dict with kind and at")
    if not set(value) >= {"kind", "at"}:
        _reject("event requires kind and at (ISO-8601 UTC)")
    validate_category(value["kind"], code_set=event_types)
    validate_iso8601_utc(value["at"])
    if "payload" in value and value["payload"] is not None:
        _validate_json_tree(value["payload"])
    return value


def validate_temporal_interval(value, **attrs):
    if not isinstance(value, dict):
        _reject("temporal_interval must be a dict with start and end")
    if set(value) < {"start", "end"}:
        _reject("temporal_interval requires start and end (ISO-8601 UTC)")
    start = validate_iso8601_utc(value["start"])
    end = validate_iso8601_utc(value["end"])
    if start > end:
        _reject("temporal_interval end precedes start: %r > %r"
                % (start, end))
    return value


def validate_geometric_point(value, space=None, tolerance=None, **attrs):
    if not isinstance(value, (list, tuple)):
        _reject("geometric_point must be a coordinate sequence")
    if len(value) not in (2, 3):
        _reject("geometric_point must be 2D or 3D")
    _numbers(value)
    if space is not None:
        lo_x, hi_x, lo_y, hi_y = space
        x, y = value[0], value[1]
        if not (lo_x <= x <= hi_x and lo_y <= y <= hi_y):
            _reject("geometric_point %s outside declared space %s"
                    % (tuple(value), (lo_x, hi_x, lo_y, hi_y)))
    if tolerance is not None and (not isinstance(tolerance, (int, float))
                                  or tolerance < 0.0):
        _reject("tolerance must be a non-negative number")
    return value


def validate_geometric_vector(value, dim=None, **attrs):
    return validate_vector(value, dim=dim)


def validate_geometric_transform(value, kind=None, **attrs):
    if not isinstance(value, dict):
        _reject("geometric_transform must be a dict with parameters")
    if kind is None:
        kind = value.get("kind")
    if kind not in TRANSFORM_KINDS:
        _reject("transform kind %r not in %s" % (kind, TRANSFORM_KINDS))
    if "parameters" not in value:
        _reject("geometric_transform requires a parameters member")
    params = value["parameters"]
    if kind == "translate":
        validate_geometric_vector(params.get("delta"), dim=params.get("dim"))
    elif kind == "rotate":
        _number(params.get("theta"))
        validate_geometric_point(params.get("axis_point"))
    elif kind == "scale":
        validate_geometric_vector(params.get("factors"),
                                  dim=params.get("dim"))
    elif kind == "reflect":
        _number(params.get("axis_x"))
    elif kind == "compose":
        steps = params.get("steps")
        if not isinstance(steps, (list, tuple)) or not steps:
            _reject("compose transform requires a non-empty steps sequence")
        for step in steps:
            validate_geometric_transform(step, kind=step.get("kind"))
    return value


def validate_geometric_object(value, space=None, tolerance=None,
                              geometry_kind=None, **attrs):
    if not isinstance(value, dict):
        _reject("geometric_object must be a dict with geometry_kind and data")
    if geometry_kind is None:
        geometry_kind = value.get("geometry_kind")
    if geometry_kind not in GEOMETRIC_KINDS:
        _reject("geometry_kind %r not in %s" % (geometry_kind, GEOMETRIC_KINDS))
    data = value.get("data")
    if geometry_kind == "point":
        validate_geometric_point(data, space=space, tolerance=tolerance)
    elif geometry_kind == "curve":
        if not isinstance(data, (list, tuple)) or not data:
            _reject("curve data must be a non-empty sequence of points")
        for point in data:
            validate_geometric_point(point, space=space, tolerance=tolerance)
    elif geometry_kind == "surface":
        if not isinstance(data, (list, tuple)) or not data:
            _reject("surface data must be a non-empty sequence of curves")
        for curve in data:
            if not isinstance(curve, (list, tuple)) or not curve:
                _reject("surface row must be a sequence of points")
            for point in curve:
                validate_geometric_point(point, space=space,
                                         tolerance=tolerance)
    elif geometry_kind == "mesh":
        if not isinstance(data, dict):
            _reject("mesh data must be a dict with vertices and faces")
        vertices = data.get("vertices", [])
        faces = data.get("faces", [])
        if not isinstance(vertices, (list, tuple)) or not vertices:
            _reject("mesh requires a non-empty vertices sequence")
        count = len(vertices)
        for point in vertices:
            validate_geometric_point(point, space=space, tolerance=tolerance)
        if not isinstance(faces, (list, tuple)):
            _reject("mesh faces must be a sequence of vertex-index sequences")
        for face in faces:
            if not isinstance(face, (list, tuple)) or not face:
                _reject("mesh face must be a non-empty index sequence")
            for index in face:
                if not isinstance(index, int) or isinstance(index, bool) \
                        or not (0 <= index < count):
                    _reject("mesh face index %r out of range for %d vertices"
                            % (index, count))
    else:  # pragma: no cover - guarded above
        _reject("unknown geometry_kind")
    return value


def validate_graph(value, **attrs):
    if not isinstance(value, dict):
        _reject("graph must be a dict with nodes and edges")
    if set(value) < {"nodes", "edges"}:
        _reject("graph requires nodes and edges")
    nodes = value["nodes"]
    edges = value["edges"]
    if not isinstance(nodes, (list, tuple)):
        _reject("graph nodes must be a sequence of identifiers")
    node_ids = []
    for node in nodes:
        validate_identifier(node)
        node_ids.append(node)
    if len(set(node_ids)) != len(node_ids):
        _reject("graph nodes must be unique")
    if not isinstance(edges, (list, tuple)):
        _reject("graph edges must be a sequence of endpoint pairs")
    seen = set()
    for edge in edges:
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            _reject("graph edge must be a pair of node identifiers")
        a, b = edge
        validate_identifier(a)
        validate_identifier(b)
        if a not in node_ids or b not in node_ids:
            _reject("graph edge references an undefined node")
        if a == b:
            _reject("graph self-loop %r is not admissible" % (a,))
        key = (a, b)
        if key in seen:
            _reject("duplicate graph edge %s" % (key,))
        seen.add(key)
    return value


def validate_probability(value, **attrs):
    _number(value)
    if not (0.0 <= value <= 1.0):
        _reject("probability %r outside [0, 1]" % (value,))
    return value


def validate_confidence(value, **attrs):
    _number(value)
    if not (0.0 <= value <= 1.0):
        _reject("confidence %r outside [0, 1]" % (value,))
    return value


def validate_uncertainty(value, **attrs):
    _number(value)
    if not (0.0 <= value <= 1.0):
        _reject("uncertainty %r outside [0, 1]" % (value,))
    return value


def _forbidden_private_field_present(text):
    combined = text.lower()
    for marker in ("password", "token", "secret", "private_key",
                   "credit_card", "ssn"):
        if marker in combined:
            return True
    return False


def validate_provenance(value, **attrs):
    if not isinstance(value, dict):
        _reject("provenance must be a dict")
    if not set(value) >= {"source", "retrieved_at", "evidence_type",
                          "confidence"}:
        _reject("provenance requires source, retrieved_at, evidence_type, "
                "confidence")
    source = value["source"]
    if not isinstance(source, str) or not source.strip():
        _reject("provenance source must be a non-empty string")
    validate_iso8601_utc(value["retrieved_at"])
    evidence_type = value["evidence_type"]
    if not isinstance(evidence_type, str) or evidence_type not in \
            ALLOWED_EVIDENCE_TYPES:
        _reject("evidence_type %r not in world-model set %s"
                % (evidence_type, sorted(ALLOWED_EVIDENCE_TYPES)))
    confidence = value["confidence"]
    if not isinstance(confidence, str) or confidence not in ALLOWED_CONFIDENCE:
        _reject("provenance confidence %r not in world-model set %s"
                % (confidence, sorted(ALLOWED_CONFIDENCE)))
    source_url = value.get("source_url", "")
    if source_url:
        if not isinstance(source_url, str):
            _reject("source_url must be a string")
        if not (source_url.startswith("https://")
                or source_url.startswith("http://")):
            _reject("source_url %r is not an http(s) URL" % (source_url,))
    if _forbidden_private_field_present("%s %s"
                                        % (source, str(value.get("claim", "")))):
        _reject("provenance carries a forbidden private field marker")
    return value


def _validate_json_tree(value, depth=0):
    if depth > MAX_DEPTH_VALUES:
        _reject("payload nesting exceeds %d" % MAX_DEPTH_VALUES)
    if value is None or isinstance(value, (bool, str)):
        if isinstance(value, str):
            validate_text(value)
        return
    if isinstance(value, (int, float)):
        _number(value)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_tree(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            validate_identifier(key)
            _validate_json_tree(item, depth + 1)
        return
    _reject("payload member of unsupported type %s" % type(value).__name__)


def validate_metadata(value, **attrs):
    if not isinstance(value, dict):
        _reject("metadata must be a dict of identifier keys to JSON-safe "
                "atomic values")
    for key, item in value.items():
        validate_identifier(key)
        if isinstance(item, (list, tuple, dict)):
            _reject("metadata values must be atomic (str/number/bool/null)")
        if isinstance(item, str):
            validate_text(item)
        elif isinstance(item, (int, float)):
            _number(item)
        elif item is None or isinstance(item, bool):
            pass
        else:
            _reject("metadata value of unsupported type %s"
                    % type(item).__name__)
    return value


_VALIDATORS = {
    "identifier": validate_identifier,
    "text": validate_text,
    "scalar": validate_scalar,
    "measurement": validate_measurement,
    "vector": validate_vector,
    "matrix": validate_matrix,
    "symbol": validate_symbol,
    "equation": validate_equation,
    "category": validate_category,
    "relation": validate_relation,
    "event": validate_event,
    "temporal_interval": validate_temporal_interval,
    "geometric_point": validate_geometric_point,
    "geometric_vector": validate_geometric_vector,
    "geometric_transform": validate_geometric_transform,
    "geometric_object": validate_geometric_object,
    "graph": validate_graph,
    "probability": validate_probability,
    "confidence": validate_confidence,
    "uncertainty": validate_uncertainty,
    "provenance": validate_provenance,
    "metadata": validate_metadata,
}

# ---------------------------------------------------------------------------
# Contract table (living, introspectable) mirroring the rig_math
# NUMERIC_CONTRACTS style: representation / allowed values / domain / units /
# precision / semantic-or-opaque / transformable / lossless-or-lossy notes.
# ---------------------------------------------------------------------------
TYPE_CONTRACTS = {
    "identifier": {
        "representation": "opaque string",
        "allowed": "ASCII alnum/dot/colon/slash/dash/equals, 1..128 chars, "
                   "no dunder",
        "domain": "length [1, 128]",
        "units": "none (never a measurement)",
        "precision": None,
        "semantic_or_opaque": "opaque (references an identity, never measures)",
        "transformable": False,
        "lossless": True,
        "notes": "an identifier is never a measurement; generation is "
                 "caller-supplied (deterministic layer)",
    },
    "text": {
        "representation": "Unicode string",
        "allowed": "no lone surrogates, no control chars except \\t \\n \\r",
        "domain": "length <= 100000",
        "units": "none",
        "precision": None,
        "semantic_or_opaque": "opaque bytes until interpreted",
        "transformable": True,
        "lossless": True,
        "notes": "JCS-serializable by construction (no lone surrogates)",
    },
    "scalar": {
        "representation": "IEEE 754 finite number",
        "allowed": "finite reals; NaN/Infinity rejected",
        "domain": "declared per usage (e.g. [0, 1])",
        "units": "none; a scalar with units is a measurement",
        "precision": "declared positive int when relevant",
        "semantic_or_opaque": "numeric atom",
        "transformable": True,
        "lossless": True,
        "notes": "never silently clamped or zeroed here",
    },
    "measurement": {
        "representation": "IEEE 754 finite number + declared units",
        "allowed": "finite reals; units required",
        "domain": "declared per usage",
        "units": "REQUIRED (a bare number is not a measurement)",
        "precision": "declared positive int when relevant",
        "semantic_or_opaque": "numeric + unit context",
        "transformable": True,
        "lossless": False,
        "notes": "misdeclaring a categorical code as a measurement fails "
                 "(the code carries no units)",
    },
    "vector": {
        "representation": "sequence of finite reals",
        "allowed": "finite components; dim required",
        "domain": "component domain declared per usage",
        "units": "per-component when relevant",
        "precision": "declared when relevant",
        "semantic_or_opaque": "numeric aggregate",
        "transformable": True,
        "lossless": True,
        "notes": "",
    },
    "matrix": {
        "representation": "rectangular sequence of sequences of reals",
        "allowed": "finite components; rows/cols required",
        "domain": "per-cell declared when relevant",
        "units": "per-cell when relevant",
        "precision": "declared when relevant",
        "semantic_or_opaque": "numeric aggregate",
        "transformable": True,
        "lossless": True,
        "notes": "",
    },
    "symbol": {
        "representation": "opaque string name",
        "allowed": "identifier pattern",
        "domain": "length [1, 128]",
        "units": "none",
        "precision": None,
        "semantic_or_opaque": "opaque symbol (no evaluation semantics here)",
        "transformable": False,
        "lossless": True,
        "notes": "a symbol names; it does not compute",
    },
    "equation": {
        "representation": "declared opaque text",
        "allowed": "language required; hostile constructs rejected",
        "domain": "length <= 4096",
        "units": "declared by language when relevant",
        "precision": "declared when relevant",
        "semantic_or_opaque": "opaque text (never eval/exec)",
        "transformable": False,
        "lossless": True,
        "notes": "stored as a structured artifact of its declared language, "
                 "with an explicit semantics boundary: nothing here evaluates "
                 "it",
    },
    "category": {
        "representation": "string code from a declared closed set",
        "allowed": "only codes in code_set",
        "domain": "the declared code_set",
        "units": "none (a categorical code is never a scalar)",
        "precision": None,
        "semantic_or_opaque": "opaque label with declared universe",
        "transformable": False,
        "lossless": True,
        "notes": "a bare number is never a category code",
    },
    "relation": {
        "representation": "dict {source_id, target_id, predicate}",
        "allowed": "validated identifiers, declared predicate universe",
        "domain": "predicate universe + optional node set",
        "units": "none",
        "precision": None,
        "semantic_or_opaque": "semantic edge (facts live here)",
        "transformable": False,
        "lossless": True,
        "notes": "contradictory self-references rejected",
    },
    "event": {
        "representation": "dict {kind, at, optional payload}",
        "allowed": "validated category + ISO-8601 UTC + JSON-safe payload",
        "domain": "event_types when declared",
        "units": "none",
        "precision": None,
        "semantic_or_opaque": "semantic (happens-at)",
        "transformable": False,
        "lossless": True,
        "notes": "",
    },
    "temporal_interval": {
        "representation": "dict {start, end} ISO-8601 UTC",
        "allowed": "validated RFC 3339; end >= start",
        "domain": "UTC timeline",
        "units": "none",
        "precision": "declared when relevant",
        "semantic_or_opaque": "semantic (interval)",
        "transformable": False,
        "lossless": True,
        "notes": "lexographic order agrees with chronological for fixed-offset "
                 "UTC forms",
    },
    "geometric_point": {
        "representation": "coordinate sequence (2D or 3D)",
        "allowed": "finite components; in-space when space declared",
        "domain": "declared space bounds when provided",
        "units": "space units (normalized [0,1] for identity geometry)",
        "precision": "declared when relevant",
        "semantic_or_opaque": "semantic (a location, not a feature)",
        "transformable": True,
        "lossless": True,
        "notes": "coordinates are not semantic features",
    },
    "geometric_vector": {
        "representation": "vector with declared dim",
        "allowed": "finite components; dim required",
        "domain": "as declared",
        "units": "space units",
        "precision": "declared when relevant",
        "semantic_or_opaque": "numeric (a displacement)",
        "transformable": True,
        "lossless": True,
        "notes": "",
    },
    "geometric_transform": {
        "representation": "dict {kind, parameters}",
        "allowed": "translate/rotate/scale/reflect/compose",
        "domain": "parameters validated per kind",
        "units": "space units",
        "precision": "declared when relevant",
        "semantic_or_opaque": "numeric (a mapping)",
        "transformable": True,
        "lossless": True,
        "notes": "the math kernel (rig_math) composes the actual algebra; this "
                 "layer only admits well-formed descriptors",
    },
    "geometric_object": {
        "representation": "dict {geometry_kind, data}",
        "allowed": "point/curve/surface/mesh",
        "domain": "space bounds when declared",
        "units": "space units",
        "precision": "declared when relevant",
        "semantic_or_opaque": "semantic geometry reference",
        "transformable": True,
        "lossless": False,
        "notes": "deformations are recorded, never silently accepted",
    },
    "graph": {
        "representation": "dict {nodes, edges}",
        "allowed": "unique validated identifiers; edges pairs, no self-loops",
        "domain": "the node set",
        "units": "none",
        "precision": None,
        "semantic_or_opaque": "structure (topology without meaning)",
        "transformable": False,
        "lossless": True,
        "notes": "",
    },
    "probability": {
        "representation": "IEEE 754 finite number in [0, 1]",
        "allowed": "0.0 <= p <= 1.0, finite",
        "domain": "[0, 1]",
        "units": "none",
        "precision": "declared when relevant",
        "semantic_or_opaque": "semantic (a measure under a stated model)",
        "transformable": False,
        "lossless": True,
        "notes": "never reinterpreted as confidence",
    },
    "confidence": {
        "representation": "IEEE 754 finite number in [0, 1]",
        "allowed": "0.0 <= c <= 1.0, finite",
        "domain": "[0, 1]",
        "units": "none",
        "precision": "declared when relevant",
        "semantic_or_opaque": "semantic (fused support weight, not a "
                              "probability)",
        "transformable": False,
        "lossless": True,
        "notes": "world-model enum confidence (low/medium/high) is a separate "
                 "provenance vocabulary keyed under provenance",
    },
    "uncertainty": {
        "representation": "IEEE 754 finite number in [0, 1]",
        "allowed": "0.0 <= u <= 1.0, finite",
        "domain": "[0, 1]",
        "units": "none",
        "precision": "declared when relevant",
        "semantic_or_opaque": "semantic (indeterminacy, not error-free)",
        "transformable": False,
        "lossless": True,
        "notes": "UNKNOWN is a regime, never a numeric 0",
    },
    "provenance": {
        "representation": "world-model-aligned evidence record",
        "allowed": "world-model ALLOWED_EVIDENCE_TYPES / ALLOWED_CONFIDENCE, "
                   "ISO-8601 UTC retrieved_at, http(s) source_url optional",
        "domain": "shared evidence vocabulary (maya_world_model)",
        "units": "none",
        "precision": None,
        "semantic_or_opaque": "semantic (how and when a claim arrived)",
        "transformable": False,
        "lossless": True,
        "notes": "reuses maya_world_model constants; never stores private "
                 "fields",
    },
    "metadata": {
        "representation": "dict of identifier keys to atomic JSON-safe values",
        "allowed": "identifier keys; str/number/bool/null atomics",
        "domain": "as declared",
        "units": "none",
        "precision": "declared when relevant",
        "semantic_or_opaque": "descriptive (never the measured payload)",
        "transformable": False,
        "lossless": True,
        "notes": "metadata describes; it is not evidence",
    },
}


def contract(type_name):
    """Return the introspectable contract dict for a representation type."""
    if type_name not in TYPE_CONTRACTS:
        _reject("unknown representation type %r" % (type_name,))
    return TYPE_CONTRACTS[type_name]


def known(type_name):
    return type_name in REPRESENTATION_TYPES


def validate(value, type_name, **attrs):
    """Validate ``value`` as an instance of ``type_name``.

    Returns the (normalized-as-validated) value on success; raises
    ``RepresentationError`` on any contract violation. Nothing is clamped,
    zeroed, or reinterpreted.
    """
    if type_name not in _VALIDATORS:
        _reject("unknown representation type %r" % (type_name,))
    return _VALIDATORS[type_name](value, **attrs)


def _regime(candidate, declared=None):
    """Classify a candidate; return (regime, selected_type, reason)."""
    if declared is not None:
        if not isinstance(declared, str):
            return "INVALID", None, "declared type must be a string"
        if not known(declared):
            return "INVALID", None, "unknown declared type %r" % (declared,)
        try:
            validate(candidate, declared)
        except RepresentationError as exc:
            return "INVALID", declared, "declared %s failed: %s" % (declared, exc)
        return "KNOWN", declared, None

    if isinstance(candidate, bool):
        return "UNKNOWN", None, "bare boolean carries no declared type"
    if isinstance(candidate, dict):
        declared_in = candidate.get("type")
        if isinstance(declared_in, str) and known(declared_in):
            try:
                validate(candidate.get("value"), declared_in,
                         **{k: v for k, v in candidate.items()
                            if k not in ("type", "value")})
            except RepresentationError as exc:
                return "INVALID", declared_in, "declared %s failed: %s" % (declared_in, exc)
            return "KNOWN", declared_in, None
        return "AMBIGUOUS", None, "dict without an exactly-known type member"
    if isinstance(candidate, (int, float)):
        if isinstance(candidate, bool):
            return "UNKNOWN", None, "bare boolean carries no declared type"
        if not math.isfinite(candidate):
            return "INVALID", None, "non-finite number is valid for no type"
        if 0.0 <= candidate <= 1.0:
            return ("AMBIGUOUS", None,
                    "probability/confidence/uncertainty/scalar all admit [0,1]")
        return "AMBIGUOUS", None, "scalar/measurement both admit a finite real"
    if isinstance(candidate, str):
        return "AMBIGUOUS", None, "identifier/text/symbol/category all admit strings"
    if isinstance(candidate, (list, tuple)):
        if candidate and all(isinstance(item, (int, float))
                             and not isinstance(item, bool)
                             and math.isfinite(item) for item in candidate):
            return ("AMBIGUOUS", None,
                    "vector/geometric_vector/geometric_point/matrix-row all "
                    "admit number sequences")
        return "UNKNOWN", None, "sequence shape admits no known type"
    return "INVALID", None, "unsupported Python type %s" % type(candidate).__name__


def classify(candidate, declared=None):
    """Representation-detection foundation.

    Returns ``{"regime": <KNOWN|INVALID|AMBIGUOUS|UNKNOWN>,
    "type": <type-or-None>, "reason": <str-or-None>}``. The return is a
    regime label; ``UNKNOWN`` is never the numeric 0 and ``AMBIGUOUS`` is
    never coerced to False. A caller must commit to a declared type to obtain
    a value, and committing wrongly yields INVALID, never reinterpretation.
    """
    regime, selected, reason = _regime(candidate, declared)
    return {
        "regime": regime,
        "type": selected,
        "reason": reason,
        "admitted": regime == "KNOWN",
        "selected": selected if regime == "KNOWN" else None,
        "value": candidate if regime == "KNOWN" else None,
    }