"""Clean-room oracle for the persona state + weighted multi-persona fusion
contract (Batch #6).

Independent, non-importing re-derivation of the persona/fusion decisions from
the *published contract* alone. This module imports ONLY the standard
library: it must never import ``maya_runtime``, otherwise its comparison in
``test_persona_fusion.py`` would be circular rather than independent.

The persona/fusion contract (as published):

- Personas are contextual lenses over shared state. PersonaState is DERIVED;
  it references the source and never mutates canonical values, geometry
  coordinates, epistemic status, safety, provenance or identity.
- Activation is deterministic from representation type, world kind, domain,
  explicit caller context (task type / switches) and relevance signals.
  Score = matched-fraction of declared predicates. ACTIVE when
  score >= threshold (default 0.5), AMBIGUOUS when 0 < score < threshold,
  INACTIVE when score == 0. No LLM, no randomness, no invented intent.
- Weights: raw (finite, non-negative, declared) and normalized with
  wi' = wi / sum(wi). NaN/infinity/negative fail closed; zero sum is an
  explicit zero_sum/no-active state. When no persona reaches the threshold
  the fusion is the explicit NO_ACTIVE_PERSONA state — never a silent default.
- persona_weight is influence weighting, NOT epistemic probability; the
  inherited epistemic frame is copied through unchanged.
- Conflicts are retained: NO_CONFLICT / WEIGHTED_DISAGREEMENT /
  UNRESOLVED_CONFLICT / INCOMPATIBLE. Core safety constraints dominate; a
  required core override is blocked and recorded, never hidden.
- Geometry stays mathematically intact; a persona changes only emphasis.
"""
from __future__ import annotations

import math

ORACLE_ACTIVATION_STATUSES = frozenset({"ACTIVE", "INACTIVE", "AMBIGUOUS"})
ORACLE_FUSION_STATUSES = frozenset({"FUSED", "NO_ACTIVE_PERSONA"})
ORACLE_CONFLICT_STATUSES = ("NO_CONFLICT", "WEIGHTED_DISAGREEMENT",
                            "UNRESOLVED_CONFLICT", "INCOMPATIBLE")

EPS = 1e-9
DISAGREEMENT_MAGNITUDE = 0.1
UNRESOLVED_SPREAD = 0.3
CORE_OVERRIDE_TOKENS = frozenset({
    "override_epistemic", "promote_to_fact", "override_safety_hold",
    "override_safety_blocked", "override_identity",
})


def _predicates(conditions, detected_type, world_kind, domain, task_type,
                switches, signals):
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
        predicates.append(bool(
            set(conditions["relevance_signals"]) & frozenset(signals)))
    return predicates


ORACLE_SIGNAL_FOR_TYPE = {
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
ORACLE_SIGNAL_FOR_WORLD_KIND = {
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


def oracle_signals(detected_type=None, world_kind=None):
    signals = []
    for kind, board in ((detected_type, ORACLE_SIGNAL_FOR_TYPE),
                        (world_kind, ORACLE_SIGNAL_FOR_WORLD_KIND)):
        for signal in board.get(kind, ()):
            if signal not in signals:
                signals.append(signal)
    return tuple(sorted(signals))


def oracle_score(conditions, detected_type, world_kind, domain, task_type,
                 switches, signals=None):
    conditions = conditions or {}
    if signals is None:
        signals = oracle_signals(detected_type, world_kind)
    predicates = _predicates(conditions, detected_type, world_kind, domain,
                             task_type, switches, signals)
    if not predicates:
        return 1.0 if conditions.get("active_by_default") else 0.0
    return len([p for p in predicates if p]) / float(len(predicates))


def oracle_status(score, threshold=0.5):
    score = float(score)
    if score >= float(threshold):
        return "ACTIVE"
    if score > 0.0:
        return "AMBIGUOUS"
    return "INACTIVE"


def oracle_normalize(raw_weights):
    if not raw_weights:
        return {"raw": [], "total": 0.0, "normalized": [], "status": "empty"}
    total = sum(float(w) for w in raw_weights)
    if total <= 0.0:
        return {"raw": list(raw_weights), "total": round(total, 12),
                "normalized": [], "status": "zero_sum"}
    return {
        "raw": [float(w) for w in raw_weights],
        "total": round(total, 12),
        "normalized": [round(float(w) / total, 6) for w in raw_weights],
        "status": "normalized",
    }


def oracle_consensus(active, normalized):
    dims = sorted(set().union(*[set(s["priority_vector"])
                                for s in active]) if active else set())
    consensus = {}
    for dim in dims:
        total = 0.0
        for state, w in zip(active, normalized):
            total += w * float(state["priority_vector"].get(dim, 0.0))
        consensus[dim] = round(total, 4)
    return consensus


def _constraint_pairs_incompatible(a, b):
    a_requires = set((a or {}).get("requires") or [])
    a_prohibits = set((a or {}).get("prohibited_modes") or [])
    b_requires = set((b or {}).get("requires") or [])
    b_prohibits = set((b or {}).get("prohibited_modes") or [])
    return bool(a_requires & b_prohibits) or bool(b_requires & a_prohibits)


def oracle_classify_conflict(a, b):
    va = a.get("priority_vector") or {}
    vb = b.get("priority_vector") or {}
    dims = sorted(set(va) | set(vb))
    if not dims:
        return "NO_CONFLICT", []
    differences = [d for d in dims
                   if abs(float(va.get(d, 0.0)) - float(vb.get(d, 0.0))) > EPS]
    if not differences:
        if _constraint_pairs_incompatible(a.get("constraints"),
                                          b.get("constraints")):
            return "INCOMPATIBLE", []
        return "NO_CONFLICT", []
    if _constraint_pairs_incompatible(a.get("constraints"),
                                      b.get("constraints")):
        return "INCOMPATIBLE", differences
    opposing = [d for d in differences
                if (float(va.get(d, 0.0)) > DISAGREEMENT_MAGNITUDE
                    and float(vb.get(d, 0.0)) < -DISAGREEMENT_MAGNITUDE)
                or (float(va.get(d, 0.0)) < -DISAGREEMENT_MAGNITUDE
                    and float(vb.get(d, 0.0)) > DISAGREEMENT_MAGNITUDE)]
    if opposing:
        return "UNRESOLVED_CONFLICT", differences
    return "WEIGHTED_DISAGREEMENT", differences


def _required_overrides(state):
    return sorted(set((state.get("constraints") or {}).get("requires") or ())
                  & CORE_OVERRIDE_TOKENS)


def oracle_fused(persona_states, personas, core_epistemic=None,
                 core_safety=None, core_constraints=None):
    """Recompute the stable facets of the fused result for comparison.

    ``persona_states`` is the FULL list of PersonaState dicts for a turn;
    ACTIVE states are selected and sorted deterministically (mirroring the
    implementation, which excludes INACTIVE/AMBIGUOUS explicitly). ``personas``
    maps persona_id -> spec (for weights). Returns a plain dict of the facets
    ``test_persona_fusion.py`` must match exactly.
    """
    active_all = [s for s in persona_states
                  if s["activation_status"] == "ACTIVE"]
    excluded = sorted(s["persona_id"] for s in persona_states
                      if s["activation_status"] != "ACTIVE")
    order = sorted(active_all, key=lambda s: s["persona_id"])
    raw = []
    for s in order:
        weight = personas[s["persona_id"]]["weights"]["base"]
        weight = float(weight)
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError("oracle: invalid weight for %r" % s["persona_id"])
        raw.append(weight)
    normalization = oracle_normalize(raw)
    normalized = normalization["normalized"]
    weights = {s["persona_id"]: {
        "raw_weight": round(raw[i], 6),
        "normalized_weight": normalized[i]}
        for i, s in enumerate(order)}
    consensus = oracle_consensus(order, normalized)

    conflicts = []
    severity = 0
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            classification, dims_diff = oracle_classify_conflict(
                order[i], order[j])
            conflicts.append({
                "between": [order[i]["persona_id"], order[j]["persona_id"]],
                "classification": classification,
                "dimensions": dims_diff,
            })
            severity = max(severity,
                           ORACLE_CONFLICT_STATUSES.index(classification))

    unresolved = []
    for dim in sorted(set().union(*[set(s["priority_vector"])
                                   for s in order])):
        spread = 0.0
        for s, w in zip(order, normalized):
            spread += w * abs(float(s["priority_vector"].get(dim, 0.0))
                              - consensus[dim])
        if spread > UNRESOLVED_SPREAD:
            unresolved.append(dim)

    # epistemic inheritance preservation
    inherited = None
    inheritance_violation = False
    for s in order:
        block = s.get("inherited_epistemic")
        if block is None:
            continue
        if inherited is None:
            inherited = block
        elif inherited != block:
            inheritance_violation = True
            break
    if order and core_epistemic is not None:
        if inherited != core_epistemic:
            inheritance_violation = True
        inherited = core_epistemic
    if order and inheritance_violation:
        severity = max(severity,
                       ORACLE_CONFLICT_STATUSES.index("INCOMPATIBLE"))

    core_holds = None
    core_blocked = None
    if isinstance(core_safety, dict):
        core_holds = bool(core_safety.get("hold")
                          or core_safety.get("safety_hold"))
        core_blocked = bool(core_safety.get("blocked")
                            or core_safety.get("safety_blocked"))
    overrides = []
    for s in order:
        tokens = _required_overrides(s)
        if tokens:
            overrides.append({"persona_id": s["persona_id"],
                              "tokens": tokens})
            severity = max(severity,
                           ORACLE_CONFLICT_STATUSES.index("INCOMPATIBLE"))

    effective = sorted(set(core_constraints or []))
    for s in order:
        for token in (s.get("constraints") or {}).get("requires") or ():
            if token not in effective and token not in CORE_OVERRIDE_TOKENS:
                effective.append(token)
    effective = sorted(set(effective))

    return {
        "status": "FUSED" if order else "NO_ACTIVE_PERSONA",
        "active_personas": [s["persona_id"] for s in order],
        "weights": weights,
        "consensus": consensus,
        "conflict_classifications": [c["classification"] for c in conflicts],
        "conflict_between": [c["between"] for c in conflicts],
        "conflict_dimensions": [c["dimensions"] for c in conflicts],
        "conflict_status": ORACLE_CONFLICT_STATUSES[severity],
        "unresolved_dimensions": unresolved,
        "excluded_inactive": excluded,
        "inherited_epistemic": inherited,
        "inheritance_violation": inheritance_violation,
        "safety_core_holds": core_holds,
        "safety_core_blocked": core_blocked,
        "safety_override_blocked": bool(overrides),
        "overrides_recorded": [o["persona_id"] for o in overrides],
        "constraints_core": sorted(core_constraints or []),
        "constraints_effective": effective,
    }