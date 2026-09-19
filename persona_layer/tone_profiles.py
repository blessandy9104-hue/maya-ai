"""Tone profiles: bounded channel bands + pace per tone id.

Each tone declares expression/viseme/micro bands and a pace. Bands are
constructed within the canonical CHANNEL_MAX ceilings; tone_targets() returns a
deterministic midpoint target per channel.
"""

from maya_runtime.core import CHANNEL_MAX

_CH = ("expression", "viseme", "micro")

TONE_RULES = {
    "even": {
        "expression": (0.20, 0.35),
        "viseme": (0.10, 0.20),
        "micro": (0.000, 0.004),
        "pace": 0.60,
    },
    "warm": {
        "expression": (0.30, 0.50),
        "viseme": (0.15, 0.28),
        "micro": (0.002, 0.008),
        "pace": 0.65,
    },
    "lively": {
        "expression": (0.35, 0.50),
        "viseme": (0.20, 0.35),
        "micro": (0.004, 0.011),
        "pace": 0.75,
    },
    "authoritative": {
        "expression": (0.25, 0.40),
        "viseme": (0.12, 0.22),
        "micro": (0.002, 0.006),
        "pace": 0.50,
    },
    "soothing": {
        "expression": (0.18, 0.30),
        "viseme": (0.08, 0.18),
        "micro": (0.000, 0.004),
        "pace": 0.55,
    },
    "technical": {
        "expression": (0.20, 0.32),
        "viseme": (0.10, 0.20),
        "micro": (0.000, 0.003),
        "pace": 0.58,
    },
}


def tone_ids():
    """Sorted tuple of registered tone ids."""
    return tuple(sorted(TONE_RULES))


def tone_targets(tone):
    """Deterministic midpoint targets for a tone; unknown ids raise ValueError.

    Returns {'expression': float, 'viseme': float, 'micro': float, 'pace': float}.
    """
    if tone not in TONE_RULES:
        raise ValueError("unknown tone: %s" % tone)
    rule = TONE_RULES[tone]
    targets = {}
    for channel_name in _CH:
        lo, hi = rule[channel_name]
        targets[channel_name] = round((lo + hi) / 2.0, 6)
    targets["pace"] = rule["pace"]
    for channel_name in _CH:
        if targets[channel_name] > CHANNEL_MAX[channel_name] + 1e-9:
            raise ValueError("tone target above ceiling: %s" % tone)
    return targets


def tone_band(tone, channel_name):
    """Return the (lo, hi) band for a tone/channel as floats."""
    if tone not in TONE_RULES:
        raise ValueError("unknown tone: %s" % tone)
    if channel_name not in _CH:
        raise ValueError("unknown channel: %s" % channel_name)
    return TONE_RULES[tone][channel_name]


def validate_tone_profiles():
    """Registry-level invariants over tone profiles."""
    for tone in TONE_RULES:
        for channel_name in _CH:
            lo, hi = TONE_RULES[tone][channel_name]
            if not (0.0 <= lo <= hi <= CHANNEL_MAX[channel_name] + 1e-9):
                raise ValueError("tone band out of bounds: %s.%s" % (tone, channel_name))
            if not (0.0 < TONE_RULES[tone]["pace"] <= 1.0):
                raise ValueError("invalid pace for tone: %s" % tone)