"""Versioned deployment profiles for local execution and universal web
embedding. Each profile carries the personas, math precision, safety
policy override, world-model limits, confidence floor, and allowed
channels for one environment.
"""
from __future__ import annotations

from ..core import CHANNEL_MAX, PRECISION_STANDARD, PRECISION_EXPERT
from ..isolation.ceilings import WEB_PERSONA_ALLOWLIST

_ENVIRONMENTS = ("local", "embed", "cloud_runtime", "api", "kiosk")

_CANONICAL_SAFETY = {
    "max_cpu_percent": 60.0,
    "max_memory_percent": 70.0,
    "max_process_count": 2,
    "max_launches_per_minute": 1,
}

DEPLOYMENT_PROFILES = {
    "local": {
        "environment": "local",
        "version": "1.0.0",
        "personas": list(WEB_PERSONA_ALLOWLIST),
        "precision": "standard",
        "safety": dict(_CANONICAL_SAFETY),
        "world": {"max_std": 0.05, "drift_tolerance": 0.35,
                  "coherence_floor": 0.6},
        "confidence_floor": 0.6,
        "channels": ["expression", "viseme", "micro"],
    },
    "cloud_runtime": {
        "environment": "cloud_runtime",
        "version": "1.0.0",
        "personas": list(WEB_PERSONA_ALLOWLIST),
        "precision": "expert",
        "safety": dict(_CANONICAL_SAFETY),
        "world": {"max_std": 0.04, "drift_tolerance": 0.30,
                  "coherence_floor": 0.65},
        "confidence_floor": 0.65,
        "channels": ["expression", "viseme"],
    },
    "embed": {
        "environment": "embed",
        "version": "1.0.0",
        "personas": ["receptionist", "concierge", "sales_agent", "tutor"],
        "precision": "standard",
        "safety": {"max_cpu_percent": 40.0, "max_memory_percent": 50.0,
                   "max_process_count": 1, "max_launches_per_minute": 1},
        "world": {"max_std": 0.035, "drift_tolerance": 0.30,
                  "coherence_floor": 0.7},
        "confidence_floor": 0.7,
        "channels": ["expression", "viseme"],
    },
    "api": {
        "environment": "api",
        "version": "1.0.0",
        "personas": ["market_analyst", "concierge"],
        "precision": "expert",
        "safety": dict(_CANONICAL_SAFETY),
        "world": {"max_std": 0.035, "drift_tolerance": 0.25,
                  "coherence_floor": 0.7},
        "confidence_floor": 0.75,
        "channels": ["expression"],
    },
    "kiosk": {
        "environment": "kiosk",
        "version": "1.0.0",
        "personas": ["receptionist"],
        "precision": "standard",
        "safety": {"max_cpu_percent": 35.0, "max_memory_percent": 45.0,
                   "max_process_count": 1, "max_launches_per_minute": 1},
        "world": {"max_std": 0.03, "drift_tolerance": 0.25,
                  "coherence_floor": 0.7},
        "confidence_floor": 0.75,
        "channels": ["expression"],
    },
}


class DeploymentProfiles:
    """Read-only profile registry; profiles are immutable at runtime."""

    profiles = DEPLOYMENT_PROFILES

    def select(self, environment):
        if environment not in DEPLOYMENT_PROFILES:
            raise ValueError("unknown deployment environment %r" % environment)
        profile = DEPLOYMENT_PROFILES[environment]
        self._validate(profile)
        return dict(profile)

    def environments(self):
        return list(_ENVIRONMENTS)

    def _validate(self, profile):
        channels = profile["channels"]
        for ch in channels:
            if ch not in CHANNEL_MAX:
                raise ValueError("unknown channel %r in profile" % ch)
        for persona in profile["personas"]:
            if persona not in WEB_PERSONA_ALLOWLIST:
                raise ValueError("unknown persona %r in profile" % persona)

    def verify_channel_limits(self, fused_channels, environment):
        profile = DEPLOYMENT_PROFILES[environment]
        allowed = set(profile["channels"])
        violations = []
        for ch, value in (fused_channels or {}).items():
            if ch not in allowed:
                violations.append({"rule": "channel_not_allowed", "channel": ch})
                continue
            if value < 0.0 or value > float(CHANNEL_MAX[ch]):
                violations.append({"rule": "channel_beyond_ceiling",
                                   "channel": ch, "value": value})
        return {"ok": not violations, "violations": violations}


DEPLOYMENT = DeploymentProfiles()


def select(*args, **kwargs):
    return DEPLOYMENT.select(*args, **kwargs)