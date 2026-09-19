"""Controlled deciphering contract (MAYA Batch #4).

The FIRST controlled interface between raw input and evaluation. It wraps
the deterministic detector and answers, without inventing semantics:

    {"status", "detected_type", "canonical_candidate", "evidence",
     "provenance", "losses", "validation", "epistemic"}

Guarantees:

- KNOWN/AMBIGUOUS/UNKNOWN/INVALID are never coerced (no UNKNOWN->0,
  AMBIGUOUS->first match, INVALID->fallback meaning).
- A canonical candidate is produced ONLY for KNOWN inputs.
- Losses are explicit in both directions: committing a parsed numeric value
  records precision loss when decimal text exceeds binary-float exactness,
  and refusing to commit records that no loss-free interpretation existed.
- Representation validity never implies factual truth: the epistemic frame
  travels beside the record and is kept on its own axis.

Only safe, well-defined decoders are exposed (typed canonical objects,
structured numeric records, geometry contracts, supported equation
structures, declared language metadata, typed relations/events, unified
canonical envelopes). No arbitrary cipher breaking is implemented or claimed.
"""
from __future__ import annotations

import copy

from . import detector
from . import epistemic
from . import representation
from .detector import numeric_token, parse_measurement_text

DECIPHER_KEYS = ("status", "detected_type", "canonical_candidate",
                 "evidence", "provenance", "losses", "validation",
                 "epistemic")


def losses_for(candidate, detection):
    """Deterministic loss accounting for an already-known detection."""
    losses = []
    status = detection.get("status")
    if status == "KNOWN":
        kind = detection.get("detected_type")
        raw = candidate
        if kind == "measurement" and isinstance(raw, str):
            parsed = parse_measurement_text(raw)
            if parsed is None:
                losses.append("measurement value not parseable as a number")
            else:
                _value, is_float, _unit = parsed
                if is_float:
                    digits = sum(1 for ch in raw if ch.isdigit())
                    if digits > 16:
                        losses.append(
                            "binary-float precision after decimal parsing "
                            "(%d significant digits)" % digits)
        if kind in ("temporal", "language"):
            losses.append("detector-only type canonicalized onto a shared "
                          "representation type")
        return losses
    if status == "AMBIGUOUS":
        return ["none — no commitment made; loss would require guessing"]
    if status == "UNKNOWN":
        return ["no supported contract; no canonical loss-free form exists"]
    return ["invalid input admits no canonical form"]


def _default_provenance():
    return None


def decipher(candidate, declared=None, *, provenance=None,
             epistemic_status=None, empirical_status=None, domain=None):
    """Decipher one input into the controlled detection contract.

    ``provenance`` is caller-supplied (this layer is deterministic and owns
    no clock); when provided it is validated against the shared provenance
    contract. ``epistemic_status``/``empirical_status``/``domain`` are
    declared evidence, never inferred from structure.
    """
    detection = detector.detect(candidate, declared=declared)

    if provenance is not None:
        try:
            provenance = representation.validate_provenance(provenance)
        except representation.RepresentationError as exc:
            return {
                "status": "INVALID",
                "detected_type": None,
                "canonical_candidate": None,
                "evidence": detection["evidence"],
                "provenance": None,
                "losses": ["provenance rejected: %s" % (exc,)],
                "validation": {
                    "representation_valid": False,
                    "reason": "provenance failed validation",
                    "canonical_maps_to": None,
                    "oracle_eligible": False,
                },
                "epistemic": None,
            }

    losses = losses_for(candidate, detection)

    detected_type = detection.get("detected_type")
    canonical = detection.get("canonical_candidate")
    if canonical is not None:
        canonical = copy.deepcopy(canonical)
    canonical_target = None
    if detected_type:
        try:
            canonical_target = detector.canonical_type(detected_type)
        except representation.RepresentationError:
            canonical_target = None

    domain_from_evidence = detection["evidence"].get("domain")
    effective_domain = domain if domain is not None else domain_from_evidence
    if effective_domain is not None:
        try:
            epistemic.validate_domain(effective_domain)
        except epistemic.EpistemicError:
            effective_domain = None

    status = detection.get("status")
    valid = status == "KNOWN"

    if epistemic_status is None:
        if effective_domain in epistemic.CULTURAL_DOMAINS:
            epistemic_status = "TRADITIONAL"
            empirical_status = empirical_status or "UNVERIFIED"
        else:
            epistemic_status = "UNKNOWN"
    empirical = empirical_status or "UNKNOWN"

    try:
        epi = epistemic.frame(
            representation_valid=valid,
            epistemic_status=epistemic_status,
            empirical_status=empirical,
            domain=effective_domain,
        )
    except epistemic.EpistemicError:
        epi = None

    return {
        "status": detection.get("status"),
        "detected_type": detected_type,
        "canonical_candidate": canonical,
        "evidence": detection.get("evidence"),
        "provenance": copy.deepcopy(provenance)
        if provenance is not None else None,
        "losses": losses,
        "validation": {
            "representation_valid": valid,
            "detected_type": detected_type,
            "reason": (detection["evidence"].get("validation_reason")
                       or detection["evidence"].get("ambiguity_reason")
                       or None),
            "canonical_maps_to": canonical_target,
            "oracle_eligible": (valid and detected_type not in
                                ("temporal", "language",
                                 "structured_canonical_object")),
        },
        "epistemic": epi,
    }


def contract_keys():
    return list(DECIPHER_KEYS)


__all__ = ("DECIPHER_KEYS", "decipher", "losses_for", "contract_keys")