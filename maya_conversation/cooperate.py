"""Cooperative orchestration layer (Batch 8H).

Bridges the two existing interpretation engines so they can cooperate,
challenge one another, and surface disagreement — rather than silently
coexisting in the LLM prompt.

Core principle: no subsystem is automatically correct. Relevant subsystems
cooperate, challenge one another, and provide evidence for or against a
result.

This module is deterministic: no wall clock, no randomness, no file writes.
It is fail-open: any exception returns a degraded result, never crashes.
"""
from __future__ import annotations

# -- cooperation verdicts -------------------------------------------------

AGREEMENT = "agreement"           # subsystems agree on core assessment
AGREEMENT_WITH_CAVEAT = "agreement_with_caveat"  # agree but one has warnings
DISAGREEMENT = "disagreement"     # subsystems conflict — needs investigation
SINGLE_SOURCE = "single_source"  # only one subsystem produced output
FALLBACK_USED = "fallback_used"  # primary failed; fallback engaged
NO_ENGAGEMENT = "no_engagement"  # no subsystem was relevant


# -- cooperation epistemic status -----------------------------------------
#
# These are ENGINE-LEVEL statuses describing the cooperation itself, distinct
# from claim-level epistemic statuses (REPORTED/HYPOTHESIS/BELIEVED/DISPUTED)
# used inside single interpretations. A downstream consumer uses these to
# decide how much weight to give the combined answer.

EPISTEMIC_SUPPORTED = "supported"       # dual-source agreement
EPISTEMIC_CONTESTED = "contested"       # dual-source conflict
EPISTEMIC_PRELIMINARY = "preliminary"   # single-source only
EPISTEMIC_UNAVAILABLE = "unavailable"   # no engine produced output
EPISTEMIC_FALLBACK = "fallback"         # primary failed, fallback used

_EPISTEMIC_SUPPORTING = {
    AGREEMENT: EPISTEMIC_SUPPORTED,
    AGREEMENT_WITH_CAVEAT: EPISTEMIC_SUPPORTED,
    DISAGREEMENT: EPISTEMIC_CONTESTED,
    SINGLE_SOURCE: EPISTEMIC_PRELIMINARY,
    FALLBACK_USED: EPISTEMIC_FALLBACK,
    NO_ENGAGEMENT: EPISTEMIC_UNAVAILABLE,
}


# -- data containers (plain dicts for serialization) ---------------------

def _epistemic_for(verdict, supporting, disputing):
    """Build the epistemic frame for a cooperation verdict."""
    status = _EPISTEMIC_SUPPORTING.get(verdict, EPISTEMIC_UNAVAILABLE)
    return {
        "status": status,
        "supporting_sources": sorted(supporting),
        "disputing_sources": sorted(disputing),
        "basis": {
            AGREEMENT: "both engines agree on the core assessment",
            AGREEMENT_WITH_CAVEAT: "engines agree but one carries a warning",
            DISAGREEMENT: "engines conflict; the combined answer is contested",
            SINGLE_SOURCE: "only one engine produced output; "
                           "answer is preliminary",
            FALLBACK_USED: "primary failed; fallback evidence used",
            NO_ENGAGEMENT: "no engine produced output; "
                           "no evidence available",
        }.get(verdict, "no reliable evidence"),
    }


def _cooperation_result(verdict, primary=None, secondary=None,
                        disagreements=None, confidence=None,
                        reason="", fallback_chain=None,
                        supporting=None, disputing=None,
                        cooperation_math=None):
    """Build a cooperation result envelope. Always succeeds."""
    supporting = supporting or []
    disputing = disputing or []
    return {
        "verdict": verdict,
        "primary": primary or {},
        "secondary": secondary or {},
        "disagreements": disagreements or [],
        "confidence": confidence if confidence is not None else 1.0,
        "reason": reason,
        "fallback_chain": fallback_chain or [],
        "epistemic": _epistemic_for(verdict, supporting, disputing),
        "cooperation_math": cooperation_math or {},
    }


def _engine_confidence(mapping, key):
    """Caller-reported confidence as a clean [0, 1] float, or None when the
    caller supplied nothing usable (absent, non-numeric, or out of range).
    Never invents a value on the caller's behalf.
    """
    value = (mapping or {}).get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value != value or str(value) == "inf" or str(value) == "-inf":
        return None
    if not (0.0 <= value <= 1.0):
        return None
    return value


def _cooperation_math(conv_result, bridge_features, supporting, disputing):
    """Structural agreement frame for a cooperation verdict.

    Computed through the deterministic mathematical substrate so the
    orchestrator does not hand-roll its confidence algebra: label agreement
    is the substrate's ``label_similarity`` over the epistemic source sets,
    and when both engines supplied usable confidences the substrate also
    reports ``concordance`` and its conservative ``agreement_weighted_combine``
    of the two. When a confidence is missing those numerics are simply absent
    (fail honest, never invented). Additive: it never changes the verdict,
    the contract confidence, or the epistemic status.
    """
    try:
        from maya_math.cooperation import (
            agreement_weighted_combine, concordance, label_similarity)
    except Exception:
        return {"substrate": "unavailable"}
    conv_conf = _engine_confidence(
        (conv_result or {}).get("interpretation") or {}, "classifier_confidence")
    bridge_conf = _engine_confidence(bridge_features or {}, "confidence")
    frame = {
        "support_concordance": label_similarity(supporting, disputing),
        "engine_concordance": None,
        "combined_confidence": None,
    }
    if conv_conf is not None and bridge_conf is not None:
        frame["engine_concordance"] = concordance(conv_conf, bridge_conf)
        frame["combined_confidence"] = agreement_weighted_combine(
            conv_conf, bridge_conf)
    return frame


# -- comparison logic -----------------------------------------------------

def _compare_domain_results(conv_domains, bridge_directive):
    """Compare 8G domain results against the bridge expression directive.

    Returns a list of disagreement descriptions (empty = agreement).

    ``conv_domains``: the domain_results dict from orchestrate_turn
    ``bridge_directive``: the expression directive dict from bridge
    """
    disagreements = []

    conv_psych = (conv_domains or {}).get("psychology") or {}
    conv_phil = (conv_domains or {}).get("philosophy") or {}
    bridge_holds = list((bridge_directive or {}).get("holds") or [])
    bridge_register = (bridge_directive or {}).get("register", "")

    # Check 1: psychology engaged but bridge flags intelligence_unavailable
    if conv_psych.get("engaged") and "intelligence_unavailable" in bridge_holds:
        disagreements.append({
            "dimension": "availability",
            "detail": "8G psychology engaged but bridge reports "
                      "intelligence_unavailable",
            "severity": "high",
        })

    # Check 2: philosophy engaged but bridge restricts register
    if conv_phil.get("engaged") and bridge_register in ("reserved",):
        disagreements.append({
            "dimension": "register_conflict",
            "detail": "8G philosophy engaged but bridge register is "
                      "%s (restricted)" % bridge_register,
            "severity": "medium",
        })

    # Check 3: 8G finds clinical refusal but bridge has no safety hold
    psych_strat = conv_psych.get("strategy") or {}
    if conv_psych.get("clinical_claim_present") and not any(
            "safety" in h.lower() for h in bridge_holds):
        disagreements.append({
            "dimension": "safety_awareness",
            "detail": "8G detects clinical claim with refusal but bridge "
                      "has no safety hold",
            "severity": "low",
        })

    # Check 4: bridge holds include safety_boundary but 8G has no
    # safety-relevant objective
    safety_holds = [h for h in bridge_holds if "safety" in h.lower()]
    if safety_holds and conv_phil.get("engaged"):
        phil_obj = (conv_domains or {}).get("_plan_objective", "")
        if phil_obj not in ("refuse", "challenge"):
            disagreements.append({
                "dimension": "safety_tension",
                "detail": "bridge safety holds (%s) but 8G philosophy "
                          "objective is %s" % (safety_holds, phil_obj),
                "severity": "low",
            })

    return disagreements


def _compare_interpretations(conv_interp, bridge_features):
    """Compare 8G interpretation against bridge feature mapping.

    Returns disagreement descriptions (empty = agreement).
    """
    disagreements = []

    if not conv_interp or not bridge_features:
        return disagreements

    conv_intent = conv_interp.get("primary_intent", "")
    bridge_confidence = bridge_features.get("confidence", 0.0)

    # Check: 8G ambiguous but bridge highly confident (or vice versa)
    if conv_interp.get("ambiguous") and bridge_confidence > 0.8:
        disagreements.append({
            "dimension": "ambiguity_confidence",
            "detail": "8G marks utterance ambiguous (confidence %.2f) but "
                      "bridge confidence is %.2f" % (
                          conv_interp.get("classifier_confidence", 0.0),
                          bridge_confidence),
            "severity": "low",
        })

    return disagreements


# -- the cooperative orchestrator -----------------------------------------

def cooperate(conv_result, bridge_directive=None, bridge_features=None):
    """Compare outputs from the two interpretation engines and produce
    a cooperation verdict.

    ``conv_result``: full output from orchestrate_turn (may be None or
                    have ok=False)
    ``bridge_directive``: the expression directive from bridge
                          (may be None if bridge unavailable)
    ``bridge_features``: the raw feature mapping from bridge
                          (may be None)

    Returns a cooperation result dict. Never raises.
    """
    try:
        return _cooperate_inner(conv_result, bridge_directive, bridge_features)
    except Exception as error:
        return _cooperation_result(
            verdict=FALLBACK_USED,
            reason="cooperate_error: %s: %s" % (type(error).__name__, error),
            confidence=0.0,
        )


def _cooperate_inner(conv_result, bridge_directive, bridge_features):
    conv_ok = bool(conv_result and conv_result.get("ok"))
    bridge_ok = bool(bridge_directive)

    # Case 1: neither produced output
    if not conv_ok and not bridge_ok:
        return _cooperation_result(
            verdict=NO_ENGAGEMENT,
            reason="neither engine produced output",
            confidence=0.0,
            cooperation_math={},
        )

    # Case 2: only one engine produced output
    if conv_ok and not bridge_ok:
        return _cooperation_result(
            verdict=SINGLE_SOURCE,
            primary=conv_result,
            reason="bridge unavailable; 8G sole source",
            confidence=0.7,
            supporting=["conv_8g"],
            cooperation_math=_cooperation_math(
                conv_result, bridge_features, ["conv_8g"], []),
        )
    if not conv_ok and bridge_ok:
        return _cooperation_result(
            verdict=SINGLE_SOURCE,
            primary={"bridge_directive": bridge_directive,
                     "bridge_features": bridge_features},
            reason="8G unavailable (%s); bridge sole source" %
                   (conv_result or {}).get("reason", "unknown"),
            confidence=0.7,
            supporting=["bridge"],
            cooperation_math=_cooperation_math(
                conv_result, bridge_features, ["bridge"], []),
        )

    # Case 3: both produced output — compare
    domain_disagreements = _compare_domain_results(
        conv_result.get("domain_results"), bridge_directive)
    interp_disagreements = _compare_interpretations(
        conv_result.get("interpretation"), bridge_features)

    all_disagreements = domain_disagreements + interp_disagreements
    high_sev = [d for d in all_disagreements if d.get("severity") == "high"]
    med_sev = [d for d in all_disagreements if d.get("severity") == "medium"]

    if high_sev:
        verdict = DISAGREEMENT
        confidence = 0.3
        supporting = []
        disputing = ["bridge", "conv_8g"]
    elif med_sev:
        verdict = AGREEMENT_WITH_CAVEAT
        confidence = 0.6
        supporting = ["bridge", "conv_8g"]
        disputing = ["bridge"]
    elif all_disagreements:
        verdict = AGREEMENT_WITH_CAVEAT
        confidence = 0.8
        supporting = ["bridge", "conv_8g"]
        disputing = ["conv_8g"]
    else:
        verdict = AGREEMENT
        confidence = 0.95
        supporting = ["bridge", "conv_8g"]
        disputing = []

    return _cooperation_result(
        verdict=verdict,
        primary=conv_result,
        secondary={"bridge_directive": bridge_directive,
                   "bridge_features": bridge_features},
        disagreements=all_disagreements,
        confidence=confidence,
        reason="%d disagreement(s) found" % len(all_disagreements)
               if all_disagreements else "engines agree",
        supporting=supporting,
        disputing=disputing,
        cooperation_math=_cooperation_math(
            conv_result, bridge_features, supporting, disputing),
    )
