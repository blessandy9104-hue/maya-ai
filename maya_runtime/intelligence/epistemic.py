"""First-class epistemic-status contract (MAYA Batch #4).

Separates two axes that must never be conflated:

- *Representation validity*: does this object conform to a representation
  contract? (Deterministic, structural, decided by the detector.)
- *Epistemic status*: what kind of knowledge-claim is this object, and how
  much can it be relied upon as fact? (Declared or derived, never implied by
  structural validity alone.)

A perfectly well-formed record never implies factual truth:

    representation = VALID         (contract conformance)
    epistemic_status = TRADITIONAL / INTERPRETIVE ...
    empirical_status = UNVERIFIED  (no external validation performed)

Conversely a MEASURED scientific record may be representationally valid AND
empirically tested, which is still a *claim*, not proof by itself: factual
confidence is never manufactured from representation confidence.

Domain vocabulary (Part 15): specialized knowledge systems are recognized as
*distinct information domains* without asserting the truth of their claims.
Cultural/spiritual content is never automatically "fact": the frame records
traditional/interpretive status and claims nothing factual by default.

Determinism: pure module, no randomness, no wall-clock, none of the
intelligence package's forbidden imports.
"""
from __future__ import annotations

# Part 15 statuses (cultural/empirical vocabulary).
# Part 16 statuses (first-class epistemic vocabulary).
EPISTEMIC_STATUSES = frozenset({
    "OBSERVED", "MEASURED", "CALCULATED", "INFERRED", "REPORTED",
    "DOCUMENTED", "BELIEVED", "BELIEF", "TRADITIONAL", "INTERPRETIVE",
    "INTERPRETATION", "HYPOTHETICAL", "HYPOTHESIS", "SUPPORTED",
    "EMPIRICALLY_TESTED", "DISPUTED", "CONTRADICTED", "UNVERIFIED",
    "UNKNOWN",
})

EPISTEMIC_STATUSES_ORDERED = (
    "OBSERVED", "MEASURED", "CALCULATED", "INFERRED", "REPORTED",
    "DOCUMENTED", "BELIEVED", "BELIEF", "TRADITIONAL", "INTERPRETIVE",
    "INTERPRETATION", "HYPOTHETICAL", "HYPOTHESIS", "SUPPORTED",
    "EMPIRICALLY_TESTED", "DISPUTED", "CONTRADICTED", "UNVERIFIED",
    "UNKNOWN",
)

EMPIRICAL_STATUSES = frozenset({
    "EXTERNALLY_VALIDATED", "INTERNALLY_CONSISTENT", "EMPIRICALLY_TESTED",
    "UNVERIFIED", "DISPUTED", "CONTRADICTED", "UNKNOWN",
})

EMPIRICAL_STATUSES_ORDERED = (
    "EXTERNALLY_VALIDATED", "INTERNALLY_CONSISTENT", "EMPIRICALLY_TESTED",
    "UNVERIFIED", "DISPUTED", "CONTRADICTED", "UNKNOWN",
)

# Information-representation languages (Part 14) plus future domains that
# must eventually plug into the same detection contract.
DOMAIN_VOCABULARY = frozenset({
    "NATURAL_LANGUAGE", "NUMERICAL", "VECTOR", "MATRIX", "EQUATION",
    "SYMBOLIC", "CATEGORICAL", "TEMPORAL", "GEOMETRIC", "GRAPH_RELATIONAL",
    "PROBABILISTIC", "STRUCTURED_DATA",
    "ASTROLOGY", "RELIGIOUS_TRADITION", "PHILOSOPHICAL_SCHOOL", "MYTHOLOGY",
    "CULTURAL_SYMBOLIC",
    "IMAGE", "AUDIO", "VIDEO", "SENSOR_STREAM", "SCIENTIFIC_MODEL",
    "LEGAL_SYSTEM", "PROGRAMMING_LANGUAGE",
})

# Subset of domains whose content is NEVER auto-declared factual.
CULTURAL_DOMAINS = frozenset({
    "ASTROLOGY", "RELIGIOUS_TRADITION", "PHILOSOPHICAL_SCHOOL", "MYTHOLOGY",
    "CULTURAL_SYMBOLIC",
})

# Epistemic status -> bus declaration axis (never asserts FACT on its own).
DECLARATION_FOR_EPISTEMIC = {
    "OBSERVED": "OBSERVATION",
    "MEASURED": "OBSERVATION",
    "CALCULATED": "CALCULATION",
    "INFERRED": "INFERENCE",
    "REPORTED": "EXTERNAL_REPORT",
    "DOCUMENTED": "EXTERNAL_REPORT",
    "BELIEVED": "USER_PROVIDED",
    "BELIEF": "USER_PROVIDED",
    "TRADITIONAL": "EXTERNAL_REPORT",
    "INTERPRETIVE": "INTERPRETATION",
    "INTERPRETATION": "INTERPRETATION",
    "HYPOTHETICAL": "HYPOTHESIS",
    "HYPOTHESIS": "HYPOTHESIS",
    "SUPPORTED": "INFERENCE",
    "EMPIRICALLY_TESTED": "OBSERVATION",
    "DISPUTED": "UNKNOWN",
    "CONTRADICTED": "UNKNOWN",
    "UNVERIFIED": "UNKNOWN",
    "UNKNOWN": "UNKNOWN",
}

# Epistemic status -> bus validation axis (representation validity never
# implies a "validated" factual claim for non-empirical statuses).
VALIDATION_FOR_EPISTEMIC = {
    "OBSERVED": "validated",
    "MEASURED": "validated",
    "CALCULATED": "validated",
    "INFERRED": "unvalidated",
    "REPORTED": "unvalidated",
    "DOCUMENTED": "unvalidated",
    "BELIEVED": "unknown",
    "BELIEF": "unknown",
    "TRADITIONAL": "unknown",
    "INTERPRETIVE": "unknown",
    "INTERPRETATION": "unknown",
    "HYPOTHETICAL": "unknown",
    "HYPOTHESIS": "unknown",
    "SUPPORTED": "unvalidated",
    "EMPIRICALLY_TESTED": "validated",
    "DISPUTED": "disputed",
    "CONTRADICTED": "contradicted",
    "UNVERIFIED": "unknown",
    "UNKNOWN": "unknown",
}

# Epistemic statuses that explicitly claim nothing about factual truth.
NON_FACTUAL_STATUSES = frozenset({
    "BELIEVED", "BELIEF", "TRADITIONAL", "INTERPRETIVE", "INTERPRETATION",
    "HYPOTHETICAL", "HYPOTHESIS", "DISPUTED", "CONTRADICTED", "UNVERIFIED",
    "UNKNOWN",
})

# Epistemic statuses that assert an empirical/factual character (still only
# a claim until externally validated).
FACTUAL_CLAIMING_STATUSES = frozenset({
    "OBSERVED", "MEASURED", "CALCULATED", "INFERRED", "REPORTED",
    "DOCUMENTED", "SUPPORTED", "EMPIRICALLY_TESTED",
})


class EpistemicError(ValueError):
    """Raised when an epistemic-status contract member is violated."""


def _reject(why):
    raise EpistemicError(why)


def validate_epistemic_status(status):
    if status not in EPISTEMIC_STATUSES:
        _reject("epistemic status %r is not in the contract vocabulary "
                "(declared, never derived from structure)" % (status,))
    return status


def validate_empirical_status(status):
    if status not in EMPIRICAL_STATUSES:
        _reject("empirical status %r is not in the contract vocabulary"
                % (status,))
    return status


def validate_domain(domain):
    if domain not in DOMAIN_VOCABULARY:
        _reject("domain %r is not in the domain vocabulary; future domains "
                "must be registered explicitly" % (domain,))
    return domain


def is_cultural(domain):
    return domain in CULTURAL_DOMAINS


def declaration_hint(epistemic_status):
    """Bus declaration axis for a status (never FACT on its own)."""
    validate_epistemic_status(epistemic_status)
    return DECLARATION_FOR_EPISTEMIC[epistemic_status]


def validation_hint(epistemic_status):
    """Bus validation axis for a status (valid representation != validated
    fact)."""
    validate_epistemic_status(epistemic_status)
    return VALIDATION_FOR_EPISTEMIC[epistemic_status]


def claims_nothing_factual(epistemic_status):
    validate_epistemic_status(epistemic_status)
    return epistemic_status in NON_FACTUAL_STATUSES


def frame(representation_valid, epistemic_status="UNKNOWN",
          empirical_status="UNKNOWN", domain=None,
          claims_nothing_factual_override=None):
    """Compose the deterministic epistemic frame.

    One axis is structural validity (passed by the detector/decipher layer);
    the epistemic and empirical axes are declared, never inferred from
    structure. ``claims_nothing_factual_override`` may only make a claim
    *more* conservative; factual truth is never asserted from structure.
    """
    validate_epistemic_status(epistemic_status)
    validate_empirical_status(empirical_status)
    effective = claims_nothing_factual_override
    if effective is None:
        effective = bool(claims_nothing_factual(epistemic_status))
    if domain is not None:
        validate_domain(domain)
        if is_cultural(domain) and not effective:
            _reject("a cultural domain never claims factual truth by default; "
                    "representation validity must not imply fact")
    return {
        "representation_valid": bool(representation_valid),
        "epistemic_status": epistemic_status,
        "empirical_status": empirical_status,
        "domain": domain,
        "claims_nothing_factual": bool(effective),
        "declaration_hint": declaration_hint(epistemic_status),
        "validation_hint": validation_hint(epistemic_status),
    }


__all__ = (
    "EpistemicError", "EPISTEMIC_STATUSES", "EPISTEMIC_STATUSES_ORDERED",
    "EMPIRICAL_STATUSES", "EMPIRICAL_STATUSES_ORDERED", "DOMAIN_VOCABULARY",
    "CULTURAL_DOMAINS", "DECLARATION_FOR_EPISTEMIC",
    "VALIDATION_FOR_EPISTEMIC", "NON_FACTUAL_STATUSES",
    "FACTUAL_CLAIMING_STATUSES",
    "validate_epistemic_status", "validate_empirical_status",
    "validate_domain", "is_cultural", "declaration_hint",
    "validation_hint", "claims_nothing_factual", "frame",
)