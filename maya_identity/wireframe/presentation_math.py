"""PresentationMath — bounded math facade for Maya's visual layers.

Architecture-risk fix: presentation-layer math no longer lives inline in GUI
files. The small set of transforms the visual layers apply directly (bounds,
scale factors, gaze remaps, colour interpolation) is gathered here in one
place, using the exact constants and formulas the old per-file helpers used —
this is a routing change, not a behaviour change.

Boundary contract:
- State MERGES and pattern transitions stay exclusively with the Math
  Coordination Agent (GUI files still call ``MATH_AGENT.pattern_state``).
- This facade owns only presentation CLAMPS and SCALE FACTORS.
- Rendering geometry (trigonometry, coordinate maps, sines) stays in the
  renderer, because it is pure drawing, not decision math.

Numeric semantics deliberately match the pre-facade implementations:
- non-numeric input uses ``on_error`` (raises by default, matching the
  attention/hologram helpers; ``None`` / ``lo`` are passed where the old
  awareness/presence helpers used them);
- non-finite input passes through exactly as the original ``max/min`` clamps
  did; it is bounded downstream by the agent's domain boundaries.
"""
from __future__ import annotations

_RAISE = object()


def clip(value, lo=0.0, hi=1.0, *, on_error=_RAISE):
    """Bound ``value`` to ``[lo, hi]``. See the module docstring for
    ``on_error`` semantics."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        if on_error is _RAISE:
            raise
        return on_error
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def scale(value, factor, *, lo=None, hi=None, on_error=_RAISE):
    """``value * factor``, optionally bounded into ``[lo, hi]``."""
    try:
        v = float(value) * factor
    except (TypeError, ValueError):
        if on_error is _RAISE:
            raise
        return on_error
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def boost(value, delta, factor):
    """Focus target = clamp01(value + delta * factor) (gaze-raise blend)."""
    return clip(value + delta * factor)


def gaze_focus(gx, gy):
    """Gaze to on-screen focus point: ``(gx * 0.25 + 0.5, gy * 0.25 + 0.42)``."""
    return (gx * 0.25 + 0.5, gy * 0.25 + 0.42)


def remap_centered(value, center):
    """Centered remap: ``(value - center) * 2.0`` (gaze centring)."""
    return (value - center) * 2.0


def decay_alpha(step):
    """Gaze decay lambda cap: ``min(0.25, 0.02 * step)``."""
    return min(0.25, 0.02 * step)


def mix_color(hex1, hex2, w1):
    """Linear mix of two ``#rrggbb`` colours by weight (renderer's ``_mix``)."""
    w1 = clip(w1)
    w2 = 1 - w1
    c1 = tuple(int(hex1[i:i + 2], 16) for i in (1, 3, 5))
    c2 = tuple(int(hex2[i:i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(int(round(c1[k] * w1 + c2[k] * w2)) for k in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


__all__ = ("clip", "scale", "boost", "gaze_focus", "remap_centered",
           "decay_alpha", "mix_color")