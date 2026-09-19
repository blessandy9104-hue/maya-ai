"""Canonical JSON (RFC 8785 JCS) encoder for Maya's numerical language layer.

Minimal Batch #1 component. Produces the byte-canonical form of a JSON value
required for deterministic digests, hashing, and future knowledge-object
integrity. Stdlib-only and deterministic: identical input yields identical
canonical UTF-8 bytes on every interpreter and device; no randomness, no
wall-clock, no hardware dependence (scanned by the independent static arm).

Conformance targets (see module ``SPEC``): RFC 8785 (JCS), June 2020,
Informational (Independent Submission); building on RFC 8259 (JSON), RFC 7493
(I-JSON), ECMA-262 10th ed. number serialization, and IEEE 754-2019 doubles.

Deliberate contract decisions (documented limitations):

- Integers must be exactly representable as IEEE 754 doubles, otherwise the
  encoder refuses (``JCSEncodeError``). We do NOT silently round integers
  beyond the safe exact range; per JCS Appendix D such values belong in JSON
  strings. This is stricter than ECMAScript ``Number`` and is enforced on
  purpose for I-JSON conformance.
- ``NaN`` and ``Infinity`` (both signs) are refused, per JCS 3.2.2.3.
- Lone surrogates in strings are refused, per JCS 3.2.2.2. Proper surrogate
  pairs (astral code points) are legal and serialized raw as UTF-8.
- Duplicate object member names are refused (I-JSON / JCS 3.1).
- Object member order is the JCS order: names sorted by their UTF-16 code
  units (not Unicode code points), which differs from Python's default sort
  exactly at astral-plane names.
- Number serialization follows ECMA-262 ``Number::toString``: shortest
  round-trip digits (CPython's ``repr`` guarantees shortest round-trip),
  formatted by the ECMAScript placement rules (decimal for ``10^b`` in the
  printable window, exponential otherwise, lowercase ``e``, sign always).
  ``-0`` serializes as ``0``.
- A nesting-depth guard (``MAX_DEPTH``) is enforced; JCS does not specify a
  bound, so this is a documented safety measure, not a spec deviation.
- Python ``tuple`` is accepted as a JSON array (Python convenience); the
  canonical bytes are identical to the equivalent ``list``.
"""
from __future__ import annotations

import hashlib
import json
import math

SPEC_NAME = "RFC 8785 JCS"
SPEC_STATUS = "Informational (Independent Submission; not IETF standards track)"
SPEC_DATE = "June 2020"
BASES = ("RFC 8259 (JSON, STD 90)", "RFC 7493 (I-JSON)", "ECMA-262 10th ed.",
         "IEEE 754-2019")
VERSION = "1.0.0"
MAX_DEPTH = 512


class JCSEncodeError(ValueError):
    """Raised when a value cannot be represented in canonical JSON."""


def _reject_unsupported(value):
    raise JCSEncodeError(
        "cannot canonicalize value of type %r; supported: "
        "None, bool, str, exactly-representable int, finite float, "
        "list/tuple, dict[str, ...]" % type(value).__name__)


def _number_format(double_value):
    """ECMA-262 Number::toString shortest-round-trip formatting."""
    if double_value == 0.0:
        return "0"
    sign = "-" if math.copysign(1.0, double_value) < 0.0 else ""
    repr_text = repr(abs(double_value))
    mantissa, _, exponent_text = repr_text.partition("e")
    exp10 = int(exponent_text) if exponent_text else 0
    int_part, dot, frac = mantissa.partition(".")
    if dot and (not frac or set(frac) == {"0"}):
        frac = ""
    digits = int_part + frac
    k = len(digits)
    point = len(int_part)
    if k == 0:
        raise JCSEncodeError("empty number production for %r" % double_value)
    power = exp10 + point - k
    n = k + power
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        exponent = n - 1
        if k == 1:
            body = digits + "e%+d" % exponent
        else:
            body = digits[0] + "." + digits[1:] + "e%+d" % exponent
    return sign + body


def _validate_exact_int(value):
    as_double = float(value)
    if int(as_double) != value:
        raise JCSEncodeError(
            "integer %d is not exactly representable as an IEEE 754 double; "
            "encode it as a JSON string (JCS Appendix D / I-JSON)" % value)
    return as_double


def _jcs_string(value):
    out = ['"']
    for ch in value:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise JCSEncodeError(
                "lone surrogate U+%04X is not valid canonical JSON (JCS 3.2.2.2)" % code)
        if code == 0x22:
            out.append('\\"')
        elif code == 0x5C:
            out.append("\\\\")
        elif code == 0x08:
            out.append("\\b")
        elif code == 0x09:
            out.append("\\t")
        elif code == 0x0A:
            out.append("\\n")
        elif code == 0x0C:
            out.append("\\f")
        elif code == 0x0D:
            out.append("\\r")
        elif code < 0x20:
            out.append("\\u%04x" % code)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _utf16_sort_key(name):
    try:
        return name.encode("utf-16-be")
    except UnicodeEncodeError:
        raise JCSEncodeError(
            "string %r cannot be encoded to UTF-16 (lone surrogate)" % name)


def _encode_value(value, out, depth):
    if depth < 0:
        raise JCSEncodeError("maximum nesting depth (%d) exceeded" % MAX_DEPTH)
    if value is None:
        out.append("null")
        return
    if isinstance(value, bool):
        out.append("true" if value else "false")
        return
    if isinstance(value, str):
        out.append(_jcs_string(value))
        return
    if isinstance(value, int):
        out.append(_number_format(_validate_exact_int(value)))
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JCSEncodeError(
                "non-finite float %r is not permitted in canonical JSON "
                "(JCS 3.2.2.3)" % value)
        out.append(_number_format(value))
        return
    if isinstance(value, (list, tuple)):
        out.append("[")
        first = True
        for item in value:
            if not first:
                out.append(",")
            first = False
            _encode_value(item, out, depth - 1)
        out.append("]")
        return
    if isinstance(value, dict):
        out.append("{")
        seen = set()
        first = True
        for key in sorted(value, key=_utf16_sort_key):
            if not isinstance(key, str):
                raise JCSEncodeError(
                    "object member name must be a string (got %r)" % type(key).__name__)
            if key in seen:
                raise JCSEncodeError("duplicate object member %r (JCS 3.1)" % key)
            seen.add(key)
            if not first:
                out.append(",")
            first = False
            out.append(_jcs_string(key))
            out.append(":")
            _encode_value(value[key], out, depth - 1)
        out.append("}")
        return
    _reject_unsupported(value)


def canonicalize(value, *, max_depth=MAX_DEPTH):
    """Return the canonical JSON text of ``value`` (RFC 8785, UTF-8-serializable)."""
    out = []
    _encode_value(value, out, max_depth)
    return "".join(out)


def canonical_bytes(value, *, max_depth=MAX_DEPTH):
    """Return the canonical JSON bytes (UTF-8) of ``value``."""
    return canonicalize(value, max_depth=max_depth).encode("utf-8")


def sha256(value, *, max_depth=MAX_DEPTH):
    """Return the SHA-256 hex digest of the canonical bytes of ``value``."""
    return hashlib.sha256(canonical_bytes(value, max_depth=max_depth)).hexdigest()


def _duplicate_detecting_pairs(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            raise JCSEncodeError("duplicate object member %r (JCS 3.1)" % key)
        result[key] = val
    return result


def parse_json(text):
    """Parse JSON text with duplicate-member detection (I-JSON fail-closed)."""
    return json.loads(text, object_pairs_hook=_duplicate_detecting_pairs)


def canonicalize_json(text, *, max_depth=MAX_DEPTH):
    """Canonicalize raw JSON text; rejects duplicate keys, NaN/Inf tokens and
    lone surrogate escapes at parse or encode time."""
    return canonicalize(parse_json(text), max_depth=max_depth)