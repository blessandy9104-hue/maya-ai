"""Unified state / knowledge bus (MAYA Batch #3).

The bus is NOT another intelligence engine and NOT a new truth database. It is
the shared, typed contract through which the existing authoritative stores and
engines exchange structured state:

    REPRESENTATION
        -> CANONICAL OBJECT
        -> UNIFIED STATE / KNOWLEDGE BUS
           -> cognition, world model, evidence, memory, learning, safety,
              persona, geometry, meaning, language expression
        -> MEANING / DECISION STATE
        -> LANGUAGE / ACTION / EMBODIMENT

Rules enforced here (fail closed, never documented-away):

- Typed values only: every carried payload member is validated with the Batch
  #2 representation contracts; an identifier is never a measurement, a
  categorical code is never a scalar, unknown types are never guessed.
- Canonical representation is preserved; the eleven categories of part #2
  (FACT / OBSERVATION / CALCULATION / INFERENCE / INTERPRETATION / HYPOTHESIS
  / USER_PROVIDED / EXTERNAL_REPORT / UNKNOWN) are never collapsed into one
  generic "knowledge" state.
- Explicit provenance on every record (world-model evidence vocabulary); a
  record without provenance is rejected.
- Explicit temporal context (event/publication/retrieval/processing/state
  times). All times are caller-supplied ISO-8601 UTC; this module never reads
  a clock. ``event_time`` may not follow ``state_time`` (no events after the
  snapshot that claims them).
- Confidence/uncertainty are typed and bounded; silent reinterpretation is
  impossible by construction.
- Conflicting claims are RETAINED, never overwritten; the conflict is
  represented with both claims, both evidence sets, and an explicit status
  (SUPPORTED / DISPUTED / CONTRADICTED / UNKNOWN).
- Safety holds cannot be cleared downstream: the ``expression`` member must
  carry the hold tokens implied by the ``safety`` member.
- Identity is reference-only: the ``persona`` member cannot reach into
  identity fields (identity stays in ``maya_identity``).
- Geometry is a first-class domain, but geometry != meaning: it is carried as
  numeric descriptors validated against the identity-space contract.
- Deterministic serialization: SHA-256 over the RFC 8785 JCS canonical bytes
  of the envelope payload without its ``digest`` member. No wall clock, no
  random source, no host probe. Cross-interpreter identical.
- Learning events carry an explicit gate: an unapproved mutation request is
  rejected; approved changes are *recorded*, never executed by the bus.
- The bus references authoritative stores by id; it never copies whole
  parallel databases into memory.

No ``eval``/``exec`` exists anywhere in this module; the only integrity
primitive is the verified ``jcs`` serializer.
"""
from __future__ import annotations

import copy
import os

from . import jcs
from .canonical import detect as _detect
from .canonical import geometry_contract, geometry_space
from .representation import (
    REPRESENTATION_TYPES,
    RepresentationError,
    validate as _validate,
    validate_confidence,
    validate_identifier,
    validate_iso8601_utc,
    validate_provenance,
    validate_scalar,
    validate_text,
    validate_uncertainty,
)

PROTOCOL = "maya.unified_state"
PROTOCOL_VERSION = 1
SCHEMA_ID = "maya:unified-state:1"
SCHEMA_VERSION = 1
DIGEST_ALG = "sha-256"
DIGEST_SOURCE = "jcs-rfc-8785"

BUS_DISABLE_ENV = "MAYA_BUS_DISABLED"

# Envelope members, in stable order (mirrors verification state-bus schema).
ENVELOPE_KEYS = (
    "protocol", "protocol_version", "schema", "schema_version",
    "state_id", "source", "state_kind", "declaration", "temporal",
    "provenance", "confidence", "validation_status", "input", "knowledge",
    "context", "cognitive", "world", "memory", "learning", "safety",
    "persona", "geometry", "expression", "transform_history", "digest",
)

STATE_KINDS = ("STATE", "EVENT", "KNOWLEDGE", "EVIDENCE", "DERIVED_COGNITION",
               "EXPRESSION")
DECLARATIONS = ("FACT", "OBSERVATION", "CALCULATION", "INFERENCE",
                "INTERPRETATION", "HYPOTHESIS", "USER_PROVIDED",
                "EXTERNAL_REPORT", "UNKNOWN")
VALIDATION_STATUSES = ("unvalidated", "validated", "disputed", "contradicted",
                       "unknown")
CONFLICT_STATUSES = ("SUPPORTED", "DISPUTED", "CONTRADICTED", "UNKNOWN")
SAFETY_STATUSES = ("safe", "hold", "blocked", "unknown")
TEMPORAL_FIELDS = ("event_time", "publication_time", "retrieval_time",
                   "processing_time", "state_time")
LEARNING_KINDS = ("OBSERVATION", "EVENT", "PROPOSAL", "APPROVED_CHANGE")
GEOMETRIC_KINDS = ("point", "curve", "surface", "mesh")
KNOWLEDGE_STATUSES = ("retained", "reference_only")

ALLOWED_TRANSFORM_OPS = frozenset({
    "create", "published", "attached", "merged", "derived_from", "constraint",
    "snapshot", "carried",
})
FORBIDDEN_TRANSFORM_OPS = frozenset({
    "erase_provenance", "drop_provenance", "overwrite_provenance",
    "clear_history", "clear_safety_hold", "modify_identity",
    "overwrite_conflict",
})
ALLOWED_ALGORITHMS = frozenset({DIGEST_ALG})

# Safety status -> expression hold tokens that downstream MUST still carry.
REQUIRED_EXPRESSION_HOLDS = {
    "safe": (),
    "unknown": (),
    "hold": ("safety_hold",),
    "blocked": ("safety_blocked",),
}

# Directive hold names produced by the bridge -> bus safety status.
HOLD_TO_SAFETY = {
    "safety_boundary": "blocked",
    "unstable_world_model": "hold",
    "meaning_not_ok": "hold",
    "state_not_ok": "hold",
    "low_confidence": "hold",
    "intelligence_unavailable": "hold",
}

# Authoritative source registry (references only; the bus never copies these
# stores into memory). Identifies the single source of truth per domain.
AUTHORITATIVE_SOURCES = {
    "identity": "maya_identity/identity.json",
    "geometry": "maya_identity/geometry/*.json",
    "rig_math": "maya_runtime.math_coordinator",
    "world_evidence": "maya_world_evidence.jsonl",
    "conversation_memory": "maya_conversation_store",
    "continuity_view": "maya_conversation_continuity.json",
    "safety_policy": "maya_mission_wall + math SAFETY_POLICY",
    # COGNITIVE persona authority (maya.persona_fusion.v1): the producer of
    # ``context.persona_fusion`` is the intelligence persona fusion layer.
    # This is distinct from the PRESENTATION personality profiles in
    # maya_runtime/personality.py, which never act as a fusion source.
    "persona_fusion": "maya_runtime.intelligence.persona",
    "learning_gate": "maya_self_improvement.approve_proposal",
    "provenance_vocabulary": "maya_world_model",
}

BUS_PARTICIPANTS = (
    "cognition", "world_model", "evidence", "memory", "learning", "safety",
    "persona", "geometry", "meaning", "language",
)

_PERSONA_ALLOWED_KEYS = frozenset(
    {"selection", "weights_ref", "constraints", "identity_ref"})
_SAFETY_ALLOWED_KEYS = frozenset(
    {"status", "reason", "source", "state_context", "constraint", "budget"})
_MEMORY_ALLOWED_KEYS = frozenset(
    {"conversation_refs", "continuity_ref", "notes"})
_LEARNING_ALLOWED_KEYS = frozenset(
    {"kind", "proposal_ref", "approval_ref", "mutation_requested"})
_WORLD_ALLOWED_KEYS = frozenset(
    {"evidence_refs", "evidence_context", "conflict_status", "conflicts",
     "world_summary"})
_INPUT_ALLOWED_KEYS = frozenset({"declared", "detected_regime"})
_CONTEXT_ALLOWED_KEYS = frozenset({"active_context", "semantic_summary",
                                    "world_mapping", "persona_fusion"})
_KNOWLEDGE_ALLOWED_KEYS = frozenset({"refs", "summary", "status"})
_COGNITIVE_ALLOWED_KEYS = frozenset({
    "meaning_scalar", "meaning_vector", "meaning_ok", "stability", "drift",
    "alignment", "state_ok", "safety_ok", "register", "tone",
})
_GEOMETRY_ALLOWED_KEYS = frozenset(
    {"space", "objects", "transforms", "expressions", "symmetry"})
_EXPRESSION_ALLOWED_KEYS = frozenset(
    {"register", "budget", "holds", "text", "constraints"})

_NUMERIC_UNIT = ("measurement", "normalized")
_GEOM_KINDS_TUPLE = GEOMETRIC_KINDS


class BusError(ValueError):
    """Raised when a record cannot be a well-formed unified state record."""


def _reject(why):
    raise BusError(why)


def _wrap(why):
    raise BusError(why)


def _as_error(exc):
    return BusError("%s: %s" % (type(exc).__name__, str(exc)))


def bus_handoff_enabled():
    """Whether the conversational bridge may hand state to the bus.

    Explicit disable switch (used by the disposable inverse experiment):
    setting ``MAYA_BUS_DISABLED=1`` turns the handoff off. This is the ONLY
    environment influence in the bus and it is per-process deterministic.
    """
    return os.environ.get(BUS_DISABLE_ENV) != "1"


def participant(domain):
    if domain not in BUS_PARTICIPANTS:
        _reject("unknown bus participant domain %r" % (domain,))
    return domain


def reference(domain):
    """Authoritative source identifier for a bus participant domain."""
    participant(domain)
    if domain not in AUTHORITATIVE_SOURCES:
        _reject("no authoritative source registered for %r" % (domain,))
    return AUTHORITATIVE_SOURCES[domain]


# ---------------------------------------------------------------------------
# shared member validators (deterministic; raise BusError via _wrap)
# ---------------------------------------------------------------------------

def _identifier(value, label):
    try:
        return validate_identifier(value)
    except RepresentationError as exc:
        _wrap("%s: %s" % (label, exc))


def _text(value, label):
    try:
        return validate_text(value)
    except RepresentationError as exc:
        _wrap("%s: %s" % (label, exc))


def _iso(value, label):
    if value is None:
        return None
    try:
        return validate_iso8601_utc(value)
    except RepresentationError as exc:
        _wrap("%s: %s" % (label, exc))


def _typed(declared, label):
    if declared is None:
        return None
    if not isinstance(declared, dict) or "type" not in declared \
            or "value" not in declared:
        _wrap("%s must be a typed value dict {type, value, ...}" % (label,))
    attrs = {k: v for k, v in declared.items() if k not in ("type", "value")}
    try:
        validated = _validate(declared["value"], declared["type"], **attrs)
    except RepresentationError as exc:
        _wrap("%s: %s" % (label, exc))
    out = {k: v for k, v in declared.items() if k != "value"}
    out["value"] = validated
    return out


def _unit01(value, label):
    if value is None:
        return None
    try:
        validate_scalar(value, domain=(0.0, 1.0))
    except RepresentationError as exc:
        _wrap("%s: %s" % (label, exc))
    return value


def _validate_temporal(temporal):
    if temporal is None:
        temporal = {}
    if not isinstance(temporal, dict):
        _reject("temporal must be a dict of ISO-8601 UTC fields")
    unknown = set(temporal) - set(TEMPORAL_FIELDS)
    if unknown:
        _reject("temporal carries unknown fields %s" % sorted(unknown))
    out = {}
    for field in TEMPORAL_FIELDS:
        value = temporal.get(field)
        out[field] = _iso(value, "temporal.%s" % field)
    previous = None
    for field in TEMPORAL_FIELDS:
        value = out[field]
        if value is None:
            continue
        if previous is not None and value < previous:
            _reject("temporal order violated: %s (%r) precedes %r"
                    % (field, value, previous))
        previous = value
    return out


def _validate_confidence(confidence):
    if confidence is None:
        confidence = {}
    if not isinstance(confidence, dict):
        _reject("confidence must be a dict with value/uncertainty")
    value = confidence.get("value")
    uncertainty = confidence.get("uncertainty")
    if value is not None:
        try:
            validate_confidence(value)
        except RepresentationError as exc:
            _wrap("confidence.value: %s" % (exc,))
    if uncertainty is not None:
        try:
            validate_uncertainty(uncertainty)
        except RepresentationError as exc:
            _wrap("confidence.uncertainty: %s" % (exc,))
    return {"value": value, "uncertainty": uncertainty}


def _detected_regime(declared):
    if declared is None:
        return "UNKNOWN"
    return _detect(declared)["regime"]


def _validate_input(inp):
    if inp is None:
        return {"declared": None, "detected_regime": "UNKNOWN"}
    if not isinstance(inp, dict):
        _reject("input must be a dict with declared/detected_regime")
    if not set(inp) <= _INPUT_ALLOWED_KEYS:
        _reject("input carries unknown keys %s"
                % sorted(set(inp) - _INPUT_ALLOWED_KEYS))
    declared = _typed(inp.get("declared"), "input.declared")
    expected_regime = _detected_regime(declared)
    regime = inp.get("detected_regime")
    if regime is not None and regime != expected_regime:
        _reject("input.detected_regime %r does not match the declared value "
                "(%r); detection is recomputed, never guessed" % (
                    regime, expected_regime))
    return {"declared": declared,
            "detected_regime": regime if regime is not None else expected_regime}


def _validate_knowledge(knowledge):
    if knowledge is None:
        return {"refs": [], "summary": None, "status": "reference_only"}
    if not isinstance(knowledge, dict):
        _reject("knowledge must be a dict with refs/summary/status")
    if not set(knowledge) <= _KNOWLEDGE_ALLOWED_KEYS:
        _reject("knowledge carries unknown keys %s"
                % sorted(set(knowledge) - _KNOWLEDGE_ALLOWED_KEYS))
    refs = knowledge.get("refs") or []
    if not isinstance(refs, (list, tuple)):
        _reject("knowledge.refs must be a sequence of identifiers")
    clean_refs = [_identifier(ref, "knowledge.refs[]") for ref in refs]
    if len(set(clean_refs)) != len(clean_refs):
        _reject("knowledge.refs must be unique")
    summary = knowledge.get("summary")
    if summary is not None:
        summary = _text(summary, "knowledge.summary")
    status = knowledge.get("status") or "reference_only"
    if status not in KNOWLEDGE_STATUSES:
        _reject("knowledge.status %r not in %s" % (status, KNOWLEDGE_STATUSES))
    return {"refs": clean_refs, "summary": summary, "status": status}


def _validate_context(context):
    if context is None:
        return {"active_context": None, "semantic_summary": None}
    if not isinstance(context, dict):
        _reject("context must be a dict")
    if not set(context) <= _CONTEXT_ALLOWED_KEYS:
        _reject("context carries unknown keys %s"
                % sorted(set(context) - _CONTEXT_ALLOWED_KEYS))
    active = _identifier(context.get("active_context"),
                         "context.active_context") \
        if context.get("active_context") is not None else None
    summary = _text(context.get("semantic_summary"),
                    "context.semantic_summary") \
        if context.get("semantic_summary") is not None else None
    world_mapping = context.get("world_mapping")
    if world_mapping is not None:
        if not isinstance(world_mapping, dict):
            _reject("context.world_mapping must be a dict or null")
        world_mapping = dict(world_mapping)
    persona_fusion = context.get("persona_fusion")
    if persona_fusion is not None:
        if not isinstance(persona_fusion, dict):
            _reject("context.persona_fusion must be a dict or null")
        persona_fusion = dict(persona_fusion)
    resolved = {"active_context": active, "semantic_summary": summary}
    if world_mapping is not None:
        resolved["world_mapping"] = world_mapping
    if persona_fusion is not None:
        resolved["persona_fusion"] = persona_fusion
    return resolved


def _validate_cognitive(cognitive):
    if cognitive is None:
        return {"meaning_scalar": None, "meaning_vector": [], "meaning_ok": False,
                "stability": None, "drift": None, "alignment": None,
                "state_ok": False, "safety_ok": False, "register": None,
                "tone": None}
    if not isinstance(cognitive, dict):
        _reject("cognitive must be a dict")
    if not set(cognitive) <= _COGNITIVE_ALLOWED_KEYS:
        _reject("cognitive carries unknown keys %s"
                % sorted(set(cognitive) - _COGNITIVE_ALLOWED_KEYS))
    vector = cognitive.get("meaning_vector") or []
    if not isinstance(vector, (list, tuple)):
        _reject("cognitive.meaning_vector must be a sequence")
    cleaned_vector = []
    for item in vector:
        cleaned_vector.append(_unit01(item, "cognitive.meaning_vector[]"))
    return {
        "meaning_scalar": _unit01(cognitive.get("meaning_scalar"),
                                  "cognitive.meaning_scalar"),
        "meaning_vector": cleaned_vector,
        "meaning_ok": bool(cognitive.get("meaning_ok", False)),
        "stability": _unit01(cognitive.get("stability"), "cognitive.stability"),
        "drift": _unit01(cognitive.get("drift"), "cognitive.drift"),
        "alignment": _unit01(cognitive.get("alignment"), "cognitive.alignment"),
        "state_ok": bool(cognitive.get("state_ok", False)),
        "safety_ok": bool(cognitive.get("safety_ok", False)),
        "register": _text(cognitive.get("register"), "cognitive.register") if
        cognitive.get("register") else None,
        "tone": _text(cognitive.get("tone"), "cognitive.tone") if
        cognitive.get("tone") else None,
    }


def _validate_conflict_entry(entry):
    if not isinstance(entry, dict):
        _reject("conflicts entries must be dicts")
    required = ("subject", "predicate", "claim_a", "claim_b", "evidence_a",
                "evidence_b", "status")
    if not set(required) <= set(entry):
        _reject("conflicts entry missing required fields %s" % (required,))
    subject = _identifier(entry["subject"], "conflicts.subject")
    predicate = _identifier(entry["predicate"], "conflicts.predicate")
    evidence_a = [_identifier(ref, "conflicts.evidence_a[]")
                  for ref in entry.get("evidence_a") or []]
    evidence_b = [_identifier(ref, "conflicts.evidence_b[]")
                  for ref in entry.get("evidence_b") or []]
    status = entry.get("status")
    if status not in CONFLICT_STATUSES:
        _reject("conflicts.status %r not in %s"
                % (status, CONFLICT_STATUSES))
    if entry["claim_a"] == entry["claim_b"]:
        _reject("conflicts entry reports equal claims as conflicting")
    return {"subject": subject, "predicate": predicate,
            "claim_a": entry["claim_a"], "claim_b": entry["claim_b"],
            "evidence_a": evidence_a, "evidence_b": evidence_b,
            "status": status}


def _validate_world(world):
    if world is None:
        return {"evidence_refs": [], "evidence_context": None,
                "conflict_status": None, "conflicts": [], "world_summary": {}}
    if not isinstance(world, dict):
        _reject("world must be a dict")
    if not set(world) <= _WORLD_ALLOWED_KEYS:
        _reject("world carries unknown keys %s"
                % sorted(set(world) - _WORLD_ALLOWED_KEYS))
    refs = world.get("evidence_refs") or []
    if not isinstance(refs, (list, tuple)):
        _reject("world.evidence_refs must be a sequence of identifiers")
    clean_refs = [_identifier(ref, "world.evidence_refs[]") for ref in refs]
    if len(set(clean_refs)) != len(clean_refs):
        _reject("world.evidence_refs must be unique")
    conflict_status = world.get("conflict_status")
    if conflict_status is not None and conflict_status not in \
            CONFLICT_STATUSES:
        _reject("world.conflict_status %r not in %s"
                % (conflict_status, CONFLICT_STATUSES))
    conflicts = world.get("conflicts") or []
    if not isinstance(conflicts, (list, tuple)):
        _reject("world.conflicts must be a sequence")
    clean_conflicts = [_validate_conflict_entry(entry) for entry in conflicts]
    summary = world.get("world_summary") or {}
    if not isinstance(summary, dict):
        _reject("world.world_summary must be a dict of typed values")
    clean_summary = {}
    for key, declared in summary.items():
        field = _identifier(key, "world.world_summary key")
        clean_summary[field] = _typed(declared, "world.world_summary.%s" % key)
    evidence_context = world.get("evidence_context")
    if evidence_context is not None:
        evidence_context = _text(evidence_context, "world.evidence_context")
    return {"evidence_refs": clean_refs, "evidence_context": evidence_context,
            "conflict_status": conflict_status, "conflicts": clean_conflicts,
            "world_summary": clean_summary}


def _validate_memory(memory):
    if memory is None:
        return {"conversation_refs": [], "continuity_ref": None, "notes": None}
    if not isinstance(memory, dict):
        _reject("memory must be a dict of references")
    if not set(memory) <= _MEMORY_ALLOWED_KEYS:
        _reject("memory carries unknown keys %s"
                % sorted(set(memory) - _MEMORY_ALLOWED_KEYS))
    refs = memory.get("conversation_refs") or []
    if not isinstance(refs, (list, tuple)):
        _reject("memory.conversation_refs must be a sequence of identifiers")
    clean_refs = [_identifier(ref, "memory.conversation_refs[]") for ref in refs]
    if len(set(clean_refs)) != len(clean_refs):
        _reject("memory.conversation_refs must be unique")
    continuity = memory.get("continuity_ref")
    if continuity is not None:
        continuity = _identifier(continuity, "memory.continuity_ref")
    notes = _text(memory.get("notes"), "memory.notes") if \
        memory.get("notes") else None
    return {"conversation_refs": clean_refs, "continuity_ref": continuity,
            "notes": notes}


def _validate_learning(learning):
    if learning is None:
        return {"kind": None, "proposal_ref": None, "approval_ref": None,
                "mutation_requested": False}
    if not isinstance(learning, dict):
        _reject("learning must be a dict")
    if not set(learning) <= _LEARNING_ALLOWED_KEYS:
        _reject("learning carries unknown keys %s"
                % sorted(set(learning) - _LEARNING_ALLOWED_KEYS))
    kind = learning.get("kind")
    if kind is not None and kind not in LEARNING_KINDS:
        _reject("learning.kind %r not in %s" % (kind, LEARNING_KINDS))
    proposal_ref = learning.get("proposal_ref")
    if proposal_ref is not None:
        proposal_ref = _identifier(proposal_ref, "learning.proposal_ref")
    approval_ref = learning.get("approval_ref")
    if approval_ref is not None:
        approval_ref = _identifier(approval_ref, "learning.approval_ref")
    mutation = bool(learning.get("mutation_requested", False))
    if mutation and kind != "APPROVED_CHANGE":
        _reject("unapproved learning mutation: mutation_requested requires "
                "kind=APPROVED_CHANGE (the bus never modifies learning stores "
                "outside the approval gate)")
    if mutation and approval_ref is None:
        _reject("approved learning mutation requires an explicit approval_ref")
    return {"kind": kind, "proposal_ref": proposal_ref,
            "approval_ref": approval_ref, "mutation_requested": mutation}


def _validate_safety(safety, default_source):
    if safety is None:
        safety = {}
    if not isinstance(safety, dict):
        _reject("safety must be a dict")
    if not set(safety) <= _SAFETY_ALLOWED_KEYS:
        _reject("safety carries unknown keys %s"
                % sorted(set(safety) - _SAFETY_ALLOWED_KEYS))
    status = safety.get("status") or "unknown"
    if status not in SAFETY_STATUSES:
        _reject("safety.status %r not in %s" % (status, SAFETY_STATUSES))
    source = safety.get("source")
    if source is None:
        source = default_source
    source = _identifier(source, "safety.source")
    reason = _text(safety.get("reason"), "safety.reason") if \
        safety.get("reason") else None
    state_context = _text(safety.get("state_context"),
                          "safety.state_context") if \
        safety.get("state_context") else None
    constraint = _text(safety.get("constraint"), "safety.constraint") if \
        safety.get("constraint") else None
    budget = safety.get("budget")
    if budget is not None and (not isinstance(budget, int)
                               or isinstance(budget, bool) or budget < 0):
        _reject("safety.budget must be a non-negative integer")
    return {"status": status, "reason": reason, "source": source,
            "state_context": state_context, "constraint": constraint,
            "budget": budget}


def _validate_persona(persona):
    if persona is None:
        persona = {}
    if not isinstance(persona, dict):
        _reject("persona must be a dict")
    if not set(persona) <= _PERSONA_ALLOWED_KEYS:
        _reject("persona carries identity-reaching keys %s; identity is "
                "reference-only and never modified through persona"
                % sorted(set(persona) - _PERSONA_ALLOWED_KEYS))
    selection = _identifier(persona.get("selection"), "persona.selection") if \
        persona.get("selection") else None
    weights_ref = _identifier(persona.get("weights_ref"),
                              "persona.weights_ref") if \
        persona.get("weights_ref") else None
    constraints = [_identifier(token, "persona.constraints[]")
                   for token in persona.get("constraints") or ()]
    if not isinstance(persona.get("constraints") or (), (list, tuple)):
        _reject("persona.constraints must be a sequence of identifiers")
    identity_ref = persona.get("identity_ref")
    if identity_ref is None:
        identity_ref = "maya"
    identity_ref = _identifier(identity_ref, "persona.identity_ref")
    return {"selection": selection, "weights_ref": weights_ref,
            "constraints": constraints, "identity_ref": identity_ref}


def _validate_geometry(geometry):
    if geometry is None:
        geometry = {}
    if not isinstance(geometry, dict):
        _reject("geometry must be a dict")
    if not set(geometry) <= _GEOMETRY_ALLOWED_KEYS:
        _reject("geometry carries unknown keys %s"
                % sorted(set(geometry) - _GEOMETRY_ALLOWED_KEYS))
    contract = geometry_contract()
    lo_x, hi_x, lo_y, hi_y = geometry_space()
    space = geometry.get("space")
    if space is None:
        space = [lo_x, hi_x, lo_y, hi_y]
    if not isinstance(space, (list, tuple)) or len(space) != 4:
        _reject("geometry.space must be a 4-number bounds sequence")
    clean_space = []
    for item in space:
        try:
            validate_scalar(item)
        except RepresentationError as exc:
            _wrap("geometry.space[]: %s" % (exc,))
        clean_space.append(float(item))
    objects = []
    for item in geometry.get("objects") or ():
        if not isinstance(item, dict) or "ref" not in item:
            _reject("geometry.objects[] must be dicts with ref")
        obj_ref = _identifier(item["ref"], "geometry.objects[].ref")
        kind = item.get("geometry_kind")
        if kind not in _GEOM_KINDS_TUPLE:
            _reject("geometry.objects[].geometry_kind %r not in %s"
                    % (kind, _GEOM_KINDS_TUPLE))
        bounds = item.get("bounds")
        if bounds is not None:
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
                _reject("geometry.objects[].bounds must be a 4-number "
                        "bounds sequence")
            x1, y1, x2, y2 = (float(v) for v in bounds)
            if not (lo_x <= x1 <= hi_x and lo_y <= y1 <= hi_y
                    and lo_x <= x2 <= hi_x and lo_y <= y2 <= hi_y):
                _reject("geometry.objects[].bounds %s outside declared space "
                        "%s" % (bounds, (lo_x, hi_x, lo_y, hi_y)))
            bounds = [x1, y1, x2, y2]
        objects.append({"ref": obj_ref, "geometry_kind": kind,
                        "bounds": bounds})
    transforms = []
    for item in geometry.get("transforms") or ():
        transforms.append(_typed(item, "geometry.transforms[]"))
    expressions = {}
    for key, declared in (geometry.get("expressions") or {}).items():
        field = _identifier(key, "geometry.expressions key")
        expressions[field] = _typed(declared,
                                    "geometry.expressions.%s" % key)
    symmetry = geometry.get("symmetry") or {}
    if not isinstance(symmetry, dict):
        _reject("geometry.symmetry must be a dict")
    axis = symmetry.get("axis")
    if axis is None:
        axis = contract["axis_x"]
    tolerance = symmetry.get("tolerance")
    if tolerance is None:
        tolerance = contract["tolerance"]
    if not isinstance(axis, (int, float)) or isinstance(axis, bool) or \
            not (0.0 <= float(axis) <= 1.0):
        _reject("geometry.symmetry.axis must be a number in [0, 1]")
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) \
            or tolerance < 0.0:
        _reject("geometry.symmetry.tolerance must be a non-negative number")
    ok = bool(symmetry.get("ok", True))
    return {"space": clean_space, "objects": objects, "transforms": transforms,
            "expressions": expressions,
            "symmetry": {"axis": float(axis), "tolerance": float(tolerance),
                         "ok": ok}}


def _required_expression_holds(safety):
    return list(REQUIRED_EXPRESSION_HOLDS.get(safety.get("status"), ()))


def _validate_expression(expression, safety):
    if expression is None:
        expression = {}
    if not isinstance(expression, dict):
        _reject("expression must be a dict")
    if not set(expression) <= _EXPRESSION_ALLOWED_KEYS:
        _reject("expression carries unknown keys %s"
                % sorted(set(expression) - _EXPRESSION_ALLOWED_KEYS))
    register = _text(expression.get("register"), "expression.register") if \
        expression.get("register") else None
    budget = expression.get("budget")
    if budget is None:
        budget = 48
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        _reject("expression.budget must be a non-negative integer")
    holds = list(expression.get("holds") or ())
    required = _required_expression_holds(safety)
    missing = [token for token in required if token not in holds]
    if missing:
        _reject("expression is missing safety-implied holds %s; downstream "
                "cannot clear a safety hold" % (missing,))
    for token in holds:
        _text(token, "expression.holds[]")
    text = _text(expression.get("text"), "expression.text") if \
        expression.get("text") else ""
    constraints = [_text(token, "expression.constraints[]")
                   for token in expression.get("constraints") or ()]
    return {"register": register, "budget": int(budget), "holds": holds,
            "text": text, "constraints": constraints}


def _validate_transform_history(history, state_id, at):
    if history is None:
        history = [{"op": "create", "applied_to": state_id, "at": at}]
    if not isinstance(history, (list, tuple)) or not history:
        _reject("transform_history must be a non-empty sequence of ops")
    out = []
    for entry in history:
        if not isinstance(entry, dict) or not set(entry) >= {"op", "applied_to",
                                                             "at"}:
            _reject("transform_history entries need op/applied_to/at")
        op = _identifier(entry["op"], "transform_history.op")
        if op not in ALLOWED_TRANSFORM_OPS:
            _reject("transform op %r is not permitted (approvals, provides, "
                    "and historical provenance are append-only)" % (op,))
        if op in FORBIDDEN_TRANSFORM_OPS:
            _reject("transform op %r is forbidden (provenance is "
                    "append-only)" % (op,))
        applied_to = _identifier(entry["applied_to"],
                                 "transform_history.applied_to")
        at = _iso(entry["at"], "transform_history.at")
        out.append({"op": op, "applied_to": applied_to, "at": at})
    return out


# ---------------------------------------------------------------------------
# envelope assembly / integrity
# ---------------------------------------------------------------------------

def _copy_payload(obj):
    if not isinstance(obj, dict):
        _reject("unified state record must be a dict envelope")
    return {key: value for key, value in obj.items() if key != "digest"}


def payload(obj):
    """The envelope minus the ``digest`` member (the digest input)."""
    return _copy_payload(obj)


def _validate_envelope_shape(obj):
    if not isinstance(obj, dict):
        _reject("unified state record must be a dict envelope")
    if set(obj) != set(ENVELOPE_KEYS):
        _reject("envelope key set mismatch: %s"
                % sorted(set(obj) ^ set(ENVELOPE_KEYS)))
    if obj.get("protocol") != PROTOCOL:
        _reject("protocol %r != %r" % (obj.get("protocol"), PROTOCOL))
    if obj.get("protocol_version") != PROTOCOL_VERSION:
        _reject("protocol_version %r != %d"
                % (obj.get("protocol_version"), PROTOCOL_VERSION))
    if obj.get("schema") != SCHEMA_ID:
        _reject("schema %r != %r" % (obj.get("schema"), SCHEMA_ID))
    if obj.get("schema_version") != SCHEMA_VERSION:
        _reject("schema_version %r; supported version is %d"
                % (obj.get("schema_version"), SCHEMA_VERSION))


def _assemble(record_id, source, state_kind, declaration, temporal,
              provenance, confidence, validation_status, input_member,
              knowledge, context, cognitive, world, memory, learning, safety,
              persona, geometry, expression, transform_history):
    payload_dict = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "state_id": record_id,
        "source": source,
        "state_kind": state_kind,
        "declaration": declaration,
        "temporal": temporal,
        "provenance": provenance,
        "confidence": confidence,
        "validation_status": validation_status,
        "input": input_member,
        "knowledge": knowledge,
        "context": context,
        "cognitive": cognitive,
        "world": world,
        "memory": memory,
        "learning": learning,
        "safety": safety,
        "persona": persona,
        "geometry": geometry,
        "expression": expression,
        "transform_history": transform_history,
    }
    obj = dict(payload_dict)
    canonical_bytes = jcs.canonical_bytes(payload_dict)
    obj["digest"] = {
        "alg": DIGEST_ALG,
        "source": DIGEST_SOURCE,
        "digest": jcs.sha256(payload_dict),
        "bytes": len(canonical_bytes),
    }
    return obj


def verify(obj):
    """Recompute the digest and compare. Raises ``BusError`` if the envelope
    is malformed or the digest does not match (corruption fails closed)."""
    _validate_envelope_shape(obj)
    digest_member = obj.get("digest")
    if not isinstance(digest_member, dict) or digest_member.get("alg") not in \
            ALLOWED_ALGORITHMS:
        _reject("digest member is malformed or uses an unknown algorithm")
    recorded = digest_member.get("digest")
    if not isinstance(recorded, str) or not recorded:
        _reject("digest member is missing its digest")
    recomputed = jcs.sha256(_copy_payload(obj))
    if recomputed != recorded:
        _reject("unified-state digest mismatch: recorded %r, recomputed %r"
                % (recorded, recomputed))
    declared_bytes = digest_member.get("bytes")
    if declared_bytes is not None and declared_bytes != len(
            jcs.canonical_bytes(_copy_payload(obj))):
        _reject("digest byte count does not match the canonical payload size")
    return {"digest_ok": True, "alg": DIGEST_ALG, "digest": recomputed,
            "bytes": digest_member.get("bytes")}


def validate(obj):
    """Full revalidation: envelope shape + digest + every member contract."""
    verify(obj)
    state_kind = obj.get("state_kind")
    if state_kind not in STATE_KINDS:
        _reject("state_kind %r not in %s" % (state_kind, STATE_KINDS))
    declaration = obj.get("declaration")
    if declaration not in DECLARATIONS:
        _reject("declaration %r not in %s" % (declaration, DECLARATIONS))
    _identifier(obj.get("state_id"), "state_id")
    _identifier(obj.get("source"), "source")
    _validate_temporal(obj.get("temporal"))
    validate_provenance_or_reject(obj.get("provenance"))
    _validate_confidence(obj.get("confidence"))
    vs = obj.get("validation_status")
    if vs not in VALIDATION_STATUSES:
        _reject("validation_status %r not in %s" % (vs, VALIDATION_STATUSES))
    _validate_input(obj.get("input"))
    _validate_knowledge(obj.get("knowledge"))
    _validate_context(obj.get("context"))
    _validate_cognitive(obj.get("cognitive"))
    _validate_world(obj.get("world"))
    _validate_memory(obj.get("memory"))
    _validate_learning(obj.get("learning"))
    safety = _validate_safety(obj.get("safety"), obj.get("source"))
    _validate_persona(obj.get("persona"))
    _validate_geometry(obj.get("geometry"))
    _validate_expression(obj.get("expression"), safety)
    _validate_transform_history(obj.get("transform_history"),
                                obj.get("state_id"), None)
    return {"valid": True, "digest": obj.get("digest", {}).get("digest")}


def validate_provenance_or_reject(provenance):
    if provenance is None:
        _reject("provenance is required for every bus record (fail closed)")
    try:
        return validate_provenance(provenance)
    except RepresentationError as exc:
        _wrap("provenance: %s" % (exc,))


def digest(obj):
    return jcs.sha256(_copy_payload(obj))


def to_jcs(obj):
    return jcs.canonicalize(obj)


def canonical_bytes(obj):
    return jcs.canonical_bytes(obj)


def read(obj, name):
    """Read-only accessor returning a deep copy of one envelope member."""
    _validate_envelope_shape(obj)
    if name not in ENVELOPE_KEYS:
        _reject("unknown envelope member %r" % (name,))
    return copy.deepcopy(obj.get(name))


# ---------------------------------------------------------------------------
# record creation
# ---------------------------------------------------------------------------

def _normalize_common(state_id, source, provenance, declaration, state_kind,
                      temporal, confidence_value, uncertainty_value,
                      validation_status, input_declared, knowledge, context,
                      cognitive, world, memory, learning, safety, persona,
                      geometry, expression, transform_history):
    if state_id is None:
        _reject("state_id is required (caller-supplied; identifiers are never "
                "generated here)")
    if source is None:
        _reject("source is required (which authoritative path produced this)")
    _identifier(state_id, "state_id")
    _identifier(source, "source")
    if state_kind not in STATE_KINDS:
        _reject("state_kind %r not in %s" % (state_kind, STATE_KINDS))
    if declaration not in DECLARATIONS:
        _reject("declaration %r not in %s" % (declaration, DECLARATIONS))
    provenance = validate_provenance_or_reject(provenance)
    temporal = _validate_temporal(temporal)
    if state_kind == "EVENT" and temporal.get("event_time") is None:
        _reject("EVENT records require an explicit event_time (something "
                "happened)")
    if state_kind == "EVIDENCE" and temporal.get("event_time") is None:
        _reject("EVIDENCE records require an explicit event_time")
    validation_status = validation_status or "unvalidated"
    if validation_status not in VALIDATION_STATUSES:
        _reject("validation_status %r not in %s"
                % (validation_status, VALIDATION_STATUSES))
    confidence = _validate_confidence(
        {"value": confidence_value, "uncertainty": uncertainty_value})
    input_member = _validate_input({"declared": input_declared})
    knowledge = _validate_knowledge(knowledge)
    context = _validate_context(context)
    cognitive = _validate_cognitive(cognitive)
    world = _validate_world(world)
    memory = _validate_memory(memory)
    learning = _validate_learning(learning)
    safety = _validate_safety(safety, source)
    persona = _validate_persona(persona)
    geometry = _validate_geometry(geometry)
    expression = _validate_expression(expression, safety)
    at = temporal.get("state_time") or temporal.get("processing_time") or \
        temporal.get("event_time")
    transform_history = _validate_transform_history(transform_history,
                                                    state_id, at)
    return dict(
        record_id=state_id, source=source, state_kind=state_kind,
        declaration=declaration, temporal=temporal, provenance=provenance,
        confidence=confidence, validation_status=validation_status,
        input_member=input_member, knowledge=knowledge, context=context,
        cognitive=cognitive, world=world, memory=memory, learning=learning,
        safety=safety, persona=persona, geometry=geometry,
        expression=expression, transform_history=transform_history)


def create_state(state_id=None, *, source, provenance, declaration="INTERPRETATION",
                 state_kind="STATE", temporal=None, confidence_value=None,
                 uncertainty_value=None, validation_status=None,
                 input_declared=None, knowledge=None, context=None,
                 cognitive=None, world=None, memory=None, learning=None,
                 safety=None, persona=None, geometry=None, expression=None,
                 transform_history=None):
    """Build one unified state record (minimum canonical state envelope)."""
    c = _normalize_common(
        state_id, source, provenance, declaration, state_kind, temporal,
        confidence_value, uncertainty_value, validation_status, input_declared,
        knowledge, context, cognitive, world, memory, learning, safety,
        persona, geometry, expression, transform_history)
    return _assemble(**c)


def publish_event(state_id=None, *, source, provenance, declaration="OBSERVATION",
                  event_time=None, temporal=None, confidence_value=None,
                  uncertainty_value=None, context=None, world=None, memory=None,
                  learning=None, safety=None):
    """Append an EVENT record (immutable record semantics: an event happened).
    Requires an explicit ``event_time`` so processing time is never used as a
    substitute for event time."""
    temporal = dict(temporal or {})
    temporal.setdefault("event_time", event_time)
    if temporal.get("event_time") is None:
        _reject("publish_event requires an explicit event_time")
    c = _normalize_common(
        state_id, source, provenance, declaration, "EVENT", temporal,
        confidence_value, uncertainty_value, None, None, None, context, None,
        world, memory, learning, safety, None, None, None, None)
    history = c["transform_history"]
    if history[0]["op"] == "create":
        history[0] = {"op": "published", "applied_to": history[0]["applied_to"],
                      "at": history[0]["at"]}
    return _assemble(**c)


def attach_knowledge(state_id=None, *, source, provenance, declaration="FACT",
                     refs=None, summary=None, status="reference_only",
                     temporal=None, memory=None):
    """Append a KNOWLEDGE record (retained, referenceable structured
    information). References authoritative stores; never copies their rows."""
    knowledge = {"refs": list(refs or ()), "summary": summary, "status": status}
    c = _normalize_common(
        state_id, source, provenance, declaration, "KNOWLEDGE", temporal,
        None, None, None, None, knowledge, None, None, None, memory, None,
        None, None, None, None, None)
    history = c["transform_history"]
    if history[0]["op"] == "create":
        history[0] = {"op": "attached", "applied_to": history[0]["applied_to"],
                      "at": history[0]["at"]}
    return _assemble(**c)


def attach_evidence(state_id=None, *, source, provenance, evidence_refs,
                    event_time=None, evidence_context=None, temporal=None,
                    declaration="OBSERVATION", confidence_value=None):
    """Append an EVIDENCE record referencing rows in the authoritative
    world-evidence store (the store remains the single source of truth)."""
    temporal = dict(temporal or {})
    temporal.setdefault("event_time", event_time)
    if temporal.get("event_time") is None:
        _reject("attach_evidence requires an explicit event_time")
    if not evidence_refs or not isinstance(evidence_refs, (list, tuple)):
        _reject("attach_evidence requires a non-empty evidence_refs sequence")
    world = {"evidence_refs": list(evidence_refs),
             "evidence_context": evidence_context, "conflict_status": None,
             "conflicts": [], "world_summary": {}}
    c = _normalize_common(
        state_id, source, provenance, declaration, "EVIDENCE", temporal,
        confidence_value, None, None, None, None, None, None, world, None,
        None, None, None, None, None, None)
    history = c["transform_history"]
    if history[0]["op"] == "create":
        history[0] = {"op": "attached", "applied_to": history[0]["applied_to"],
                      "at": history[0]["at"]}
    return _assemble(**c)


def publish_learning_event(state_id=None, *, source, provenance, kind,
                           proposal_ref=None, approval_ref=None,
                           mutation_requested=False, event_time=None,
                           temporal=None, summary=None):
    """Record a learning-domain EVENT. Mutation requests are recorded only
    behind the explicit approval gate; the bus never modifies learning
    stores itself."""
    if kind not in LEARNING_KINDS:
        _reject("learning kind %r not in %s" % (kind, LEARNING_KINDS))
    temporal = dict(temporal or {})
    temporal.setdefault("event_time", event_time)
    if temporal.get("event_time") is None:
        _reject("learning events require an explicit event_time")
    learning = {"kind": kind, "proposal_ref": proposal_ref,
                "approval_ref": approval_ref,
                "mutation_requested": bool(mutation_requested)}
    _validate_learning(learning)
    knowledge = {"refs": [], "summary": summary, "status": "reference_only"}
    c = _normalize_common(
        state_id, source, provenance, "INTERPRETATION" if summary else
        "OBSERVATION", "EVENT", temporal, None, None, None, None, knowledge,
        None, None, None, None, learning, None, None, None, None, None)
    history = c["transform_history"]
    if history[0]["op"] == "create":
        history[0] = {"op": "published", "applied_to": history[0]["applied_to"],
                      "at": history[0]["at"]}
    return _assemble(**c)


def derive_state(event_records, state_id=None, *, source, provenance,
                 state_time=None, declaration="INTERPRETATION",
                 confidence_value=None, context=None, cognitive=None,
                 safety=None, temporal=None):
    """Derive a STATE record from an event stream (DERIVED; the source events
    are never mutated). Conflicts are detected deterministically from pairs
    sharing (subject, predicate) with differing claims; both claims are
    retained, the conflict is visible, and nothing is silently overwritten."""
    if not event_records or not isinstance(event_records, (list, tuple)):
        _reject("derive_state requires a non-empty event stream")
    for record in event_records:
        verify(record)
    temporal = dict(temporal or {})
    if state_time is not None:
        temporal.setdefault("state_time", state_time)
    if temporal.get("state_time") is None:
        _reject("derive_state requires an explicit state_time (derived "
                "snapshots carry their own state time)")
    refs = []
    conflicts = []
    seen = {}
    confidences = []
    for record in event_records:
        state_id_ = record.get("state_id")
        refs.append(state_id_)
        confidence = record.get("confidence") or {}
        if confidence.get("value") is not None:
            confidences.append(confidence["value"])
        claims = (record.get("world") or {}).get("world_summary") or {}
        for subject, declared in claims.items():
            if not isinstance(declared, dict):
                continue
            predicate = declared.get("predicate", "value")
            value = declared.get("value")
            evidence_refs = (record.get("world") or {}).get("evidence_refs",
                                                            [])
            key = (subject, predicate)
            if key in seen:
                prior_value, prior_refs = seen[key]
                if prior_value != value:
                    conflicts.append({
                        "subject": subject, "predicate": predicate,
                        "claim_a": prior_value, "claim_b": value,
                        "evidence_a": list(prior_refs),
                        "evidence_b": list(evidence_refs),
                        "status": "DISPUTED",
                    })
            else:
                seen[key] = (value, list(evidence_refs))
    if conflicts:
        conflict_status = "CONTRADICTED" if any(
            c["claim_a"] in (None, True, False) or
            c["claim_b"] in (None, True, False) for c in conflicts) \
            else "DISPUTED"
        validation_status = "contradicted" if conflict_status == \
            "CONTRADICTED" else "disputed"
        if confidence_value is None and confidences:
            confidence_value = min(confidences)
    else:
        conflict_status = None
        validation_status = "validated" if event_records else "unvalidated"
        if confidence_value is None and confidences:
            confidence_value = max(confidences)
    world = {"evidence_refs": sorted(set(refs)), "evidence_context": None,
             "conflict_status": conflict_status, "conflicts": conflicts,
             "world_summary": {}}
    transform_history = [{"op": "derived_from", "applied_to": ref,
                          "at": temporal["state_time"]} for ref in refs]
    c = _normalize_common(
        state_id, source, provenance, declaration, "STATE", temporal,
        confidence_value, None, validation_status, None, None, context,
        cognitive, world, None, None, safety, None, None, None,
        transform_history)
    return _assemble(**c)


def merge_state(a, b, state_id=None, *, source, provenance, policy="retain_all",
                consent=None, temporal=None):
    """Merge two unified records. Conflicting claims are always retained and
    made visible; a lossy policy requires explicit consent matching the policy
    name (no silent value loss)."""
    verify(a)
    verify(b)
    if policy not in ("retain_all", "prefer_a", "prefer_b"):
        _reject("merge policy %r is not supported (retain_all / prefer_a / "
                "prefer_b)" % (policy,))
    if policy != "retain_all" and consent != policy:
        _reject("lossy merge policy %r requires explicit consent == %r "
                "(no silent coercion)" % (policy, policy))
    temporal = temporal or {}
    if temporal.get("state_time") is None:
        _reject("merge_state requires an explicit state_time")
    claims_a = (a.get("world") or {}).get("world_summary") or {}
    claims_b = (b.get("world") or {}).get("world_summary") or {}
    conflicts = []
    retained = {}
    for key, declared in claims_a.items():
        retained[key] = _typed(declared, "merge world_summary.%s" % key)
    for key, declared in claims_b.items():
        if key in retained:
            value_a = retained[key].get("value")
            value_b = declared.get("value")
            if value_a != value_b:
                conflicts.append({
                    "subject": key, "predicate": "value",
                    "claim_a": value_a, "claim_b": value_b,
                    "evidence_a": list((a.get("world") or {}).get(
                        "evidence_refs", [])),
                    "evidence_b": list((b.get("world") or {}).get(
                        "evidence_refs", [])),
                    "status": "DISPUTED",
                })
                if policy == "prefer_b":
                    retained[key] = _typed(declared,
                                           "merge world_summary.%s" % key)
        else:
            retained[key] = _typed(declared, "merge world_summary.%s" % key)
    confidence_value = None
    for record in (a, b):
        value = (record.get("confidence") or {}).get("value")
        if value is not None:
            confidence_value = value if confidence_value is None else \
                min(confidence_value, value) if conflicts else \
                max(confidence_value, value)
    validation_status = "disputed" if conflicts else \
        ("validated" if (a.get("validation_status") == "validated" or
                         b.get("validation_status") == "validated")
         else "unvalidated")
    world = {"evidence_refs": sorted(set(
        list((a.get("world") or {}).get("evidence_refs", [])) +
        list((b.get("world") or {}).get("evidence_refs", [])))),
        "evidence_context": None,
        "conflict_status": "DISPUTED" if conflicts else None,
        "conflicts": conflicts, "world_summary": retained}
    input_member = _validate_input({"declared": (a.get("input") or {}).get(
        "declared")})
    transform_history = [
        {"op": "merged", "applied_to": a.get("state_id"),
         "at": temporal["state_time"]},
        {"op": "merged", "applied_to": b.get("state_id"),
         "at": temporal["state_time"]},
    ]
    c = _normalize_common(
        state_id, source, provenance, "INTERPRETATION", "STATE", temporal,
        confidence_value, None, validation_status, None, None, None, None,
        world, None, None, None, None, None, None, transform_history)
    return _assemble(**c)


def apply_constraint(state, *, domain, constraint, source_identifier, at=None,
                     consent=None):
    """Append a constraint to safety, persona, or expression. IMMUTABLE:
    returns a NEW record; the original is untouched. Constraints only tighten;
    a safety hold can never be cleared here."""
    verify(state)
    if domain not in ("safety", "persona", "expression"):
        _reject("constraint domain %r not in safety/persona/expression"
                % (domain,))
    if domain == "expression":
        if not consent:
            _reject("expression constraints require explicit consent (hold "
                    "curtailment is never implicit)")
    _identifier(constraint, "constraint")
    _identifier(source_identifier, "source_identifier")
    temporal = copy.deepcopy(state.get("temporal"))
    at = _iso(at, "constraint at") or temporal.get("state_time") or \
        temporal.get("processing_time")
    transform_history = copy.deepcopy(state.get("transform_history") or ())
    transform_history.append({"op": "constraint", "applied_to": constraint,
                              "at": at})
    payload_ = _copy_payload(state)
    if domain == "safety":
        safety = copy.deepcopy(state.get("safety") or {})
        existing = safety.get("constraint") or ""
        safety["constraint"] = (existing + " " + constraint).strip()
        safety["source"] = source_identifier
    elif domain == "persona":
        persona = copy.deepcopy(state.get("persona") or {})
        constraints = list(persona.get("constraints") or ())
        constraints.append(constraint)
        persona["constraints"] = constraints
    else:
        expression = copy.deepcopy(state.get("expression") or {})
        constraints = list(expression.get("constraints") or ())
        constraints.append(constraint)
        expression["constraints"] = constraints
    return _assemble_from(state, payload_, transform_history)


def snapshot(state, *, snapshot_id=None, source_identifier=None, at=None):
    """Capture an immutable snapshot record referencing the source state.
    (Read-only derivation; the source is never mutated.)"""
    verify(state)
    source_identifier = _identifier(source_identifier or
                                    (state.get("source") or "snapshot"),
                                    "snapshot source")
    at = _iso(at, "snapshot at")
    temporal = copy.deepcopy(state.get("temporal") or {})
    if at is not None:
        temporal["state_time"] = at
    _validate_temporal(temporal)
    transform_history = [
        {"op": "snapshot", "applied_to": state.get("state_id"),
         "at": temporal.get("state_time")}]
    payload_ = copy.deepcopy(state)
    context = copy.deepcopy(state.get("context") or {})
    context["active_context"] = state.get("state_id")
    c = _normalize_common(
        snapshot_id or ("snapshot-of-%s" % state.get("state_id")),
        source_identifier, state.get("provenance"),
        state.get("declaration") or "INTERPRETATION", "STATE", temporal,
        (state.get("confidence") or {}).get("value"),
        (state.get("confidence") or {}).get("uncertainty"),
        state.get("validation_status"),
        (state.get("input") or {}).get("declared"),
        state.get("knowledge"), context, state.get("cognitive"),
        state.get("world"), state.get("memory"), state.get("learning"),
        state.get("safety"), state.get("persona"), state.get("geometry"),
        state.get("expression"), transform_history)
    return _assemble(**c)


def _assemble_from(base, payload_, transform_history):
    """Re-assemble a record from an existing envelope payload plus a new
    transform history (immutable operation)."""
    payload_["transform_history"] = transform_history
    obj = dict(payload_)
    canonical_bytes_ = jcs.canonical_bytes(payload_)
    obj["digest"] = {"alg": DIGEST_ALG, "source": DIGEST_SOURCE,
                     "digest": jcs.sha256(payload_),
                     "bytes": len(canonical_bytes_)}
    _validate_envelope_shape(obj)
    validate(obj)
    return obj


def current_check(obj):
    """Stale/current determination from the record's own temporal contract:
    a record whose state time precedes any time it references is stale and may
    not be presented as current. Deterministic; never reads a clock."""
    verify(obj)
    temporal = obj.get("temporal") or {}
    state_time = temporal.get("state_time")
    refs_times = []
    for entry in obj.get("transform_history") or ():
        if entry.get("at"):
            refs_times.append(entry["at"])
    refs_times = [t for t in refs_times if t is not None]
    if state_time is None:
        return {"current": False, "stale_status": "stale",
                "detail": "no state_time declared"}
    if refs_times and state_time < max(refs_times):
        return {"current": False, "stale_status": "stale",
                "detail": "state_time %r precedes referenced time %r"
                          % (state_time, max(refs_times))}
    return {"current": True, "stale_status": "current", "detail": None}


def safety_from_holds(holds, source="bridge.conversation"):
    """Map directive hold names to a bus safety status (deterministic)."""
    holds = list(holds or ())
    blocked = any(HOLD_TO_SAFETY.get(h) == "blocked" for h in holds)
    held = any(HOLD_TO_SAFETY.get(h) == "hold" for h in holds)
    if blocked:
        status = "blocked"
    elif held:
        status = "hold"
    elif holds:
        status = "unknown"
    else:
        status = "safe"
    reason = ",".join(holds) if holds else "no directive holds"
    return {"status": status, "reason": reason, "source": source,
            "state_context": None, "constraint": None, "budget": None}


_HANDOFF_MAPPING_STATUSES = frozenset(
    {"KNOWN", "AMBIGUOUS", "UNRESOLVED", "INVALID"})

_HANDOFF_FUSION_STATUSES = frozenset({"FUSED", "NO_ACTIVE_PERSONA"})


def validate_mapping_for_handoff(world_mapping):
    """Sanitize a Batch #5 mapping result for the bus record.

    Shallow structural guard (the bus must not import the mapping layer):
    a dict whose status and core fields are present is copied verbatim into
    ``context.world_mapping``; anything else degrades to ``None`` so a
    malformed enrichment never blocks or corrupts a conversational turn.
    """
    if not isinstance(world_mapping, dict):
        return None
    if world_mapping.get("status") not in _HANDOFF_MAPPING_STATUSES:
        return None
    for key in ("world_kind", "normalized_fields", "mapping_evidence",
                "unresolved_fields"):
        if key not in world_mapping:
            return None
    return dict(world_mapping)


def validate_fusion_for_handoff(persona_fusion):
    """Sanitize a Batch #6 persona-fusion result for the bus record.

    Shallow structural guard (the bus must not import the persona layer): a
    dict whose status is an explicit fusion status and whose method is
    present is copied into ``context.persona_fusion``; anything else degrades
    to ``None`` so a malformed fusion never blocks a turn. The fused result
    is a *derived cognitive lens*; it never overrides safety or epistemic
    members of the record.
    """
    if not isinstance(persona_fusion, dict):
        return None
    if persona_fusion.get("status") not in _HANDOFF_FUSION_STATUSES:
        return None
    if not isinstance(persona_fusion.get("fusion_method"), str):
        return None
    if not isinstance(persona_fusion.get("active_personas"), list):
        return None
    return dict(persona_fusion)


def publish_turn(*, user_text, history, features, cognitive, directive,
                 sequence, environment, source="bridge.conversation",
                 created_at=None, state_id=None, provenance=None,
                 bus_enabled=None, input_declared=None, world_mapping=None,
                 persona_fusion=None):
    """Unify one conversational turn into the bus (BRIDGE HANDOFF).

    Deterministic handoff used by ``bridge.run_conversation_for_expression``.
    ``user_text`` is carried as a canonical typed value (Batch #4: a caller
    may supply a representation-detector ``input_declared`` typed value, e.g.
    measurement/vector/event; otherwise the user text is carried as typed
    text). The cognitive frame and expression directive travel verbatim into
    the record; the safety status is derived from the directive holds.
    ``created_at`` is caller-supplied: without it the bus refuses to mint a
    record (temporal provenance is explicit, never invented).

    ``world_mapping`` (Batch #5) may carry the representation -> world-model
    mapping result for the turn. When present and structurally well-formed it
    is stored under ``context.world_mapping`` and authenticated by the record
    digest; when absent or malformed the turn still unifies (records created
    without a mapping keep their exact Batch #3/#4 context shape).

    ``persona_fusion`` (Batch #6) may carry the weighted multi-persona fused
    cognitive state, stored under ``context.persona_fusion`` when well-formed.
    Like the mapping it is a derived lens: it never overrides the record's
    safety, epistemic or identity members, and records created without it
    keep their exact prior context shape.

    Returns ``{"engaged": bool, "minted": bool, "reason": str|None,
    "state": <record>|None, "digest": str|None}``.
    """
    if bus_enabled is None:
        bus_enabled = bus_handoff_enabled()
    if not bus_enabled:
        return {"engaged": False, "minted": False,
                "reason": "bus_handoff_disabled", "state": None,
                "digest": None}
    if created_at is None:
        return {"engaged": False, "minted": False,
                "reason": "temporal_context_missing", "state": None,
                "digest": None}
    created_at = _iso(created_at, "publish_turn created_at")
    if state_id is None:
        state_id = "turn-%s-%d" % (environment or "local",
                                   int(sequence or 0))
    if provenance is None:
        provenance = {
            "source": source,
            "source_url": None,
            "retrieved_at": created_at,
            "evidence_type": "observation",
            "confidence": "high",
            "claim": "Conversational turn unified via the shared state bus.",
        }
    safety = safety_from_holds(directive.get("holds") if directive else None,
                               source=source)
    holds = list((directive or {}).get("holds") or ())
    required = REQUIRED_EXPRESSION_HOLDS.get(safety["status"], ())
    holds.extend(token for token in required if token not in holds)
    expression = {
        "register": (directive or {}).get("register") or "compact",
        "budget": int((directive or {}).get("budget") or 48),
        "holds": holds,
        "text": (directive or {}).get("text") or "",
        "constraints": [],
    }
    memory = {"conversation_refs": [], "continuity_ref": None,
              "notes": None}
    temporal = {
        "event_time": created_at, "publication_time": created_at,
        "retrieval_time": None, "processing_time": created_at,
        "state_time": created_at,
    }
    cognitive_member = {
        "meaning_scalar": (cognitive or {}).get("meaning_scalar"),
        "meaning_vector": list((cognitive or {}).get("meaning_vector") or ()),
        "meaning_ok": bool((cognitive or {}).get("meaning_ok", False)),
        "stability": (cognitive or {}).get("stability"),
        "drift": (cognitive or {}).get("drift"),
        "alignment": (cognitive or {}).get("alignment"),
        "state_ok": bool((cognitive or {}).get("state_ok", False)),
        "safety_ok": bool((cognitive or {}).get("safety_ok", False)),
        "register": (cognitive or {}).get("register"),
        "tone": (cognitive or {}).get("tone"),
    }
    world_mapping = validate_mapping_for_handoff(world_mapping)
    persona_fusion = validate_fusion_for_handoff(persona_fusion)
    context = {"active_context": None,
               "semantic_summary": ("directive register=%s; holds=%s"
                                    % ((directive or {}).get("register") or
                                       "compact",
                                       ",".join((directive or {}).get(
                                           "holds") or ())) or None)}
    if world_mapping is not None:
        context["world_mapping"] = world_mapping
    if persona_fusion is not None:
        context["persona_fusion"] = persona_fusion
    record = create_state(
        state_id=state_id, source=source, provenance=provenance,
        state_kind="DERIVED_COGNITION", declaration="INTERPRETATION",
        temporal=temporal, confidence_value=(cognitive or {}).get("confidence"),
        input_declared=(input_declared
                        or {"type": "text", "value": user_text}),
        knowledge={"refs": [], "summary": None, "status": "reference_only"},
        context=context,
        cognitive=cognitive_member, world=None, memory=memory, learning=None,
        safety=safety, persona=None, geometry=None, expression=expression)
    return {"engaged": True, "minted": True, "reason": None, "state": record,
            "digest": record.get("digest", {}).get("digest")}


__all__ = (
    "BusError", "PROTOCOL", "PROTOCOL_VERSION", "SCHEMA_ID", "SCHEMA_VERSION",
    "DIGEST_ALG", "ENVELOPE_KEYS", "STATE_KINDS", "DECLARATIONS",
    "VALIDATION_STATUSES", "CONFLICT_STATUSES", "SAFETY_STATUSES",
    "TEMPORAL_FIELDS", "LEARNING_KINDS", "ALLOWED_TRANSFORM_OPS",
    "FORBIDDEN_TRANSFORM_OPS", "AUTHORITATIVE_SOURCES", "BUS_PARTICIPANTS",
    "REQUIRED_EXPRESSION_HOLDS", "HOLD_TO_SAFETY", "BUS_DISABLE_ENV",
    "bus_handoff_enabled", "participant", "reference", "payload", "verify",
    "validate", "digest", "to_jcs", "canonical_bytes", "read",
    "create_state", "publish_event", "attach_knowledge", "attach_evidence",
    "publish_learning_event", "derive_state", "merge_state",
    "apply_constraint", "snapshot", "current_check", "safety_from_holds",
    "validate_mapping_for_handoff", "validate_fusion_for_handoff",
    "publish_turn",
)