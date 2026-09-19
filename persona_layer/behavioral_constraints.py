"""Behavioral constraints: global + per-persona, with a deterministic gate.

assert_behavior_ok(signal, persona) returns (ok: bool, reason: str). The signal
dict may carry expression/viseme/micro values, an optional step and direction,
and an optional tone for persona-level checks.
"""

import math

from maya_runtime.core import CHANNEL_MAX

from .persona_rules import PERSONA_RULES, max_step_for

_CH = ("expression", "viseme", "micro")

GLOBAL_CONSTRAINTS = (
    "no_randomness",
    "no_hardware_bias",
    "no_overshoot",
    "no_ceiling_breach",
    "no_goals_created",
    "no_architecture_change",
    "bounded_output",
)

PERSONA_CONSTRAINTS = {
    "calm": ("strict_even", "deescalation_only"),
    "warm": ("fast_rapport", "deescalation_only"),
    "authoritative": ("low_amplitude",),
    "playful": (),
}

BEHAVIORAL_CONSTRAINTS = {
    "no_randomness": {
        "kind": "global",
        "description": "no RNG in persona math",
    },
    "no_hardware_bias": {
        "kind": "global",
        "description": "identical output on every device",
    },
    "no_overshoot": {
        "kind": "global",
        "description": "smoothing never exceeds its target",
    },
    "no_ceiling_breach": {
        "kind": "global",
        "description": "channels never exceed CHANNEL_MAX",
    },
    "no_goals_created": {
        "kind": "global",
        "description": "persona follows goals, never creates them",
    },
    "no_architecture_change": {
        "kind": "global",
        "description": "persona never mutates registries, models, or limits",
    },
    "bounded_output": {
        "kind": "global",
        "description": "all scalar outputs finite and in-domain",
    },
    "low_amplitude": {
        "kind": "persona",
        "description": "emotional steps capped at authoritative bound",
    },
    "deescalation_only": {
        "kind": "persona",
        "description": "load contexts allow only flat or downward motion",
    },
    "fast_rapport": {
        "kind": "persona",
        "description": "upper-half warm band allowed in onboarding contexts",
    },
    "strict_even": {
        "kind": "persona",
        "description": "default tone locked to even",
    },
}

_EXT_PREFIX = "x-"


def constraints_for(persona):
    """Frozen set of effective constraint ids for a persona (global + persona)."""
    if persona not in PERSONA_RULES:
        raise ValueError("unknown persona: %s" % persona)
    return frozenset(set(GLOBAL_CONSTRAINTS) | set(PERSONA_CONSTRAINTS.get(persona, ())))


def known_constraint(constraint_id):
    """True if a constraint id is registered or is a valid extension id."""
    if constraint_id in BEHAVIORAL_CONSTRAINTS:
        return True
    return constraint_id.startswith(_EXT_PREFIX) and len(constraint_id) > 2


def assert_behavior_ok(signal, persona):
    """Deterministic gate over a signal frame for a persona.

    Returns (ok, reason). All checks are pure and ceiling-bound.
    """
    if persona not in PERSONA_RULES:
        return False, "unknown persona"
    for channel_name in _CH:
        value = signal.get(channel_name)
        if value is None:
            continue
        if not (isinstance(value, (int, float)) and math.isfinite(value)):
            return False, "non-finite:%s" % channel_name
        if value < 0.0:
            return False, "negative:%s" % channel_name
        if value > CHANNEL_MAX[channel_name] + 1e-9:
            return False, "ceiling:%s" % channel_name
    step = signal.get("step")
    if step is not None:
        cap = max_step_for(persona)
        if step > cap + 1e-9:
            return False, "step_cap:%s" % persona
    if "deescalation_only" in PERSONA_CONSTRAINTS.get(persona, ()):
        if signal.get("direction") == "up":
            return False, "deescalation_only"
    if "strict_even" in PERSONA_CONSTRAINTS.get(persona, ()):
        tone = signal.get("tone")
        if tone is not None and tone != "even":
            return False, "strict_even"
    return True, "ok"


def validate_constraints():
    """Registry-level invariants over behavioral constraints."""
    for persona, extra in PERSONA_CONSTRAINTS.items():
        for constraint_id in extra:
            if constraint_id not in BEHAVIORAL_CONSTRAINTS:
                raise ValueError(
                    "unknown per-persona constraint: %s -> %s" % (persona, constraint_id)
                )
        if persona not in PERSONA_RULES:
            raise ValueError("constraint references unknown persona: %s" % persona)