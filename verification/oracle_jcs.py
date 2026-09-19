"""Independent canonical JSON (RFC 8785 JCS) oracle used by MAYA Batch #1.

This module is an independent observer for the JCS canonical encoder:

- It does NOT import Maya's ``maya_runtime.intelligence.jcs`` (or any other
  Maya module). Its serializer is a fresh, structurally different
  implementation of the same normative algorithm.
- It embeds the authoritative gold vectors taken from RFC 8785's own text
  (fetch ``rfc8785.txt`` from the RFC Editor): the Appendix B number
  serialization samples, the Section 3.2.2 worked example, the Section 3.2.4
  byte-for-byte UTF-8 output, and the Section 3.2.3 property-sort sample. The
  test suite therefore judges the primary implementation against the
  standard's own data, not against a mirrored implementation.
- It fails closed on anything it cannot verify.

Limitation recorded for the external accuracy register: shortest round-trip
digit production in both this oracle and the primary encoder relies on
CPython's shortest-representation guarantee (``repr``/``float.__repr__``),
which has the same guarantee class as ECMAScript ``Number.prototype.toString``
and the V8/Ryu serializers the RFC points to. That single shared dependency is
hedged by byte-exact agreement with the RFC gold table (Appendix B),
cross-interpreter gold digests, and the IEEE 754 bit-pattern reconstruction of
every sample value.

Standalone use: ``python verification/oracle_jcs.py`` verifies all embedded
gold vectors and prints one ``=OK`` evidence line per category; exit code is
non-zero if anything fails.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct

ORACLE_IDENTITY = "maya-verification/oracle-jcs/1.0.0"
SPEC_NAME = "RFC 8785 JCS (Ecma-262-inspired canonical JSON)"
SPEC_SOURCE = "https://www.rfc-editor.org/rfc/rfc8785.txt"
GOLD_SOURCE_DATE = "2026-09-09T00:00:00+00:00"

# ---------------------------------------------------------------------------
# Gold vectors (byte-exact copies of RFC 8785 data; nothing synthesized).
# ---------------------------------------------------------------------------

# RFC 8785 Appendix B, Table 1. IEEE 754 bit pattern (big-endian, hexadecimal)
# -> expected JSON representation. NaN/Infinity entries are handled separately
# because they MUST cause an error.
NUMBER_GOLD = (
    ("0000000000000000", "0"),
    ("8000000000000000", "0"),
    ("0000000000000001", "5e-324"),
    ("8000000000000001", "-5e-324"),
    ("7fefffffffffffff", "1.7976931348623157e+308"),
    ("ffefffffffffffff", "-1.7976931348623157e+308"),
    ("4340000000000000", "9007199254740992"),
    ("c340000000000000", "-9007199254740992"),
    ("4430000000000000", "295147905179352830000"),
    ("44b52d02c7e14af5", "9.999999999999997e+22"),
    ("44b52d02c7e14af6", "1e+23"),
    ("44b52d02c7e14af7", "1.0000000000000001e+23"),
    ("444b1ae4d6e2ef4e", "999999999999999700000"),
    ("444b1ae4d6e2ef4f", "999999999999999900000"),
    ("444b1ae4d6e2ef50", "1e+21"),
    ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
    ("3eb0c6f7a0b5ed8d", "0.000001"),
    ("41b3de4355555553", "333333333.3333332"),
    ("41b3de4355555554", "333333333.33333325"),
    ("41b3de4355555555", "333333333.3333333"),
    ("41b3de4355555556", "333333333.3333334"),
    ("41b3de4355555557", "333333333.33333343"),
    ("becbf647612f3696", "-0.0000033333333333333333"),
    ("43143ff3c1cb0959", "1424953923781206.2"),
)

# IEEE 754 values that are not permitted in JSON and MUST error (RFC 8785
# 3.2.2.3): NaN payload and positive/negative infinity.
ERROR_GOLD = (
    "7fffffffffffffff",   # NaN
    "7ff0000000000000",   # +Infinity
    "fff0000000000000",   # -Infinity
)

# RFC 8785 Section 3.2.2 input document (verbatim JSON from the RFC).
SEC322_SAMPLE_TEXT = (
    '{"numbers":[333333333.33333329,1E30,4.50,'
    '2e-3,0.000000000000000000000000001],'
    '"string":"\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\\"\\/",'
    '"literals":[null,true,false]}'
)

# RFC 8785 Section 3.2.4 UTF-8 output (byte-exact, from the RFC hex dump).
SEC324_BYTES = bytes.fromhex(
    "7b 22 6c 69 74 65 72 61 6c 73 22 3a 5b 6e 75 6c 6c 2c 74 72"
    "75 65 2c 66 61 6c 73 65 5d 2c 22 6e 75 6d 62 65 72 73 22 3a"
    "5b 33 33 33 33 33 33 33 33 33 2e 33 33 33 33 33 33 33 2c 31"
    "65 2b 33 30 2c 34 2e 35 2c 30 2e 30 30 32 2c 31 65 2d 32 37"
    "5d 2c 22 73 74 72 69 6e 67 22 3a 22 e2 82 ac 24 5c 75 30 30"
    "30 66 5c 6e 41 27 42 5c 22 5c 5c 5c 5c 5c 22 2f 22 7d")

# RFC 8785 Section 3.2.3 property-sort sample (verbatim JSON) and the expected
# argument (member) order after UTF-16 code-unit sorting.
SEC323_SAMPLE_TEXT = (
    '{"\\u20ac":"Euro Sign","\\r":"Carriage Return",'
    '"\\ufb33":"Hebrew Letter Dalet With Dagesh","1":"One",'
    '"\\ud83d\\ude00":"Emoji: Grinning Face",'
    '"\\u0080":"Control","\\u00f6":"Latin Small Letter O With Diaeresis"}'
)
SEC323_EXPECTED_KEYS = [
    "\r",
    "1",
    "\u0080",
    "\u00f6",
    "\u20ac",
    "\U0001F600",
    "\ufb33",
]

CONTROL_ESCAPES = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n",
                   0x0C: "\\f", 0x0D: "\\r"}


class JCSOracleError(ValueError):
    """Raised when a value cannot be expressed in canonical JSON."""


def _bits_to_double(bits_hex):
    raw = bytes.fromhex(bits_hex)
    return struct.unpack(">d", raw)[0]


def string_literal(text):
    """Serialize a string per RFC 8785 3.2.2.2 (lowercase \\u escapes)."""
    out = ['"']
    for ch in text:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            raise JCSOracleError(
                "lone surrogate U+%04X is not valid canonical JSON" % cp)
        if cp < 0x20:
            out.append(CONTROL_ESCAPES.get(cp, "\\u%04x" % cp))
        elif ch in ('"', "\\"):
            out.append("\\" + ch)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _digits_and_exponent(x):
    """Decompose ``x`` into (digits, k, point) via shortest repr expansion."""
    reps = repr(abs(x))
    mantissa, _, exp_text = reps.partition("e")
    exp10 = int(exp_text) if exp_text else 0
    int_part, dot, frac = mantissa.partition(".")
    if dot and (not frac or set(frac) == {"0"}):
        frac = ""
    digits = int_part + frac
    point = len(int_part)
    return digits, exp10, point


def number_literal(x):
    """Serialize a double per ECMA-262 Number::toString (RFC 8785 3.2.2.3)."""
    if x == 0.0:
        return "0"
    sign = "-" if math.copysign(1.0, x) < 0.0 else ""
    digits, exp10, point = _digits_and_exponent(x)
    k = len(digits)
    power = exp10 + point - k  # decimal exponent of the leading digit
    n = k + power               # position of the decimal point (ES meaning)
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        expo = n - 1
        body = digits if k == 1 else digits[0] + "." + digits[1:]
        body += "e%+d" % expo
    return sign + body


def _utf16_key(name):
    try:
        return name.encode("utf-16-be")
    except UnicodeEncodeError:
        raise JCSOracleError("member name cannot be sorted (lone surrogate)")


class Serializer:
    """Iterative (stack-based) canonical serializer -- deliberately a
    different structure from the primary encoder's recursive form."""

    def __init__(self, value):
        self.value = value
        self.parts = []

    def _scalar(self, item):
        """Append a leaf production, or raise for an invalid leaf."""
        if item is None:
            return "null"
        if isinstance(item, bool):
            return "true" if item else "false"
        if isinstance(item, str):
            return string_literal(item)
        if isinstance(item, int):
            as_double = float(item)
            if int(as_double) != item:
                raise JCSOracleError(
                    "integer %d is not exactly representable as a double" % item)
            return number_literal(as_double)
        if isinstance(item, float):
            if not math.isfinite(item):
                raise JCSOracleError("non-finite number is not JSON")
            return number_literal(item)
        raise JCSOracleError(
            "unsupported value of type %r in oracle" % type(item).__name__)

    def _ordered(self, item):
        if isinstance(item, dict):
            ordered = []
            for key in sorted(item, key=_utf16_key):
                if not isinstance(key, str):
                    raise JCSOracleError("object member names must be strings")
                ordered.append((key, item[key]))
            return ordered
        return list(item)

    def run(self):
        stack = [("value", self.value)]
        while stack:
            task = stack.pop()
            if task[0] == "part":
                self.parts.append(task[1])
                continue
            item = task[1]
            if item is None or isinstance(item, (bool, str, int, float)):
                self.parts.append(self._scalar(item))
                continue
            if isinstance(item, dict):
                block = [("part", "{")]
                for idx, (key, value) in enumerate(self._ordered(item)):
                    if idx:
                        block.append(("part", ","))
                    block.append(("part", string_literal(key)))
                    block.append(("part", ":"))
                    block.append(("value", value))
                block.append(("part", "}"))
            elif isinstance(item, (list, tuple)):
                block = [("part", "[")]
                for idx, child in enumerate(self._ordered(item)):
                    if idx:
                        block.append(("part", ","))
                    block.append(("value", child))
                block.append(("part", "]"))
            else:
                raise JCSOracleError(
                    "unsupported collective type %r" % type(item).__name__)
            for sub in reversed(block):
                stack.append(sub)
        return "".join(self.parts)


def canonical(value):
    """Canonical JSON text of ``value`` (independent oracle implementation)."""
    serializer = Serializer(value)
    return serializer.run()


def canonical_bytes(value):
    return canonical(value).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _verify_number_gold():
    failures = []
    for bits_hex, expected in NUMBER_GOLD:
        value = _bits_to_double(bits_hex)
        try:
            observed = canonical(value)
        except Exception as exc:  # pragma: no cover - reporting only
            failures.append((bits_hex, expected, "error", repr(exc)))
            continue
        if observed != expected:
            failures.append((bits_hex, expected, observed, None))
    return failures


def _verify_error_gold():
    failures = []
    for bits_hex in ERROR_GOLD:
        value = _bits_to_double(bits_hex)
        try:
            canonical(value)
        except JCSOracleError:
            continue
        except Exception as exc:
            failures.append((bits_hex, "expected JCSOracleError", repr(exc)))
            continue
        failures.append((bits_hex, "expected JCSOracleError", "accepted"))
    return failures


def _verify_section322_324():
    failures = []
    try:
        parsed = json.loads(SEC322_SAMPLE_TEXT)
    except Exception as exc:
        return [(SEC322_SAMPLE_TEXT, "parses", repr(exc))]
    try:
        text = canonical(parsed)
    except Exception as exc:
        return [(SEC322_SAMPLE_TEXT, "canonicalizes", repr(exc))]
    if text.encode("utf-8") != SEC324_BYTES:
        failures.append(("section322-canonic", "matches section324 bytes",
                         text.encode("utf-8").hex()))
    return failures


def _verify_section323():
    failures = []
    try:
        parsed = json.loads(SEC323_SAMPLE_TEXT)
    except Exception as exc:
        return [(SEC323_SAMPLE_TEXT, "parses", repr(exc))]
    try:
        text = canonical(parsed)
        observed_keys = list(json.loads(text).keys())
    except Exception as exc:
        return [(SEC323_SAMPLE_TEXT, "canonicalizes", repr(exc))]
    if observed_keys != SEC323_EXPECTED_KEYS:
        failures.append(("section323-order",
                         SEC323_EXPECTED_KEYS, observed_keys))
    return failures


def verify_gold():
    """Run every embedded RFC 8785 gold check.

    Returns ``(ok, failures, ok_lines)`` where ``ok_lines`` is a list of the
    ``=OK`` evidence lines that a clean run emits.
    """
    failures = []
    failures += _verify_number_gold()
    failures += _verify_error_gold()
    failures += _verify_section322_324()
    failures += _verify_section323()
    ok = not failures
    ok_lines = []
    if ok:
        ok_lines = [
            "oracle_gold_numbers=OK",
            "oracle_gold_errors_rejected=OK",
            "oracle_sample_section322=OK",
            "oracle_sample_section324_bytes=OK",
            "oracle_property_sort_section323=OK",
        ]
    return ok, failures, ok_lines


def main():
    ok, failures, ok_lines = verify_gold()
    for line in ok_lines:
        print(line)
    if not ok:
        print("oracle_gold_failures=%d" % len(failures))
        for entry in failures[:10]:
            print("  %r" % (entry,))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())