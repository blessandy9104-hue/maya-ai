"""Domain layer: role-bound behaviours for five industries.

The domain layer is behaviour, not new semantics: every domain describes a
deterministic combination of canonical bounded channel targets (expression /
viseme / micro) and the capability slugs it requires. Applying a domain
blends its target profile toward a bounded input signal through a clamped
``lerp``, so the produced control-target vector is always in [0, 1] and is a
pure function of its inputs. No domain introduces a new channel, a heuristic,
or a random draw.

Domains
-------
tutoring            educational pacing and encouragement profile
customer_service    measured, reliable service-response profile
therapy_support     mirroring-leaning, safety-first profile
robotics_interface  actuation-oriented, fail-closed profile
entertainment       expressive, performance-styled profile

Each role with the ``domain_specific_behaviors`` capability maps to exactly
one domain (see ``ROLE_DOMAIN``); roles without that capability are
domain-agnostic (``domain_for_role`` returns None). Integrity is checked at
import time against the capability registry.
"""
from __future__ import annotations

from .capability_registry import (
    CAPABILITY_REGISTRY, MARKET_ROLE_REGISTRY,
    capabilities_for_role,
)
from .wireframe.rig_math import clamp01, lerp, math_isclose
from .wireframe.math_coordinator import (
    CH_EXPRESSION, CH_VISEME, CH_MICRO,
)

__all__ = [
    "DOMAIN_BEHAVIORS",
    "ROLE_DOMAIN",
    "DOMAIN_SLUGS",
    "behavior_for_domain",
    "apply_domain",
    "domain_for_role",
    "domains_for_role",
    "domain_overview",
]

TUTORING = "tutoring"
CUSTOMER_SERVICE = "customer_service"
THERAPY_SUPPORT = "therapy_support"
ROBOTICS_INTERFACE = "robotics_interface"
ENTERTAINMENT = "entertainment"
DOMAIN_SLUGS = (TUTORING, CUSTOMER_SERVICE, THERAPY_SUPPORT,
                ROBOTICS_INTERFACE, ENTERTAINMENT)

# Canonical bounded channel targets each domain leans toward. These live on
# the semantic channel vocabulary (expression / viseme / micro) so a behaviour
# can never smuggle a new meaning into the rig.
DOMAIN_BEHAVIORS = {
    TUTORING: {
        "summary": "Educational pacing: expressive encouragement with a "
                   "measured speaking profile.",
        "channel_targets": {CH_EXPRESSION: 0.45, CH_VISEME: 0.55,
                            CH_MICRO: 0.04},
        "capabilities": ("expressive_math_face", "pattern_intelligence",
                         "world_stability", "cognitive_reasoning",
                         "contextual_memory", "adaptive_interaction"),
        "constraints": ("bounded [0, 1] channel targets",
                        "no-overshoot pacing"),
    },
    CUSTOMER_SERVICE: {
        "summary": "Reliable service interaction: steady expression and a "
                   "calm viseme profile for reading support.",
        "channel_targets": {CH_EXPRESSION: 0.35, CH_VISEME: 0.45,
                            CH_MICRO: 0.02},
        "capabilities": ("expressive_math_face", "emotional_blending",
                         "pattern_intelligence", "safety_monitoring",
                         "cognitive_reasoning", "contextual_memory",
                         "adaptive_interaction"),
        "constraints": ("bounded [0, 1] response targets", "no randomness"),
    },
    THERAPY_SUPPORT: {
        "summary": "Safety-first mirroring profile: minimal expression drive, "
                   "highest ceiling discipline on every channel.",
        "channel_targets": {CH_EXPRESSION: 0.25, CH_VISEME: 0.35,
                            CH_MICRO: 0.02},
        "capabilities": ("expressive_math_face", "emotional_blending",
                         "world_stability", "pattern_intelligence",
                         "safety_monitoring", "cognitive_reasoning",
                         "contextual_memory", "adaptive_interaction"),
        "constraints": ("mirroring converges without overshoot",
                        "safety thresholds never relaxed"),
    },
    ROBOTICS_INTERFACE: {
        "summary": "Actuation-facing profile: minimal expression, strongest "
                   "world/safety weighting, fail-closed by construction.",
        "channel_targets": {CH_EXPRESSION: 0.15, CH_VISEME: 0.30,
                            CH_MICRO: 0.01},
        "capabilities": ("world_stability", "pattern_intelligence",
                         "multi_agent_coordination", "safety_monitoring",
                         "cognitive_reasoning", "contextual_memory"),
        "constraints": ("fail-closed on non-finite sensors",
                        "bounded transitions only"),
    },
    ENTERTAINMENT: {
        "summary": "Performance profile: full expressive range with the "
                   "canonical blend proportions kept intact.",
        "channel_targets": {CH_EXPRESSION: 0.62, CH_VISEME: 0.50,
                            CH_MICRO: 0.08},
        "capabilities": ("expressive_math_face", "emotional_blending",
                         "adaptive_interaction", "thinkpad_performance"),
        "constraints": ("bounded [0, 1] channel targets", "CPU-light"),
    },
}

# Every role that carries domain_specific_behaviors maps to exactly one
# domain. Roles without that capability are domain-agnostic -> None.
ROLE_DOMAIN = {
    "educational_tutor": TUTORING,
    "customer_service_agent": CUSTOMER_SERVICE,
    "therapy_support_agent": THERAPY_SUPPORT,
    "robotics_interface": ROBOTICS_INTERFACE,
    "ai_companion": ENTERTAINMENT,
    "vtuber_avatar": ENTERTAINMENT,
}


def behavior_for_domain(domain):
    """The declared behaviour profile for a domain slug (raises KeyError for
    unknown domains — a domain is never guessed)."""
    if domain not in DOMAIN_BEHAVIORS:
        raise KeyError(f"domain {domain!r} is not registered")
    return {k: tuple(v) if isinstance(v, (tuple, list)) else v
            for k, v in DOMAIN_BEHAVIORS[domain].items()}


def apply_domain(domain, signal, modulation=0.5):
    """Blend a domain behaviour profile toward a bounded input signal.

    For every canonical channel in the profile:

        target[ch] = clamp01(lerp(profile[ch], clamp01(signal),
                                  clamp01(modulation)))

    ``modulation == 0.0`` yields the pure domain profile; ``modulation ==
    1.0`` makes the response fully input-driven; any value in between is a
    clamped linear blend, so every produced target stays in [0, 1] and the
    mapping is a pure function of its inputs. Deterministic, CPU-light."""
    profile = behavior_for_domain(domain)
    signal_v = clamp01(float(signal))
    mod_v = clamp01(float(modulation))
    targets = {ch: clamp01(lerp(profile["channel_targets"][ch],
                                signal_v, mod_v))
               for ch in profile["channel_targets"]}
    return {
        "domain": domain,
        "targets": targets,
        "modulation": mod_v,
        "bounded": all(0.0 <= v <= 1.0 for v in targets.values()),
    }


def domain_for_role(role):
    """The domain slug bound to a market role, or None for domain-agnostic
    roles (roles without the ``domain_specific_behaviors`` capability)."""
    if role not in MARKET_ROLE_REGISTRY:
        raise KeyError(f"role {role!r} is not registered")
    caps = capabilities_for_role(role)
    if "domain_specific_behaviors" not in caps:
        return None
    domain = ROLE_DOMAIN.get(role)
    if domain is None:
        raise AssertionError(
            f"role {role!r} carries domain_specific_behaviors but has no "
            f"domain mapping")
    return domain


def domains_for_role(role):
    """Tuple form of :func:`domain_for_role`: always deterministic and
    non-empty for domain-bearing roles."""
    domain = domain_for_role(role)
    return (domain,) if domain is not None else ()


def domain_overview():
    """Deterministic domain-by-capability coverage matrix:
    ``{domain: (capabilities, ...)}`` sorted by domain slug."""
    return {
        slug: tuple(behavior_for_domain(slug)["capabilities"])
        for slug in sorted(DOMAIN_BEHAVIORS)
    }


def _self_check():
    """Import-time integrity: every domain references only registered
    capabilities, every role's domain mapping names a registered domain, and
    every role that carries domain_specific_behaviors has a mapping."""
    for slug in DOMAIN_BEHAVIORS:
        for cap in behavior_for_domain(slug)["capabilities"]:
            if cap not in CAPABILITY_REGISTRY:
                raise AssertionError(
                    f"domain {slug!r} references unregistered "
                    f"capability {cap!r}")
    for role, domain in ROLE_DOMAIN.items():
        if domain not in DOMAIN_BEHAVIORS:
            raise AssertionError(
                f"role {role!r} maps unknown domain {domain!r}")
    for role in MARKET_ROLE_REGISTRY:
        if "domain_specific_behaviors" in capabilities_for_role(role):
            domain_for_role(role)


_self_check()