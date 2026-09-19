"""State engine: Maya's internal state, always computed before persona
fusion, world-model alignment, or language generation.

State = emotional intensity, cognitive clarity, stability, drift,
alignment, and safety boundaries. Every scalar is produced through the
verified math surface (``math_coordinator`` / ``rig_math``); non-finite
inputs degrade to neutral 0.0 and the state is never ``ok`` when any
component is invalid.
"""
from __future__ import annotations

from math import isfinite

from ..core import (
    MATH_AGENT,
    clamp01,
    WORLD_STATE_PATTERNS,
)
from .. import _loader
from .feature_map import _neutral, _as_vector

_COORD = _loader.module("math_coordinator")
LEARNING_MAX_STD = _COORD.LEARNING_MAX_STD
SAFETY_POLICY = _COORD.SAFETY_POLICY

COMPONENTS = ("emotional_intensity", "cognitive_clarity", "stability",
              "drift", "alignment")


def _bounded(value, floor_ok=True):
    v = _neutral(value)
    return clamp01(v)


class StateEngine:
    """Deterministic state machine (one frame in, one state vector out)."""

    def compute(self, encoded, world_series=None, reference=None,
                metrics=None, alpha=0.15):
        scalars = (encoded or {}).get("scalars", {})
        vectors = (encoded or {}).get("vectors", {})
        coefficients = (encoded or {}).get("coefficients", {})
        flags = (encoded or {}).get("flags", {})

        emotional_inputs = [
            v for k, v in scalars.items()
        ]
        intensity_raw = max(emotional_inputs + [0.0])
        arousal = _neutral(coefficients.get("arousal", 0.0))
        emotional_intensity = _bounded(
            MATH_AGENT.pattern_priority(
                clamp01((intensity_raw + arousal) / 2.0)))

        clarity_vec_a = vectors.get("topic_vector")
        clarity_vec_b = vectors.get("state_vector")
        if clarity_vec_a is not None and clarity_vec_b is not None:
            clarity_raw = MATH_AGENT.pattern_alignment(
                _as_vector(clarity_vec_a), _as_vector(clarity_vec_b))
        elif reference is not None:
            ref = _as_vector(reference)
            source = clarity_vec_a if clarity_vec_a is not None else clarity_vec_b
            if source is not None:
                clarity_raw = MATH_AGENT.pattern_alignment(
                    _as_vector(source), ref)
            else:
                clarity_raw = 1.0
        else:
            clarity_raw = 1.0
        clarity_raw = _neutral(clarity_raw)

        series = None
        if isinstance(world_series, (list, tuple)) and world_series:
            series = tuple(_neutral(v) for v in world_series)
        if not series:
            series = history_from_encoded(encoded)

        stability_report = MATH_AGENT.world_stability(series)
        std = stability_report.get("std")
        std_ok = bool(stability_report.get("ok", False))
        if isinstance(std, (int, float)) and isfinite(std):
            stability = _bounded(stability_score(std))
        else:
            stability = 0.0 if std is None else _bounded(stability_score(0.0))

        drift_report = MATH_AGENT.world_drift(series)
        drift = _bounded(drift_report.get("drift", 0.0))

        alignment_source = _as_vector(reference) if reference is not None else None
        if alignment_source is not None:
            anchor = _as_vector(WORLD_STATE_PATTERNS["stable_equilibrium"])
            alignment = _bounded(MATH_AGENT.pattern_alignment(
                alignment_source[:2], anchor[:2]))
        else:
            alignment = _bounded(1.0 - drift)

        safety_report = self._safety(metrics)
        safety_boundaries = safety_report

        state_vector = (
            emotional_intensity,
            clarity_raw,
            stability,
            drift,
            alignment,
        )
        components_ok = all(isfinite(v) and 0.0 <= v <= 1.0
                            for v in state_vector)
        safety_ok = bool(safety_report.get("safe", True))
        stable_ok = std_ok and drift_report.get("ok", True) is True
        ok = bool(components_ok and safety_ok and stable_ok)

        return {
            "emotional_intensity": emotional_intensity,
            "cognitive_clarity": clarity_raw,
            "stability": stability,
            "drift": drift,
            "alignment": alignment,
            "std": std,
            "stability_ok": std_ok,
            "safety_boundaries": safety_boundaries,
            "state_vector": state_vector,
            "ok": ok,
            "reference": tuple(alignment_source) if alignment_source is not None else None,
        }

    def _safety(self, metrics):
        m = metrics or {}
        policy = m.get("policy", SAFETY_POLICY)
        try:
            margin_report = MATH_AGENT.pattern_safety_margin(
                _neutral(m.get("cpu_percent", 0.0)),
                _neutral(m.get("memory_percent", 0.0)),
                max(0, int(_neutral(m.get("process_count", 0)))),
                max(0, int(_neutral(m.get("launches", 0)))),
                policy=policy,
            )
        except Exception:
            margin_report = 0.0
        margin = _bounded(margin_report)
        limits = MATH_AGENT.check_limits(
            _neutral(m.get("cpu_percent", 0.0)),
            _neutral(m.get("memory_percent", 0.0)),
            max(0, int(_neutral(m.get("process_count", 0)))),
            max(0, int(_neutral(m.get("launches", 0)))),
            policy=policy,
        )
        violations = list(limits.get("violations", []))
        safe = bool(limits.get("safe", False)) and margin > 0.0
        return {
            "safe": safe,
            "margin": margin,
            "violations": violations,
            "policy": dict(policy),
        }


def stability_score(std, max_std=LEARNING_MAX_STD):
    """stability = 1 - clamp01(std / max_std). Neutral when std is invalid."""
    std = _neutral(std)
    max_std = _neutral(max_std)
    if max_std <= 0.0:
        return 0.0
    return 1.0 - clamp01(std / max_std)


def history_from_encoded(encoded):
    scalars = (encoded or {}).get("scalars", {})
    candidates = [v for k, v in scalars.items()
                  if isinstance(v, (int, float)) and isfinite(v)]
    if candidates:
        return tuple(candidates)
    vectors = (encoded or {}).get("vectors", {})
    for vector in vectors.values():
        if isinstance(vector, (list, tuple)) and len(vector) > 1:
            return tuple(_neutral(v) for v in vector)
    return (0.0,)


STATE_ENGINE = StateEngine()


def compute(*args, **kwargs):
    return STATE_ENGINE.compute(*args, **kwargs)