"""Feature encoder: every sensed input becomes math primitives.

Convert semantic, emotional, contextual, and historical inputs into
vectors, scalars, coefficients, and flags. No feature may interact
directly with another: each is routed through its governing primitive
(see ``feature_map``); any combination of features happens only through
the verified functions ``blend_pose`` / ``task_fuse`` / ``pattern_state``.
"""
from __future__ import annotations

from .feature_map import (
    FEATURE_INDEX,
    PRIMITIVE_BINDINGS,
    apply_primitive,
    feature_key,
    _neutral,
)


class FeatureEncoder:
    """Deterministic, stateless encoder of raw inputs into math atoms."""

    def encode(self, semantic=None, emotional=None, contextual=None,
               historical=None, reference=None, render=None):
        """Encode one frame. Unknown features fail closed; non-finite -> 0.0.

        Returns ``{"vectors", "scalars", "coefficients", "flags",
        "governing"}``. ``governing`` reports the primitive that produced
        each output, for full traceability.
        """
        sources = {
            "semantic": semantic or {},
            "emotional": emotional or {},
            "contextual": contextual or {},
            "historical": historical or {},
            "render": render or {},
        }
        vectors = {}
        scalars = {}
        coefficients = {}
        flags = {}
        governing = {}
        for category, mapping in sources.items():
            for name, value in mapping.items():
                key = feature_key(category, name)
                spec = FEATURE_INDEX[key]
                binding = PRIMITIVE_BINDINGS[spec["primitive"]]
                domain = spec["domain"]
                kind = spec["kind"]
                ref = reference if reference is not None else None
                if category == "historical" and spec["primitive"] in (
                        "world_stability", "world_drift"):
                    result = apply_primitive(
                        binding, None, reference=ref,
                        series=value if isinstance(value, (list, tuple)) else [value])
                elif spec["primitive"] == "pattern_alignment" and isinstance(
                        value, (list, tuple)):
                    result = apply_primitive(binding, value, reference=ref)
                else:
                    result = apply_primitive(
                        binding, value, reference=ref,
                        series=value if isinstance(value, (list, tuple)) else None)
                if isinstance(result, dict):
                    result = _report_scalar(result)
                flat = _neutral(result)
                if kind == "vector":
                    vectors[name] = flat
                elif kind == "coefficient":
                    coefficients[name] = _clamp_domain(flat, domain)
                elif kind == "flag":
                    flags[name] = bool(_clamp_domain(flat, domain))
                else:
                    scalars[name] = _clamp_domain(flat, domain)
                governing[key] = spec["primitive"]
        return {
            "vectors": vectors,
            "scalars": scalars,
            "coefficients": coefficients,
            "flags": flags,
            "governing": governing,
        }


def _clamp_domain(value, domain):
    lo, hi = domain
    return max(lo, min(hi, value))


def _report_scalar(result):
    for key in ("std", "drift", "coherence", "alignment", "fused", "confidence"):
        if key in result:
            candidate = result[key]
            try:
                return float(candidate)
            except (TypeError, ValueError):
                continue
    return 0.0


ENCODER = FeatureEncoder()


def encode(*args, **kwargs):
    return ENCODER.encode(*args, **kwargs)