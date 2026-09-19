"""MAYA world mapping — Representation -> World-Model Mapping (Batch #5).

Deterministic bridge between the representation layer (Batch #4) and the
world-model layer: it answers, for the *detected* representation, whether the
input may deterministically be treated as carrying a *world reference* — an
entity, event, measurement, relation, location, temporal interval, geometric
object, process/state, or a claim/assertion — and what remains unresolved.

Statuses (Part 1):

- KNOWN:       the detected representation maps to exactly one world kind and
               the world reference's normalized fields are complete.
- AMBIGUOUS:   the representation supports more than one distinct world
               mapping and the candidate list is bounded (timestamp role,
               interval-vs-duration ...). Ambiguity is preserved; nothing is
               forced.
- UNRESOLVED:  the representation is valid but no world reference can be
               determined from structure alone (bare number, free text,
               identifier, symbol, category, language, scalar, generic vector/
               matrix, structured envelope ...). Never invented.
- INVALID:     the representation was invalid, the provenance was malformed,
               or non-finite contamination was present. Fail-closed.

Epistemic separation (Part 4): representation validity NEVER makes a world
claim; a successfully parsed and mapped value never becomes WORLD STATE.
The result carries an explicit ``claim`` / ``world_state`` distinction: a
"measurement" mapping is a *candidate reference* whose factual character is
only as strong as the caller-declared epistemic/empirical evidence, and a
free-text or cultural statement is preserved *as a claim* with provenance —
it never promotes to a world fact through this layer. World state is never
mutated here; that would require an explicit validation pathway (not in this
batch).

Geometry (Part 8) is first-class: geometric candidates preserve their
coordinate space, space bounds, source and y-axis convention. Space is taken
from the input when declared, otherwise from the authoritative identity
``maya_identity/geometry/maya_geometry.json`` contract. Units/coordinate
systems are never reinterpreted.

Temporal (Part 9) is conservative: a timestamp maps to a temporal reference
but its semantic role (event_time / publication_time / retrieval_time /
processing_time) is left unresolved; a duration maps to a temporal interval/
duration candidate with unresolved bounds; the bus temporal contract stores
instants and is never bypassed.

Cryptographic extensibility (Part 10): the world-kind vocabulary reserves
encoded/encrypted data, hash, signature, key, certificate and cryptographic
claim kinds so future batches can map them without ever confusing encoded
data with encrypted data, a digest with a signature, or any of them with a
claim. This batch performs NO cryptographic detection or classification and
never labels identifier/hex-like input as a hash, key or signature.

Determinism: no randomness, no clock, no network, no eval/exec. Provenance
timestamps travel only when the caller supplies them.
"""
from __future__ import annotations

import copy
import math
import re

from . import detector
from . import epistemic
from . import representation
from .canonical import geometry_contract

WORLD_MAPPING_PROTOCOL = "maya.world_mapping.v1"
WORLD_MAPPING_PROTOCOL_VERSION = 1

WORLD_MAPPING_STATUSES = ("KNOWN", "AMBIGUOUS", "UNRESOLVED", "INVALID")

WORLD_KINDS = (
    "measurement", "event", "relation", "temporal_reference",
    "temporal_interval", "geometric_object", "geometric_point",
    "geometric_vector", "geometric_transform", "graph", "entity", "location",
    "process_state", "claim_assertion", "unknown_reference",
    "encoded_data", "encrypted_data", "hash", "signature", "key",
    "certificate", "cryptographic_claim",
)
WORLD_KIND_SET = frozenset(WORLD_KINDS)

RESERVED_CRYPTO_KINDS = frozenset({
    "encoded_data", "encrypted_data", "hash", "signature", "key",
    "certificate", "cryptographic_claim",
})

MAP_RESULT_KEYS = (
    "status", "detected_type", "world_kind", "candidate_reference",
    "normalized_fields", "mapping_evidence", "unresolved_fields",
    "provenance", "validation", "epistemic", "losses",
)

TIMESTAMP_ROLE_CANDIDATES = (
    "event_time", "publication_time", "retrieval_time", "processing_time",
)

_DURATION_SECONDS = {
    "ms": 0.001, "us": 1.0e-6, "µs": 1.0e-6, "s": 1.0, "min": 60.0,
    "h": 3600.0, "d": 86400.0,
}

_DURATION_PARTS_RE = re.compile(
    r"^[+-]?([0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*"
    r"(ms|us|µs|s|min|h|d)$")

_WORLD_STATE_MUTATION = "none"

_GEO_CONTRACT_CACHE = {}


def _identity_space():
    contract = _GEO_CONTRACT_CACHE.get("contract")
    if contract is None:
        try:
            contract = geometry_contract()
        except Exception:
            contract = {"space": (0.0, 1.0, 0.0, 1.0), "y_down": True}
        _GEO_CONTRACT_CACHE["contract"] = contract
    lo_x, hi_x, lo_y, hi_y = contract.get("space") or (0.0, 1.0, 0.0, 1.0)
    return {
        "space": [float(lo_x), float(hi_x), float(lo_y), float(hi_y)],
        "y_down": bool(contract.get("y_down", True)),
        "coordinate_system": "identity_maya_2d",
        "source": "maya_identity/geometry/maya_geometry.json",
    }


def _space_for(candidate):
    declared = candidate.get("space")
    if declared is not None:
        if isinstance(declared, (list, tuple)) and len(declared) == 4:
            try:
                space = [float(item) for item in declared]
            except (TypeError, ValueError):
                space = None
            if space is not None and all(math.isfinite(item)
                                         for item in space):
                return {"space": space, "coordinate_system": "declared_space",
                        "source": "input_declared", "y_down": None}
    identity = _identity_space()
    return {"space": identity["space"],
            "coordinate_system": identity["coordinate_system"],
            "source": identity["source"], "y_down": identity["y_down"]}


def _floats(value, limit=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return [number] if limit is None or len([number]) <= limit else None


def _point_coords(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            coords = [float(item) for item in value[:2]]
        except (TypeError, ValueError):
            return None
        if all(math.isfinite(item) for item in coords):
            return coords
        return None
    if isinstance(value, dict) and isinstance(value.get("point"),
                                              (list, tuple)):
        return _point_coords(value["point"])
    return None


def _component_list(value):
    if isinstance(value, (list, tuple)):
        try:
            items = [float(item) for item in value]
        except (TypeError, ValueError):
            return None
        if items and all(math.isfinite(item) for item in items):
            return items
        return None
    if isinstance(value, dict) and isinstance(value.get("components"),
                                              (list, tuple)):
        return _component_list(value["components"])
    return None


def _is_iso_timestamp(text):
    return bool(isinstance(text, str)
                and representation.ISO_UTC_RE.match(text.strip()))


def _duration_seconds(text):
    if not isinstance(text, str):
        return None
    match = _DURATION_PARTS_RE.match(text.strip())
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


def _validate_provenance_for_mapping(provenance):
    if provenance is None:
        return {"source": "undeclared", "retrieved_at": None,
                "evidence_type": None, "confidence": None,
                "status": "unattributed"}
    if not isinstance(provenance, dict):
        return None
    try:
        representation.validate_provenance(provenance)
    except representation.RepresentationError:
        return None
    return dict(provenance)


def _epistemic_status_default(epistemic_status, domain):
    if epistemic_status is not None:
        return epistemic_status
    if domain in epistemic.CULTURAL_DOMAINS:
        return "TRADITIONAL"
    return "UNKNOWN"


def _epistemic_for(representation_valid, epistemic_status=None,
                   empirical_status=None, domain=None):
    effective_status = _epistemic_status_default(epistemic_status, domain)
    effective_empirical = empirical_status or "UNKNOWN"
    try:
        return epistemic.frame(
            representation_valid=bool(representation_valid),
            epistemic_status=effective_status,
            empirical_status=effective_empirical,
            domain=domain,
        )
    except epistemic.EpistemicError:
        return None


def classify_claim(epi):
    """Label the claim character of a mapping from its epistemic frame."""
    if not isinstance(epi, dict):
        return "claim-undefined"
    if epi.get("claims_nothing_factual"):
        return "non-factual-claim"
    if epi.get("epistemic_status") in epistemic.FACTUAL_CLAIMING_STATUSES:
        return "factual-claim-candidate"
    return "claim-undefined"


def _claim_factual(epi):
    if not isinstance(epi, dict):
        return False
    if epi.get("claims_nothing_factual"):
        return False
    return bool(epi.get("epistemic_status")
                in epistemic.FACTUAL_CLAIMING_STATUSES)


def _evidence(mapping_evidence, validation_reason=None):
    evidence = dict(mapping_evidence)
    if validation_reason is not None:
        evidence["validation_reason"] = validation_reason
    return evidence


def _invalid_result(reason, detected_type=None, provenance=None,
                    evidence_reason=None, world_state_mutation=_WORLD_STATE_MUTATION):
    prov = _validate_provenance_for_mapping(provenance)
    if prov is None:
        prov = {"source": "undeclared", "retrieved_at": None,
                "evidence_type": None, "confidence": None,
                "status": "unattributed"}
        reason = "%s; provenance rejected" % (reason,)
    epi = _epistemic_for(False)
    return {
        "status": "INVALID",
        "detected_type": detected_type,
        "world_kind": None,
        "candidate_reference": None,
        "normalized_fields": {},
        "mapping_evidence": _evidence({
            "method": "structure-derived",
            "representation_status": "INVALID",
            "world_reference_resolved": False,
            "claim_status": "claim-undefined",
            "world_state_mutation": world_state_mutation,
            "conservatism": ["fail-closed: no world reference is produced"],
            "crypto_class": "not_classified",
        }, evidence_reason),
        "unresolved_fields": ["world_reference"],
        "provenance": prov,
        "validation": {
            "representation_valid": False,
            "world_reference_resolved": False,
            "claim_factual": False,
            "validation_status": "unvalidated",
            "external_validation": "unvalidated",
            "reason": reason,
        },
        "epistemic": epi,
        "losses": [reason],
    }


def _assemble_reference(status, world_kind, normalized_fields, unresolved,
                        candidate_reference, mapping_evidence, losses,
                        provenance, detected_type, reason=None,
                        representation_valid=True,
                        epistemic_status=None, empirical_status=None,
                        domain=None):
    world_resolved = status == "KNOWN"
    epi = _epistemic_for(representation_valid,
                         epistemic_status=epistemic_status,
                         empirical_status=empirical_status, domain=domain)
    claim_status = classify_claim(epi)
    validation_status = "unvalidated"
    if isinstance(epi, dict) and epi.get("validation_hint"):
        validation_status = epi["validation_hint"]
    evidence = dict(mapping_evidence)
    evidence.update({
        "representation_status": "KNOWN" if representation_valid
                               else ("INVALID" if status == "INVALID"
                                     else "AMBIGUOUS" if status == "AMBIGUOUS"
                                     else "UNRESOLVED"),
        "world_reference_resolved": world_resolved,
        "claim_status": claim_status,
        "world_state_mutation": _WORLD_STATE_MUTATION,
        "crypto_class": "not_classified",
        "method": evidence.get("method", "structure-derived"),
    })
    if reason is not None:
        evidence["validation_reason"] = reason
    return {
        "status": status,
        "detected_type": detected_type,
        "world_kind": world_kind,
        "candidate_reference": candidate_reference,
        "normalized_fields": dict(normalized_fields),
        "mapping_evidence": evidence,
        "unresolved_fields": sorted(set(unresolved)),
        "provenance": dict(provenance) if isinstance(provenance, dict)
                      else provenance,
        "validation": {
            "representation_valid": bool(representation_valid),
            "world_reference_resolved": world_resolved,
            "claim_factual": _claim_factual(epi),
            "validation_status": validation_status,
            "external_validation": "unvalidated",
            "reason": reason,
        },
        "epistemic": epi,
        "losses": list(losses),
    }


def _geometry_reference(kind, space_block, extra=None):
    reference = {"kind": kind, "space": space_block["space"],
                 "coordinate_system": space_block["coordinate_system"],
                 "space_source": space_block["source"],
                 "space_unit": "identity_normalized"}
    reference.update(dict(extra or {}))
    return reference


def _map_known(detection, original, provenance, epistemic_status,
               empirical_status, domain):
    detected_type = detection.get("detected_type")
    candidate = detection.get("canonical_candidate")
    candidate = copy.deepcopy(candidate) if isinstance(candidate, dict) else {}

    if detected_type == "measurement":
        value = candidate.get("value")
        units = candidate.get("units")
        reference = {"kind": "measurement", "value": value, "units": units}
        return _assemble_reference(
            "KNOWN", "measurement", {"value": value, "units": units}, [],
            reference, {"conservatism": ["unit %r preserved; magnitude is not "
                                         "converted or reinterpreted" % (units,)]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "event":
        value = candidate.get("value") or {}
        kind = value.get("kind")
        at = value.get("at")
        event_types = list(candidate.get("event_types") or [])
        reference = {"kind": "event", "event_type": kind, "at": at}
        normalized = {"kind": kind, "at": at, "event_types": event_types}
        return _assemble_reference(
            "KNOWN", "event", normalized, [],
            reference,
            {"conservatism": ["the event timestamp is preserved as the "
                              "candidate event time; no other temporal role"
                              " is inferred"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "relation":
        value = candidate.get("value") or {}
        source_id = value.get("source_id")
        target_id = value.get("target_id")
        predicate = value.get("predicate")
        predicates = list(candidate.get("predicates") or [])
        reference = {"kind": "relation", "source_id": source_id,
                     "target_id": target_id, "predicate": predicate}
        normalized = {"source_id": source_id, "target_id": target_id,
                      "predicate": predicate, "predicate_universe": predicates}
        return _assemble_reference(
            "KNOWN", "relation", normalized, [], reference,
            {"conservatism": ["relation members are preserved verbatim; "
                              "predicate meaning is not asserted"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "temporal_interval":
        value = candidate.get("value") or {}
        start = value.get("start")
        end = value.get("end")
        reference = {"kind": "temporal_interval", "start": start, "end": end}
        normalized = {"start": start, "end": end}
        return _assemble_reference(
            "KNOWN", "temporal_interval", normalized, [], reference,
            {"conservatism": ["interval bounds preserved; the interval "
                              "semantic (activity/validity/...) is not "
                              "asserted"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "geometric_point":
        coords = _point_coords(candidate.get("value"))
        space = _space_for(candidate)
        normalized = {"geometry_kind": "point", "point": coords,
                      "space": space["space"],
                      "space_source": space["source"],
                      "space_unit": "identity_normalized",
                      "coordinate_system": space["coordinate_system"],
                      "y_down": space["y_down"]}
        reference = _geometry_reference("geometric_point", space,
                                        {"point": coords})
        return _assemble_reference(
            "KNOWN", "geometric_point", normalized, [], reference,
            {"conservatism": ["coordinate space and y-axis convention are "
                              "preserved; the point is not interpreted as a "
                              "location or any semantic coordinate"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "geometric_vector":
        components = _component_list(candidate.get("value"))
        dimensions = len(components) if components is not None else None
        space = _space_for(candidate)
        normalized = {"geometry_kind": "vector", "components": components,
                      "dimensions": dimensions, "space": space["space"],
                      "space_source": space["source"],
                      "space_unit": "identity_normalized",
                      "coordinate_system": space["coordinate_system"],
                      "y_down": space["y_down"]}
        reference = _geometry_reference("geometric_vector", space,
                                        {"dimensions": dimensions,
                                         "components": components})
        return _assemble_reference(
            "KNOWN", "geometric_vector", normalized, [], reference,
            {"conservatism": ["a geometric vector is preserved as a vector; "
                              "it is never reinterpreted as a point, a "
                              "location, a displacement or a velocity"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "geometric_transform":
        value = candidate.get("value") or {}
        kind = value.get("kind")
        parameters = value.get("parameters")
        space = _space_for(candidate)
        normalized = {"transform_kind": kind, "parameters": parameters,
                      "space": space["space"], "space_source": space["source"],
                      "space_unit": "identity_normalized",
                      "coordinate_system": space["coordinate_system"],
                      "y_down": space["y_down"]}
        reference = _geometry_reference("geometric_transform", space,
                                        {"transform_kind": kind,
                                         "parameters": parameters})
        return _assemble_reference(
            "KNOWN", "geometric_transform", normalized, [], reference,
            {"conservatism": ["transform kind and parameters are preserved "
                              "verbatim; their geometric effect is not "
                              "recomputed or re-derived"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "geometric_object":
        value = candidate.get("value") or {}
        geometry_kind = value.get("geometry_kind")
        data = value.get("data")
        space = _space_for(candidate)
        normalized = {"geometry_kind": geometry_kind, "data": data,
                      "space": space["space"], "space_source": space["source"],
                      "space_unit": "identity_normalized",
                      "coordinate_system": space["coordinate_system"],
                      "y_down": space["y_down"]}
        reference = _geometry_reference("geometric_object", space,
                                        {"geometry_kind": geometry_kind})
        return _assemble_reference(
            "KNOWN", "geometric_object", normalized, [], reference,
            {"conservatism": ["object data is preserved in its declared "
                              "coordinate space; boundaries/units are not "
                              "reinterpreted"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "graph":
        value = candidate.get("value") or {}
        nodes = value.get("nodes")
        edges = value.get("edges")
        node_count = len(nodes) if isinstance(nodes, (list, tuple)) else None
        edge_count = len(edges) if isinstance(edges, (list, tuple)) else None
        normalized = {"node_count": node_count, "edge_count": edge_count,
                      "directed": None}
        reference = {"kind": "graph", "nodes": node_count,
                     "edges": edge_count, "directed": None}
        return _assemble_reference(
            "KNOWN", "graph", normalized, [], reference,
            {"conservatism": ["graph structure only; node/edge identifiers "
                              "are not resolved to world entities"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type in ("probability", "confidence", "uncertainty"):
        value = candidate.get("value")
        metric = {detected_type: value}
        normalized = {"metric": metric}
        reference = {"kind": "claim_assertion", "claim_target": None,
                     "metric": metric,
                     "assertion_note": "quantified estimate; not a world fact"}
        return _assemble_reference(
            "KNOWN", "claim_assertion", normalized, [], reference,
            {"conservatism": ["a %s value is a quantified epistemic estimate,"
                              " never a world fact or state" % detected_type]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "equation":
        value = candidate.get("value")
        language = candidate.get("language")
        normalized = {"expression": value, "language": language}
        reference = {"kind": "claim_assertion", "claim_target": None,
                     "expression": value, "language": language,
                     "assertion_note": "mathematical statement; recovered "
                                       "meaning is not asserted"}
        return _assemble_reference(
            "KNOWN", "claim_assertion", normalized, [], reference,
            {"conservatism": ["the equation is preserved as a mathematical "
                              "statement; its ground truth or factual "
                              "character is not asserted"]},
            [], provenance, detected_type,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    unresolved = {"world_reference", "world_kind"}
    if detected_type == "text":
        normalized = {"text": candidate.get("value")}
        losses = ["no NLU: free-text proposition structure is not derived",
                  "the source assertion is preserved as a claim only; world "
                  "state is never inferred from it"]
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["free text is never promoted to a world fact; "
                              "its claim character is carried by the "
                              "epistemic frame and provenance"]},
            losses, provenance, detected_type, representation_valid=True,
            epistemic_status=epistemic_status, empirical_status=empirical_status,
            domain=domain)

    if detected_type == "scalar":
        normalized = {"value": candidate.get("value")}
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["a scalar number receives no age/weight/id/"
                              "probability/coordinate/quantity semantic "
                              "without explicit declaration"]},
            ["scalar value preserved; no semantic role assigned"], provenance,
            detected_type, epistemic_status=epistemic_status,
            empirical_status=empirical_status, domain=domain)

    if detected_type == "identifier":
        normalized = {"identifier": candidate.get("value")}
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["an identifier is a potential reference but "
                              "no entity resolution is performed here; it is "
                              "not classified as a hash/key/signature"]},
            ["identifier preserved; reference unresolved"], provenance,
            detected_type, epistemic_status=epistemic_status,
            empirical_status=empirical_status, domain=domain)

    if detected_type == "symbol":
        normalized = {"symbol": candidate.get("value"),
                      "language": candidate.get("language")}
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["a symbolic token is preserved without "
                              "assigned world function"]},
            ["symbol preserved; no world function assigned"], provenance,
            detected_type, epistemic_status=epistemic_status,
            empirical_status=empirical_status, domain=domain)

    if detected_type == "category":
        normalized = {"category_code": candidate.get("value"),
                      "code_set": candidate.get("code_set")}
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["a category code classifies; the classified "
                              "subject is not resolved to a world entity"]},
            ["category preserved; subject unresolved"], provenance,
            detected_type, epistemic_status=epistemic_status,
            empirical_status=empirical_status, domain=domain)

    if detected_type == "language":
        normalized = {"language_tag": candidate.get("value")}
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["a language tag is metadata about the "
                              "representation, not a world entity"]},
            ["language metadata preserved; no world reference"], provenance,
            detected_type, epistemic_status=epistemic_status,
            empirical_status=empirical_status, domain=domain)

    if detected_type == "vector":
        components = _component_list(candidate.get("value"))
        normalized = {"components": components}
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["a generic vector is preserved structurally;"
                              " it is not auto-mapped to a geometric "
                              "point/vector/velocity"]},
            ["generic vector preserved; world reference unresolved"],
            provenance, detected_type, epistemic_status=epistemic_status,
            empirical_status=empirical_status, domain=domain)

    if detected_type == "matrix":
        normalized = {"rows": candidate.get("value")}
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["a matrix is preserved structurally; it is not "
                              "auto-mapped to transform/data/adjacency"]},
            ["matrix preserved; world reference unresolved"], provenance,
            detected_type, epistemic_status=epistemic_status,
            empirical_status=empirical_status, domain=domain)

    if detected_type == "structured_canonical_object":
        normalized = {"record_type": candidate.get("record_type"),
                      "protocol": candidate.get("protocol")}
        return _assemble_reference(
            "UNRESOLVED", "unknown_reference", normalized, unresolved, None,
            {"conservatism": ["a canonical envelope is a record carrier; its "
                              "world reference requires member inspection "
                              "(not performed by this layer)"]},
            ["envelope preserved; member-level mapping not performed"],
            provenance, detected_type, epistemic_status=epistemic_status,
            empirical_status=empirical_status, domain=domain)

    return _invalid_result("no world mapping handler for detected type %r"
                           % (detected_type,), detected_type=detected_type,
                           provenance=provenance)


def _map_ambiguous(detection, original, provenance, epistemic_status,
                   empirical_status, domain):
    candidate_types = list(detection["evidence"].get("candidate_types") or ())
    evidence = detection["evidence"]
    reason = evidence.get("ambiguity_reason")

    raw = detection.get("original")
    if raw is None:
        raw = original
    duration = None
    if raw is not None:
        duration = _duration_seconds(raw)

    if "temporal" in candidate_types or duration is not None:
        timestamp = None
        if isinstance(raw, str) and _is_iso_timestamp(raw):
            timestamp = raw.strip()
        if timestamp is not None:
            normalized = {"timestamp": timestamp,
                          "temporal_role": None}
            reference = {"kind": "temporal_reference", "timestamp": timestamp,
                         "role_candidates": list(TIMESTAMP_ROLE_CANDIDATES)}
            return _assemble_reference(
                "AMBIGUOUS", "temporal_reference", normalized,
                ["temporal_role"], reference,
                {"conservatism": ["a timestamp is a temporal reference; its "
                                  "semantic role (event/publication/"
                                  "retrieval/processing) is unresolved"]},
                ["temporal role unresolved; bus temporal contract remains "
                 "authoritative for instants"], provenance, "temporal",
                representation_valid=False,
                epistemic_status=epistemic_status,
                empirical_status=empirical_status, domain=domain)
        if duration is not None:
            normalized = {"duration_seconds": duration, "start": None,
                          "end": None}
            reference = {"kind": "temporal_interval", "start": None,
                         "end": None, "duration_seconds": duration,
                         "candidate_kinds": ["temporal_interval", "duration"]}
            return _assemble_reference(
                "AMBIGUOUS", "temporal_interval", normalized,
                ["start", "end"],
                reference,
                {"conservatism": ["a duration is a temporal interval/duration "
                                  "candidate; its interval bounds are "
                                  "unresolved and the bus temporal contract "
                                  "is never bypassed"]},
                ["duration bounds unresolved"], provenance, "temporal",
                representation_valid=False,
                epistemic_status=epistemic_status,
                empirical_status=empirical_status, domain=domain)

    return _assemble_reference(
        "AMBIGUOUS", None, {"preserved_value": raw}, ["world_reference",
                                                      "world_kind"], None,
        {"conservatism": ["representation ambiguity is preserved; no world "
                          "candidate is invented for an ambiguous input"],
         "ambiguity_reason": reason or "ambiguous representation"},
        ["ambiguous representation carries no committed world reference"],
        provenance, None, representation_valid=False,
        epistemic_status=epistemic_status, empirical_status=empirical_status,
        domain=domain)


def _map_unknown(detection, original, provenance, epistemic_status,
                 empirical_status, domain):
    value = detection.get("original")
    if value is None:
        value = original
    return _assemble_reference(
        "UNRESOLVED", None, {"preserved_value": value}, ["world_reference",
                                                         "world_kind"], None,
        {"conservatism": ["the input is structurally valid but matches no "
                          "supported representation; no world mapping is "
                          "forced"]},
        ["no supported representation; world reference unresolved"],
        provenance, None, representation_valid=False,
        epistemic_status=epistemic_status, empirical_status=empirical_status,
        domain=domain)


def map_to_world(detection, original=None, *, provenance=None,
                 epistemic_status=None, empirical_status=None, domain=None):
    """Map a Batch #4 detector result to the world-model vocabulary.

    ``original`` preserves the raw input for AMBIGUOUS/UNKNOWN results.
    ``provenance`` is caller-supplied (this layer owns no clock); it is
    validated against the shared provenance contract. ``epistemic_status``,
    ``empirical_status`` and ``domain`` are declared evidence, never inferred
    from structure. Returns the complete mapping result contract.
    """
    if not isinstance(detection, dict) or "status" not in detection:
        return _invalid_result("detection is not a valid detector result",
                               provenance=provenance)
    det_status = detection.get("status")
    if det_status not in detector.VERDICTS:
        return _invalid_result("detection status %r outside the verdict "
                               "vocabulary" % (det_status,),
                               provenance=provenance)

    provenance = _validate_provenance_for_mapping(provenance)
    if provenance is None:
        return _invalid_result("provenance rejected: must be a dict of the "
                               "shared provenance contract",
                               provenance=None)

    detection = dict(detection)
    detection["original"] = detection.get("canonical_candidate") \
        if detection.get("original") is None else detection["original"]
    if detection["original"] is None:
        detection["original"] = original

    if det_status == "INVALID":
        reason = (detection["evidence"].get("validation_reason")
                  or "representation invalid (fail-closed)")
        return _invalid_result(reason,
                               detected_type=detection.get("detected_type"),
                               provenance=provenance,
                               evidence_reason=reason)
    if det_status == "KNOWN":
        return _map_known(detection, original, provenance, epistemic_status,
                          empirical_status, domain)
    if det_status == "AMBIGUOUS":
        return _map_ambiguous(detection, original, provenance,
                              epistemic_status, empirical_status, domain)
    return _map_unknown(detection, original, provenance, epistemic_status,
                        empirical_status, domain)


def validate_mapping(mapping):
    """Structural validation of a mapping result (corruption guard)."""
    if not isinstance(mapping, dict):
        return {"valid": False, "reason": "mapping must be a dict"}
    if set(mapping) != set(MAP_RESULT_KEYS):
        return {"valid": False,
                "reason": "keys differ from the mapping contract: %s"
                          % (sorted(MAP_RESULT_KEYS),)}
    status = mapping.get("status")
    if status not in WORLD_MAPPING_STATUSES:
        return {"valid": False,
                "reason": "status %r outside %s"
                          % (status, WORLD_MAPPING_STATUSES)}
    world_kind = mapping.get("world_kind")
    if world_kind is not None and world_kind not in WORLD_KIND_SET:
        return {"valid": False, "reason": "world_kind %r outside the "
                                          "vocabulary" % (world_kind,)}
    detected_type = mapping.get("detected_type")
    if detected_type is not None and not isinstance(detected_type, str):
        return {"valid": False, "reason": "detected_type must be a string or "
                                          "null"}
    candidate_reference = mapping.get("candidate_reference")
    if candidate_reference is not None \
            and not isinstance(candidate_reference, dict):
        return {"valid": False,
                "reason": "candidate_reference must be a dict or null"}
    if not isinstance(mapping.get("normalized_fields"), dict):
        return {"valid": False, "reason": "normalized_fields must be a dict"}
    if not isinstance(mapping.get("mapping_evidence"), dict):
        return {"valid": False,
                "reason": "mapping_evidence must be a dict"}
    unresolved = mapping.get("unresolved_fields")
    if not isinstance(unresolved, list) or not all(
            isinstance(item, str) for item in unresolved):
        return {"valid": False,
                "reason": "unresolved_fields must be a list of strings"}
    provenance = mapping.get("provenance")
    if provenance is not None and not isinstance(provenance, dict):
        return {"valid": False, "reason": "provenance must be a dict or null"}
    if not isinstance(mapping.get("validation"), dict):
        return {"valid": False, "reason": "validation must be a dict"}
    epistemic_block = mapping.get("epistemic")
    if epistemic_block is not None and not isinstance(epistemic_block, dict):
        return {"valid": False, "reason": "epistemic must be a dict or null"}
    if not isinstance(mapping.get("losses"), list):
        return {"valid": False, "reason": "losses must be a list"}
    return {"valid": True, "reason": None}


def contract_keys():
    return list(MAP_RESULT_KEYS)


__all__ = (
    "WORLD_MAPPING_PROTOCOL", "WORLD_MAPPING_PROTOCOL_VERSION",
    "WORLD_MAPPING_STATUSES", "WORLD_KINDS", "WORLD_KIND_SET",
    "RESERVED_CRYPTO_KINDS", "MAP_RESULT_KEYS", "TIMESTAMP_ROLE_CANDIDATES",
    "map_to_world", "validate_mapping", "classify_claim", "contract_keys",
)