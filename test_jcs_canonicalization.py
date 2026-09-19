"""JCS canonical encoder (RFC 8785) suite for MAYA Batch #1.

Executed by ``python -m verification`` (registered in manifest.py). Verifies
the primary implementation in ``maya_runtime/intelligence/jcs.py`` against:

- the authoritative gold vectors of RFC 8785 (Appendix B number table,
  Section 3.2.2 sample, Section 3.2.4 byte-exact UTF-8 output, Section 3.2.3
  property order), re-embedded in ``verification/oracle_jcs.py``;
- the structurally independent oracle in ``verification/oracle_jcs.py``
  (byte-for-byte canonical text and SHA-256 agreement on a deterministic
  corpus);
- embedded SHA-256 gold digests (cross-interpreter determinism: the same
  digest must be produced by CPython 3.13 and 3.14);
- fail-closed negative cases (lone surrogates, NaN/Infinity, duplicate keys,
  integers not exactly representable as IEEE 754 doubles).

Every assertion raises; only fully-passing runs emit the contracted ``=OK``
lines below (9 total).
"""
import hashlib
import json
import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_runtime.intelligence import jcs
from verification import oracle_jcs as oracle

# SHA-256 of the RFC 8785 Section 3.2.4 canonical UTF-8 bytes.
DIGEST_SECTION324 = "2d5e01a318d0f0879ab568c4be289c8b1f64ef8921a53c6277d5e069978baacb"

# SHA-256 of a representative Batch #1 literal (record structure below).
RECORD = {
    "protocol": "maya.jcs.batch1",
    "schema_version": 1,
    "geometry": {
        "space": {"width": 1.0, "height": 1.0, "x": 0.5, "y_down": True},
        "tolerance": 0.004,
        "seed": 21098,
    },
    "features": ["symmetry", "bilateral"],
    "presence": {"blink": 0.12, "jaw": 1.2},
    "ok": True,
}
DIGEST_RECORD = "e8697f09266730b152a74530172e615e803113bb2acf7c83956e8f287692d0d7"

LONE_SURROGATES = ("\ud800", "\udfff", "\udbff\udfff_no_pair")


def _nminutes_deterministic_corpus():
    # Fixed literal corpus, unchanged across interpreters.
    return [
        None, True, False,
        0, -0, 5e-324, -5e-324, 1.7976931348623157e308,
        0.1, 0.5, 0.002, 1e-21, 1e+21, 0.000001,
        9007199254740992, -9007199254740992,
        333333333.33333325, -0.0000033333333333333333,
        "plain string",
        "\u20ac\u00f6\u00e9~plain",
        "\u0000\u0001\u001f\"\\",
        ["a", {"b": [1, 2.5, None]}, "z"],
        {"\r": 1, "1": 2, "\u0080": 3, "\u00f6": 4, "\u20ac": 5,
         "\U0001F600": 6, "\ufb33": 7},
    ]


def _test_gold_numbers_and_errors():
    for bits_hex, expected in oracle.NUMBER_GOLD:
        value = oracle._bits_to_double(bits_hex)
        assert jcs.canonicalize(value) == expected
        assert oracle.canonical(value) == expected
    for bits_hex in oracle.ERROR_GOLD:
        value = oracle._bits_to_double(bits_hex)
        for fn in (jcs.canonicalize, oracle.canonical):
            try:
                fn(value)
            except ValueError:
                pass
            else:
                raise AssertionError("non-finite accepted: %s" % bits_hex)


def _test_sample_section322_and_324():
    parsed = json.loads(oracle.SEC322_SAMPLE_TEXT)
    primary_bytes = jcs.canonical_bytes(parsed)
    assert primary_bytes == oracle.SEC324_BYTES, "RFC 3.2.4 bytes mismatch"
    assert oracle.canonical_bytes(parsed) == oracle.SEC324_BYTES
    assert hashlib.sha256(primary_bytes).hexdigest() == DIGEST_SECTION324


def _test_property_sort_section323():
    parsed = json.loads(oracle.SEC323_SAMPLE_TEXT)
    canonical = jcs.canonicalize(parsed)
    keys = list(json.loads(canonical).keys())
    assert keys == oracle.SEC323_EXPECTED_KEYS
    assert oracle.canonical(parsed) == canonical


def _test_negative_cases():
    try:
        jcs.canonicalize_json('{"a": 1, "a": 2}')
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate object member accepted")
    for surrogate in LONE_SURROGATES:
        try:
            jcs.canonicalize(surrogate)
        except ValueError:
            pass
        else:
            raise AssertionError("lone surrogate accepted: %r" % surrogate)
    try:
        jcs.canonicalize_json('"\\ud800"')
    except ValueError:
        pass
    else:
        raise AssertionError("escaped lone surrogate accepted")
    try:
        jcs.canonicalize(2 ** 53 + 1)
    except ValueError:
        pass
    else:
        raise AssertionError("int not exactly representable as double accepted")
    assert jcs.canonicalize(2 ** 53) == "9007199254740992"
    assert jcs.canonicalize(0.0) == "0"
    assert jcs.canonicalize(-0.0) == "0"


def _test_cross_implementation_agreement():
    for value in _nminutes_deterministic_corpus():
        primary_bytes = jcs.canonical_bytes(value)
        oracle_bytes = oracle.canonical_bytes(value)
        assert primary_bytes == oracle_bytes, repr(value)
        parsed_back = json.loads(primary_bytes.decode("utf-8"))
        assert jcs.canonical_bytes(parsed_back) == primary_bytes


def _test_embedded_gold_digests():
    assert jcs.sha256(RECORD) == DIGEST_RECORD
    assert jcs.canonicalize_json(
        '{"ok":true,"presence":{"blink":0.12,"jaw":1.2},"protocol":'
        '"maya.jcs.batch1","schema_version":1}'
    ) == '{"ok":true,"presence":{"blink":0.12,"jaw":1.2},"protocol":' \
        '"maya.jcs.batch1","schema_version":1}'
    parsed = json.loads(oracle.SEC322_SAMPLE_TEXT)
    assert oracle.digest(parsed) == DIGEST_SECTION324


def _test_structural_and_depth_guards():
    deep = None
    for _ in range(700):
        deep = [deep]
    try:
        jcs.canonicalize(deep)
    except ValueError:
        pass
    else:
        raise AssertionError("over-deep nesting accepted")
    assert jcs.canonicalize(["ok", {"nested": [1, True, None]}]) == \
        '["ok",{"nested":[1,true,null]}]'


for _name, _fn in sorted(globals().items()):
    if _name.startswith("_test_") and callable(_fn):
        _fn()

print("jcs_gold_numbers_and_errors=OK")
print("jcs_sample_section322=OK")
print("jcs_sample_section324_utf8=OK")
print("jcs_property_sort_section323=OK")
print("jcs_negative_cases=OK")
print("jcs_cross_implementation_agreement=OK")
print("jcs_embedded_gold_digests=OK")
print("jcs_structural_guards=OK")
print("jcs_batch1_suite_contract=OK")