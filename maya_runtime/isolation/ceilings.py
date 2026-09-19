"""Isolation ceilings: the single authoritative lock of CHANNEL_MAX and the
per-web-persona ceilings, plus per-tenant quotas.

Everything here is a plain immutable constant or a pure function. There is no
random, no wall-clock, no GPU and no IO. Every runtime surface pulls its
ceilings from this module, so no surface can invent its own cap.
"""
from __future__ import annotations

CHANNEL_KEYS = ("expression", "viseme", "micro", "anatomical")
CHANNEL_MAX = {
    "expression": 0.5,
    "viseme": 0.35,
    "micro": 0.012,
    "anatomical": 0.8,
}

PERSONA_CEILINGS = {
    "receptionist": {"expression": 0.38, "viseme": 0.24, "micro": 0.008},
    "tutor": {"expression": 0.40, "viseme": 0.26, "micro": 0.009},
    "concierge": {"expression": 0.35, "viseme": 0.20, "micro": 0.006},
    "sales_agent": {"expression": 0.42, "viseme": 0.28, "micro": 0.010},
    "market_analyst": {"expression": 0.25, "viseme": 0.12, "micro": 0.002},
}

WEB_PERSONA_ALLOWLIST = ("receptionist", "tutor", "concierge", "sales_agent", "market_analyst")

TENANT_QUOTAS = {
    "cpu_budget_pct": 12,
    "max_active_embeds_per_tenant": 4,
    "quota_calls_per_day": 5000,
    "token_ttl_seconds": 900,
}

EMBED_MESSAGE_SIZE_LIMIT_BYTES = 16 * 1024

MUS_BOUNDARY_ORDER = ("safety", "isolation", "legal", "business", "operator", "founder")

OPERATOR_BOUNDARY = "nonlegal_nonfinancial"
FOUNDER_BOUNDARY = "legal_business_go_no_go"

DENY = "deny"
ALLOW = "allow"
ESCALATE = "escalate_founder"


def within_channel(ceiling, current):
    for ch, cap in ceiling.items():
        value = current.get(ch, 0.0)
        if not isinstance(value, (int, float)) or not (0.0 <= value <= cap):
            return False
    return True


def persona_allows(persona_id, current):
    if persona_id not in PERSONA_CEILINGS:
        return False
    return within_channel(PERSONA_CEILINGS[persona_id], current)


def ceiling_report(current):
    return [ch for ch in CHANNEL_KEYS if current.get(ch, 0.0) > CHANNEL_MAX[ch]]