"""Feature-to-math mapping table and primitive bindings.

Every feature Maya senses (semantic, emotional, contextual, historical) is
governed by exactly one verified math primitive. A feature never reaches
another feature directly: the only way two encoded features interact is
through the verified function that governs them. Unknown features fail
closed, non-finite inputs degrade to the neutral 0.0.

The six headline primitives the table routes through are:

    glow01, depth01, thickness01, world_index, pattern_alignment, task_fuse

plus the supporting verified surface (clamp01, pattern_priority,
world_stability, world_drift, world_coherence, world_classify, blend_pose).
"""
from __future__ import annotations

from math import isfinite

from ..core import (
    MATH_AGENT,
    clamp01,
    glow01,
    depth01,
    thickness01,
    zprime,
    blend_pose,
    jaw_open,
    math_isclose,
)

CATEGORIES = ("semantic", "emotional", "contextual", "historical")

SCALAR = "scalar"
VECTOR = "vector"
COEFFICIENT = "coefficient"
FLAG = "flag"

KINDS = frozenset({SCALAR, VECTOR, COEFFICIENT, FLAG})

FEATURE_MATH_MAP = {
    "semantic": {
        "coherence":       {"primitive": "pattern_alignment", "kind": SCALAR, "domain": (0.0, 1.0)},
        "salience":        {"primitive": "pattern_alignment", "kind": SCALAR, "domain": (0.0, 1.0)},
        "novelty":         {"primitive": "pattern_alignment", "kind": SCALAR, "domain": (0.0, 1.0)},
        "topic_vector":    {"primitive": "pattern_alignment", "kind": VECTOR, "domain": (0.0, 1.0)},
        "evidence_sufficient": {"primitive": "pattern_alignment", "kind": FLAG, "domain": (0.0, 1.0)},
    },
    "emotional": {
        "intensity":       {"primitive": "pattern_priority", "kind": SCALAR, "domain": (0.0, 1.0)},
        "valence":         {"primitive": "clamp01", "kind": COEFFICIENT, "domain": (0.0, 1.0)},
        "arousal":         {"primitive": "clamp01", "kind": SCALAR, "domain": (0.0, 1.0)},
        "warmth":          {"primitive": "clamp01", "kind": COEFFICIENT, "domain": (0.0, 1.0)},
        "state_vector":    {"primitive": "pattern_alignment", "kind": VECTOR, "domain": (0.0, 1.0)},
        "reactive":        {"primitive": "clamp01", "kind": FLAG, "domain": (0.0, 1.0)},
    },
    "contextual": {
        "urgency":         {"primitive": "task_fuse", "kind": SCALAR, "domain": (0.0, 1.0)},
        "impact":          {"primitive": "task_fuse", "kind": SCALAR, "domain": (0.0, 1.0)},
        "effort":          {"primitive": "task_fuse", "kind": SCALAR, "domain": (0.0, 1.0)},
        "relevance":       {"primitive": "pattern_alignment", "kind": SCALAR, "domain": (0.0, 1.0)},
        "task_vector":     {"primitive": "task_fuse", "kind": VECTOR, "domain": (0.0, 1.0)},
        "time_critical":   {"primitive": "pattern_priority", "kind": FLAG, "domain": (0.0, 1.0)},
    },
    "historical": {
        "stability":       {"primitive": "world_stability", "kind": SCALAR, "domain": (0.0, 1.0)},
        "drift":           {"primitive": "world_drift", "kind": SCALAR, "domain": (0.0, 1.0)},
        "coherence":       {"primitive": "world_coherence", "kind": SCALAR, "domain": (0.0, 1.0)},
        "consensus":       {"primitive": "world_index", "kind": SCALAR, "domain": (0.0, 1.0)},
        "currency":        {"primitive": "world_index", "kind": SCALAR, "domain": (0.0, 1.0)},
        "equilibrium_near": {"primitive": "pattern_alignment", "kind": FLAG, "domain": (0.0, 1.0)},
    },
    "render": {
        "glow":            {"primitive": "glow01", "kind": SCALAR, "domain": (0.0, 1.0)},
        "depth":           {"primitive": "depth01", "kind": SCALAR, "domain": (0.0, 1.0)},
        "thickness":       {"primitive": "thickness01", "kind": COEFFICIENT, "domain": (1.0, 5.0)},
        "zprime":          {"primitive": "zprime", "kind": SCALAR, "domain": (-0.9, 0.8)},
        "jaw":             {"primitive": "jaw_open", "kind": COEFFICIENT, "domain": (0.0, 1.0)},
        "glow_present":    {"primitive": "glow01", "kind": FLAG, "domain": (0.0, 1.0)},
    },
}

FEATURE_INDEX = {}
for _category, _features in FEATURE_MATH_MAP.items():
    for _name, _spec in _features.items():
        FEATURE_INDEX["%s.%s" % (_category, _name)] = _spec
del _category, _features, _name, _spec

PRIMITIVE_BINDINGS = {
    "pattern_alignment": MATH_AGENT.pattern_alignment,
    "pattern_priority": MATH_AGENT.pattern_priority,
    "pattern_transition": MATH_AGENT.pattern_transition,
    "pattern_state": MATH_AGENT.pattern_state,
    "clamp01": clamp01,
    "blend_pose": blend_pose,
    "glow01": glow01,
    "depth01": depth01,
    "thickness01": thickness01,
    "zprime": zprime,
    "jaw_open": jaw_open,
    "task_fuse": MATH_AGENT.task_fuse,
    "task_blend": MATH_AGENT.task_blend,
    "task_confidence": MATH_AGENT.task_confidence,
    "world_index": MATH_AGENT.world_index,
    "world_stability": MATH_AGENT.world_stability,
    "world_drift": MATH_AGENT.world_drift,
    "world_coherence": MATH_AGENT.world_coherence,
    "world_classify": MATH_AGENT.world_classify,
    "math_isclose": math_isclose,
}


def _neutral(value, fallback=0.0):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    if not isfinite(v):
        return fallback
    return v


def _as_vector(value):
    if isinstance(value, (list, tuple)):
        return tuple(_neutral(v) for v in value)
    return (_neutral(value),)


def feature_key(category, name):
    key = "%s.%s" % (category, name)
    if key not in FEATURE_INDEX:
        raise ValueError("feature %r has no governing primitive" % key)
    return key


def spec_of(category, name):
    return FEATURE_INDEX[feature_key(category, name)]


def governing(category, name):
    return spec_of(category, name)["primitive"]


def domain_of(category, name):
    return spec_of(category, name)["domain"]


def known(category, name):
    return "%s.%s" % (category, name) in FEATURE_INDEX


def apply_primitive(binding, value, reference=None, series=None, ceiling=None,
                    context=None, weights=None, floor=0.6):
    """Apply one verified primitive to one feature.

    Every form is a direct call into MATH_AGENT or rig_math; no feature ever
    computes another feature's value. Raw values are passed through so each
    verified primitive's own fail-degraded (non-finite) path is preserved;
    a neutral 0.0 fallback is never substituted ahead of the math surface.
    """
    if binding is None:
        raise ValueError("primitive binding unavailable")
    if isinstance(value, (list, tuple)):
        item = tuple(_neutral(v) for v in value)
    else:
        item = value
    if binding.__name__ == "pattern_alignment":
        if reference is None:
            return 0.0
        ref_v = _as_vector(reference)
        val_v = _as_vector(value)
        if len(val_v) == 1 and len(ref_v) > 1:
            val_v = tuple(val_v[0] for _ in ref_v)
        return binding(val_v, ref_v)
    if binding.__name__ == "pattern_priority":
        return binding(item)
    if binding.__name__ == "pattern_transition":
        return binding(item, _neutral(reference, 1.0), _neutral(context, 0.0))
    if binding.__name__ == "pattern_state":
        return binding(item, _neutral(reference, 1.0), _neutral(context, 0.15))
    if binding.__name__ == "clamp01":
        return binding(item)
    if binding.__name__ == "blend_pose":
        return binding(item, _neutral(context, 0.0), _neutral(reference, 0.0))
    if binding.__name__ == "task_fuse":
        report = binding(item, _neutral(context, 0.0), _neutral(reference, 0.0))
        return report.get("fused", 0.0)
    if binding.__name__ == "task_blend":
        report = binding(item, weights)
        return report
    if binding.__name__ == "task_confidence":
        report = binding(item, _neutral(context, 0.0), _neutral(reference, 0.0))
        return report.get("confidence", 0.0)
    if binding.__name__ == "world_index":
        return binding(item, _neutral(ceiling, 1.0))
    if binding.__name__ == "world_stability":
        series_v = tuple(_neutral(s) for s in (series if series is not None else ()))
        return binding(series_v)
    if binding.__name__ == "world_drift":
        series_v = tuple(_neutral(s) for s in (series if series is not None else ()))
        return binding(series_v)
    if binding.__name__ == "world_coherence":
        vector = _as_vector(value)
        ref_v = _as_vector(reference)
        report = binding(vector, equilibrium=ref_v, floor=floor)
        return report
    if binding.__name__ == "world_classify":
        vector = _as_vector(value)
        return binding(vector, floor=floor)
    if binding.__name__ in ("glow01", "depth01", "thickness01", "zprime", "jaw_open"):
        return binding(item)
    if binding.__name__ == "math_isclose":
        return bool(binding(item, _neutral(reference, 1.0)))
    raise ValueError("primitive %r is not bound" % binding.__name__)


ALIGNMENT_FLOOR = 0.6
STABILITY_FLOOR = 0.6