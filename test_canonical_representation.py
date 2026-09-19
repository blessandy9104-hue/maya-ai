"""Canonical representation foundation suite (MAYA Batch #2).

Verifies ``maya_runtime/intelligence/representation.py`` and
``maya_runtime/intelligence/canonical.py`` (registered in verification/manifest
as part of the readiness battery):

- the 22 representation-type contracts and their introspectable form;
- atom validation (all types, positive cases) against the fail-closed rules;
- the canonical knowledge-object envelope: construction, JCS canonical bytes,
  SHA-256 integrity digest computed over the payload without its integrity
  member, and corruption detection;
- representation detection (KNOWN / INVALID / AMBIGUOUS / UNKNOWN) with the
  guarantees that UNKNOWN is never the numeric 0 and AMBIGUOUS is never
  coerced to False;
- 16 fail-closed negative cases (misdeclared measurement, missing units,
  out-of-range probability/confidence, NaN/Infinity measurements, wrong vector
  dimension, out-of-space coordinate, corrupted digest, unknown schema
  version, unknown encoding scheme, malformed equation, code-injection
  attempt, missing provenance, contradictory relation, malformed temporal
  metadata);
- provenance reusing the world-model evidence vocabulary;
- geometry contracts read from maya_identity/geometry (unit space, axis 0.5,
  tolerance 0.004) with a real mirror-pair check;
- translation with explicit loss accounting and refused semantic
  cross-casting (probability/confidence/uncertainty never silently
  interconverted);
- the independent oracle (verification/oracle_representation) recomputing the
  type rules, schema witness, geometry, and digest without any Maya import;
- a cross-interpreter embedded gold digest.

Every assertion raises; only a fully passing run emits the contracted
evidence markers (19 total).
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_runtime.intelligence import canonical
from maya_runtime.intelligence import representation as rep
from verification import oracle_jcs
from verification import oracle_representation as oracle

# Cross-interpreter gold digest: the canonical knowledge object below must
# produce exactly this SHA-256 on every interpreter and device.
GOLD_DIGEST = "99356ad10420cdd91bb20ff50f4675012f2e39d951b11168beb68ab76f90cee1"

GOLD_ARGS = dict(
    record_type="identity.geometry",
    object_id="geo-gold-0001",
    created_at="2026-09-10T00:00:00Z",
    provenance={
        "source": "RFC 8785 + geometry contracts",
        "source_url": "https://www.rfc-editor.org/rfc/rfc8785.txt",
        "retrieved_at": "2026-09-10T00:00:00Z",
        "evidence_type": "fact",
        "confidence": "high",
        "claim": "Embedded cross-interpreter gold literal for Batch 2.",
    },
    metadata={"batch": 2, "layer": "canonical"},
    body={
        "axis_x": {"type": "measurement", "value": 0.5, "units": "normalized"},
        "point": {"type": "geometric_point", "value": [0.5, 0.46]},
        "confidence_floor": {"type": "confidence", "value": 0.6},
    },
)

EXPECTED_TYPES = frozenset({
    "identifier", "text", "scalar", "measurement", "vector", "matrix",
    "symbol", "equation", "category", "relation", "event",
    "temporal_interval", "geometric_point", "geometric_vector",
    "geometric_transform", "geometric_object", "graph", "probability",
    "confidence", "uncertainty", "provenance", "metadata",
})

CONTRACT_KEYS = frozenset({
    "representation", "allowed", "domain", "units", "precision",
    "semantic_or_opaque", "transformable", "lossless", "notes",
})


def _valid(value, type_name, **attrs):
    try:
        return rep.validate(value, type_name, **attrs) is not None
    except rep.RepresentationError:
        return False


def _expect_error(fn, exc_type, label):
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(label)


# create() raises CanonicalError for envelope-shape violations and the type
# system's RepresentationError for value-contract violations; both are
# validation failures that must fail closed.
VALIDATION_ERROR = (rep.RepresentationError, canonical.CanonicalError)


def _test_types_registered():
    assert set(rep.REPRESENTATION_TYPES) == EXPECTED_TYPES
    assert len(rep.REPRESENTATION_TYPES_ORDERED) == len(EXPECTED_TYPES)
    assert set(rep.REPRESENTATION_TYPES) == set(rep.REPRESENTATION_TYPES_ORDERED)
    assert oracle.REPRESENTATION_TYPES == rep.REPRESENTATION_TYPES


def _test_contracts_introspectable():
    for type_name in rep.REPRESENTATION_TYPES_ORDERED:
        entry = rep.contract(type_name)
        assert CONTRACT_KEYS <= set(entry), type_name
        assert isinstance(entry["semantic_or_opaque"], str)
        assert isinstance(entry["lossless"], bool)
    _expect_error(lambda: rep.contract("not_a_type"), rep.RepresentationError,
                  "unknown type contract accepted")
    assert not rep.known("not_a_type")
    assert rep.known("measurement")


def _test_atom_validation():
    assert _valid("geo-0001", "identifier")
    assert _valid("plain text", "text")
    assert _valid(0.5, "scalar", domain=(0.0, 1.0))
    assert _valid(0.5, "measurement", units="normalized")
    assert _valid([1.0, 2.0, 3.0], "vector", dim=3)
    assert _valid([[1.0, 0.0], [0.0, 1.0]], "matrix", rows=2, cols=2)
    assert _valid("phi", "symbol")
    assert _valid(0.5, "probability")
    assert _valid(0.6, "confidence")
    assert _valid(0.2, "uncertainty")
    assert _valid("human-inspired", "category",
                  code_set=["human-inspired", "cyber-organic"])
    assert _valid("x = 2 * t + 1", "equation", language="maya.symbolic.v1")
    assert _valid({"source_id": "a", "target_id": "b",
                   "predicate": "coexists_with"}, "relation",
                  predicates=["coexists_with"], nodes=["a", "b"])
    assert _valid({"kind": "noticed", "at": "2026-09-09T00:00:00Z"},
                  "event", event_types=["noticed"])
    assert _valid({"start": "2026-09-09T00:00:00Z",
                   "end": "2026-09-09T00:05:00Z"}, "temporal_interval")
    assert _valid([0.5, 0.46], "geometric_point", space=(0.0, 1.0, 0.0, 1.0))
    assert _valid([0.5, 0.46], "geometric_vector", dim=2)
    assert _valid({"kind": "reflect", "parameters": {"axis_x": 0.5}},
                  "geometric_transform")
    assert _valid({"geometry_kind": "point", "data": [0.5, 0.46]},
                  "geometric_object", space=(0.0, 1.0, 0.0, 1.0))
    assert _valid({"nodes": ["a", "b"], "edges": [["a", "b"]]}, "graph")
    assert _valid({"source": "RFC 8785",
                   "retrieved_at": "2026-09-09T00:00:00Z",
                   "evidence_type": "fact", "confidence": "high"},
                  "provenance")
    assert _valid({"revision": 1, "layer": "canonical"}, "metadata")
    # bool is never a numeric atom.
    assert not _valid(True, "scalar")
    assert not _valid(True, "probability")


def _test_geometry_contract_reused():
    geo = canonical.geometry_contract()
    assert geo["space"] == (0.0, 1.0, 0.0, 1.0)
    assert geo["axis_x"] == 0.5
    assert geo["tolerance"] == 0.004
    assert geo["y_down"] is True
    assert canonical.geometry_space() == (0.0, 1.0, 0.0, 1.0)
    # Real mirror pair from the authoritative facial_structure data: the left
    # brow runs outer->inner while the right brow runs inner->outer, so a
    # mirrored pair is (left[i], right[last - i]).
    facial_path = ROOT / "maya_identity" / "geometry" / "facial_structure.json"
    facial = json.loads(facial_path.read_text(encoding="utf-8"))
    left = facial["brows"]["left"]
    right = facial["brows"]["right"]
    assert len(left) == len(right) and left and right
    for index in range(len(left)):
        lx = left[index][0]
        rx = right[len(right) - 1 - index][0]
        deviation = abs((0.5 - lx) - (rx - 0.5))
        assert deviation <= 0.004, (index, deviation)
    # Points outside the identity space are rejected (fail closed).
    _expect_error(lambda: rep.validate([0.5, 1.5], "geometric_point",
                                       space=canonical.geometry_space()),
                  rep.RepresentationError, "out-of-space point accepted")
    assert canonical.geometry_contract()["source_files"]


def _test_temporal_validation():
    assert rep.validate_iso8601_utc("2026-09-09T00:00:00Z") == \
        "2026-09-09T00:00:00Z"
    assert rep.validate_iso8601_utc("2026-09-09T23:59:60+02:00") == \
        "2026-09-09T23:59:60+02:00"
    assert rep.validate_iso8601_utc("2024-02-29T12:00:00Z") == \
        "2024-02-29T12:00:00Z"
    for bad in ("2026-02-31T00:00:00Z", "2026-13-01T00:00:00Z",
                "2026-09-09T25:00:00Z", "2026-09-09T00:00:00",
                "2026-09-09 00:00:00Z", "2023-02-29T00:00:00Z"):
        _expect_error(lambda b=bad: rep.validate_iso8601_utc(b),
                      rep.RepresentationError, "invalid timestamp accepted: "
                      + bad)
    assert not _valid({"start": "2026-09-09T00:05:00Z",
                       "end": "2026-09-09T00:00:00Z"}, "temporal_interval")
    assert _valid({"start": "2026-09-09T00:00:00Z",
                   "end": "2026-09-09T00:00:00Z"}, "temporal_interval")


def _test_equation_symbolic_no_eval():
    assert _valid("x = 2 * t + 1", "equation", language="maya.symbolic.v1")
    for token in ("eval", "exec", "__", "os.", "subprocess", "builtins"):
        sample = "x = __x__" if token == "__" else "x = %s" % token
        _expect_error(lambda s=sample: rep.validate(s, "equation",
                                                    language="maya.symbolic.v1"),
                      rep.RepresentationError, "hostile equation accepted: "
                      + sample)
    _expect_error(lambda: rep.validate("x = 2", "equation",
                                       language="base128-fake"),
                  rep.RepresentationError, "unknown encoding scheme accepted")
    _expect_error(lambda: rep.validate("x+\u0007", "equation",
                                       language="maya.symbolic.v1"),
                  rep.RepresentationError, "control-char equation accepted")
    # Static proof: neither implementation module evaluates anything.
    for module in (canonical.__file__, rep.__file__):
        source = pathlib.Path(module).read_text(encoding="utf-8")
        assert "eval(" not in source, module
        assert "exec(" not in source, module


def _test_graph_relation_foundation():
    _expect_error(lambda: rep.validate(
        {"source_id": "a", "target_id": "a", "predicate": "not_equal"},
        "relation", predicates=["not_equal"]),
        rep.RepresentationError, "contradictory reflexive relation accepted")
    assert _valid({"source_id": "a", "target_id": "a",
                   "predicate": "equals"},
                  "relation", predicates=["equals"])
    _expect_error(lambda: rep.validate(
        {"source_id": "a", "target_id": "c", "predicate": "equals"},
        "relation", predicates=["equals"], nodes=["a", "b"]),
        rep.RepresentationError, "relation with undefined node accepted")
    _expect_error(lambda: rep.validate(
        {"nodes": ["a", "b"], "edges": [["a", "a"]]}, "graph"),
        rep.RepresentationError, "graph self-loop accepted")
    _expect_error(lambda: rep.validate(
        {"nodes": ["a", "b"], "edges": [["a", "b"], ["a", "b"]]}, "graph"),
        rep.RepresentationError, "duplicate graph edge accepted")
    _expect_error(lambda: rep.validate(
        {"nodes": ["a", "a"], "edges": []}, "graph"),
        rep.RepresentationError, "duplicate graph node accepted")
    _expect_error(lambda: rep.validate(
        {"kind": "unknown_kind", "at": "2026-09-09T00:00:00Z"}, "event",
        event_types=["noticed"]),
        rep.RepresentationError, "unknown event kind accepted")
    _expect_error(lambda: rep.validate(
        {"kind": "noticed", "at": "2026-09-09T25:00:00Z"}, "event",
        event_types=["noticed"]),
        rep.RepresentationError, "event with malformed timestamp accepted")


def _test_provenance_contract():
    base = {"source": "RFC 8785", "retrieved_at": "2026-09-09T00:00:00Z",
            "evidence_type": "fact", "confidence": "high"}
    assert _valid(dict(base), "provenance")
    _expect_error(lambda: rep.validate({k: v for k, v in base.items()
                                        if k != "source"}, "provenance"),
                  rep.RepresentationError, "provenance without source accepted")
    _expect_error(lambda: rep.validate(dict(base, evidence_type="gossip"),
                                       "provenance"),
                  rep.RepresentationError, "non-world-model evidence_type "
                  "accepted")
    _expect_error(lambda: rep.validate(dict(base, confidence="certain"),
                                       "provenance"),
                  rep.RepresentationError, "non-world-model confidence "
                  "accepted")
    _expect_error(lambda: rep.validate(dict(base,
                                            retrieved_at="yesterday"),
                                       "provenance"),
                  rep.RepresentationError, "non-ISO retrieved_at accepted")
    _expect_error(lambda: rep.validate(dict(base,
                                            source_url="ftp://host/x"),
                                       "provenance"),
                  rep.RepresentationError, "non-http source_url accepted")
    _expect_error(lambda: rep.validate(dict(base, claim="my password is x"),
                                       "provenance"),
                  rep.RepresentationError, "private-field marker accepted")
    # The vocabulary is the world-model vocabulary, enforced.
    from maya_world_model import ALLOWED_CONFIDENCE, ALLOWED_EVIDENCE_TYPES
    assert ALLOWED_CONFIDENCE == {"low", "medium", "high"}


def _test_uncertainty_semantics():
    assert _valid(0.7, "probability")
    assert _valid(0.7, "confidence")
    assert _valid(0.7, "uncertainty")
    assert _valid(0.7, "scalar")
    # The semantic boundary is enforced: a bare 0.7 is ambiguous, and the
    # translation layer refuses to reinterpret across the boundary.
    detection = canonical.detect(0.7)
    assert detection["regime"] == "AMBIGUOUS"
    assert detection["selected"] is None
    _expect_error(lambda: canonical.translate(0.7, "probability", "confidence"),
                  canonical.CanonicalError, "probability->confidence admitted")
    _expect_error(lambda: canonical.translate(0.7, "confidence", "probability"),
                  canonical.CanonicalError, "confidence->probability admitted")
    assert canonical.detect(0.7, declared="confidence")["regime"] == "KNOWN"
    assert canonical.detect(1.7, declared="confidence")["regime"] == "INVALID"


def _test_object_construction():
    obj = canonical.create(**GOLD_ARGS)
    assert tuple(obj) == canonical.ENVELOPE_KEYS
    assert obj["schema_version"] == canonical.SCHEMA_VERSION == 1
    assert obj["body"]["axis_x"]["units"] == "normalized"
    assert obj["body"]["point"]["space"] == [0.0, 1.0, 0.0, 1.0]
    assert canonical.body_field_type(obj, "point") == "geometric_point"
    assert canonical.body_field_type(obj, "missing") is None
    assert canonical.types_used(obj) == ("measurement", "confidence",
                                         "geometric_point")
    assert canonical.verify(obj)["integrity_ok"] is True
    assert canonical.schema_present()
    _expect_error(lambda: canonical.create(record_type="identity.geometry",
                                           object_id="x", created_at="2026-09-09T00:00:00Z",
                                           body={}, provenance=None),
                  canonical.CanonicalError, "object without provenance "
                  "accepted")
    _expect_error(lambda: canonical.create(record_type="identity.geometry",
                                           object_id="x",
                                           provenance=GOLD_ARGS["provenance"],
                                           body={}),
                  canonical.CanonicalError, "object without created_at "
                  "accepted")
    _expect_error(lambda: canonical.create(record_type="identity.geometry",
                                           created_at="2026-09-09T00:00:00Z",
                                           provenance=GOLD_ARGS["provenance"],
                                           body={}),
                  canonical.CanonicalError, "object without object_id accepted")
    _expect_error(lambda: canonical.create(record_type="identity.geometry",
                                           object_id="x", created_at="2026-09-09T00:00:00Z",
                                           provenance=GOLD_ARGS["provenance"],
                                           body={"bad_field": {
                                               "type": "not_a_type", "value": 1}}),
                  VALIDATION_ERROR, "unknown body type accepted")
    _expect_error(lambda: canonical.create(record_type="identity.geometry",
                                           object_id="x", created_at="2026-09-09T00:00:00Z",
                                           provenance=GOLD_ARGS["provenance"],
                                           body={"bad_field": 3}),
                  canonical.CanonicalError, "untyped body field accepted")
    _expect_error(lambda: canonical.create(record_type="identity geometry",
                                           object_id="x", created_at="2026-09-09T00:00:00Z",
                                           provenance=GOLD_ARGS["provenance"],
                                           body={}),
                  VALIDATION_ERROR, "invalid record_type accepted")


def _test_object_jcs_integrity():
    obj = canonical.create(**GOLD_ARGS)
    payload = canonical.payload(obj)
    assert "integrity" not in payload
    assert canonical.digest(obj) == canonical.verify(obj)["digest"]
    assert canonical.digest(obj) == \
        oracle_jcs.digest(payload)  # verified JCS layer agreement
    parsed = json.loads(canonical.to_jcs(obj))
    assert canonical.payload(parsed) == payload
    assert oracle_jcs.digest(canonical.payload(parsed)) == canonical.digest(obj)
    # Any mutation invalidates the digest (fail closed).
    tampered = dict(obj)
    tampered["body"] = dict(tampered["body"])
    tampered["body"]["point"] = dict(tampered["body"]["point"])
    tampered["body"]["point"]["value"] = [0.6, 0.46]
    _expect_error(lambda: canonical.verify(tampered), canonical.CanonicalError,
                  "value mutation not detected")
    tampered2 = dict(obj)
    tampered2["integrity"] = dict(obj["integrity"], digest="0" * 64)
    _expect_error(lambda: canonical.verify(tampered2), canonical.CanonicalError,
                  "digest corruption not detected")
    tampered3 = dict(obj)
    tampered3["body"] = dict(tampered3["body"])
    tampered3["body"]["point"] = dict(tampered3["body"]["point"],
                                      type="geometric_vector")
    _expect_error(lambda: canonical.verify(tampered3), canonical.CanonicalError,
                  "type-tag mutation not detected")
    tampered4 = dict(obj, schema_version=999)
    _expect_error(lambda: canonical.verify(tampered4), canonical.CanonicalError,
                  "unknown schema_version not detected")
    # JCS canonical form is stable: re-canonicalizing the canonical text yields
    # identical bytes.
    assert oracle_jcs.canonical(parsed) == canonical.to_jcs(obj)


def _test_embedded_gold_digest():
    obj = canonical.create(**GOLD_ARGS)
    assert canonical.digest(obj) == GOLD_DIGEST
    assert oracle.oracle_digest(obj) == GOLD_DIGEST
    assert oracle_jcs.digest(canonical.payload(obj)) == GOLD_DIGEST
    body = obj["body"]
    oracle_envelope = oracle.independent_envelope(
        object_id=obj["object_id"], record_type=obj["record_type"],
        created_at=obj["created_at"], provenance=obj["provenance"],
        metadata=obj["metadata"], body=body)
    assert oracle.oracle_digest(oracle_envelope) == GOLD_DIGEST


def _test_detection_behaviour():
    known = canonical.detect({"type": "probability", "value": 0.4})
    assert known["regime"] == "KNOWN" and known["type"] == "probability"
    assert known["admitted"] and known["selected"] == "probability"
    assert canonical.detect({"type": "probability", "value": 1.5})["regime"] == \
        "INVALID"
    ambiguous = canonical.detect(0.7)
    assert ambiguous["regime"] == "AMBIGUOUS"
    assert ambiguous["selected"] is None and ambiguous["value"] is None
    assert ambiguous["admitted"] is False, "ambiguous coerced to admissible"
    assert canonical.detect(True)["regime"] == "UNKNOWN"
    assert canonical.detect(True)["value"] is None
    assert canonical.detect(float("nan"))["regime"] == "INVALID"
    assert canonical.detect("some text")["regime"] == "AMBIGUOUS"
    assert canonical.detect({})["regime"] == "AMBIGUOUS"
    assert canonical.detect(42, declared="probability")["regime"] == "INVALID"
    assert canonical.detect(0.4, declared="uncertainty")["regime"] == "KNOWN"
    assert canonical.detect("label", declared="category")["regime"] == "INVALID"
    # Guarantee: an UNKNOWN/AMBIGUOUS regime is never returned as 0 or False.
    for probe in (canonical.detect("zxq"), canonical.detect(True),
                  canonical.detect(0.7)):
        assert probe["value"] is None
        assert probe["selected"] is None
        assert probe["admitted"] is False


def _test_negative_fail_closed():
    # 1. 42 (an enumerated code) misdeclared as a measurement without units.
    _expect_error(lambda: rep.validate(42, "measurement", units=None),
                  rep.RepresentationError, "measurement misdeclared")
    _expect_error(lambda: rep.validate(42, "measurement"),
                  rep.RepresentationError, "unitless measurement admitted")
    # 4. probability below zero.
    _expect_error(lambda: rep.validate(-0.25, "probability"),
                  rep.RepresentationError, "negative probability admitted")
    # 3. confidence above one.
    _expect_error(lambda: rep.validate(1.6, "confidence"),
                  rep.RepresentationError, "over-one confidence admitted")
    # 5/6. NaN/Infinity measurements.
    _expect_error(lambda: rep.validate(float("nan"), "measurement",
                                       units="normalized"),
                  rep.RepresentationError, "NaN measurement admitted")
    _expect_error(lambda: rep.validate(float("inf"), "measurement",
                                       units="normalized"),
                  rep.RepresentationError, "Infinity measurement admitted")
    # 7. wrong vector dimension.
    _expect_error(lambda: rep.validate([1.0, 2.0], "vector", dim=3),
                  rep.RepresentationError, "wrong-dimension vector admitted")
    # 8. coordinate outside the identity space.
    _expect_error(lambda: canonical.create(record_type="identity.geometry",
                                           object_id="x",
                                           created_at="2026-09-09T00:00:00Z",
                                           provenance=GOLD_ARGS["provenance"],
                                           body={"p": {"type": "geometric_point",
                                                       "value": [0.5, 1.5]}}),
                  VALIDATION_ERROR, "out-of-space coordinate admitted")
    # 9. corrupted integrity digest.
    obj = canonical.create(**GOLD_ARGS)
    corrupted = dict(obj)
    corrupted["integrity"] = dict(obj["integrity"],
                                  digest="1" * 64)
    _expect_error(lambda: canonical.verify(corrupted), canonical.CanonicalError,
                  "corrupted digest not detected")
    # 10. unknown schema version.
    wrong_version = dict(obj, schema_version=999)
    _expect_error(lambda: canonical.verify(wrong_version),
                  canonical.CanonicalError, "unknown schema_version admitted")
    # 11. unknown encoding scheme.
    _expect_error(lambda: rep.validate("x = 1", "equation",
                                       language="base128-fake"),
                  rep.RepresentationError, "unknown encoding scheme admitted")
    # 12. malformed equation text.
    _expect_error(lambda: rep.validate("x" + "\u0000" + "=1", "equation",
                                       language="maya.symbolic.v1"),
                  rep.RepresentationError, "malformed equation admitted")
    # 13. code-injection attempt via symbolic input.
    _expect_error(lambda: rep.validate("__import__('os').system('id')",
                                       "equation", language="maya.symbolic.v1"),
                  rep.RepresentationError, "code-injection equation admitted")
    # 14. missing provenance.
    _expect_error(lambda: canonical.create(record_type="identity.geometry",
                                           object_id="x",
                                           created_at="2026-09-09T00:00:00Z",
                                           provenance={}, body={}),
                  VALIDATION_ERROR, "missing provenance admitted")
    # 15. contradictory relation.
    _expect_error(lambda: rep.validate(
        {"source_id": "a", "target_id": "a", "predicate": "not_equal"},
        "relation", predicates=["not_equal"]),
        rep.RepresentationError, "contradictory relation admitted")
    # 16. malformed temporal metadata.
    _expect_error(lambda: canonical.create(record_type="identity.geometry",
                                           object_id="x",
                                           created_at="2026-02-31T25:00:00Z",
                                           provenance=GOLD_ARGS["provenance"],
                                           body={}),
                  VALIDATION_ERROR, "malformed temporal metadata "
                  "admitted")


def _test_translation_preservation():
    gained = canonical.translate(0.5, "scalar", "measurement",
                                 units="normalized")
    assert gained["lossy"] is False and gained["to_type"] == "measurement"
    assert gained["value"] == 0.5
    dropped = canonical.translate(0.5, "measurement", "scalar",
                                  units="normalized",
                                  context={"drop_units": True})
    assert dropped["lossy"] is True
    assert "units dropped" in dropped["losses"]
    _expect_error(lambda: canonical.translate(0.5, "measurement", "scalar"),
                  canonical.CanonicalError, "unit drop without consent "
                  "admitted")
    moved = canonical.translate("geo-0001", "identifier", "text",
                                context={"allow_identifier_to_text": True})
    assert moved["lossy"] is True
    _expect_error(lambda: canonical.translate("geo-0001", "identifier",
                                              "text"),
                  canonical.CanonicalError, "identifier contract dropped "
                  "without consent")
    a = canonical.create(**GOLD_ARGS)
    b = canonical.create(**GOLD_ARGS)
    metrics = canonical.semantic_preservation(a, b)
    assert all(metrics.values()), metrics
    altered = dict(b)
    altered["body"] = dict(altered["body"])
    altered["body"]["point"] = dict(altered["body"]["point"],
                                    value=[0.6, 0.46])
    metrics2 = canonical.semantic_preservation(a, altered)
    assert not metrics2["byte_equal"]
    assert not metrics2["value_equal"]
    assert not metrics2["semantic_equal"]
    assert metrics2["provenance_preserved"] is True
    assert metrics2["type_equal"] is True


def _test_schema_conformance():
    schema_path = canonical.schema_path()
    assert canonical.schema_present()
    doc = json.loads(schema_path.read_text(encoding="utf-8"))
    assert doc["$schema"] == oracle.SCHEMA_2020_12_META
    assert "knowledge-object" in doc["$id"]
    assert set(doc["required"]) == set(canonical.ENVELOPE_KEYS)
    assert len(doc["required"]) == len(canonical.ENVELOPE_KEYS)
    assert set(doc["properties"]) == set(canonical.ENVELOPE_KEYS)
    assert doc["additionalProperties"] is False
    body_schema = doc["properties"]["body"]
    type_enum = body_schema["additionalProperties"]["properties"]["type"]["enum"]
    assert set(type_enum) == EXPECTED_TYPES
    assert doc["properties"]["protocol"]["const"] == canonical.PROTOCOL
    assert doc["properties"]["schema_version"]["const"] == 1
    assert doc["properties"]["integrity"]["properties"]["alg"]["const"] == \
        "sha-256"
    obj = canonical.create(**GOLD_ARGS)
    for key in obj:
        assert key in doc["required"]
    ok, reports = oracle.schema_witness()
    assert ok, reports


def _test_digest_cross_witness():
    for body in (
        GOLD_ARGS["body"],
        {"probe": {"type": "measurement", "value": 0.004, "units": "tolerance"}},
        {"v": {"type": "vector", "value": [0.5, 0.46], "dim": 2}},
    ):
        obj = canonical.create(record_type="identity.geometry",
                               object_id="geo-x-0001",
                               created_at="2026-09-10T00:00:00Z",
                               provenance=GOLD_ARGS["provenance"],
                               body=body)
        assert oracle.oracle_digest(obj) == canonical.digest(obj)
        assert oracle_jcs.canonical_bytes(canonical.payload(obj)) == \
            canonical.canonical_bytes(canonical.payload(obj))
        assembly = oracle.independent_envelope(
            object_id=obj["object_id"], record_type=obj["record_type"],
            created_at=obj["created_at"], provenance=obj["provenance"],
            metadata=obj["metadata"], body=obj["body"])
        assert oracle.oracle_digest(assembly) == canonical.digest(obj)


def _test_oracle_corpus_agreement():
    for entry in oracle.CORPUS:
        expected = True
        impl_ok = _valid(entry["value"], entry["type"],
                         **entry.get("attrs", {}))
        oracle_ok, _ = oracle._validate_independent(
            entry["value"], entry["type"], **entry.get("attrs", {}))
        assert impl_ok == expected, ("corpus", entry, impl_ok)
        assert oracle_ok == expected, ("corpus-oracle", entry, oracle_ok)
    for entry in oracle.NEGATIVE_CORPUS:
        expected = False
        impl_ok = _valid(entry["value"], entry["type"],
                         **entry.get("attrs", {}))
        oracle_ok, _ = oracle._validate_independent(
            entry["value"], entry["type"], **entry.get("attrs", {}))
        assert impl_ok == expected, ("negative", entry, impl_ok)
        assert oracle_ok == expected, ("negative-oracle", entry, oracle_ok)


def _test_batch2_suite_contract():
    # Aggregate marker: the runner enforces the exact evidence count.
    assert oracle or canonical or rep  # always true when imports loaded
    assert GOLD_DIGEST
    assert len(EXPECTED_TYPES) == 22


for _name, _fn in sorted(globals().items()):
    if _name.startswith("_test_") and callable(_fn):
        _fn()

print("canonical_representation_types_registered=OK")
print("canonical_contracts_introspectable=OK")
print("canonical_atom_validation=OK")
print("canonical_geometry_contract_reused=OK")
print("canonical_temporal_validation=OK")
print("canonical_equation_symbolic_no_eval=OK")
print("canonical_graph_relation_foundation=OK")
print("canonical_provenance_contract=OK")
print("canonical_uncertainty_semantics=OK")
print("canonical_object_construction=OK")
print("canonical_object_jcs_integrity=OK")
print("canonical_embedded_gold_digest=OK")
print("canonical_detection_behaviour=OK")
print("canonical_negative_fail_closed=OK")
print("canonical_translation_preservation=OK")
print("canonical_schema_conformance=OK")
print("canonical_digest_cross_witness=OK")
print("canonical_oracle_corpus_agreement=OK")
print("canonical_batch2_suite_contract=OK")