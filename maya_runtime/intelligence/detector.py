"""Deterministic representation detector (MAYA Batch #4).

Answers the pre-interpretation question: *"What kind of information am I
looking at?"* — strictly at the REPRESENTATION level, before any meaning is
assigned. It never guesses semantics from arbitrary content when the
information is insufficient.

Verdict vocabulary (Part 3):

- KNOWN:    exactly one supported representation contract is matched by the
            input's declared evidence and structural rules.
- AMBIGUOUS: more than one supported interpretation remains possible.
- UNKNOWN:  the input is structurally valid but no supported representation
            contract applies.
- INVALID:  malformed, corrupted, unsafe, impossible, out-of-range, or
            contract-violating.

Never converted: UNKNOWN -> 0, UNKNOWN -> false, AMBIGUOUS -> first match,
INVALID -> fallback meaning. A bare ``42`` stays AMBIGUOUS (rank, code,
coordinate, scalar, measured value... all remain possible; none is committed
without declaration). ``0.7`` stays AMBIGUOUS (probability/confidence/
uncertainty/scalar). Only declared evidence commits a type.

Every verdict exposes structured type evidence: candidate types, matched
contracts, required fields, rejected candidates with reasons, ambiguity
reason, validation reason. No fake confidence values are ever produced to
rank candidates; a boolean is never enough.

Supported detector-type vocabulary (Part 2's 22 classes, mapped onto the
shared canonical representation vocabulary where such a type exists, plus
detector-only carriers ``temporal`` and ``language`` and the full
``structured_canonical_object`` envelope):

    text, scalar, measurement, vector, matrix, equation, symbol, category,
    relation, event, temporal_interval, temporal, geometric_point,
    geometric_vector, geometric_transform, geometric_object, graph,
    probability, confidence, uncertainty, identifier, language,
    structured_canonical_object

Determinism contract: no randomness, no wall-clock, no clock imports, pure
structural evaluation. Equations/symbolic text are never eval/exec'd.
"""
from __future__ import annotations

import copy
import json
import math
import re

from . import bus
from . import epistemic
from . import representation

MAX_DETECTION_DEPTH = 64
MAX_JSON_TRIAL = 4096

VERDICTS = ("KNOWN", "AMBIGUOUS", "UNKNOWN", "INVALID")

DETECTOR_TYPES = (
    "text", "scalar", "measurement", "vector", "matrix", "equation", "symbol",
    "category", "relation", "event", "temporal_interval", "temporal",
    "geometric_point", "geometric_vector", "geometric_transform",
    "geometric_object", "graph", "probability", "confidence", "uncertainty",
    "identifier", "language", "structured_canonical_object",
)
DETECTOR_TYPE_SET = frozenset(DETECTOR_TYPES)

# Extra detector-only types that have no 1:1 canonical representation type
# (they canonicalize onto the closest shared type).
DETECTOR_ONLY_TYPES = frozenset(
    {"temporal", "language", "structured_canonical_object"})

# Shared canonical representation types reachable through this detector.
CANONICAL_MAPPING = {
    "text": "text",
    "scalar": "scalar",
    "measurement": "measurement",
    "vector": "vector",
    "matrix": "matrix",
    "equation": "equation",
    "symbol": "symbol",
    "category": "category",
    "relation": "relation",
    "event": "event",
    "temporal_interval": "temporal_interval",
    "temporal": "text",
    "geometric_point": "geometric_point",
    "geometric_vector": "geometric_vector",
    "geometric_transform": "geometric_transform",
    "geometric_object": "geometric_object",
    "graph": "graph",
    "probability": "probability",
    "confidence": "confidence",
    "uncertainty": "uncertainty",
    "identifier": "identifier",
    "language": "text",
    "structured_canonical_object": None,
}

# Information-representation domain mapping (Part 14).
TYPE_DOMAIN = {
    "text": "NATURAL_LANGUAGE",
    "scalar": "NUMERICAL",
    "measurement": "NUMERICAL",
    "vector": "VECTOR",
    "matrix": "MATRIX",
    "equation": "EQUATION",
    "symbol": "SYMBOLIC",
    "category": "CATEGORICAL",
    "relation": "GRAPH_RELATIONAL",
    "event": "TEMPORAL",
    "temporal_interval": "TEMPORAL",
    "temporal": "TEMPORAL",
    "geometric_point": "GEOMETRIC",
    "geometric_vector": "GEOMETRIC",
    "geometric_transform": "GEOMETRIC",
    "geometric_object": "GEOMETRIC",
    "graph": "GRAPH_RELATIONAL",
    "probability": "PROBABILISTIC",
    "confidence": "PROBABILISTIC",
    "uncertainty": "PROBABILISTIC",
    "identifier": "STRUCTURED_DATA",
    "language": "NATURAL_LANGUAGE",
    "structured_canonical_object": "STRUCTURED_DATA",
}

# Bounded unit lexicon (documented against BIPM SI base/derived units plus a
# small set of common compound forms). Time units are deliberately EXCLUDED:
# a number + time unit is temporal (duration) evidence, never a measurement.
MEASUREMENT_UNITS_ORDERED = (
    "kg", "g", "mg", "t", "m", "cm", "mm", "km", "um", "nm",
    "N", "Pa", "kPa", "hPa", "J", "kJ", "W", "kW", "Hz", "kHz", "MHz",
    "V", "kV", "A", "mA", "ohm", "Ohm", "F", "uF", "K", "degC", "degF",
    "mol", "cd", "L", "mL", "dB", "lx",
)
MEASUREMENT_UNITS = frozenset(MEASUREMENT_UNITS_ORDERED)

# Time units: a number + one of these is temporal evidence (duration),
# distinct from a measurement.
DURATION_UNITS = frozenset({"ms", "us", "us", "s", "min", "h", "d"})

# BCP-47 basic well-formedness (lower-level than full RFC 5646 registry
# conformance; the oracle and external validation treat this as a structural
# gateway, never a language-catalog claim).
_LANGTAG_RE = re.compile(
    r"^(?:[A-Za-z]{2,3}(?:-[A-Za-z]{3}){0,3}|[A-Za-z]{4}|[A-Za-z]{5,8})"
    r"(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?"
    r"(?:-(?:[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}))*$")

_NUM_TOKEN_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
_MEASURE_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*"
    r"([A-Za-z][A-Za-z0-9_]*)$")
_DURATION_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*"
    r"(ms|us|µs|s|min|h|d)$")

_DATE_TIME_ISH_RE = re.compile(
    r"^\s*(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}:[0-9]{2}(?::[0-9]{2})?"
    r"(?:\.[0-9]+)?)[TtZz ]?")
_TRUNC_JSON_RE = re.compile(r"^\s*[\{\[]\s*[\"0-9\{\[]")


def _significative_digits(text):
    return len(re.sub(r"[^0-9]", "", text))


def numeric_token(text):
    """Parse a numeric text token into (value, is_float) or None. Pure."""
    if not isinstance(text, str):
        return None
    token = text.strip()
    if not _NUM_TOKEN_RE.match(token):
        return None
    if "." in token or "e" in token or "E" in token:
        return float(token), True
    return int(token), False


def parse_measurement_text(text):
    """Parse ``<number> <measurement-unit>`` text into (value, is_float,
    unit) or None. Pure and bounded to the declared unit lexicon."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    m = _MEASURE_RE.match(stripped)
    if not m or m.group(1) not in MEASUREMENT_UNITS:
        return None
    parsed = numeric_token(text[:m.start(1)].rstrip())
    if parsed is None:
        return None
    value, is_float = parsed
    return value, is_float, m.group(1)


def bcp47_well_formed(tag):
    if not isinstance(tag, str) or not tag or len(tag) > 128:
        return False
    return bool(_LANGTAG_RE.match(tag))


def _reject_type(name, reason):
    return {"type": name, "reason": reason}


# ---------------------------------------------------------------------------
# result builder
# ---------------------------------------------------------------------------

def _result(status, detected_type, canonical_candidate, accepted, rejected,
            required_fields, ambiguity_reason, validation_reason,
            candidate_types, declared_type, domain):
    return {
        "status": status,
        "detected_type": detected_type,
        "canonical_candidate": canonical_candidate,
        "evidence": {
            "candidate_types": sorted(set(candidate_types)),
            "accepted": accepted,
            "rejected": sorted(rejected, key=lambda item: item["type"]),
            "required_fields": sorted(set(required_fields)),
            "ambiguity_reason": ambiguity_reason,
            "validation_reason": validation_reason,
            "declared_type": declared_type,
            "domain": domain,
        },
    }


def _invalid(reason, detected_type=None, rejected=None, required=None,
             declared_type=None):
    return _result("INVALID", detected_type, None, [],
                   rejected or [], required or [], None, reason, [],
                   declared_type, None)


def _known(detected_type, canonical_candidate, accepted, rejected,
           required_fields=None, declared_type=None, domain=None):
    return _result("KNOWN", detected_type, canonical_candidate,
                   accepted, rejected, required_fields or [], None, None,
                   [detected_type], declared_type, domain or
                   TYPE_DOMAIN.get(detected_type))


def _ambiguous(candidate_types, accepted, rejected, ambiguity_reason,
               required_fields=None, declared_type=None, domain=None):
    return _result("AMBIGUOUS", None, None, accepted, rejected,
                   required_fields or [], ambiguity_reason, None,
                   candidate_types, declared_type, domain)


def _unknown(reason, rejected=None, candidate_types=None):
    return _result("UNKNOWN", None, None, [], rejected or [], [],
                   None, None, candidate_types or [], None, None)


# ---------------------------------------------------------------------------
# tree guards
# ---------------------------------------------------------------------------

def _bounded_scan(value, depth=0):
    """Return True if the tree contains a non-finite float (corrupted)."""
    if depth > MAX_DETECTION_DEPTH:
        return True
    if isinstance(value, float) and not math.isfinite(value):
        return True
    if isinstance(value, (list, tuple)):
        for item in value:
            if _bounded_scan(item, depth + 1):
                return True
        return False
    if isinstance(value, dict):
        for item in value.values():
            if _bounded_scan(item, depth + 1):
                return True
        return False
    return False


def _json_shape(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_json_shape(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_shape(v)
                   for k, v in value.items())
    return False


# ---------------------------------------------------------------------------
# numeric candidates
# ---------------------------------------------------------------------------

def _numeric_analysis(value):
    rejected = []
    if not math.isfinite(value):
        return _invalid("non-finite number %r is representable in no "
                        "supported type" % (value,))
    candidate_types = []
    if 0.0 <= float(value) <= 1.0:
        for name in ("probability", "confidence", "uncertainty"):
            candidate_types.append(name)
            rejected.append(_reject_type(
                name, "bare [0,1] number admits probability/confidence/"
                      "uncertainty/scalar; none is committed without a "
                      "declaration"))
    else:
        for name in ("probability", "confidence", "uncertainty"):
            rejected.append(_reject_type(
                name, "value %s outside declared domain [0, 1]" % (value,)))
    candidate_types.append("scalar")
    candidate_types.append("measurement")
    rejected.append(_reject_type(
        "scalar", "a bare number is structurally admissible as scalar but is "
                  "never committed to scalar semantics (rank/code/coordinate/"
                  "feature all remain possible) without a declaration"))
    rejected.append(_reject_type(
        "measurement", "a bare number is not a measurement (measurement "
                       "requires declared units)"))
    rejected.append(_reject_type("identifier",
                                 "identifier requires a string"))
    rejected.append(_reject_type("category",
                                 "a bare number is never a categorical code"))
    rejected.append(_reject_type("text", "text requires a string"))
    rejected += [_reject_type(name, "requires a sequence/structured shape")
                 for name in ("vector", "matrix", "relation", "event",
                              "temporal_interval", "geometric_point",
                              "geometric_vector", "geometric_transform",
                              "geometric_object", "graph")]
    rejected += [_reject_type("equation",
                              "requires declared language and opaque text")
                 for _ in ()]
    rejected.append(_reject_type("symbol", "symbol requires an identifier"))
    rejected.append(_reject_type("language",
                                 "requires a declared language metadata "
                                 "object with language_tag"))
    rejected.append(_reject_type("equation",
                                 "requires declared language and opaque "
                                 "text"))
    rejected.append(_reject_type("temporal",
                                 "requires a timestamp-shaped string or "
                                 "declared temporal member"))
    rejected.append(_reject_type("structured_canonical_object",
                                 "requires a unified-state envelope"))
    return _ambiguous(
        candidate_types, [], rejected,
        "a bare number carries no declaring evidence; supported numeric "
        "contracts are all admissible and rank/code/coordinate remain "
        "possible semantic roles — none is committed")


# ---------------------------------------------------------------------------
# string analysis
# ---------------------------------------------------------------------------

def _string_analysis(text, _depth):
    stripped = text.strip()
    if not stripped:
        return _unknown("the empty string applies to no supported "
                        "representation contract")
    # Malformed structured JSON (truncated/constructed fragments).
    if stripped[0] in ("{", "["):
        if len(text) > MAX_JSON_TRIAL:
            return _invalid("structured input exceeds the %d-char detection "
                            "trial boundary" % MAX_JSON_TRIAL)
        try:
            parsed = json.loads(text)
        except (ValueError, RecursionError):
            if _TRUNC_JSON_RE.match(text):
                return _invalid(
                    "malformed structured input: JSON container is "
                    "unterminated or corrupted", required=["{}", "[]"])
            return _text_parse(text, _depth)
        return detect(parsed, _depth=_depth + 1)
    # ISO-8601 / RFC 3339 full timestamp shape.
    if representation.ISO_UTC_RE.match(stripped):
        try:
            representation.validate_iso8601_utc(stripped)
        except representation.RepresentationError as exc:
            return _invalid("malformed timestamp: %s" % (exc,))
        return _ambiguous(
            ["temporal"],
            [],
            [_reject_type("temporal",
                          "timestamp shape detected; the temporal semantic "
                          "(event_time/publication_time/retrieval_time/"
                          "processing_time) is undeclared and must not be "
                          "inferred"),
             _reject_type(
                 "text",
                 "the full string is consumed by the timestamp pattern, so "
                 "free-text classification does not apply")],
            "a valid timestamp string carries no declared temporal semantic; "
            "event time is never inferred from an undeclared timestamp",
            required_fields=["event_time", "publication_time",
                             "retrieval_time", "processing_time"])
    # Looks like a date/time but fails validation -> malformed timestamp.
    if _DATE_TIME_ISH_RE.match(stripped):
        return _invalid("malformed timestamp %r: does not validate as "
                        "ISO-8601/RFC 3339 UTC" % (text,),
                        required=["YYYY-MM-DDTHH:MM:SS(.fff)Z|±HH:MM"])
    # number + duration unit -> temporal shape (duration), uncommitted.
    m = _DURATION_RE.match(stripped)
    if m and m.group(1) in DURATION_UNITS:
        return _ambiguous(
            ["temporal"],
            [],
            [_reject_type("temporal",
                          "duration shape detected; no supported instant or "
                          "interval contract is committed without a declarati"
                          "on — the bus temporal contract stores instants"),
             _reject_type("measurement",
                          "time units are duration evidence, never a "
                          "generic measurement")],
            "a duration value carries duration semantics but no instant/"
            "interval contract; commit a start/end interval or declared "
            "temporal member")
    # number + measurement unit -> measurement KNOWN.
    parsed_measurement = parse_measurement_text(text)
    if parsed_measurement is not None:
        value, is_float, unit = parsed_measurement
        accepted = [_reject_type("measurement",
                                 "declared unit %r + numeric value" % unit)]
        rejected = [_reject_type("text",
                                 "the full string is consumed by the "
                                 "number+unit pattern"),
                    _reject_type("temporal",
                                 "measurement units are not temporal units")]
        canonical = {"type": "measurement", "value": value, "units": unit}
        return _result("KNOWN", "measurement", canonical, accepted, rejected,
                       ["number", "unit"], None, None, ["measurement"], None,
                       "NUMERICAL")
    # pure numeric token.
    if _NUM_TOKEN_RE.match(stripped):
        parsed = numeric_token(text)
        if parsed is None:
            return _invalid("numeric token %r did not parse" % (text,))
        value, _ = parsed
        return _numeric_analysis(value)
    return _text_parse(text, _depth)


def _text_parse(text, _depth):
    try:
        representation.validate_text(text)
    except representation.RepresentationError as exc:
        return _invalid("not valid text: %s" % (exc,), required=["text"])
    # Single identifier-shaped token: several string contracts admit it.
    if representation.IDENTIFIER_RE.match(text):
        rejected = [
            _reject_type("category", "category requires a declared code_set"),
            _reject_type("language",
                         "a bare token is not language metadata; declare a "
                         "language_tag object"),
            _reject_type("equation",
                         "requires declared language and opaque text"),
        ]
        return _ambiguous(
            ["identifier", "text", "symbol"],
            [],
            rejected,
            "an identifier-shaped token is admitted by identifier, text and "
            "symbol contracts; none is committed without declaration")
    accepted = [_reject_type("text", "free text (only text admits a string "
                                        "that is not identifier-shaped and "
                                        "not a structured pattern)")]
    return _known("text", {"type": "text", "value": text}, accepted, [],
                  required_fields=["text"], domain="NATURAL_LANGUAGE")


# ---------------------------------------------------------------------------
# sequence analysis
# ---------------------------------------------------------------------------

def _sequence_analysis(value):
    if not value:
        return _unknown("an empty sequence applies to no supported "
                        "representation contract (vector requires a declared "
                        "dimension)")
    numeric = all(isinstance(item, (int, float))
                  and not isinstance(item, bool)
                  and math.isfinite(item) for item in value)
    if numeric:
        rejected = [_reject_type("vector",
                                 "vector requires a declared dimension"),
                    _reject_type("geometric_vector",
                                 "geometric vector requires a declared "
                                 "dimension"),
                    _reject_type("matrix",
                                 "matrix requires a declared rows/cols "
                                 "shape"),
                    _reject_type("geometric_point",
                                 "point-ness is not committed; coordinates "
                                 "are not semantic features and a bare "
                                 "sequence does not declare them")]
        return _ambiguous(
            ["vector", "geometric_vector", "geometric_point"],
            [], rejected,
            "a number sequence is admitted by vector, geometric_vector and "
            "(for 2-3 components) geometric_point contracts; the semantic "
            "distinctions (coordinate vs identifier vs feature) are "
            "undeclared")
    rectangular = (all(isinstance(row, (list, tuple)) and row
                       and all(isinstance(item, (int, float))
                               and not isinstance(item, bool)
                               and math.isfinite(item) for item in row)
                       for row in value)
                   and len({len(row) for row in value}) == 1)
    if rectangular:
        rejected = [_reject_type("matrix",
                                 "matrix requires declared rows/cols"),
                    _reject_type("geometric_object",
                                 "requires a geometry_kind/data member "
                                 "(surface rows are not committed)")]
        return _ambiguous(
            ["matrix"],
            [], rejected,
            "a rectangular number array is matrix-shaped but rows/cols and "
            "semantic contract are undeclared")
    return _unknown("mixed/heterogeneous sequence applies to no supported "
                    "representation contract", rejected=[
                        _reject_type("vector", "non-numeric components"),
                        _reject_type("matrix", "non-uniform row shapes")])


# ---------------------------------------------------------------------------
# envelope / structured dict checks
# ---------------------------------------------------------------------------

def _envelope_analysis(candidate):
    try:
        bus.validate(candidate)
    except bus.BusError as exc:
        return _invalid("malformed or corrupted canonical object: %s"
                        % (exc,), detected_type="structured_canonical_object",
                        required=list(bus.ENVELOPE_KEYS))
    accepted = [_reject_type(
        "structured_canonical_object",
        "envelope protocol %s with all %d contract members; digest "
        "recomputed and verified"
        % (candidate.get("protocol"), len(bus.ENVELOPE_KEYS)))]
    return _known("structured_canonical_object",
                  copy.deepcopy(candidate), accepted, [],
                  required_fields=list(bus.ENVELOPE_KEYS))


def _dict_analysis(candidate, _depth):
    declared_type = candidate.get("type")
    if isinstance(declared_type, str):
        if declared_type not in DETECTOR_TYPE_SET and \
                declared_type not in representation.REPRESENTATION_TYPES:
            return _invalid(
                "declared type %r is outside the supported representation "
                "vocabulary; unknown declared types are contract-violating"
                % (declared_type,),
                required=["supported type"])
        attrs = {k: v for k, v in candidate.items()
                 if k not in ("type", "value")}
        return _detect_declared(candidate.get("value"), declared_type, attrs,
                                _depth)

    keys = set(candidate)
    # ---- structured canonical object (bus envelope) ---------------------
    if candidate.get("protocol") == bus.PROTOCOL or \
            candidate.get("schema") == bus.SCHEMA_ID:
        return _envelope_analysis(candidate)

    # ---- language metadata (Part 6) -------------------------------------
    tag = candidate.get("language_tag")
    if isinstance(tag, str) and tag:
        if not bcp47_well_formed(tag):
            return _invalid("malformed BCP-47 language tag %r" % (tag,),
                            required=["bcp-47 well-formed tag"])
        script = candidate.get("script")
        encoding = candidate.get("encoding")
        canonical = {"type": "text", "value": tag}
        if isinstance(script, str) and script:
            canonical["script"] = script
        if isinstance(encoding, str) and encoding:
            canonical["encoding"] = encoding
        canonical["language_tag"] = tag
        accepted = [_reject_type(
            "language",
            "declared BCP-47 well-formed language tag %r" % tag)]
        return _known("language", canonical, accepted, [],
                      required_fields=["language_tag"],
                      domain="NATURAL_LANGUAGE")

    # ---- temporal interval ----------------------------------------------
    if "start" in keys and "end" in keys:
        try:
            representation.validate_temporal_interval(candidate)
        except representation.RepresentationError as exc:
            return _invalid("malformed temporal interval: %s" % (exc,),
                            required=["start", "end"])
        accepted = [_reject_type(
            "temporal_interval", "start/end ISO-8601 UTC instants with "
                                 "end >= start")]
        return _known("temporal_interval",
                      {"type": "temporal_interval",
                       "value": {"start": candidate["start"],
                                 "end": candidate["end"]}},
                      accepted, [], required_fields=["start", "end"],
                      domain="TEMPORAL")

    # ---- event ----------------------------------------------------------
    if "kind" in keys and "at" in keys:
        if not candidate.get("at") or not isinstance(candidate["at"], str):
            return _invalid("event without a valid event time (at): event "
                            "time is required and never inferred",
                            required=["kind", "at"])
        event_types = candidate.get("event_types")
        if not isinstance(event_types, (list, tuple)) or not event_types:
            return _ambiguous(
                ["event"],
                [],
                [_reject_type("event",
                              "event shape detected but the event_types code "
                              "set is undeclared; the event kind cannot be "
                              "validated")],
                "event-shaped dict {kind, at} but no declared event_types "
                "universe")
        try:
            representation.validate_event(candidate,
                                          event_types=event_types)
        except representation.RepresentationError as exc:
            return _invalid("malformed event: %s" % (exc,),
                            required=["kind", "at", "event_types"])
        accepted = [_reject_type("event", "kind/at with declared event_types")]
        return _known("event",
                      {"type": "event", "value": {"kind": candidate["kind"],
                                                 "at": candidate["at"]},
                       "event_types": list(event_types)},
                      accepted, [], required_fields=["kind", "at"],
                      domain="TEMPORAL")

    # ---- relation --------------------------------------------------------
    if {"source_id", "target_id", "predicate"} <= keys:
        predicates = candidate.get("predicates")
        if not isinstance(predicates, (list, tuple)) or not predicates:
            return _ambiguous(
                ["relation"],
                [],
                [_reject_type("relation",
                              "relation shape detected but the predicate "
                              "universe is undeclared")],
                "relation-shaped dict {source_id, target_id, predicate} "
                "without a declared predicate universe; the predicate cannot "
                "be validated")
        try:
            representation.validate_relation(candidate, predicates=predicates)
        except representation.RepresentationError as exc:
            return _invalid("malformed or contradictory relation: %s"
                            % (exc,), required=["source_id", "target_id",
                                                "predicate", "predicates"])
        accepted = [_reject_type("relation", "source/target/predicate within "
                                             "the declared universe")]
        return _known("relation",
                      {"type": "relation",
                       "value": {"source_id": candidate["source_id"],
                                 "target_id": candidate["target_id"],
                                 "predicate": candidate["predicate"]},
                       "predicates": list(predicates)},
                      accepted, [], required_fields=["source_id", "target_id",
                                                     "predicate"],
                      domain="GRAPH_RELATIONAL")

    # ---- geometric_transform --------------------------------------------
    if "kind" in keys and "parameters" in keys:
        if candidate["kind"] not in representation.TRANSFORM_KINDS:
            return _invalid(
                "transform kind %r not in %s" % (candidate["kind"],
                                                 (representation.
                                                  TRANSFORM_KINDS,)),
                required=["kind", "parameters"])
        try:
            representation.validate_geometric_transform(candidate)
        except representation.RepresentationError as exc:
            return _invalid("malformed geometric transform: %s" % (exc,),
                            required=["kind", "parameters"])
        accepted = [_reject_type("geometric_transform",
                                 "declared kind %r with validated parameters"
                                 % candidate["kind"])]
        return _known("geometric_transform",
                      {"type": "geometric_transform", "value": candidate},
                      accepted, [], required_fields=["kind", "parameters"],
                      domain="GEOMETRIC")

    # ---- geometric_object -----------------------------------------------
    if "geometry_kind" in keys and "data" in keys:
        if candidate["geometry_kind"] not in representation.GEOMETRIC_KINDS:
            return _invalid("geometry_kind %r not in %s"
                            % (candidate["geometry_kind"],
                               (representation.GEOMETRIC_KINDS,)),
                            required=["geometry_kind", "data"])
        space = candidate.get("space")
        try:
            representation.validate_geometric_object(
                candidate,
                space=tuple(space) if space is not None else None,
                geometry_kind=candidate["geometry_kind"])
        except representation.RepresentationError as exc:
            return _invalid("malformed or out-of-space geometric object: %s"
                            % (exc,), required=["geometry_kind", "data"])
        attrs = {}
        if space is not None:
            attrs["space"] = list(space)
        canonical = dict(attrs)
        canonical.update({"type": "geometric_object", "value": candidate})
        accepted = [_reject_type("geometric_object",
                                 "declared geometry_kind %r with validated "
                                 "data%s" % (candidate["geometry_kind"],
                                             " in declared space" if
                                             space is not None else ""))]
        return _known("geometric_object", canonical, accepted, [],
                      required_fields=["geometry_kind", "data"],
                      domain="GEOMETRIC")

    # ---- graph -----------------------------------------------------------
    if "nodes" in keys and "edges" in keys:
        try:
            representation.validate_graph(candidate)
        except representation.RepresentationError as exc:
            return _invalid("malformed graph: %s" % (exc,),
                            required=["nodes", "edges"])
        accepted = [_reject_type("graph", "unique validated nodes and "
                                          "self-loop-free edges")]
        return _known("graph",
                      {"type": "graph",
                       "value": {"nodes": list(candidate["nodes"]),
                                 "edges": [list(e)
                                           for e in candidate["edges"]]}},
                      accepted, [], required_fields=["nodes", "edges"],
                      domain="GRAPH_RELATIONAL")

    # ---- measurement dict {value, units} --------------------------------
    if "value" in keys and "units" in keys and \
            isinstance(candidate["value"], (int, float)) \
            and not isinstance(candidate["value"], bool) \
            and isinstance(candidate["units"], str) and candidate["units"]:
        try:
            representation.validate_measurement(candidate["value"],
                                                units=candidate["units"])
        except representation.RepresentationError as exc:
            return _invalid("malformed measurement dict: %s" % (exc,),
                            required=["value", "units"])
        accepted = [_reject_type("measurement", "numeric value + declared "
                                                "units %r"
                                 % candidate["units"])]
        return _known("measurement",
                      {"type": "measurement", "value": candidate["value"],
                       "units": candidate["units"]},
                      accepted, [], required_fields=["value", "units"],
                      domain="NUMERICAL")

    # ---- numeric-looking value dict without units -----------------------
    if "value" in keys and isinstance(candidate["value"], (int, float)) \
            and not isinstance(candidate["value"], bool):
        return _numeric_analysis(candidate["value"])

    # ---- nothing recognizable -------------------------------------------
    return _unknown("the dict carries no declared type member and no "
                    "supported structural signature (protocol, language_tag, "
                    "start/end, kind/at, source_id/target_id/predicate, "
                    "kind/parameters, geometry_kind/data, nodes/edges, "
                    "value+units)",
                    rejected=[_reject_type(
                        "structured_canonical_object",
                        "no unified-state protocol/schema declared")])


# ---------------------------------------------------------------------------
# declared path
# ---------------------------------------------------------------------------

def _detect_declared(value, type_name, attrs, _depth):
    if type_name in DETECTOR_ONLY_TYPES:
        if type_name == "structured_canonical_object":
            if not isinstance(value, dict):
                return _invalid("structured_canonical_object value must be "
                                "the unified-state envelope dict")
            return _envelope_analysis(value)
        if type_name == "temporal":
            if isinstance(value, str) and representation.ISO_UTC_RE.match(
                    value.strip()):
                field = attrs.get("field")
                canonical = {"type": "text", "value": value}
                if field:
                    canonical["temporal_field"] = field
                accepted = [_reject_type("temporal", "declared timestamp")]
                return _known("temporal", canonical, accepted, [],
                              required_fields=["value"], domain="TEMPORAL")
            try:
                representation.validate_temporal_interval(value)
            except representation.RepresentationError as exc:
                return _invalid("declared temporal failed: %s" % (exc,),
                                detected_type="temporal")
            accepted = [_reject_type("temporal", "declared interval")]
            return _known("temporal",
                          {"type": "temporal_interval", "value": value},
                          accepted, [], required_fields=["start", "end"],
                          domain="TEMPORAL")
        if type_name == "language":
            tag = attrs.get("language_tag") or value
            if not isinstance(tag, str) or not bcp47_well_formed(tag):
                return _invalid("declared language tag %r is not BCP-47 "
                                "well-formed" % (tag,),
                                detected_type="language")
            canonical = {"type": "text", "value": tag, "language_tag": tag}
            accepted = [_reject_type("language", "declared BCP-47 tag")]
            return _known("language", canonical, accepted, [],
                          required_fields=["language_tag"],
                          domain="NATURAL_LANGUAGE")
    try:
        result = representation.validate(value, type_name, **attrs)
    except representation.RepresentationError as exc:
        _ = attrs
        return _invalid("declared %s failed: %s" % (type_name, exc),
                        detected_type=type_name,
                        required=["%s contract" % type_name])
    canonical = {"type": type_name, "value": result}
    for key, item in attrs.items():
        canonical[key] = copy.deepcopy(item)
    accepted = [_reject_type(type_name, "declared type; contract validated")]
    return _known(type_name, canonical, accepted, [],
                  required_fields=["value"], domain=TYPE_DOMAIN.get(type_name))


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def detect(candidate, declared=None, *, _depth=0):
    """Detect the representation type of ``candidate``.

    ``declared`` may provide an explicit type name (the input then commits to
    it and either matches KNOWN or fails closed INVALID). Returns the verdict
    dict with structured evidence.
    """
    if _depth > MAX_DETECTION_DEPTH:
        return _invalid("detection nesting exceeds %d" % MAX_DETECTION_DEPTH)

    declared_type = declared
    if declared_type is None and isinstance(candidate, dict) \
            and isinstance(candidate.get("type"), str) \
            and (candidate["type"] in DETECTOR_TYPE_SET
                 or candidate["type"] in representation.REPRESENTATION_TYPES):
        declared_type = candidate["type"]
        attrs = {k: v for k, v in candidate.items()
                 if k not in ("type", "value")}
        return _detect_declared(candidate.get("value"), declared_type, attrs,
                                _depth + 1)
    if declared_type is not None:
        if isinstance(declared_type, str) \
                and (declared_type in DETECTOR_TYPE_SET
                     or declared_type in representation.REPRESENTATION_TYPES):
            if isinstance(candidate, dict) and "value" in candidate:
                value = candidate["value"]
                attrs = {k: v for k, v in candidate.items()
                         if k not in ("type", "value")}
                return _detect_declared(value, declared_type, attrs,
                                        _depth + 1)
            return _detect_declared(candidate, declared_type, {}, _depth + 1)
        return _invalid("declared type %r is outside the supported "
                        "representation vocabulary" % (declared_type,),
                        required=["supported type"])

    if isinstance(candidate, (bool, type(None))):
        return _unknown("a bare %s carries no declared representation type "
                        "and applies to no supported contract"
                        % (type(candidate).__name__,))

    if isinstance(candidate, (int, float)):
        return _numeric_analysis(candidate)

    if isinstance(candidate, str):
        return _string_analysis(candidate, _depth + 1)

    if isinstance(candidate, (list, tuple)):
        return _sequence_analysis(candidate)

    if isinstance(candidate, dict):
        if _bounded_scan(candidate):
            return _invalid("corrupted input: non-finite number present in "
                            "the structured object")
        return _dict_analysis(candidate, _depth + 1)

    return _invalid("unsupported Python type %s" % type(candidate).__name__)


def canonical_type(detected_type):
    """Map a detector type to the shared canonical representation type."""
    if detected_type not in CANONICAL_MAPPING:
        raise representation.RepresentationError(
            "unknown detector type %r" % (detected_type,))
    return CANONICAL_MAPPING[detected_type]


def information_domain(candidate, detection=None):
    """Information-representation domain for the input (Part 14), or a
    declared cultural domain (Part 15) — recognized without asserting truth.
    """
    if isinstance(candidate, dict):
        declared_domain = candidate.get("domain")
        if isinstance(declared_domain, str) and declared_domain and \
                declared_domain in epistemic.DOMAIN_VOCABULARY:
            return declared_domain
    detection = detection or detect(candidate)
    if detection["status"] == "KNOWN" and detection["detected_type"]:
        return TYPE_DOMAIN.get(detection["detected_type"])
    return None


__all__ = (
    "VERDICTS", "DETECTOR_TYPES", "DETECTOR_TYPE_SET",
    "CANONICAL_MAPPING", "TYPE_DOMAIN", "MEASUREMENT_UNITS",
    "MEASUREMENT_UNITS_ORDERED", "DURATION_UNITS", "MAX_DETECTION_DEPTH",
    "numeric_token", "bcp47_well_formed", "detect", "canonical_type",
    "information_domain",
)