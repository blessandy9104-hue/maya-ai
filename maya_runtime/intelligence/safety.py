"""Safety enforcement: clamping, thresholding, normalization, drift limits,
and persona weight restrictions. Runs before meaning computation and
language generation. Failure degrades to neutral; it never fabricates.
"""
from __future__ import annotations

from math import isfinite

from ..core import (
    MATH_AGENT,
    CHANNEL_MAX,
    clamp01,
    math_isclose,
)
from ..isolation.ceilings import PERSONA_CEILINGS
from .feature_map import _neutral
from .fusion import CHANNELS, math_weights_sum

MAX_PERSONA_WEIGHT = 0.6
DRIFT_TOLERANCE = 0.35
NEUTRAL = 0.0


class SafetyEnforcer:
    """Deterministic sanitization of a fused frame."""

    def enforce(self, encoded=None, state=None, fusion=None,
                series=None, weights=None, persona_weights=None):
        violations = []
        encoded = encoded or {}
        state = state or {}
        fusion = fusion or {}

        clamped = {}
        for category in ("scalars", "vectors", "coefficients", "flags"):
            source = encoded.get(category, {})
            for name, value in source.items():
                if category == "flags" and not isinstance(value, bool):
                    value = str(value).strip().lower() in ("1", "true", "yes")
                    clamped[name] = value
                    continue
                if isinstance(value, (list, tuple)):
                    flattened = tuple(clamp01(_neutral(v)) for v in value)
                    if not all(isfinite(v) for v in flattened):
                        violations.append({"rule": "non_finite_sequence", "feature": name})
                    clamped[name] = flattened
                else:
                    v = _neutral(value)
                    if not isfinite(v):
                        violations.append({"rule": "non_finite_value", "feature": name})
                        v = NEUTRAL
                    clamped[name] = clamp01(v)

        base_weights = dict(persona_weights or (fusion.get("weights") or {}))
        restricted = {}
        for persona, weight in base_weights.items():
            w = clamp01(_neutral(weight))
            if not isfinite(w):
                violations.append({"rule": "non_finite_weight", "persona": persona})
                w = NEUTRAL
            restricted[persona] = min(w, MAX_PERSONA_WEIGHT)
        ordered = list(restricted)
        raw_list = [restricted[p] for p in ordered]

        drift_state = _neutral(state.get("drift", 0.0))
        drift_ok = drift_state <= DRIFT_TOLERANCE
        if not drift_ok:
            violations.append({"rule": "drift_beyond_tolerance",
                               "drift": drift_state})
            raw_list = [w * 0.25 for w in raw_list]

        if sum(raw_list) <= 0.0:
            for i, _p in enumerate(ordered):
                raw_list[i] = 1.0 / max(1, len(ordered))

        normalized = tuple(float(x) for x in
                           MATH_AGENT.task_blend(
                               raw_list, weights=raw_list)["weights"])
        final_weights = {p: w for p, w in zip(ordered, normalized)}

        channels = {}
        for ch in CHANNELS:
            values = [float(PERSONA_CEILINGS[p].get(ch, 0.0)) for p in ordered]
            fused = MATH_AGENT.task_blend(values, weights=normalized)["fused"]
            cap = float(CHANNEL_MAX[ch])
            channels[ch] = clamp01(min(fused, cap))

        if not renormalized_ok(normalized):
            violations.append({"rule": "weights_not_normalized"})

        safe = bool(not violations and state.get("ok", True) is not False)
        return {
            "sanitized": clamped,
            "weights": final_weights,
            "channels": channels,
            "violations": violations,
            "ok": safe,
        }


def renormalized_ok(weights):
    return all(w >= 0.0 for w in weights) and \
        math_isclose(sum(weights), 1.0)


SAFETY = SafetyEnforcer()


def enforce(*args, **kwargs):
    return SAFETY.enforce(*args, **kwargs)