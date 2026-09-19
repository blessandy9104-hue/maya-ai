"""Market Analyst persona runtime + financial-safety language governor.

Calm, precise, neutral, risk-aware. Interpretation-only. Loads the persona
profile and the financial-safety ruleset from ``maya_identity/market`` and
enforces them deterministically: closed vocabulary, banned directive terms,
forbidden phrases, the ESCALATION ladder E0-E3, and the disclaimer suffix.

The persona is stateless: identical input always produces identical output,
and nothing here reads clocks, randomness or the filesystem for logic.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Dict, List, Optional, Sequence

from ..isolation import (
    PERSONA_CEILINGS,
    SURFACE_WHITELIST,
    PersonaSeal,
)
from ..isolation.router import BOUNDARY_TABLE

PERSONA_ID = "market_analyst"
OUTPUT_CATEGORY = "market_interpretation"
OPERATOR_BOUNDARY = "operator"

_MARKET_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "maya_identity"
    / "market"
)
_PERSONA_FILE = _MARKET_DIR / "market_analyst.persona.json"
_RULES_FILE = _MARKET_DIR / "financial_safety_rules.json"

_TAG_RE = re.compile(r"[A-Za-z][A-Za-z0-9_']*")
_ESC_VERDICTS = {"E0": "rephrase", "E1": "neutralize", "E2": "revoke_ready", "E3": "halt"}

_cached_profile: Optional[Dict[str, Any]] = None
_cached_rules: Optional[Dict[str, Any]] = None


def _load_json(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def profile() -> Dict[str, Any]:
    """Persona profile (maya_identity/market/market_analyst.persona.json)."""
    global _cached_profile
    if _cached_profile is None:
        _cached_profile = _load_json(_PERSONA_FILE)
    return dict(_cached_profile)


def rules() -> Dict[str, Any]:
    """Financial-safety ruleset (maya_identity/market/financial_safety_rules.json)."""
    global _cached_rules
    if _cached_rules is None:
        _cached_rules = _load_json(_RULES_FILE)
    return dict(_cached_rules)


def ceiling() -> Dict[str, float]:
    return dict(PERSONA_CEILINGS[PERSONA_ID])


def _tokens(text: str) -> List[str]:
    return _TAG_RE.findall(text.lower())


def available() -> bool:
    """Allowlist readiness: surface, output category and ceiling all present."""
    return (
        PERSONA_ID in SURFACE_WHITELIST
        and OUTPUT_CATEGORY in BOUNDARY_TABLE.get(OPERATOR_BOUNDARY, ())
        and PERSONA_ID in PERSONA_CEILINGS
    )


def seal(tenant: str) -> PersonaSeal:
    return PersonaSeal(PERSONA_ID, tenant)


def violations(text: str) -> List[Dict[str, str]]:
    """Directive-term and forbidden-phrase scan. Deterministic order."""
    if not isinstance(text, str):
        return [{"class": "input", "term": "", "severity": "high",
                 "note": "violations requires text"}]
    lowered = text.lower()
    found: List[Dict[str, str]] = []
    for term in rules()["directive_terms"]:
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(term) + r"(?![A-Za-z0-9_])", lowered):
            found.append({"class": "directive_term", "term": term,
                          "severity": "medium",
                          "note": "directive term present in market wording."})
    for class_name, phrases in rules()["forbidden_phrases"].items():
        for phrase in phrases:
            if phrase.lower() in lowered:
                found.append({"class": class_name, "term": phrase,
                              "severity": "high",
                              "note": "forbidden phrase detected in market wording."})
    return found


def shape(mpm_obj: Dict[str, Any], register: str = "even") -> Dict[str, Any]:
    """Shape an MPM interpretation into compliant persona wording.

    Closed register set (default ``even``), banned directive terms removed,
    the disclaimer template appended, and any stated confidence capped at the
    safety limit. Pure and deterministic.
    """
    data = rules()
    allowed_registers = set(data["allowed_registers"])
    if register not in allowed_registers:
        raise ValueError(f"register must be one of {sorted(allowed_registers)}")
    personas = profile()
    allowed = set(allowed_registers).difference(personas["tone_profile"]["banned_registers"])
    if register not in allowed:
        raise ValueError(f"register {register!r} is banned for this persona")

    explanation = str(mpm_obj.get("explanation", ""))
    stripped = [
        token for token in _tokens(explanation)
        if token not in set(data["directive_terms"]).union({"must"})
    ]
    cleaned = " ".join(stripped) if stripped else "Market structure interpretation."

    confidence = mpm_obj.get("pattern", {}).get("confidence", 0.0)
    cap = float(data["confidence_cap"])
    stated = round(min(float(confidence), cap), 2)

    text = f"{cleaned} {data['disclaimer_template']}".strip()
    return {
        "persona": PERSONA_ID,
        "register": register,
        "directive_free": not violations(cleaned),
        "stated_confidence": stated,
        "disclaimer": data["disclaimer_template"],
        "text": text,
    }


def escalate(step: Optional[str] = None, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Deterministic governance ladder E0-E3.

    An explicit ``step`` (E0..E3) selects the policy directly; otherwise the
    level is derived deterministically from the violation count in ``ctx``.
    """
    data = rules()
    ladder = data["escalation"]
    ctx = dict(ctx or {})
    if step is None:
        count = ctx.get("violation_count", 0)
        if not isinstance(count, int) or count < 0:
            count = 0
        if count == 0:
            return {"esc_level": None, "verdict": "pass",
                    "policy": ladder["E0"], "detail": "no violations detected."}
        if count <= 2:
            step = "E0"
        elif count <= 5:
            step = "E1"
        elif count <= 10:
            step = "E2"
        else:
            step = "E3"
    if step not in _ESC_VERDICTS:
        raise ValueError(f"unknown escalation step: {step!r}")
    trap = bool(ctx.get("trap_limit_exceeded", False))
    if step == "E2" and trap:
        return {"esc_level": "E2", "verdict": "revoke_ready", "policy": ladder["E2"],
                "detail": "trap-limited rephrase exhausted; scope revoked."}
    return {"esc_level": step, "verdict": _ESC_VERDICTS[step],
            "policy": ladder[step], "detail": f"ladder {step} policy active."}


def _verify_parity_sources() -> None:
    # Structural sanity: the persona's banned directive terms are a subset of
    # the safety ruleset's directive terms, so the linter can never miss one.
    persona_terms = set(profile()["vocabulary"]["banned_directive_terms"])
    rule_terms = set(rules()["directive_terms"])
    assert persona_terms <= rule_terms, persona_terms - rule_terms
    assert all(name in profile()["channel_ceiling"] for name in ("expression", "viseme", "micro"))


_verify_parity_sources()