"""Cross-registry bridge: the UX self-description and the math engine.

Maya has two capability inventories that serve different layers:

- ``maya_capabilities`` — the user-facing display registry (13 groups of
  command surfaces) used by every NL/status/help answer.
- ``maya_identity.capability_registry`` — the canonical math-engine
  capability registry (11 slugs across 4 platform layers) produced by the
  deterministic substrate.

This bridge maps display groups to math-engine slugs **explicitly**, classifies
the purely local feature groups (whose execution lives in the local command
layer, not the math engine) and the system-internal math slugs (engine
internals with no user-facing group), and exposes a consistency_check() that
fails when any display group is unmapped, any mapped slug goes missing from the
math registry, or a math slug is neither mapped nor declared internal.

Nothing here invents behavior; it makes the two inventories' overlap
reviewable and machine-checked. Read-only, deterministic, import-light.
"""
from __future__ import annotations

# Display group  -> tuple of math-engine slugs it is built on.
DISPLAY_TO_SLUG = {
    "conversation": ("emotional_blending", "cognitive_reasoning"),
    "research": ("cognitive_reasoning",),
    "evidence drilldown": ("contextual_memory",),
    "world model": ("world_stability",),
    "knowledge network": ("contextual_memory",),
    "system": ("safety_monitoring", "thinkpad_performance"),
}

# Display groups whose execution lives in the local command layer (status,
# tasks, reports, recap, review surfaces), not in the math engine.
_LOCAL_FEATURE_GROUPS = frozenset({
    "status", "session recap", "reports", "tasks", "observations",
    "improvement", "interests",
})

# Math-engine slugs with no user-facing display group: platform internals
# (face, pattern, coordination, interaction, domain profiles).
_SYSTEM_INTERNAL_SLUGS = frozenset({
    "expressive_math_face", "pattern_intelligence",
    "multi_agent_coordination", "adaptive_interaction",
    "domain_specific_behaviors",
})


def display_groups() -> tuple[str, ...]:
    from maya_capabilities import CAPABILITY_REGISTRY
    return tuple(name for name, _, _ in CAPABILITY_REGISTRY)


def math_slugs() -> tuple[str, ...]:
    from maya_identity.capability_registry import CAPABILITY_REGISTRY
    return tuple(sorted(CAPABILITY_REGISTRY))


def group_for_slug(slug: str) -> str | None:
    """First display group mapped to a math-engine slug, or None."""
    for group, slugs in sorted(DISPLAY_TO_SLUG.items()):
        if slug in slugs:
            return group
    return None


def slugs_for_group(group: str) -> tuple[str, ...]:
    """The math-engine slugs a display group is declared to build on."""
    return tuple(DISPLAY_TO_SLUG.get(group, ()))


def local_feature_groups() -> tuple[str, ...]:
    return tuple(sorted(_LOCAL_FEATURE_GROUPS))


def system_internal_slugs() -> tuple[str, ...]:
    return tuple(sorted(_SYSTEM_INTERNAL_SLUGS))


def _check_registries():
    """Import-time validation of every mapping target. Raises instead of
    returning a problem list so an unmappable name breaks loudly at import
    (a check the tests also run explicitly)."""
    from maya_capabilities import CAPABILITY_REGISTRY as DISPLAY
    from maya_identity.capability_registry import CAPABILITY_REGISTRY as MATH

    display_names = {name for name, _, _ in DISPLAY}
    unknown_group = set(DISPLAY_TO_SLUG) - display_names
    if unknown_group:
        raise KeyError("bridge maps unregistered display groups: "
                       + ", ".join(sorted(unknown_group)))
    unknown_slug = set()
    for slugs in DISPLAY_TO_SLUG.values():
        unknown_slug |= set(slugs) - set(MATH)
    if unknown_slug:
        raise KeyError("bridge maps unregistered math slugs: "
                       + ", ".join(sorted(unknown_slug)))
    nonexistent_local = _LOCAL_FEATURE_GROUPS - display_names
    if nonexistent_local:
        raise KeyError("bridge names unregistered local groups: "
                       + ", ".join(sorted(nonexistent_local)))
    nonexistent_internal = _SYSTEM_INTERNAL_SLUGS - set(MATH)
    if nonexistent_internal:
        raise KeyError("bridge names unregistered internal slugs: "
                       + ", ".join(sorted(nonexistent_internal)))
    overlap = _LOCAL_FEATURE_GROUPS & set(DISPLAY_TO_SLUG)
    if overlap:
        raise KeyError("bridge group is both local-feature and mapped: "
                       + ", ".join(sorted(overlap)))


def consistency_check() -> list[str]:
    """Drift report comparing the bridge with both live registries.

    Returns one problem description per violation, or the single sentinel
    ``"capability_bridge_ok"`` when the two inventories are in the declared
    relationship: every display group is mapped or declared local; every math
    slug is mapped or declared system-internal. Read-only.
    """
    _check_registries()
    display_names = set(display_groups())
    math_names = set(math_slugs())

    problems = []
    mapped = set(DISPLAY_TO_SLUG)
    unmapped = sorted(display_names - mapped - _LOCAL_FEATURE_GROUPS)
    if unmapped:
        problems.append("display groups unmapped and not local: "
                        + ", ".join(unmapped))
    mapped_slugs = set()
    for slugs in DISPLAY_TO_SLUG.values():
        mapped_slugs |= set(slugs)
    orphan = sorted(math_names - mapped_slugs - _SYSTEM_INTERNAL_SLUGS)
    if orphan:
        problems.append("math engine slugs neither mapped nor internal: "
                        + ", ".join(orphan))
    return problems or ["capability_bridge_ok"]


def coverage_summary() -> dict[str, object]:
    """Numbers behind the unified self-report, derived from live registries."""
    _check_registries()
    return {
        "display_groups": len(display_groups()),
        "math_engine_slugs": len(math_slugs()),
        "mapped_display_groups": len(DISPLAY_TO_SLUG),
        "local_feature_groups": len(_LOCAL_FEATURE_GROUPS),
        "system_internal_slugs": len(_SYSTEM_INTERNAL_SLUGS),
        "layers": _layer_counts(),
    }


def _layer_counts() -> dict[str, int]:
    from maya_identity.capability_registry import (
        CAPABILITY_REGISTRY, LAYERS)
    counts = {layer: 0 for layer in LAYERS}
    for entry in CAPABILITY_REGISTRY.values():
        counts[entry.get("layer", "core")] += 1
    return counts


_check_registries()