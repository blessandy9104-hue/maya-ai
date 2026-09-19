"""Emotional ranges per persona, always inside canonical channel ceilings.

Bands define the achievable amplitude per channel per persona. clamp/validation
are deterministic; band_for()/in_band()/clamp_to_range() never leave the ceiling.
"""

from maya_runtime.core import CHANNEL_MAX

_CH = ("expression", "viseme", "micro")

EMOTIONAL_RANGES = {
    "calm": {
        "expression": (0.15, 0.40),
        "viseme": (0.05, 0.22),
        "micro": (0.000, 0.006),
    },
    "warm": {
        "expression": (0.20, 0.50),
        "viseme": (0.08, 0.28),
        "micro": (0.002, 0.009),
    },
    "authoritative": {
        "expression": (0.15, 0.45),
        "viseme": (0.05, 0.25),
        "micro": (0.001, 0.007),
    },
    "playful": {
        "expression": (0.20, 0.50),
        "viseme": (0.10, 0.35),
        "micro": (0.003, 0.012),
    },
}


def band_for(persona, channel_name):
    """Return the (lo, hi) emotional band for a persona/channel."""
    if persona not in EMOTIONAL_RANGES:
        raise ValueError("unknown persona: %s" % persona)
    if channel_name not in _CH:
        raise ValueError("unknown channel: %s" % channel_name)
    return EMOTIONAL_RANGES[persona][channel_name]


def clamp_to_range(value, persona, channel_name):
    """Clamp a channel value into the persona band and the canonical ceiling."""
    lo, hi = band_for(persona, channel_name)
    ceiling = CHANNEL_MAX[channel_name]
    upper = min(hi, ceiling)
    clamped = max(lo, min(float(value), upper))
    return round(clamped, 6)


def in_band(persona, channel_name, value, epsilon=1e-9):
    """True if a value lies inside the persona band (within epsilon)."""
    lo, hi = band_for(persona, channel_name)
    return lo - epsilon <= value <= hi + epsilon


def validate_emotional_ranges():
    """Registry-level invariants: bands ordered and inside ceilings."""
    for persona in EMOTIONAL_RANGES:
        for channel_name in _CH:
            lo, hi = EMOTIONAL_RANGES[persona][channel_name]
            if not (0.0 <= lo <= hi <= CHANNEL_MAX[channel_name] + 1e-9):
                raise ValueError(
                    "emotional range out of bounds: %s.%s" % (persona, channel_name)
                )