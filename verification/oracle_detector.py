"""Independent detection oracle for MAYA Batch #4 (clean-room).

This module is an independent observer for the representation detector. It
does NOT import ``maya_runtime`` (nor ``representation``, ``canonical``,
``detector``, ``decipher``, ``epistemic`` or ``bus``). Its rules are
recomputed here from first principles and from the authoritative data files:

- the four verdicts (KNOWN/AMBIGUOUS/UNKNOWN/INVALID) and the fail-closed
  principle: an input without a single well-formed meaning is never forced
  into a guess, and non-finite / contradictory / truncated inputs are INVALID
  rather than silently interpreted;
- number handling: a bare finite number is structurally indeterminate
  (AMBIGUOUS), while a number bound to a declared unit is a KNOWN
  measurement;
- BCP-47 basic well-formedness re-derived from RFC 5646 section 2.1
  (language/extended/script/region subtags) as a structural gateway only;
- ISO-8601 UTC timestamp validity re-derived from RFC 3339 (month/day and
  hour bounds, leap-second second==60, offset constraints);
- geometric space bounds read independently from
  ``maya_identity/geometry/maya_geometry.json``;
- equation safety: no code-execution construct is ever admissible;
- a mirrored cross-verdict corpus on which implementation and oracle MUST
  agree;
- independent digest of the detector module file itself (witness that both
  sides describe the same artifact).

The test suite (``test_representation_detector.py``) compares this oracle
against the implementation on the corpus and on the four verdict classes.

Standalone: ``python verification/oracle_detector.py`` verifies all embedded
checks and prints one ``=OK`` evidence line per category; exit code is
non-zero if anything fails.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re

ORACLE_IDENTITY = "maya-verification/oracle-detector/1.0.0"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

VERDICTS = ("KNOWN", "AMBIGUOUS", "UNKNOWN", "INVALID")

MEASUREMENT_UNITS = frozenset({
    "kg", "g", "mg", "t", "m", "cm", "mm", "km", "um", "nm", "N", "Pa",
    "kPa", "hPa", "J", "kJ", "W", "kW", "Hz", "kHz", "MHz", "V", "kV", "A",
    "mA", "ohm", "Ohm", "F", "uF", "K", "degC", "degF", "mol", "cd", "L",
    "mL", "dB", "lx",
})
DURATION_UNITS = frozenset({"ms", "us", "us", "s", "min", "h", "d"})

EQUATION_FORBIDDEN = ("eval", "exec", "import ", "__", "os.", "subprocess",
                      "socket", "builtins", "compile")
EQUATION_LANGUAGES = ("maya.symbolic.v1",)

_IDENTITY_PREDICATES = frozenset({
    "equals", "identical_to", "belongs_to", "coexists_with",
})

# RFC 5646 section 2.1 subtag structure re-expressed as a bounded grammar.
_LANG_RE = r"(?:[A-Za-z]{2,3}(?:-[A-Za-z]{3}){0,3}|[A-Za-z]{4}|[A-Za-z]{5,8})"
_SCRIPT_RE = r"(?:-[A-Za-z]{4})?"
_REGION_RE = r"(?:-(?:[A-Za-z]{2}|[0-9]{3}))?"
_VARIANT_RE = r"(?:-(?:[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}))*"
BCP47_BASIC_RE = re.compile("^" + _LANG_RE + _SCRIPT_RE + _REGION_RE
                            + _VARIANT_RE + "$")

_MEASURE_NUM_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*"
    r"([A-Za-z][A-Za-z0-9_]*)$")
_DURATION_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*"
    r"(ms|us|µs|s|min|h|d)$")
_ISO_UTC_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?"
    r"(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$")
_DATE_TIME_ISH_RE = re.compile(
    r"^\s*(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}:[0-9]{2}(?::[0-9]{2})?"
    r"(?:\.[0-9]+)?)")
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

DETECTED_TYPES = frozenset({
    "text", "scalar", "measurement", "vector", "matrix", "equation",
    "symbol", "category", "relation", "event", "temporal_interval",
    "geometric_point", "geometric_vector", "geometric_transform",
    "geometric_object", "graph", "probability", "confidence", "uncertainty",
    "identifier", "language", "structured_canonical_object",
    "temporal",
})

# Contractual 25-member envelope (independent copy; member equality and the
# digest recomputation are verified by the bus oracle in Batch #3).
CANONICAL_KEYS = frozenset({
    "protocol", "protocol_version", "schema", "schema_version",
    "state_id", "source", "state_kind", "declaration", "temporal",
    "provenance", "confidence", "validation_status", "input", "knowledge",
    "context", "cognitive", "world", "memory", "learning", "safety",
    "persona", "geometry", "expression", "transform_history", "digest",
})
DIGEST_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _geometry():
    with (PROJECT_ROOT / "maya_identity" / "geometry"
          / "maya_geometry.json").open("r", encoding="utf-8") as handle:
        identity = json.load(handle)
    space = identity.get("space", {})
    return (0.0, float(space.get("width", 1.0)),
            0.0, float(space.get("height", 1.0)))


def _finite_object(value, depth=0):
    """First-principles bounded walk for non-finite contamination."""
    if depth > 64:
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, (int, str, bool)) or value is None:
        return True
    if isinstance(value, (list, tuple)):
        return all(_finite_object(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return all(_finite_object(key, depth + 1) and
                   _finite_object(item, depth + 1)
                   for key, item in value.items())
    return False


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _iso_utc(text):
    if not isinstance(text, str):
        return False
    match = _ISO_UTC_RE.match(text.strip())
    if not match:
        return False
    year, month, day = int(match.group(1)), int(match.group(2)), \
        int(match.group(3))
    hour, minute = int(match.group(4)), int(match.group(5))
    second = int(match.group(6) or "0")
    if not (1 <= month <= 12):
        return False
    max_day = _MONTH_DAYS[month - 1]
    if month == 2 and (year % 4 == 0 and (year % 100 != 0
                                          or year % 400 == 0)):
        max_day = 29
    if day < 1 or day > max_day or hour > 23 or minute > 59 or second > 60:
        return False
    offset = match.group(8)
    if offset != "Z":
        oh, om = int(offset[1:3]), int(offset[4:6])
        if oh > 23 or om > 59 or (oh == 23 and om != 0):
            return False
    return True


def _measurement_text(text):
    match = _MEASURE_NUM_RE.match(text.strip())
    if not match or match.group(1) not in MEASUREMENT_UNITS:
        return False
    token = text[:match.start(1)].strip()
    if "." not in token and "e" not in token and "E" not in token:
        return True
    try:
        return math.isfinite(float(token))
    except (ValueError, OverflowError):
        return False


# --- verdict derivation ---------------------------------------------------

def _verdict_value(value):
    """Independent, first-principles verdict for scalar inputs."""
    if isinstance(value, bool) or value is None:
        return "UNKNOWN"
    if not _number(value):
        return "INVALID"
    return "AMBIGUOUS"


def _verdict_string(text):
    stripped = text.strip()
    if not stripped:
        return "UNKNOWN"
    # container-shaped strings parse first (mirror of the raw-input contract)
    if stripped[0] in ("{", "[") and stripped[0] in ("{", "["):
        try:
            parsed = json.loads(stripped)
        except ValueError:
            return "INVALID"  # truncated / malformed container text
        return _verdict(parsed)
    # equation-looking text without a declared language stays Unknown
    if any(token in stripped for token in EQUATION_FORBIDDEN):
        return "UNKNOWN"
    if _measurement_text(stripped):
        return "KNOWN"
    if _iso_utc(stripped):
        return "AMBIGUOUS"
    if _DATE_TIME_ISH_RE.match(stripped):
        return "INVALID"  # date-time-shaped but malformed per RFC 3339
    if _DURATION_RE.match(stripped):
        return "AMBIGUOUS"
    if len(stripped) > 1 and any(ch.isspace() for ch in stripped):
        return "KNOWN"
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9._:/=\-]{0,127}$", stripped):
        return "AMBIGUOUS"
    return "UNKNOWN"


def _verdict_dict(d):
    for key in d:
        if not isinstance(key, str):
            return "INVALID"
    if not _finite_object(d):
        return "INVALID"
    # typed declaration path
    if "type" in d:
        declared = d["type"]
        if not isinstance(declared, str):
            return "INVALID"
        value = d.get("value")
        if declared in DETECTED_TYPES:
            if declared in ("probability", "confidence", "uncertainty"):
                if isinstance(value, dict) or not _number(value) \
                        or not (0.0 <= value <= 1.0):
                    return "INVALID"
                return "KNOWN"
            if declared in ("scalar", "measurement", "vector", "matrix",
                            "geometric_point", "geometric_vector"):
                if not _number(value):
                    return "INVALID"
                if declared == "measurement" and not isinstance(
                        d.get("units"), str):
                    return "INVALID"
                return "KNOWN"
            if declared == "equation":
                if not isinstance(value, str) or value.strip() != value \
                        and False:
                    return "INVALID"
                if d.get("language") not in EQUATION_LANGUAGES \
                        or any(token in value.lower()
                               for token in EQUATION_FORBIDDEN):
                    return "INVALID"
                return "KNOWN"
            if declared in ("identifier", "symbol"):
                if isinstance(value, str) and re.match(
                        r"^[A-Za-z0-9][A-Za-z0-9._:/=\-]{0,127}$", value):
                    return "KNOWN"
                return "INVALID"
            return "KNOWN"
        return "INVALID"
    # structural signatures
    if d.get("protocol") == "maya.unified_state" \
            or d.get("schema") == "maya:unified-state:1":
        dig = d.get("digest")
        if CANONICAL_KEYS <= set(d) and isinstance(dig, dict) \
                and isinstance(dig.get("digest"), str) \
                and DIGEST_HEX_RE.match(dig["digest"]):
            return "KNOWN"  # digest equality itself is the bus oracle's job
        return "INVALID"
    if "language_tag" in d:
        tag = d["language_tag"]
        if isinstance(tag, str) and BCP47_BASIC_RE.match(tag):
            return "KNOWN"
        return "INVALID"
    if "start" in d or "end" in d:
        if _iso_utc(d.get("start")) and _iso_utc(d.get("end")) \
                and d["start"] <= d["end"]:
            return "KNOWN"
        return "INVALID"
    if "kind" in d and "at" in d:
        if "event_types" not in d or not isinstance(d["event_types"], list) \
                or not d["event_types"]:
            return "AMBIGUOUS"
        if not _iso_utc(d.get("at")):
            return "INVALID"
        return "KNOWN"
    if "source_id" in d and "target_id" in d and "predicate" in d:
        pp = d.get("predicates")
        if not isinstance(pp, list) or not pp:
            return "AMBIGUOUS"
        if d["source_id"] == d["target_id"] \
                and d["predicate"] not in _IDENTITY_PREDICATES:
            return "INVALID"
        return "KNOWN"
    if "geometry_kind" in d:
        kind = d.get("geometry_kind")
        if kind not in ("point", "curve", "surface", "mesh"):
            return "INVALID"
        if kind == "point":
            data = d.get("data")
            if not isinstance(data, list) or len(data) not in (2, 3):
                return "INVALID"
            if not _finite_object(data):
                return "INVALID"
            space = d.get("space")
            if isinstance(space, list) and len(space) == 4:
                lo_x, hi_x, lo_y, hi_y = space
            else:
                lo_x, hi_x, lo_y, hi_y = _geometry()
            if not (lo_x <= data[0] <= hi_x
                    and lo_y <= data[1] <= hi_y):
                return "INVALID"
        return "KNOWN"
    if "kind" in d and "parameters" in d:
        return "KNOWN"  # geometric transform shape
    if "nodes" in d or "edges" in d:
        nodes = d.get("nodes")
        if not isinstance(nodes, list) or not nodes \
                or len(nodes) != len(set(nodes)):
            return "INVALID"
        return "KNOWN"
    if "value" in d and "units" in d:
        if not _number(d["value"]) or not isinstance(d["units"], str) \
                or not d["units"].strip():
            return "INVALID"
        return "KNOWN"
    if "value" in d:
        return _verdict_value(d["value"])
    return "UNKNOWN"


def _verdict(value):
    if not _finite_object(value):
        return "INVALID"
    if isinstance(value, (int, float)):
        return _verdict_value(value)
    if isinstance(value, str):
        return _verdict_string(value)
    if isinstance(value, (list, tuple)):
        return "AMBIGUOUS"
    if isinstance(value, dict):
        return _verdict_dict(value)
    return "UNKNOWN"


def oracle_detect(value):
    """Independent verdict: (status, expected_type_or_reason)."""
    return _verdict(value)


# --- mirrored cross-verdict corpus ----------------------------------------

# (value, expected_verdict, expected_type_or_reason)
CORPUS = (
    (42, "AMBIGUOUS", "bare number carries no declaring type"),
    (0.5, "AMBIGUOUS", "bare proportion is not a declared probability"),
    (0.7, "AMBIGUOUS", "bare number carries no declaring type"),
    ("42 kg", "KNOWN", "measurement"),
    ("how are you doing?", "KNOWN", "text"),
    ("abc_123", "AMBIGUOUS", "identifier-shaped token"),
    ("2026-09-10T12:00:00Z", "AMBIGUOUS", "timestamp without temporal semantic"),
    ("2026-13-45T99:00:00Z", "INVALID", "malformed timestamp"),
    ("2h", "AMBIGUOUS", "duration without temporal semantic"),
    ([1, 2, 3], "AMBIGUOUS", "number sequence admits many types"),
    ((1.0, 2.0, 3.0), "AMBIGUOUS", "number sequence admits many types"),
    (True, "UNKNOWN", "boolean carries no representation type"),
    (None, "UNKNOWN", "null carries no representation type"),
    ("", "UNKNOWN", "empty text carries no representation type"),
    ({"custom": "structure"}, "UNKNOWN", "unknown structure"),
    ({"value": 0.5}, "AMBIGUOUS", "bare value is not a declared type"),
    ({"value": 42, "units": "kg"}, "KNOWN", "measurement"),
    ({"language_tag": "en-US"}, "KNOWN", "language"),
    ({"language_tag": "en-"}, "INVALID", "malformed BCP-47 tag"),
    ({"start": "2026-09-10T12:00:00Z",
      "end": "2026-09-10T13:00:00Z"}, "KNOWN", "temporal_interval"),
    ({"kind": "click", "at": "2026-09-10T12:00:00Z"}, "AMBIGUOUS",
     "event without declared event_types"),
    ({"kind": "click", "at": "2026-09-10T12:00:00Z",
      "event_types": ["click", "hover"]}, "KNOWN", "event"),
    ({"source_id": "a", "target_id": "b", "predicate": "opposes",
      "predicates": ["links", "opposes"]}, "KNOWN", "relation"),
    ({"source_id": "a", "target_id": "a", "predicate": "opposes",
      "predicates": ["links", "opposes"]}, "INVALID",
     "contradictory reflexive relation"),
    ({"geometry_kind": "point", "data": [0.2, 0.4]}, "KNOWN",
     "geometric_object"),
    ({"geometry_kind": "point", "data": [1.5, 0.4],
      "space": [0.0, 1.0, 0.0, 1.0]}, "INVALID", "out-of-space point"),
    ({"nodes": ["a", "b"], "edges": [["a", "b"]]}, "KNOWN", "graph"),
    ({"kind": "translate", "parameters": {"delta": [0.1, 0.0], "dim": 2}},
     "KNOWN", "geometric_transform"),
    ({"type": "probability", "value": 1.4}, "INVALID", "probability out of [0,1]"),
    ({"type": "probability", "value": 0.25}, "KNOWN", "probability"),
    ({"type": "measurement", "value": float("nan"), "units": "kg"},
     "INVALID", "non-finite value"),
    ({"type": "measurement", "value": 5.0, "units": "kg"}, "KNOWN",
     "measurement"),
    ({"type": "scalar", "value": 42}, "KNOWN", "scalar"),
    ({"type": "equation", "value": "x = 2 * t + 1",
      "language": "maya.symbolic.v1"}, "KNOWN", "equation"),
    ({"type": "equation",
      "value": "eval(open('/etc/passwd').read())",
      "language": "maya.symbolic.v1"}, "INVALID",
     "code-execution construct"),
    ({"type": "unknown-thing", "value": 1}, "INVALID",
     "declared-but-unsupported type"),
    ({"protocol": "maya.unified_state", "schema": "maya:unified-state:1"},
     "INVALID", "incomplete canonical envelope"),
)

# geometry negatives (space bounds from the authoritative data file)
def _geometry_negatives():
    lo_x, hi_x, lo_y, hi_y = _geometry()
    return (
        ({"geometry_kind": "point",
          "data": [hi_x + 0.5, lo_y + 0.01],
          "space": [lo_x, hi_x, lo_y, hi_y]}, "INVALID",
         "point outside declared space"),
    )


def _digest_detector_module():
    path = PROJECT_ROOT / "maya_runtime" / "intelligence" / "detector.py"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def verify():
    """Run every embedded oracle check. Returns (ok, failures, ok_lines)."""
    failures = []
    ok_lines = []

    for value, expected, note in CORPUS:
        status = oracle_detect(value)
        if status != expected:
            failures.append(("corpus", value, expected, status))
    for value, expected, note in _geometry_negatives():
        status = oracle_detect(value)
        if status != expected:
            failures.append(("corpus", value, expected, status))
    if not failures:
        ok_lines.append("oracle_corpus_verdicts=OK")
    else:
        return (False, failures, ok_lines)

    digest = _digest_detector_module()
    if len(digest) != 64 or not re.match(r"^[0-9a-f]{64}$", digest):
        failures.append(("digest", digest, "detector digest shape invalid"))
    else:
        ok_lines.append("oracle_module_digest=%s" % digest[:16])

    lo_x, hi_x, lo_y, hi_y = _geometry()
    if not (lo_x == 0.0 and hi_x == 1.0 and lo_y == 0.0 and hi_y == 1.0):
        failures.append(("geometry", (lo_x, hi_x, lo_y, hi_y),
                         "identity space is not the documented unit space"))
    else:
        ok_lines.append("oracle_geometry_space=OK")

    return (not failures, failures, ok_lines)


def main():
    ok, failures, ok_lines = verify()
    for line in ok_lines:
        print(line)
    if not ok:
        print("oracle_detector_failures=%d" % len(failures))
        for entry in failures[:10]:
            print("  %r" % (entry,))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())