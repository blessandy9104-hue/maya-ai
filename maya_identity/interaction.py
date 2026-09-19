"""Interaction layer: voice input, gesture mapping, emotional mirroring,
adaptive teaching.

Every interaction modality reduces to bounded, deterministic math over the
canonical control domain [0, 1] (per-axis gesture components on [-1, 1]).
Voice input maps a bounded acoustic feature vector onto bounded channel
targets through the canonical blend proportions — it is a math layer, not a
speech-recognition stack: it never invents meaning for a feature it does not
recognize (unknown features raise). Gesture mapping projects a normalized
gesture onto per-channel displacements that respect the canonical channel
ceilings. Emotional mirroring is a clamped exponential-smoothing convergence
toward the partner state that can never overshoot. Adaptive teaching paces a
learner toward a target with the step size governed by observed performance,
again through clamped interpolation — bounded, monotone, deterministic.
"""
from __future__ import annotations

from .wireframe.rig_math import (
    clamp01, lerp, exp_smooth, math_isclose,
    normalize, magnitude,
)
from .wireframe.math_coordinator import (
    MATH_AGENT,
    CHANNEL_MAX, CH_EXPRESSION, CH_VISEME, CH_MICRO,
)

__all__ = [
    "Interaction",
    "INTERACTION",
    "VOICE_FEATURES",
    "MIRROR_DEFAULT_ALPHA",
    "TEACH_DEFAULT_ALPHA",
    "TEACH_NEUTRAL_PACE",
]

VOICE_FEATURES = ("pitch", "rate", "energy", "pause")
MIRROR_DEFAULT_ALPHA = 0.15
TEACH_DEFAULT_ALPHA = 0.2
TEACH_NEUTRAL_PACE = 0.5

# Canonical interaction blend: 0.6 / 0.3 / 0.1 proportions reused for
# feature-to-channel mapping, exactly as in the pose blend and task fusion.
_INTERACT_E = 0.6
_INTERACT_V = 0.3
_INTERACT_M = 0.1

# Default per-channel ceilings for gesture projection. CHANNEL_MAX is the
# canonical source; these are the channel semantics gesture may drive.
_GESTURE_CEILINGS = {
    CH_EXPRESSION: CHANNEL_MAX.get(CH_EXPRESSION, 0.02),
    CH_VISEME: CHANNEL_MAX.get(CH_VISEME, 0.03),
    CH_MICRO: CHANNEL_MAX.get(CH_MICRO, 0.012),
}


class Interaction:
    """Deterministic interaction math: every method is a pure function of its
    inputs (no state, no RNG), so identical inputs give identical responses."""

    # ---- voice input -----------------------------------------------------
    def voice_input(self, features):
        """Map a bounded acoustic feature vector onto bounded channel targets.

        ``features`` maps a subset of ``VOICE_FEATURES`` (pitch, rate,
        energy, pause) to bounded values. The viseme target blends energy,
        rate, and pitch through the canonical 0.6 / 0.3 / 0.1 proportions;
        expression glow and eye focus are bounded complements of energy and
        pause. An unrecognized feature raises ``ValueError`` — voice input
        never guesses what a feature means. Every output is clamped onto
        [0, 1]."""
        known = dict(features)
        unknown = [name for name in known
                   if name not in set(VOICE_FEATURES)]
        if unknown:
            raise ValueError(
                f"unknown voice feature {unknown[0]!r} "
                f"(expected one of {sorted(VOICE_FEATURES)})")
        pitch = clamp01(float(known.get("pitch", 0.0)))
        rate = clamp01(float(known.get("rate", 0.0)))
        energy = clamp01(float(known.get("energy", 0.0)))
        pause = clamp01(float(known.get("pause", 0.0)))
        viseme = clamp01(_INTERACT_E * energy + _INTERACT_V * rate
                         + _INTERACT_M * pitch)
        expression = clamp01(_INTERACT_E * energy + _INTERACT_V * pitch
                             + _INTERACT_M * pause)
        eye_focus = clamp01(1.0 - pause)
        return {
            "viseme_target": viseme,
            "expression_glow": expression,
            "eye_focus": eye_focus,
        }

    # ---- gesture mapping -------------------------------------------------
    def gesture_mapping(self, gesture, ceilings=None):
        """Project a normalized gesture vector onto per-channel displacements.

        ``gesture`` is a 3-tuple (x, y, z) with normalized components on
        [-1, 1]. Each component is scaled by its channel ceiling and clamped
        to ``[-ceiling, ceiling]``:

            displacement[i] = clamp(gesture[i] * ceiling[i], -c_i, c_i)

        Ceilings default to the canonical ``CHANNEL_MAX`` ceilings for the
        expression / viseme / micro channels, so a gesture can never push a
        channel past its semantic ceiling. Deterministic and bounded."""
        ceilings = dict(ceilings) if ceilings else _GESTURE_CEILINGS
        axes = (CH_EXPRESSION, CH_VISEME, CH_MICRO)
        if len(gesture) != len(axes):
            raise ValueError(
                f"gesture must have {len(axes)} components (got {len(gesture)})")
        displacements = []
        for axis, component in zip(axes, gesture):
            ceiling = float(ceilings.get(axis, _GESTURE_CEILINGS[axis]))
            c = max(0.0, ceiling)
            try:
                v = float(component)
            except (TypeError, ValueError):
                v = 0.0
            if v != v:  # non-finite -> neutral
                displacements.append(0.0)
                continue
            displacements.append(max(-c, min(c, v * c)))
        return {"displacements": tuple(displacements),
                "ceilings": tuple(ceilings.get(axis, _GESTURE_CEILINGS[axis])
                                  for axis in axes),
                "bounded": True}

    # ---- emotional mirroring --------------------------------------------
    def emotional_mirroring(self, own, partner, alpha=None):
        """Emotional mirroring that converges toward the partner without
        overshoot.

        The mirror state is one clamped exponential-smoothing step
        ``exp_smooth(clamp01(own), clamp01(partner), clamp01(alpha))`` — the
        canonical pattern-state change. Because both endpoints and ``alpha``
        are clamped, the mirrored emotion stays inside
        ``[min(own, partner), max(own, partner)]`` every step and approaches
        the partner monotonically. Affinity is ``1 - |own - partner|``
        (bounded [0, 1]). Deterministic across calls."""
        alpha_v = clamp01(float(MIRROR_DEFAULT_ALPHA
                                if alpha is None else alpha))
        o = clamp01(own)
        p = clamp01(partner)
        mirror = exp_smooth(o, p, alpha_v)
        affinity = clamp01(1.0 - abs(o - p))
        return {
            "mirror_state": mirror,
            "affinity": affinity,
            "converged": math_isclose(mirror, p),
            "alpha": alpha_v,
        }

    # ---- adaptive teaching ----------------------------------------------
    def adaptive_teaching(self, learner, target, performance=None, alpha=None):
        """Performance-paced, no-overshoot teaching recommendation.

        The recommended next level interpolates the learner toward the target
        with a step size governed by observed performance: the effective step
        is ``clamp01(alpha) * (0.5 + 0.5 * clamp01(pace))`` where ``pace`` is
        the clamped performance (default neutral ``TEACH_NEUTRAL_PACE``).
        Because the interpolation factor always lies in [0, 1] and both
        endpoints are clamped, the recommendation stays inside
        ``[min(learner, target), max(learner, target)]`` and moves monotonically
        toward the target. Deterministic and CPU-light."""
        alpha_v = clamp01(float(TEACH_DEFAULT_ALPHA
                                if alpha is None else alpha))
        l = clamp01(learner)
        t = clamp01(target)
        pace = TEACH_NEUTRAL_PACE if performance is None \
            else clamp01(float(performance))
        factor = clamp01(alpha_v * (0.5 + 0.5 * pace))
        recommended = lerp(l, t, factor)
        move = abs(recommended - l)
        gap = abs(t - l)
        return {
            "recommended_level": recommended,
            "move": move,
            "gap": gap,
            "pace": pace,
            "alpha": alpha_v,
            "converged": math_isclose(recommended, t),
        }


INTERACTION = Interaction()