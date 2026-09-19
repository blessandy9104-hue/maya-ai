"""MAYA persona state + weighted multi-persona fusion foundation (Batch #6).

Minimal deterministic architecture for personas as *contextual lenses over
shared state*, never as separate memories or separate world models:

    UNIFIED STATE
        -> relevant personas
        -> persona-specific state transform
        -> weights
        -> fusion
        -> unified cognitive state

Personas may adjust priorities, interpretation emphasis, response
objectives, domain weighting, reasoning perspective, and language/expression
preferences within allowed bounds. They must NEVER modify: canonical truth or
evidence rules; epistemic status; safety boundaries; provenance; immutable
identity rules; canonical representation; or world-model facts without an
approved pathway.

Invariants enforced here (fail closed, deterministic):

- ``PersonaState`` is DERIVED from canonical/shared state. It references the
  source (``input_state_reference``) and never silently mutates it; geometry
  coordinates and canonical values travel in shared state, not in persona
  state, and candidate interpretations cannot override them.
- Activation is procedural: representation type, world kind, domain, explicit
  caller context (task type / switches), and relevance signals. No LLM, no
  randomness, no invented user intent. Insufficient evidence means AMBIGUOUS
  or INACTIVE; a free-text turn never implies a psychological persona.
- Weights are explicit and inspectable: ``raw_weight`` (declared, finite,
  non-negative) and ``normalized_weight`` with wi' = wi / sum(wi). NaN,
  infinity, negative and zero-sum weights fail closed. When no persona
  reaches the activation threshold the result is the explicit
  ``NO_ACTIVE_PERSONA`` state — no silent default.
- ``persona_weight`` NEVER equals epistemic confidence: a persona with weight
  0.8 does not make its interpretation 80% true. Fusion separates weights,
  activation confidence, and the inherited epistemic frame, which it copies
  from the canonical state (epistemic inheritance) and never alters.
- Conflicts are retained, never collapsed into false agreement:
  NO_CONFLICT / WEIGHTED_DISAGREEMENT / UNRESOLVED_CONFLICT / INCOMPATIBLE.
- Safety constraints are dominant: a persona cannot override a safety hold or
  block; core constraints win and the attempted override is *recorded*, not
  hidden.
- Geometry stays first-class and mathematically intact: a persona changes
  perspective/emphasis, never coordinate values.
- Growth foundation: personas are data/configuration objects conforming to
  ``validate_persona``, managed by ``PersonaRegistry`` (register / validate /
  activate / weight / deactivate / deploy). Deploy requires architect
  approval. This batch performs NO autonomous persona creation.

Boundary (Batch 8J-A naming contract): this module is the COGNITIVE persona
authority for the ``persona_fusion`` bus channel. It is deliberately NOT a
presentation personality layer and NOT an identity definition: how Maya
appears is owned by ``maya_runtime/personality.py`` (presentation), and who
Maya is is owned by ``maya_identity/identity.json`` (core identity). ``compute``
outputs a FusedPersonaState keyed for the intelligence bus; any future user of
this module must keep cognition, presentation, and identity separate.

Determinism: no randomness, no wall-clock, no network, no GUI, no LLM, no
eval/exec. Stable ordering (persona_id) throughout.
"""
from __future__ import annotations

import copy
import math
import re

from . import epistemic
from . import representation

PERSONA_PROTOCOL = "maya.persona_fusion.v1"
PERSONA_PROTOCOL_VERSION = 1

ACTIVATION_STATUSES = ("ACTIVE", "INACTIVE", "AMBIGUOUS")

PERSONA_SPEC_KEYS = (
    "persona_id", "name", "version", "domain", "priorities", "weights",
    "activation_conditions", "reasoning_profile", "expression_profile",
    "constraints", "provenance",
)

# PersonaState: derived, reference-only lens over shared canonical state.
PERSONA_STATE_KEYS = (
    "persona_id", "input_state_reference", "activation_score",
    "activation_status", "priority_vector", "perspective", "constraints",
    "candidate_interpretations", "confidence", "inherited_epistemic",
    "provenance",
)

CONFLICT_STATUSES = ("NO_CONFLICT", "WEIGHTED_DISAGREEMENT",
                     "UNRESOLVED_CONFLICT", "INCOMPATIBLE")

FUSION_STATUSES = ("FUSED", "NO_ACTIVE_PERSONA")
NO_ACTIVE_PERSONA = "NO_ACTIVE_PERSONA"
FUSION_METHOD = "weighted_multi_persona_fusion"

ARCHITECT_APPROVAL_ROLE = "architect"

FUSED_STATE_KEYS = (
    "status", "fusion_method", "active_personas", "weights", "consensus",
    "per_persona_contributions", "conflicts", "conflict_status",
    "unresolved_dimensions", "constraints", "inherited_epistemic", "safety",
    "notes", "excluded_inactive", "provenance",
)

# Candidate interpretations may only reframe emphasis; they can never carry
# world facts, geometry coordinates, epistemic/safety overrides, or memory.
_FORBIDDEN_CANDIDATE_KEYS = frozenset({
    "world_fact", "world_state", "geometry", "coordinates", "epistemic",
    "epistemic_status", "empirical_status", "validation_status",
    "external_validation", "claim_status", "safety", "safety_hold",
    "safety_blocked", "provenance",
})

_CORE_OVERRIDE_TOKENS = frozenset({
    "override_epistemic", "promote_to_fact", "override_safety_hold",
    "override_safety_blocked", "override_identity",
})

# Deterministic provenance anchor for the persona layer: a fixed constant,
# never a clock read. The shared provenance contract requires a UTC
# retrieval timestamp; this constant records the persona system's authoring
# anchor so every derived provenance is spelled on both interpreters.
PERSONA_ANCHOR_TIME = "2026-09-10T00:00:00Z"

_PERSONA_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")

# Relevance signals (mechanism, not a population) -- Part 12 of the contract.
SIGNAL_FOR_TYPE = {
    "text": ("language",),
    "scalar": ("numerical",),
    "measurement": ("quantitative", "evidential"),
    "vector": ("analytical", "quantitative"),
    "matrix": ("analytical", "structural"),
    "equation": ("mathematical", "analytical"),
    "symbol": ("symbolic",),
    "category": ("categorical", "structured"),
    "relation": ("relational", "structural"),
    "event": ("event", "temporal"),
    "temporal_interval": ("temporal",),
    "temporal": ("temporal",),
    "geometric_point": ("spatial", "analytical"),
    "geometric_vector": ("spatial", "analytical"),
    "geometric_transform": ("spatial", "analytical"),
    "geometric_object": ("spatial", "structural"),
    "graph": ("structural",),
    "probability": ("probabilistic", "epistemic"),
    "confidence": ("epistemic", "probabilistic"),
    "uncertainty": ("epistemic",),
    "identifier": ("identifier", "unresolved"),
    "language": ("language", "metadata"),
    "structured_canonical_object": ("structured", "metadata"),
    "claim": ("claim", "epistemic"),
}

SIGNAL_FOR_WORLD_KIND = {
    "measurement": ("quantitative", "evidential"),
    "event": ("event",),
    "relation": ("relational",),
    "temporal_reference": ("temporal",),
    "temporal_interval": ("temporal",),
    "geometric_object": ("spatial",),
    "geometric_point": ("spatial",),
    "geometric_vector": ("spatial",),
    "geometric_transform": ("spatial",),
    "graph": ("structural",),
    "entity": ("entity",),
    "location": ("spatial",),
    "process_state": ("process",),
    "claim_assertion": ("claim", "epistemic"),
    "unknown_reference": ("unresolved",),
    "encoded_data": ("encoded",),
    "encrypted_data": ("encrypted",),
    "hash": ("hash",),
    "signature": ("signature",),
    "key": ("key",),
    "certificate": ("certificate",),
    "cryptographic_claim": ("cryptographic_claim",),
}

_ALL_SIGNALS = frozenset(sum(list(SIGNAL_FOR_TYPE.values())
                              + list(SIGNAL_FOR_WORLD_KIND.values()), ()))


class PersonaError(ValueError):
    """Raised when a persona/fusion contract member is violated."""


def _reject(reason):
    raise PersonaError(reason)


def relevance_signals(detected_type=None, world_kind=None):
    """Deterministic relevance-signal set for a detection + mapping."""
    signals = []
    for kind, board in ((detected_type, SIGNAL_FOR_TYPE),
                        (world_kind, SIGNAL_FOR_WORLD_KIND)):
        for signal in board.get(kind, ()):
            if signal not in signals:
                signals.append(signal)
    return tuple(sorted(signals))


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------

def validate_weight(value, label="persona weight"):
    """Weights are finite and non-negative (no signed influence supported)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject("%s must be a real number" % (label,))
    number = float(value)
    if not math.isfinite(number):
        _reject("%s must be finite (no NaN/infinity)" % (label,))
    if number < 0.0:
        _reject("%s must be non-negative (signed influence is not supported "
                "by the contract)" % (label,))
    return number


def normalize_weights(raw_weights):
    """Explicit, inspectable normalization: wi' = wi / sum(wi).

    Returns ``{"raw": ..., "total": float, "normalized": ..., "status": ...}``.
    NaN/infinity/negative weights fail closed (PersonaError). A total of zero
    is an explicit ``zero_sum`` state, never a silent default. Ordering of the
    output follows the input list (callers must sort deterministically).
    """
    if not isinstance(raw_weights, (list, tuple)) or not raw_weights:
        _reject("raw_weights must be a non-empty sequence")
    raw = [validate_weight(w) for w in raw_weights]
    total = sum(raw)
    if total <= 0.0:
        return {"raw": raw, "total": total, "normalized": [],
                "status": "zero_sum"}
    return {"raw": raw, "total": round(total, 12),
            "normalized": [round(w / total, 6) for w in raw],
            "status": "normalized"}


# ---------------------------------------------------------------------------
# activation conditions
# ---------------------------------------------------------------------------

def _validate_conditions(conditions):
    if not isinstance(conditions, dict):
        _reject("activation_conditions must be a dict")
    allowed = {"threshold", "representation_types", "world_kinds", "domains",
               "task_types", "switches", "relevance_signals",
               "active_by_default"}
    unknown = set(conditions) - allowed
    if unknown:
        _reject("activation_conditions carry unknown keys %s"
                % sorted(unknown))
    threshold = conditions.get("threshold", 0.5)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        _reject("activation threshold must be a real number")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not (0.0 < threshold <= 1.0):
        _reject("activation threshold must be in (0, 1]")
    for key in ("representation_types", "world_kinds", "domains",
                "task_types"):
        values = conditions.get(key)
        if values is None:
            continue
        if not isinstance(values, (list, tuple)) or not all(
                isinstance(v, str) for v in values):
            _reject("activation %s must be a list of strings" % (key,))
    switches = conditions.get("switches")
    if switches is not None:
        if not isinstance(switches, dict) or not all(
                isinstance(k, str) and isinstance(v, bool)
                for k, v in switches.items()):
            _reject("activation switches must be a dict of str -> bool")
    signals = conditions.get("relevance_signals")
    if signals is not None:
        if not isinstance(signals, (list, tuple)) or not all(
                isinstance(s, str) and s in _ALL_SIGNALS
                for s in signals):
            _reject("relevance_signals must be declared signals "
                    "(%s ...)" % (", ".join(sorted(_ALL_SIGNALS)[:6]),))
    active_default = conditions.get("active_by_default")
    if active_default is not None and not isinstance(active_default, bool):
        _reject("active_by_default must be a bool")
    return conditions


def _condition_predicates(conditions, detected_type, world_kind, domain,
                          task_type, switches, signals):
    predicates = []
    if conditions.get("representation_types"):
        predicates.append(detected_type in conditions["representation_types"])
    if conditions.get("world_kinds"):
        predicates.append(world_kind in conditions["world_kinds"])
    if conditions.get("domains"):
        predicates.append(domain in conditions["domains"])
    if conditions.get("task_types"):
        predicates.append(task_type in conditions["task_types"])
    for name, required in (conditions.get("switches") or {}).items():
        predicates.append(bool((switches or {}).get(name)) == bool(required))
    if conditions.get("relevance_signals"):
        declared = frozenset(conditions["relevance_signals"])
        predicates.append(bool(declared & frozenset(signals)))
    return predicates


def activation(outcome, threshold=0.5):
    """Classify a [0,1] activation score into the 3-state vocabulary."""
    try:
        score = float(outcome)
    except (TypeError, ValueError):
        _reject("activation score must be a real number")
    if not math.isfinite(score):
        _reject("activation score must be finite")
    if score < 0.0 or score > 1.0:
        _reject("activation score must be in [0, 1]")
    threshold = float(threshold)
    if not (0.0 < threshold <= 1.0):
        _reject("activation threshold must be in (0, 1]")
    if score >= threshold:
        return "ACTIVE"
    if score > 0.0:
        return "AMBIGUOUS"
    return "INACTIVE"


def activation_score(persona, detected_type=None, world_kind=None,
                     domain=None, task_type=None, switches=None):
    """Deterministic activation score of one persona against a turn context.

    A persona with declared conditions scores the matched-fraction of its
    predicates. A persona with no conditions is INACTIVE unless it explicitly
    declares ``active_by_default`` (recorded, never silent).
    """
    conditions = persona.get("activation_conditions") or {}
    predicates = _condition_predicates(
        conditions, detected_type, world_kind, domain, task_type, switches,
        relevance_signals(detected_type, world_kind))
    if not predicates:
        if conditions.get("active_by_default"):
            return 1.0
        return 0.0
    return len([p for p in predicates if p]) / float(len(predicates))


# ---------------------------------------------------------------------------
# persona specification
# ---------------------------------------------------------------------------

def _validate_provenance(provenance):
    if provenance is None:
        return None
    if not isinstance(provenance, dict):
        _reject("persona provenance must be a dict or null")
    try:
        representation.validate_provenance(provenance)
    except representation.RepresentationError as exc:
        _reject("persona provenance rejected: %s" % (exc,))
    return dict(provenance)


def _validate_constraints(constraints):
    if constraints is None:
        return {"allowed_modes": [], "prohibited_modes": [],
                "requires": [], "notes": None}
    if not isinstance(constraints, dict):
        _reject("persona constraints must be a dict or null")
    allowed = {"allowed_modes", "prohibited_modes", "requires", "notes"}
    unknown = set(constraints) - allowed
    if unknown:
        _reject("constraints carry unknown keys %s" % sorted(unknown))
    resolved = {}
    for key in ("allowed_modes", "prohibited_modes", "requires"):
        values = constraints.get(key) or []
        if not isinstance(values, (list, tuple)) or not all(
                isinstance(v, str) for v in values):
            _reject("constraints.%s must be a list of strings" % (key,))
        resolved[key] = list(values)
    notes = constraints.get("notes")
    if notes is not None and not isinstance(notes, str):
        _reject("constraints.notes must be a string or null")
    resolved["notes"] = notes
    return resolved


def validate_persona(persona):
    """Structural validation of a persona *data object* (fail closed)."""
    if not isinstance(persona, dict):
        return {"valid": False, "reason": "persona must be a dict"}
    if set(persona) != set(PERSONA_SPEC_KEYS):
        return {"valid": False,
                "reason": "keys differ from the persona specification: %s"
                          % (sorted(PERSONA_SPEC_KEYS),)}
    persona_id = persona.get("persona_id")
    if not isinstance(persona_id, str) or not _PERSONA_ID_RE.match(persona_id):
        return {"valid": False,
                "reason": "persona_id must be an identifier string"}
    if not isinstance(persona.get("name"), str) or not persona["name"].strip():
        return {"valid": False, "reason": "name must be a non-empty string"}
    if not isinstance(persona.get("version"), str) or \
            not persona["version"].strip():
        return {"valid": False, "reason": "version must be a non-empty string"}
    domain = persona.get("domain")
    if domain not in epistemic.DOMAIN_VOCABULARY:
        return {"valid": False,
                "reason": "domain %r not in the domain vocabulary"
                          % (domain,)}
    priorities = persona.get("priorities")
    if not isinstance(priorities, dict) or not priorities:
        return {"valid": False,
                "reason": "priorities must be a non-empty dict"}
    for dimension, value in priorities.items():
        try:
            validate_weight(value, "priorities.%s" % (dimension,))
            if abs(float(value)) > 1.0:
                raise PersonaError(
                    "priority components are bounded to [-1, 1] "
                    "(sign = direction, magnitude = importance)")
        except PersonaError as exc:
            return {"valid": False, "reason": "priorities: %s" % (exc,)}
    weights = persona.get("weights")
    if not isinstance(weights, dict) or "base" not in weights:
        return {"valid": False,
                "reason": "weights must be a dict with a base weight"}
    try:
        validate_weight(weights.get("base"), "weights.base")
    except PersonaError as exc:
        return {"valid": False, "reason": str(exc)}
    try:
        _validate_conditions(persona.get("activation_conditions"))
    except PersonaError as exc:
        return {"valid": False, "reason": str(exc)}
    reasoning = persona.get("reasoning_profile")
    expression = persona.get("expression_profile")
    if not isinstance(reasoning, dict) or not reasoning:
        return {"valid": False,
                "reason": "reasoning_profile must be a non-empty dict"}
    if not isinstance(expression, dict) or not expression:
        return {"valid": False,
                "reason": "expression_profile must be a non-empty dict"}
    try:
        _validate_constraints(persona.get("constraints"))
        _validate_provenance(persona.get("provenance"))
    except PersonaError as exc:
        return {"valid": False, "reason": str(exc)}
    return {"valid": True, "reason": None}


def require_valid_persona(persona):
    result = validate_persona(persona)
    if not result["valid"]:
        _reject("persona %r rejected: %s"
                % (persona.get("persona_id") if isinstance(persona, dict)
                   else persona, result["reason"]))
    return persona


# ---------------------------------------------------------------------------
# persona state (derived lens over shared canonical state)
# ---------------------------------------------------------------------------

def derive_persona_state(persona, *, world_mapping=None, detected_type=None,
                         state_reference=None, task_type=None, switches=None,
                         provenance=None):
    """Derive the typed PersonaState for one persona from the turn context.

    The state is derived from canonical/shared state: it references the source
    (``input_state_reference``), copies only the epistemic frame, and never
    mutates the source. ``detected_type``/``world_mapping`` may be supplied by
    the calling layer; insufficient evidence yields INACTIVE or AMBIGUOUS.
    """
    require_valid_persona(persona)
    mapping = world_mapping
    if mapping is not None and not isinstance(mapping, dict):
        _reject("world_mapping must be a dict or null (corrupted canonical "
                "state fails closed)")
    world_kind = mapping.get("world_kind") if isinstance(mapping, dict) \
        else None
    epistemic_block = mapping.get("epistemic") if isinstance(mapping, dict) \
        else None
    if epistemic_block is not None and not isinstance(epistemic_block, dict):
        _reject("world_mapping.epistemic must be a dict or null")
    inherited = copy.deepcopy(epistemic_block) if isinstance(epistemic_block,
                                                             dict) else None
    domain = None
    if isinstance(inherited, dict):
        domain = inherited.get("domain")
    score = activation_score(persona, detected_type=detected_type,
                             world_kind=world_kind,
                             domain=domain if domain in
                             epistemic.DOMAIN_VOCABULARY else None,
                             task_type=task_type, switches=switches)
    conditions = persona.get("activation_conditions") or {}
    threshold = float(conditions.get("threshold", 0.5))
    status = activation(score, threshold)
    state_id = persona.get("persona_id")

    perspective = {
        "perspective": str(persona.get("reasoning_profile", {}).get(
            "perspective") or persona.get("name")),
        "emphasis": list(persona.get("reasoning_profile", {}).get(
            "emphasis") or []),
        "expression": str(persona.get("expression_profile", {}).get(
            "register") or "measured"),
    }
    constraints = _validate_constraints(persona.get("constraints"))
    candidate_interpretations = [
        {"interpretation": text, "scope": "emphasis"}
        for text in (persona.get("reasoning_profile", {}).get(
            "candidate_interpretations") or [])
        if isinstance(text, str)
    ]
    if provenance is None:
        provenance = {"source": "persona.layer", "source_url": None,
                      "retrieved_at": PERSONA_ANCHOR_TIME,
                      "evidence_type": "observation",
                      "confidence": "medium",
                      "claim": "Persona lens derived from shared canonical "
                               "state."}
    return {
        "persona_id": state_id,
        "input_state_reference": state_reference,
        "activation_score": round(score, 6),
        "activation_status": status,
        "priority_vector": dict(persona["priorities"]),
        "perspective": perspective,
        "constraints": constraints,
        "candidate_interpretations": candidate_interpretations,
        "confidence": round(score, 6),
        "inherited_epistemic": inherited,
        "provenance": _validate_provenance(provenance),
    }


def validate_persona_state(state, canonical_epistemic=None):
    """Structural + inheritance guard for a derived PersonaState."""
    if not isinstance(state, dict):
        return {"valid": False, "reason": "persona state must be a dict"}
    if set(state) != set(PERSONA_STATE_KEYS):
        return {"valid": False,
                "reason": "keys differ from the PersonaState contract: %s"
                          % (sorted(PERSONA_STATE_KEYS),)}
    if state.get("activation_status") not in ACTIVATION_STATUSES:
        return {"valid": False,
                "reason": "activation_status %r outside %s"
                          % (state.get("activation_status"),
                             ACTIVATION_STATUSES)}
    score = state.get("activation_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or \
            not math.isfinite(float(score)) or not (0.0 <= score <= 1.0):
        return {"valid": False, "reason": "activation_score must be in [0,1]"}
    if not isinstance(state.get("priority_vector"), dict):
        return {"valid": False, "reason": "priority_vector must be a dict"}
    perspective = state.get("perspective")
    if not isinstance(perspective, dict) or not perspective:
        return {"valid": False,
                "reason": "perspective must be a non-empty dict"}
    if not isinstance(state.get("constraints"), dict):
        return {"valid": False, "reason": "constraints must be a dict"}
    candidates = state.get("candidate_interpretations")
    if not isinstance(candidates, list):
        return {"valid": False,
                "reason": "candidate_interpretations must be a list"}
    for item in candidates:
        if not isinstance(item, dict):
            return {"valid": False,
                    "reason": "candidate_interpretations entries must be "
                              "dicts"}
        forbidden = sorted(set(item) & _FORBIDDEN_CANDIDATE_KEYS)
        if forbidden:
            return {"valid": False,
                    "reason": "candidate_interpretations attempt forbidden "
                              "fields %s (world facts/geometry/epistemic/"
                              "safety/memory are never carried by a persona)"
                              % (forbidden,)}
        if "scope" in item and item.get("scope") != "emphasis":
            return {"valid": False,
                    "reason": "candidate_interpretations may only be "
                              "emphasis reframings"}
    confidence = state.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence,
                                                      (int, float)) or \
            not math.isfinite(float(confidence)):
        return {"valid": False, "reason": "confidence must be finite"}
    state_epistemic = state.get("inherited_epistemic")
    if state_epistemic is not None and not isinstance(state_epistemic, dict):
        return {"valid": False,
                "reason": "inherited_epistemic must be a dict or null"}
    if canonical_epistemic is not None:
        if state_epistemic != canonical_epistemic:
            return {"valid": False,
                    "reason": "epistemic inheritance violated: the persona "
                              "state does not preserve the canonical "
                              "epistemic frame"}
    if not isinstance(state.get("provenance"), dict):
        return {"valid": False, "reason": "provenance must be a dict"}
    return {"valid": True, "reason": None}


# ---------------------------------------------------------------------------
# conflicts
# ---------------------------------------------------------------------------

_EPS = 1e-9
_DISAGREEMENT_MAGNITUDE = 0.1


def _constraint_pairs_incompatible(a, b):
    a_requires = set(a.get("requires") or ())
    a_prohibits = set(a.get("prohibited_modes") or ())
    b_requires = set(b.get("requires") or ())
    b_prohibits = set(b.get("prohibited_modes") or ())
    return bool(a_requires & b_prohibits) or bool(b_requires & a_prohibits)


def classify_conflict(state_a, state_b):
    """Pairwise conflict classification (never collapses disagreement)."""
    va = state_a.get("priority_vector") or {}
    vb = state_b.get("priority_vector") or {}
    dims = sorted(set(va) | set(vb))
    if not dims:
        return "NO_CONFLICT", [], "no comparable priority dimensions"
    differences = []
    for dim in dims:
        a = float(va.get(dim, 0.0))
        b = float(vb.get(dim, 0.0))
        if abs(a - b) > _EPS:
            differences.append(dim)
    if not differences:
        if _constraint_pairs_incompatible(state_a.get("constraints") or {},
                                          state_b.get("constraints") or {}):
            return "INCOMPATIBLE", differences, \
                "persona constraints are mutually exclusive"
        return "NO_CONFLICT", differences, \
            "priority vectors agree on every dimension"
    if _constraint_pairs_incompatible(state_a.get("constraints") or {},
                                      state_b.get("constraints") or {}):
        return "INCOMPATIBLE", differences, \
            "persona constraints are mutually exclusive"
    opposing = []
    for dim in differences:
        a = float(va.get(dim, 0.0))
        b = float(vb.get(dim, 0.0))
        if (a > _DISAGREEMENT_MAGNITUDE and b < -_DISAGREEMENT_MAGNITUDE) or \
                (a < -_DISAGREEMENT_MAGNITUDE and b > _DISAGREEMENT_MAGNITUDE):
            opposing.append(dim)
    if opposing:
        return "UNRESOLVED_CONFLICT", differences, \
            "opposing priority directions on %s" % (",".join(opposing),)
    return "WEIGHTED_DISAGREEMENT", differences, "weighted disagreement"


def _core_violation_tokens(state):
    """A persona only *attempts* a core override when it REQUIRES one.

    A persona that *prohibits* a core-override token (e.g.
    ``prohibited_modes: ["promote_to_fact"]``) is protective and must never
    be flagged; only a required override is an attempt, and it is blocked.
    """
    tokens = set()
    constraints = state.get("constraints") or {}
    for token in constraints.get("requires") or ():
        if token in _CORE_OVERRIDE_TOKENS:
            tokens.add(token)
    return tokens


# ---------------------------------------------------------------------------
# fusion
# ---------------------------------------------------------------------------

def _no_active_fusion(excluded, reason="no persona reaches the activation "
                                      "threshold"):
    return {
        "status": NO_ACTIVE_PERSONA,
        "fusion_method": FUSION_METHOD,
        "active_personas": [],
        "weights": {},
        "consensus": {},
        "per_persona_contributions": [],
        "conflicts": [],
        "conflict_status": "NO_CONFLICT",
        "unresolved_dimensions": [],
        "constraints": {"core": [], "effective": [],
                        "persona_contributions": [],
                        "overrides_recorded": []},
        "inherited_epistemic": None,
        "safety": {"core_dominant": True, "persona_override_blocked": False,
                   "core_holds": None, "core_blocked": None,
                   "restrictions_recorded": []},
        "notes": [reason],
        "excluded_inactive": sorted(excluded),
        "provenance": {"source": "persona.layer", "source_url": None,
                       "retrieved_at": PERSONA_ANCHOR_TIME,
                       "evidence_type": "observation",
                       "confidence": "medium",
                       "claim": "No active persona; explicit state, no "
                                "silent default."},
    }


def fuse(persona_states, personas=None, *, core_epistemic=None,
         core_safety=None, core_constraints=None):
    """Weighted multi-persona fusion -> FusedPersonaState (cognitive state).

    ``personas`` is the persona registry mapping (persona_id -> persona spec)
    that supplies declared ``weights.base``. Non-ACTIVE states are excluded
    explicitly; adversarial states are rejected (fail closed). Consensus is a
    weighted aggregate of *priority vectors* (a steering lens, never truth);
    conflicts are retained. The inherited epistemic frame is copied through
    unchanged, and core safety constraints dominate.
    """
    for state in persona_states:
        result = validate_persona_state(state)
        if not result["valid"]:
            _reject("persona state invalid (fails closed): %s"
                    % result["reason"])
    active = [s for s in persona_states
              if s["activation_status"] == "ACTIVE"]
    excluded = [s["persona_id"] for s in persona_states
                if s["activation_status"] != "ACTIVE"]
    if not active:
        return _no_active_fusion(excluded)

    ordered = sorted(active, key=lambda s: s["persona_id"])
    personas = personas or {}
    raw_by_id = {}
    for state in ordered:
        persona = personas.get(state["persona_id"])
        if not isinstance(persona, dict):
            _reject("unknown persona id %r (fail closed)"
                    % (state["persona_id"],))
        raw_by_id[state["persona_id"]] = validate_weight(
            persona.get("weights", {}).get("base"),
            "weights.base of %s" % state["persona_id"])

    norm = normalize_weights(
        [raw_by_id[s["persona_id"]] for s in ordered])
    if norm["status"] == "zero_sum":
        return _no_active_fusion(excluded,
                                 reason="zero total weight among active "
                                        "personas (fail closed)")

    weights = {}
    for state, normalized in zip(ordered, norm["normalized"]):
        weights[state["persona_id"]] = {
            "raw_weight": round(raw_by_id[state["persona_id"]], 6),
            "normalized_weight": normalized,
        }

    # consensus: weighted element-wise aggregate of priority vectors
    dims = sorted(set().union(*[set(s["priority_vector"])
                                for s in ordered]) if ordered else set())
    consensus = {}
    for dim in dims:
        total = 0.0
        for state, normalized in zip(ordered, norm["normalized"]):
            total += normalized * float(state["priority_vector"].get(dim, 0.0))
        consensus[dim] = round(total, 4)

    # conflicts (pairwise, retained, never collapsed)
    conflicts = []
    conflict_severity = 0
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            classification, dims_diff, note = classify_conflict(
                ordered[i], ordered[j])
            entry = {
                "between": [ordered[i]["persona_id"],
                            ordered[j]["persona_id"]],
                "classification": classification,
                "dimensions": dims_diff,
                "note": note,
            }
            conflicts.append(entry)
            order = (CONFLICT_STATUSES.index(classification)
                     if classification in CONFLICT_STATUSES else 0)
            conflict_severity = max(conflict_severity, order)
            if classification == "INCOMPATIBLE":
                core_tokens_a = _core_violation_tokens(ordered[i])
                core_tokens_b = _core_violation_tokens(ordered[j])
                if core_tokens_a or core_tokens_b:
                    entry["note"] = "%s; core constraint wins" % (note,)
    conflict_status = CONFLICT_STATUSES[conflict_severity]

    # unresolved dimensions: high-weighted disagreement from the consensus
    unresolved = []
    for dim in dims:
        spread = 0.0
        for state, normalized in zip(ordered, norm["normalized"]):
            spread += normalized * abs(
                float(state["priority_vector"].get(dim, 0.0))
                - consensus[dim])
        if spread > 0.3:
            unresolved.append(dim)

    # epistemic inheritance: all active personas must preserve the frame
    inherited = None
    inheritance_violation = False
    for state in ordered:
        block = state.get("inherited_epistemic")
        if block is None:
            continue
        if inherited is None:
            inherited = block
        elif inherited != block:
            inheritance_violation = True
            break
    if core_epistemic is not None:
        if inherited != core_epistemic:
            inheritance_violation = True
        inherited = copy.deepcopy(core_epistemic)
    if inheritance_violation:
        conflicts.append({
            "between": [s["persona_id"] for s in ordered],
            "classification": "INCOMPATIBLE",
            "dimensions": ["inherited_epistemic"],
            "note": "epistemic inheritance violated; canonical frame wins",
        })
        conflict_status = "INCOMPATIBLE"

    # safety + core constraints precedence
    core_holds = None
    core_blocked = None
    restrictions = []
    if isinstance(core_safety, dict):
        core_holds = bool(core_safety.get("hold") or
                          core_safety.get("safety_hold"))
        core_blocked = bool(core_safety.get("blocked") or
                            core_safety.get("safety_blocked"))
    discovered_overrides = []
    for state in ordered:
        core_tokens = sorted(_core_violation_tokens(state))
        if core_tokens:
            discovered_overrides.append({
                "persona_id": state["persona_id"],
                "tokens": core_tokens,
            })
            conflicts.append({
                "between": [state["persona_id"]],
                "classification": "INCOMPATIBLE",
                "dimensions": ["core_constraints"],
                "note": "persona attempted to override a core constraint; "
                        "core wins",
            })
            conflict_status = "INCOMPATIBLE"
    if discovered_overrides:
        restrictions = [{"persona_id": item["persona_id"],
                         "blocked_tokens": item["tokens"]}
                        for item in discovered_overrides]

    effective = sorted(set(core_constraints or ()))
    persona_contribs = []
    for state in ordered:
        for token in (state.get("constraints", {}).get("requires") or ()):
            if token not in effective and token not in _CORE_OVERRIDE_TOKENS:
                effective.append(token)
    effective = sorted(effective)

    overrides_recorded = [item["persona_id"] for item in
                          discovered_overrides]
    contributions = []
    for state, normalized in zip(ordered, norm["normalized"]):
        contributions.append({
            "persona_id": state["persona_id"],
            "weight": normalized,
            "perspective": state["perspective"],
            "candidate_interpretations": state["candidate_interpretations"],
        })

    return {
        "status": "FUSED",
        "fusion_method": FUSION_METHOD,
        "active_personas": [s["persona_id"] for s in ordered],
        "weights": weights,
        "consensus": consensus,
        "per_persona_contributions": contributions,
        "conflicts": conflicts,
        "conflict_status": conflict_status,
        "unresolved_dimensions": sorted(unresolved),
        "constraints": {
            "core": sorted(core_constraints or ()),
            "effective": effective,
            "persona_contributions": persona_contribs,
            "overrides_recorded": overrides_recorded,
        },
        "inherited_epistemic": copy.deepcopy(inherited),
        "safety": {
            "core_dominant": True,
            "persona_override_blocked": bool(discovered_overrides),
            "core_holds": core_holds,
            "core_blocked": core_blocked,
            "restrictions_recorded": restrictions,
        },
        "notes": [
            "weights are influence weights only; persona_weight is not "
            "epistemic probability and never changes epistemic status or "
            "validation",
            "consensus is a weighted priority lens, not a truth value; "
            "conflicts are retained",
        ],
        "excluded_inactive": sorted(excluded),
        "provenance": {"source": "persona.layer", "source_url": None,
                       "retrieved_at": PERSONA_ANCHOR_TIME,
                       "evidence_type": "observation",
                       "confidence": "medium",
                       "claim": "Weighted multi-persona fusion over shared "
                                "canonical state."},
    }


def validate_fused_state(fused):
    """Structural validation of a fused cognitive state (fail closed)."""
    if not isinstance(fused, dict):
        return {"valid": False, "reason": "fused state must be a dict"}
    if set(fused) != set(FUSED_STATE_KEYS):
        return {"valid": False,
                "reason": "keys differ from the FusedPersonaState contract: "
                          "%s" % (sorted(FUSED_STATE_KEYS),)}
    if fused.get("status") not in FUSION_STATUSES:
        return {"valid": False,
                "reason": "status %r outside %s"
                          % (fused.get("status"), FUSION_STATUSES)}
    if fused.get("fusion_method") != FUSION_METHOD:
        return {"valid": False, "reason": "fusion_method must be %r"
                                          % (FUSION_METHOD,)}
    if fused.get("status") == NO_ACTIVE_PERSONA:
        if fused.get("active_personas"):
            return {"valid": False,
                    "reason": "NO_ACTIVE_PERSONA must have no active personas"}
    else:
        if not fused.get("active_personas"):
            return {"valid": False,
                    "reason": "FUSED must have at least one active persona"}
        if not isinstance(fused.get("consensus"), dict):
            return {"valid": False, "reason": "consensus must be a dict"}
    if not isinstance(fused.get("weights"), dict):
        return {"valid": False, "reason": "weights must be a dict"}
    if not isinstance(fused.get("conflicts"), list):
        return {"valid": False, "reason": "conflicts must be a list"}
    conflict_status = fused.get("conflict_status")
    if conflict_status not in CONFLICT_STATUSES:
        return {"valid": False,
                "reason": "conflict_status %r outside %s"
                          % (conflict_status, CONFLICT_STATUSES)}
    if not isinstance(fused.get("unresolved_dimensions"), list):
        return {"valid": False,
                "reason": "unresolved_dimensions must be a list"}
    if not isinstance(fused.get("constraints"), dict):
        return {"valid": False, "reason": "constraints must be a dict"}
    epistemic_block = fused.get("inherited_epistemic")
    if epistemic_block is not None and not isinstance(epistemic_block, dict):
        return {"valid": False,
                "reason": "inherited_epistemic must be a dict or null"}
    if not isinstance(fused.get("safety"), dict):
        return {"valid": False, "reason": "safety must be a dict"}
    if not isinstance(fused.get("provenance"), dict):
        return {"valid": False, "reason": "provenance must be a dict"}
    return {"valid": True, "reason": None}


# ---------------------------------------------------------------------------
# registry + starter personas (mechanism, not a population)
# ---------------------------------------------------------------------------

DEFAULT_PERSONAS = (
    {
        "persona_id": "persona.analytical.geometry",
        "name": "geometry and analytical lens",
        "version": "1.0",
        "domain": "GEOMETRIC",
        "priorities": {"precision": 0.9, "interpretation": 0.1},
        "weights": {"base": 2.0},
        "activation_conditions": {
            "threshold": 0.5,
            "representation_types": ["geometric_point", "geometric_vector",
                                     "geometric_transform",
                                     "geometric_object"],
            "world_kinds": ["geometric_point", "geometric_vector",
                            "geometric_transform", "geometric_object"],
            "relevance_signals": ["spatial"],
        },
        "reasoning_profile": {
            "perspective": "coordinate precision and spatial structure",
            "emphasis": ["coordinate precision", "spatial structure",
                         "identity-space conformance"],
            "candidate_interpretations": [
                "analyze geometric structure without altering coordinates",
            ],
        },
        "expression_profile": {"register": "precise", "tone": "technical"},
        "constraints": {"allowed_modes": ["geometry"],
                        "prohibited_modes": [],
                        "requires": ["preserve_coordinates"],
                        "notes": "coordinates live in shared state; never "
                                 "reinterpreted"},
        "provenance": {"source": "persona.registry", "source_url": None,
                       "retrieved_at": PERSONA_ANCHOR_TIME,
                       "evidence_type": "observation",
                       "confidence": "medium",
                       "claim": "Deterministic starter persona (architect "
                                "approved).",
                       "approval_role": ARCHITECT_APPROVAL_ROLE},
    },
    {
        "persona_id": "persona.core.evidence",
        "name": "evidence and measurement lens",
        "version": "1.0",
        "domain": "STRUCTURED_DATA",
        "priorities": {"precision": 0.6, "interpretation": 0.2,
                       "conservatism": 0.8},
        "weights": {"base": 1.0},
        "activation_conditions": {
            "threshold": 0.5,
            "representation_types": ["measurement"],
            "world_kinds": ["measurement"],
            "relevance_signals": ["quantitative", "evidential"],
        },
        "reasoning_profile": {
            "perspective": "quantitative evidence with declared validation",
            "emphasis": ["units preserved", "validation declared",
                         "no unsupported magnitude claims"],
            "candidate_interpretations": [
                "treat the value as a quantitative observation",
            ],
        },
        "expression_profile": {"register": "measured", "tone": "neutral"},
        "constraints": {"allowed_modes": ["evidence"],
                        "prohibited_modes": ["promote_to_fact"],
                        "requires": [],
                        "notes": "the epistemic frame is inherited; never "
                                 "promoted"},
        "provenance": {"source": "persona.registry", "source_url": None,
                       "retrieved_at": PERSONA_ANCHOR_TIME,
                       "evidence_type": "observation",
                       "confidence": "medium",
                       "claim": "Deterministic starter persona (architect "
                                "approved).",
                       "approval_role": ARCHITECT_APPROVAL_ROLE},
    },
)


class PersonaRegistry:
    """Minimal deterministic persona registry (growth foundation).

    Personas are data objects conforming to ``validate_persona``. The
    registry supports register / validate / activate / weight / deactivate /
    deploy; deployment requires architect approval recorded in provenance.
    """

    def __init__(self, personas=()):
        self._personas = {}
        self._enabled = set()
        for persona in personas:
            self.register(persona)

    def _lookup(self, persona_id):
        if not isinstance(persona_id, str) or persona_id not in self._personas:
            _reject("unknown persona id %r (fail closed)" % (persona_id,))
        return self._personas[persona_id]

    def register(self, persona):
        require_valid_persona(persona)
        persona_id = persona["persona_id"]
        if persona_id in self._personas:
            _reject("duplicate persona id %r (fail closed)" % (persona_id,))
        self._personas[persona_id] = copy.deepcopy(persona)
        self._enabled.add(persona_id)
        return persona_id

    def validate(self, persona):
        return validate_persona(persona)

    def activate(self, persona_id, *, world_mapping=None, detected_type=None,
                 state_reference=None, task_type=None, switches=None,
                 provenance=None):
        persona = self._lookup(persona_id)
        state = derive_persona_state(
            persona, world_mapping=world_mapping, detected_type=detected_type,
            state_reference=state_reference, task_type=task_type,
            switches=switches, provenance=provenance)
        if persona_id in self._enabled:
            return state
        return _deactivate_state(state)

    def weight(self, persona_id):
        persona = self._lookup(persona_id)
        return {"persona_id": persona_id,
                "raw_weight": validate_weight(persona["weights"]["base"])}

    def deactivate(self, persona_id):
        self._lookup(persona_id)
        self._enabled.discard(persona_id)
        return {"persona_id": persona_id, "enabled": False}

    def deploy(self, persona_id):
        persona = self._lookup(persona_id)
        provenance = persona.get("provenance") or {}
        role = provenance.get("approval_role")
        if role != ARCHITECT_APPROVAL_ROLE:
            _reject("deployment of persona %r requires architect approval "
                    "(fail closed)" % (persona_id,))
        self._enabled.add(persona_id)
        return {"persona_id": persona_id, "deployed": True}

    def lookup(self, persona_id):
        return copy.deepcopy(self._lookup(persona_id))

    def all(self):
        return tuple(sorted(self._personas))

    def enabled(self):
        return tuple(sorted(self._enabled))


def _deactivate_state(state):
    state = copy.deepcopy(state)
    state["activation_status"] = "INACTIVE"
    state["activation_score"] = 0.0
    state["confidence"] = 0.0
    return state


def default_registry():
    return PersonaRegistry(DEFAULT_PERSONAS)


def compute(*, world_mapping=None, detected_type=None, personas=None,
            task_type=None, switches=None, state_reference=None,
            core_epistemic=None, core_safety=None, core_constraints=None,
            provenance=None):
    """Convenience: derive every enabled persona state and fuse the turn.

    Returns the FusedPersonaState (FUSED or the explicit NO_ACTIVE_PERSONA
    state). Deterministic; safe at the bridge boundary because it never
    raises for a mere absence of evidence (an adversarial/corrupt input still
    fails closed through the raise paths above).
    """
    registry = personas if isinstance(personas, PersonaRegistry) \
        else default_registry()
    states = []
    for persona_id in registry.enabled():
        persona = registry._personas[persona_id]
        states.append(derive_persona_state(
            persona, world_mapping=world_mapping,
            detected_type=detected_type, state_reference=state_reference,
            task_type=task_type, switches=switches, provenance=provenance))
    if core_epistemic is not None and isinstance(world_mapping, dict):
        mapping_epistemic = world_mapping.get("epistemic")
        if isinstance(mapping_epistemic, dict) and \
                core_epistemic != mapping_epistemic:
            _reject("core_epistemic must equal the canonical epistemic frame")
    return fuse(states, personas=registry._personas, core_epistemic=core_epistemic,
                core_safety=core_safety, core_constraints=core_constraints)


__all__ = (
    "PERSONA_PROTOCOL", "PERSONA_PROTOCOL_VERSION", "ACTIVATION_STATUSES",
    "PERSONA_SPEC_KEYS", "PERSONA_STATE_KEYS", "CONFLICT_STATUSES",
    "FUSION_STATUSES", "NO_ACTIVE_PERSONA", "FUSION_METHOD",
    "FUSED_STATE_KEYS", "SIGNAL_FOR_TYPE", "SIGNAL_FOR_WORLD_KIND",
    "PersonaError", "relevance_signals", "validate_weight",
    "normalize_weights", "activation", "activation_score", "validate_persona",
    "require_valid_persona", "derive_persona_state", "validate_persona_state",
    "classify_conflict", "fuse", "validate_fused_state", "DEFAULT_PERSONAS",
    "ARCHITECT_APPROVAL_ROLE", "PersonaRegistry", "default_registry",
    "compute",
)