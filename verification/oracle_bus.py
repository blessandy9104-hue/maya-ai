"""Independent state-bus oracle (Batch #3).

This module is deliberately independent from ``maya_runtime.intelligence.bus``:
it imports only the standard library plus the verification-team's own oracle
primitives (``oracle_jcs`` and ``oracle_representation``). It re-derives the
unified-state contract from first principles and checks a bus record against
it: required fields, type restrictions, conflict rules, temporal rules,
provenance presence, safety-state invariants, and the canonical digest.

A record that fails the oracle is a discrepancy by construction (the
implementation and the oracle disagree), independent of anything Maya's code
says about itself.
"""
import hashlib
import importlib.util
import os
import sys

_ORACLE_REP = None
_ORACLE_JCS = None


def _load_oracles():
    """Load the sibling verification oracles (never import Maya's bus)."""
    global _ORACLE_REP, _ORACLE_JCS
    if _ORACLE_REP is not None:
        return
    directory = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, directory)
    entries = {
        "oracle_representation": "oracle_representation.py",
        "oracle_jcs": "oracle_jcs.py",
    }
    loaded = {}
    for name, filename in entries.items():
        path = os.path.join(directory, filename)
        spec = importlib.util.spec_from_file_location(
            name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    _ORACLE_REP = loaded["oracle_representation"]
    _ORACLE_JCS = loaded["oracle_jcs"]


# Independent contract tables (re-derived here, never imported from Maya).
ENVELOPE_KEYS = frozenset({
    "protocol", "protocol_version", "schema", "schema_version", "state_id",
    "source", "state_kind", "declaration", "temporal", "provenance",
    "confidence", "validation_status", "input", "knowledge", "context",
    "cognitive", "world", "memory", "learning", "safety", "persona",
    "geometry", "expression", "transform_history", "digest",
})
PROTOCOL = "maya.unified_state"
SCHEMA_ID = "maya:unified-state:1"
STATE_KINDS = frozenset({"STATE", "EVENT", "KNOWLEDGE", "EVIDENCE",
                         "DERIVED_COGNITION", "EXPRESSION"})
DECLARATIONS = frozenset({
    "FACT", "OBSERVATION", "CALCULATION", "INFERENCE", "INTERPRETATION",
    "HYPOTHESIS", "USER_PROVIDED", "EXTERNAL_REPORT", "UNKNOWN"})
VALIDATION_STATUSES = frozenset(
    {"unvalidated", "validated", "disputed", "contradicted", "unknown"})
CONFLICT_STATUSES = frozenset(
    {"SUPPORTED", "DISPUTED", "CONTRADICTED", "UNKNOWN"})
SAFETY_STATUSES = frozenset({"safe", "hold", "blocked", "unknown"})
TEMPORAL_FIELDS = ("event_time", "publication_time", "retrieval_time",
                   "processing_time", "state_time")
DIGEST_ALG = "sha-256"
SAFETY_HOLD_TOKENS = {"hold": "safety_hold", "blocked": "safety_blocked"}

# Standalone contract (used by the sample records).
_T = "2026-09-10T12:00:00Z"


def _iso_ok(text):
    return _ORACLE_REP._iso_utc_ok(text)


def _identifier_ok(value):
    return _ORACLE_REP._validate_independent(value, "identifier")[0]


def _text_ok(value):
    return _ORACLE_REP._validate_independent(value, "text")[0]


def _prov_ok(provenance):
    return _ORACLE_REP._validate_independent(provenance, "provenance")[0]


def _conf_ok(value):
    return (value is None
            or (_ORACLE_REP._number_ok(value) and 0.0 <= value <= 1.0))


def _typed_ok(declared):
    """A declared typed value must name a known type and satisfy it."""
    if not isinstance(declared, dict):
        return False
    if "type" not in declared or "value" not in declared:
        return False
    type_name = declared["type"]
    value = declared["value"]
    attrs = {k: v for k, v in declared.items()
             if k in ("units", "dim", "domain", "space", "code_set",
                      "language", "precision")}
    ok, _ = _ORACLE_REP._validate_independent(value, type_name, **attrs)
    return ok


def canonical_bytes_without_digest(record):
    """RFC 8785 canonical bytes of the envelope minus its ``digest`` member."""
    if not isinstance(record, dict):
        raise TypeError("bus oracle input must be a dict envelope")
    payload = {key: value for key, value in record.items() if key != "digest"}
    return _ORACLE_JCS.canonical_bytes(payload)


def digest_of(record):
    return hashlib.sha256(canonical_bytes_without_digest(record)).hexdigest()


# ---------------------------------------------------------------------------
# structural + contract checks
# ---------------------------------------------------------------------------

def check_envelope(record):
    failures = []
    if not isinstance(record, dict):
        return ["envelope must be a dict"]
    if set(record) != ENVELOPE_KEYS:
        failures.append("envelope keys != contract: %s"
                        % sorted(set(record) ^ ENVELOPE_KEYS))
    if record.get("protocol") != PROTOCOL:
        failures.append("protocol != %r" % PROTOCOL)
    if record.get("schema") != SCHEMA_ID:
        failures.append("schema != %r" % SCHEMA_ID)
    if record.get("protocol_version") != 1:
        failures.append("protocol_version != 1")
    if record.get("schema_version") != 1:
        failures.append("schema_version != 1")
    if (record.get("digest") or {}).get("alg") != DIGEST_ALG:
        failures.append("digest algorithm != %s" % DIGEST_ALG)
    if record.get("digest", {}).get("digest") != digest_of(record):
        failures.append("recorded digest != independent JCS/SHA-256 digest")
    return failures


def check_required_fields(record):
    failures = []
    if not _identifier_ok(record.get("state_id")):
        failures.append("state_id is not a valid identifier")
    if not _identifier_ok(record.get("source")):
        failures.append("source is not a valid identifier")
    if record.get("state_kind") not in STATE_KINDS:
        failures.append("state_kind %r not in %s"
                        % (record.get("state_kind"), sorted(STATE_KINDS)))
    if record.get("declaration") not in DECLARATIONS:
        failures.append("declaration %r not in %s"
                        % (record.get("declaration"), sorted(DECLARATIONS)))
    if record.get("validation_status") not in VALIDATION_STATUSES:
        failures.append("validation_status %r not allowed"
                        % (record.get("validation_status"),))
    return failures


def check_provenance(record):
    provenance = record.get("provenance")
    if provenance is None:
        return ["provenance is required (fail closed); record has none"]
    if not _prov_ok(provenance):
        return ["provenance lacks source/retrieved_at/evidence_type/"
                "confidence or a valid ISO-8601 UTC retrieved_at"]
    return []


def check_temporal(record):
    failures = []
    temporal = record.get("temporal") or {}
    if not isinstance(temporal, dict):
        return ["temporal must be a dict"]
    unknown = set(temporal) - set(TEMPORAL_FIELDS)
    if unknown:
        failures.append("temporal carries unknown fields %s"
                        % sorted(unknown))
    ordered = []
    for field in TEMPORAL_FIELDS:
        value = temporal.get(field)
        if value is None:
            continue
        if not _iso_ok(value):
            failures.append("temporal.%s is not RFC 3339 UTC" % field)
            continue
        ordered.append((field, value))
    for (field, value), (prior_field, prior_value) in zip(ordered[1:],
                                                          ordered):
        if value < prior_value:
            failures.append("temporal order violated: %s (%r) precedes %r"
                            % (field, value, prior_value))
    state_kind = record.get("state_kind")
    if state_kind in ("EVENT", "EVIDENCE") and temporal.get("event_time") \
            is None:
        failures.append("%s records require an explicit event_time"
                        % state_kind)
    return failures


def check_conflicts(record):
    failures = []
    world = record.get("world") or {}
    conflicts = world.get("conflicts") or []
    if not isinstance(conflicts, list):
        return ["world.conflicts must be a list"]
    for index, entry in enumerate(conflicts):
        if not isinstance(entry, dict):
            failures.append("conflicts[%d] must be a dict" % index)
            continue
        for field in ("subject", "predicate", "claim_a", "claim_b",
                      "evidence_a", "evidence_b", "status"):
            if field not in entry:
                failures.append("conflicts[%d] missing %s" % (index, field))
        status = entry.get("status")
        if status not in CONFLICT_STATUSES:
            failures.append("conflicts[%d].status %r not allowed"
                            % (index, status))
        if entry.get("claim_a") is not None and \
                entry.get("claim_a") == entry.get("claim_b"):
            failures.append("conflicts[%d] reports equal claims as "
                            "conflicting" % index)
    declared_status = world.get("conflict_status")
    if declared_status is not None and declared_status not in CONFLICT_STATUSES:
        failures.append("world.conflict_status %r not allowed"
                        % (declared_status,))
    if conflicts and declared_status not in ("DISPUTED", "CONTRADICTED"):
        failures.append("world.conflicts present but conflict_status %r "
                        "does not mark the dispute" % (declared_status,))
    return failures


def check_safety_invariants(record):
    failures = []
    safety = record.get("safety") or {}
    status = safety.get("status")
    if status not in SAFETY_STATUSES:
        return ["safety.status %r not in %s"
                % (status, sorted(SAFETY_STATUSES))]
    if not _identifier_ok(safety.get("source")):
        failures.append("safety.source is not a valid identifier")
    if safety.get("reason") is not None and not _text_ok(safety["reason"]):
        failures.append("safety.reason must be text")
    budget = safety.get("budget")
    if budget is not None and (not isinstance(budget, int)
                               or isinstance(budget, bool) or budget < 0):
        failures.append("safety.budget must be a non-negative integer")
    expression = record.get("expression") or {}
    holds = expression.get("holds") or []
    required = SAFETY_HOLD_TOKENS.get(status)
    if required is not None and required not in holds:
        failures.append("safety.status %r requires expression hold %r "
                        "downstream; it is missing" % (status, required))
    return failures


def check_confidence(record):
    failures = []
    confidence = record.get("confidence") or {}
    if not _conf_ok(confidence.get("value")):
        failures.append("confidence.value must be in [0, 1]")
    if not _conf_ok(confidence.get("uncertainty")):
        failures.append("confidence.uncertainty must be in [0, 1]")
    return failures


def check_input(record):
    failures = []
    inp = record.get("input") or {}
    if not isinstance(inp, dict):
        return ["input must be a dict"]
    if inp.get("declared") is not None and not _typed_ok(inp["declared"]):
        failures.append("input.declared is not a valid typed value")
    regime = inp.get("detected_regime")
    if regime not in ("KNOWN", "INVALID", "AMBIGUOUS", "UNKNOWN"):
        failures.append("input.detected_regime %r not allowed" % (regime,))
    return failures


def check_typed_members(record):
    failures = []
    knowledge = record.get("knowledge") or {}
    world = record.get("world") or {}
    geometry = record.get("geometry") or {}
    summary = knowledge.get("summary")
    if summary is not None and not _text_ok(summary):
        failures.append("knowledge.summary must be text")
    for key, declared in (world.get("world_summary") or {}).items():
        if not _typed_ok(declared):
            failures.append("world.world_summary.%s is not a valid typed "
                            "value" % key)
    for key, declared in (geometry.get("expressions") or {}).items():
        if not _typed_ok(declared):
            failures.append("geometry.expressions.%s is not a valid typed "
                            "value" % key)
    return failures


def oracle_check(record):
    """Full independent check. Returns (ok, failures)."""
    failures = []
    failures.extend(check_envelope(record))
    failures.extend(check_required_fields(record))
    failures.extend(check_provenance(record))
    failures.extend(check_temporal(record))
    failures.extend(check_conflicts(record))
    failures.extend(check_safety_invariants(record))
    failures.extend(check_confidence(record))
    failures.extend(check_input(record))
    failures.extend(check_typed_members(record))
    return not failures, failures


# ---------------------------------------------------------------------------
# sample record, exercised standalone
# ---------------------------------------------------------------------------

def make_sample_record():
    """A self-digested record built entirely from independent primitives."""
    base = {
        "protocol": PROTOCOL, "protocol_version": 1,
        "schema": SCHEMA_ID, "schema_version": 1,
        "state_id": "oracle-bus-1", "source": "oracle.bus",
        "state_kind": "STATE", "declaration": "INTERPRETATION",
        "temporal": {"event_time": _T, "publication_time": _T,
                     "processing_time": _T, "state_time": _T},
        "provenance": {"source": "oracle.bus", "source_url": None,
                       "retrieved_at": _T, "evidence_type": "observation",
                       "confidence": "high", "claim": "oracle sample"},
        "confidence": {"value": 0.8, "uncertainty": 0.1},
        "validation_status": "validated",
        "input": {"declared": {"type": "text", "value": "oracle sample"},
                  "detected_regime": "KNOWN"},
        "knowledge": {"refs": ["know:oracle:1"], "summary": "oracle",
                      "status": "reference_only"},
        "context": {"active_context": None, "semantic_summary": None},
        "cognitive": {"meaning_scalar": 0.5, "meaning_vector": [],
                      "meaning_ok": True, "stability": 0.5, "drift": 0.1,
                      "alignment": 0.5, "state_ok": True, "safety_ok": True,
                      "register": "compact", "tone": "calm"},
        "world": {"evidence_refs": ["ev:oracle:1"], "evidence_context": None,
                  "conflict_status": None, "conflicts": [],
                  "world_summary": {"maya.state.x": {"type": "scalar",
                                                    "value": 0.5}}},
        "memory": {"conversation_refs": [], "continuity_ref": None,
                   "notes": None},
        "learning": {"kind": None, "proposal_ref": None,
                     "approval_ref": None, "mutation_requested": False},
        "safety": {"status": "safe", "reason": "oracle sample",
                   "source": "oracle.bus", "state_context": None,
                   "constraint": None, "budget": None},
        "persona": {"selection": None, "weights_ref": None,
                    "constraints": [], "identity_ref": "maya"},
        "geometry": {"space": [0.0, 1.0, 0.0, 1.0], "objects": [],
                     "transforms": [], "expressions": {},
                     "symmetry": {"axis": 0.5, "tolerance": 0.004,
                                  "ok": True}},
        "expression": {"register": "compact", "budget": 48, "holds": [],
                       "text": "oracle", "constraints": []},
        "transform_history": [{"op": "create", "applied_to": "oracle-bus-1",
                               "at": _T}],
    }
    canonical = _ORACLE_JCS.canonical_bytes(base)
    base["digest"] = {"alg": "sha-256", "source": "jcs-rfc-8785",
                      "digest": hashlib.sha256(canonical).hexdigest(),
                      "bytes": len(canonical)}
    return base


def verify():
    failures = []
    ok_lines = []
    _load_oracles()
    for record in (make_sample_record(),):
        ok, issues = oracle_check(record)
        if not ok:
            failures.extend(issues)
    if not failures:
        ok_lines.append("oracle_bus_contract=OK")
    return not failures, failures, ok_lines


def main():
    _load_oracles()
    ok, failures, ok_lines = verify()
    for line in ok_lines:
        print(line)
    if not ok:
        print("oracle_bus_failures=%d" % len(failures))
        for entry in failures[:10]:
            print("  %s" % entry)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())