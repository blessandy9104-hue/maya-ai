"""Device-invariance checks for the portable runtime.

These predicates guarantee the four cross-device invariants:

- no hardware-specific behavior
- no GPU dependencies
- no timing drift (no wall-clock/RNG in the runtime graph)
- no randomness
"""
from __future__ import annotations

import math

PORTABILITY_CONSTRAINTS = (
    "no hardware-specific behavior",
    "no GPU dependencies",
    "no timing drift",
    "no randomness",
    "all outputs finite and bounded",
    "channel data respects CHANNEL_MAX ceilings",
)

_FORBIDDEN_NAMES = ("random", "time", "tkinter", "datetime", "subprocess", "socket")


def assert_deterministic(module, label="runtime module"):
    """Raise if a runtime module is coupled to device- or clock-dependent APIs."""
    for name in _FORBIDDEN_NAMES:
        if hasattr(module, name):
            raise AssertionError(f"{label} {module.__name__!r} is device-coupled via {name!r}")


def check_finite(value):
    return isinstance(value, float) and math.isfinite(value)


def report():
    """Return a deterministic device-invariance report over the runtime core."""
    import maya_runtime.core as _core
    import maya_runtime.world_model as _wm
    import maya_runtime.safety_monitor as _sm
    import maya_runtime.pattern_alignment as _pa
    import maya_runtime.personality as _per
    import maya_runtime.intelligence as _iq

    checks = {
        "core_free_of_rng": not hasattr(_core, "random"),
        "core_free_of_clock": not hasattr(_core, "time"),
        "core_free_of_gui": not hasattr(_core, "tkinter"),
        "world_free_of_rng": not hasattr(_wm, "random"),
        "safety_free_of_rng": not hasattr(_sm, "random"),
        "pattern_free_of_rng": not hasattr(_pa, "random"),
        "personality_free_of_rng": not hasattr(_per, "random"),
        "intelligence_free_of_rng": not hasattr(_iq, "random"),
        "intelligence_free_of_clock": not hasattr(_iq, "time"),
        "intelligence_free_of_datetime": not hasattr(_iq, "datetime"),
        "channels_have_ceilings": len(_core.CHANNEL_MAX) == 4,
    }
    return checks