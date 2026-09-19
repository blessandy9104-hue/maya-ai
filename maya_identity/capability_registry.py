"""Capability and market-role registries for Maya.

Deterministic, inspection-only metadata: which production capabilities the
math engine currently delivers (11 capabilities across the core, cognitive,
interaction, and domain layers) and which market roles those capabilities
serve (8 roles). Nothing here invents behavior — the registry declares what
the canonical math layer already provides, so a role can be matched to a
capability without heuristics. Lookups are deterministic (sorted); the
registry is a constant, not a mutable runtime store.

Layers
------
core        — the expression, world, safety, and coordination planes produced
              by rig_math + math_coordinator.
cognitive   — reasoning, planning, contextual memory, bounded prediction
              (maya_identity.cognition).
interaction — voice-input mapping, gesture mapping, emotional mirroring,
              adaptive teaching (maya_identity.interaction).
domain      — role-bound domain behaviours for tutoring, customer service,
              therapy support, robotics, and entertainment
              (maya_identity.domains).

Every capability, regardless of layer, inherits the platform guarantees:
deterministic math (no randomness), bounded [0, 1] output wherever a scalar
meaning is produced, semantic correctness (no invented channel labels),
pattern alignment through cosine similarity, world stability, canonical
safety thresholds, and CPU-light operation.
"""

__all__ = [
    "CAPABILITY_REGISTRY",
    "MARKET_ROLE_REGISTRY",
    "REGISTRY_VERSION",
    "CORE_LAYER",
    "COGNITIVE_LAYER",
    "INTERACTION_LAYER",
    "DOMAIN_LAYER",
    "LAYERS",
    "capability",
    "capabilities_for_role",
    "roles_for_capability",
    "capabilities_for_layer",
    "layer_for_capability",
    "role_summary",
    "market_overview",
]

REGISTRY_VERSION = "1.1"

CORE_LAYER = "core"
COGNITIVE_LAYER = "cognitive"
INTERACTION_LAYER = "interaction"
DOMAIN_LAYER = "domain"
LAYERS = (CORE_LAYER, COGNITIVE_LAYER, INTERACTION_LAYER, DOMAIN_LAYER)


def _finalize(registry):
    """Return a deterministic, immutable mapping for a registry dict."""
    return {name: dict(entry) for name, entry in
            sorted(registry.items())}


# Every capability is produced TODAY by the canonical math layer. "slug" is
# the canonical identifier, "layer" names the platform layer that owns it,
# "dependencies" names the primitives it builds on, "deterministic" is always
# True (Maya never randomizes).
CAPABILITY_REGISTRY = _finalize({
    "expressive_math_face": {
        "layer": CORE_LAYER,
        "summary": "Math-driven expressive face: affect, viseme, and micro "
                   "channels blended by the canonical 0.6/0.3/0.1 pose blend.",
        "dependencies": ("blend_pose", "compose_vertex", "control_channel",
                         "interpret"),
        "outcome": "A finite, bounded facial pose per frame",
        "deterministic": True,
    },
    "emotional_blending": {
        "layer": CORE_LAYER,
        "summary": "Emotional controls blended through the canonical semantic "
                   "channels so no label can smuggle one channel into another.",
        "dependencies": ("semantic_profile", "emotion_gate", "pattern_state"),
        "outcome": "Channel-safe emotional expression",
        "deterministic": True,
    },
    "world_stability": {
        "layer": CORE_LAYER,
        "summary": "World-state stability, equilibrium drift, and coherence "
                   "monitoring over normalized feature series.",
        "dependencies": ("world_stability", "world_drift", "world_coherence"),
        "outcome": "A finite drift/stability report per series",
        "deterministic": True,
    },
    "pattern_intelligence": {
        "layer": CORE_LAYER,
        "summary": "Five-domain pattern alignment, classification, and "
                   "transition exclusively through cosine similarity and "
                   "clamped lerp/exp_smooth.",
        "dependencies": ("pattern_alignment", "world_classify",
                         "pattern_transition", "pattern_state"),
        "outcome": "Bounded [0, 1] alignment scores, no heuristics",
        "deterministic": True,
    },
    "safety_monitoring": {
        "layer": CORE_LAYER,
        "summary": "Policy threshold compliance, fail-closed metric gates, and "
                   "variance-based resource anomaly detection.",
        "dependencies": ("check_limits", "pattern_safety_margin",
                         "resource_anomaly", "safety_evaluate"),
        "outcome": "Safe/unsafe decision, never a false-clear on bad input",
        "deterministic": True,
    },
    "multi_agent_coordination": {
        "layer": CORE_LAYER,
        "summary": "Peer-agent coordination where every message is a "
                   "normalized vector, goals align by dot similarity, and "
                   "contributions blend through lerp/exp_smooth.",
        "dependencies": ("agent_collaborate", "semantic_alignment",
                         "output_consistency"),
        "outcome": "Validated collaboration report per round",
        "deterministic": True,
    },
    "thinkpad_performance": {
        "layer": CORE_LAYER,
        "summary": "CPU-light, deterministic math tuned for constrained "
                   "hardware: fast-path finiteness probes in the frame loop, "
                   "no GPU dependencies, no randomness.",
        "dependencies": ("_fast_finite", "_blend_kernel", "posed_vertices"),
        "outcome": "Stable frame cadence without numeric shortcuts",
        "deterministic": True,
    },
    "cognitive_reasoning": {
        "layer": COGNITIVE_LAYER,
        "summary": "Reasoning, planning, and bounded prediction as math: "
                   "multi-signal evidence fused by the canonical blend "
                   "proportions, goal alignment by cosine similarity, and "
                   "monotone no-overshoot plans through clamped exp_smooth.",
        "dependencies": ("cognition.reasoning", "cognition.planning",
                         "cognition.bounded_prediction"),
        "outcome": "Bounded [0, 1] reasoned scores; monotone plan paths",
        "deterministic": True,
    },
    "contextual_memory": {
        "layer": COGNITIVE_LAYER,
        "summary": "Deterministic bounded context recall: relevance weights "
                   "normalized to a unit weight vector, capacity-capped, with "
                   "the recalled context selected by the greatest weight.",
        "dependencies": ("cognition.contextual_memory",),
        "outcome": "A normalized weight vector and a single recalled context",
        "deterministic": True,
    },
    "adaptive_interaction": {
        "layer": INTERACTION_LAYER,
        "summary": "Interaction mapping and mirroring as math: bounded voice "
                   "feature-to-channel targets, ceiling-respecting gesture "
                   "mapping, emotional mirroring that converges without "
                   "overshoot, and performance-paced adaptive teaching.",
        "dependencies": ("interaction.voice_input",
                         "interaction.gesture_mapping",
                         "interaction.emotional_mirroring",
                         "interaction.adaptive_teaching"),
        "outcome": "Bounded channel targets and no-overshoot adaptation",
        "deterministic": True,
    },
    "domain_specific_behaviors": {
        "layer": DOMAIN_LAYER,
        "summary": "Role-bound domain behaviour profiles (tutoring, customer "
                   "service, therapy support, robotics interface, "
                   "entertainment) expressed as canonical bounded channel "
                   "targets and verified against the capability registry.",
        "dependencies": ("domains.DOMAIN_BEHAVIORS",
                         "domains.apply_domain",
                         "domains.domain_for_role"),
        "outcome": "A domain-matched, bounded control-target vector",
        "deterministic": True,
    },
})

# Market roles: the production-facing deployable identities the capability
# registry supports. Each role maps to the capabilities it needs; a role is
# deployable when every named capability exists in CAPABILITY_REGISTRY.
MARKET_ROLE_REGISTRY = _finalize({
    "ai_companion": {
        "summary": "A personal companion persona: responsive emotional "
                   "dialogue with an expressive, stable face and contextual "
                   "recall.",
        "capabilities": ("expressive_math_face", "emotional_blending",
                         "world_stability", "pattern_intelligence",
                         "safety_monitoring", "cognitive_reasoning",
                         "contextual_memory", "adaptive_interaction",
                         "domain_specific_behaviors"),
        "constraints": ("bounded [0, 1] emotional channel", "no randomness",
                        "face stays finite on any input"),
    },
    "holographic_assistant": {
        "summary": "A holographic display assistant: expressive face bounded "
                   "to display physics, multi-agent coordination, and "
                   "enterprise task handling.",
        "capabilities": ("expressive_math_face", "emotional_blending",
                         "multi_agent_coordination", "safety_monitoring",
                         "cognitive_reasoning", "contextual_memory"),
        "constraints": ("channels respect display brightness", "finite poses"),
    },
    "educational_tutor": {
        "summary": "A tutoring persona: expressive face blended with "
                   "pattern-based lesson pacing, contextual recall, and "
                   "performance-paced adaptive teaching.",
        "capabilities": ("expressive_math_face", "pattern_intelligence",
                         "world_stability", "safety_monitoring",
                         "cognitive_reasoning", "contextual_memory",
                         "adaptive_interaction", "domain_specific_behaviors"),
        "constraints": ("alignment scores in [0, 1]", "bounded state changes"),
    },
    "vtuber_avatar": {
        "summary": "A live VTuber avatar: high-frequency expressive face, "
                   "emotional blending, and interaction mapping on "
                   "constrained hardware.",
        "capabilities": ("expressive_math_face", "emotional_blending",
                         "safety_monitoring", "thinkpad_performance",
                         "adaptive_interaction", "domain_specific_behaviors"),
        "constraints": ("frame cadence friendly", "CPU-light", "deterministic"),
    },
    "robotics_interface": {
        "summary": "A robotics-facing interface persona: world-state "
                   "stability, pattern intelligence, reasoned planning, and "
                   "safety-gated coordination over an actuation loop.",
        "capabilities": ("world_stability", "pattern_intelligence",
                         "multi_agent_coordination", "safety_monitoring",
                         "cognitive_reasoning", "contextual_memory",
                         "domain_specific_behaviors"),
        "constraints": ("fail-closed on non-finite sensors",
                        "bounded transitions only"),
    },
    "therapy_support_agent": {
        "summary": "A therapy-support persona: mirroring-focused interaction "
                   "with strict safety ceilings and bounded, drift-free "
                   "emotional state changes.",
        "capabilities": ("expressive_math_face", "emotional_blending",
                         "world_stability", "pattern_intelligence",
                         "safety_monitoring", "cognitive_reasoning",
                         "contextual_memory", "adaptive_interaction",
                         "domain_specific_behaviors"),
        "constraints": ("emotional mirroring converges without overshoot",
                        "safety thresholds never relaxed"),
    },
    "customer_service_agent": {
        "summary": "A customer-service persona: reliable reasoning, bounded "
                   "response mapping, and domain behaviour routed through "
                   "canonical channels.",
        "capabilities": ("expressive_math_face", "emotional_blending",
                         "world_stability", "pattern_intelligence",
                         "safety_monitoring", "cognitive_reasoning",
                         "contextual_memory", "adaptive_interaction",
                         "domain_specific_behaviors"),
        "constraints": ("bounded [0, 1] response targets", "no randomness"),
    },
    "enterprise_assistant": {
        "summary": "An enterprise-assistant persona: multi-agent coordination, "
                   "reasoned task planning, and domain behaviour over a "
                   "stable, monitored world model.",
        "capabilities": ("expressive_math_face", "world_stability",
                         "pattern_intelligence", "safety_monitoring",
                         "multi_agent_coordination", "cognitive_reasoning",
                         "contextual_memory"),
        "constraints": ("bounded task fusion", "deterministic plans"),
    },
})

_RECOGNIZED = "recognized_capability"


def _require_map(registry, name, what):
    if name not in registry:
        raise KeyError(f"{what} {name!r} is not registered")
    return registry[name]


def capability(name):
    """Return the declared entry for a capability slug (raises KeyError for
    unknown capabilities — Maya never guesses what it can do)."""
    return dict(_require_map(CAPABILITY_REGISTRY, name, "capability"))


def layer_for_capability(name):
    """The platform layer that owns a capability slug."""
    entry = _require_map(CAPABILITY_REGISTRY, name, "capability")
    return entry.get("layer", CORE_LAYER)


def capabilities_for_layer(layer):
    """Every capability slug owned by a layer, sorted deterministically.
    Raises ValueError for an unknown layer (Maya never guesses)."""
    if layer not in LAYERS:
        raise ValueError(
            f"unknown layer {layer!r} (expected one of {sorted(LAYERS)})")
    return tuple(sorted(
        slug for slug, entry in CAPABILITY_REGISTRY.items()
        if entry.get("layer", CORE_LAYER) == layer))


def role_summary(name):
    """Return the declared entry for a market-role slug (raises KeyError for
    unknown roles)."""
    return dict(_require_map(MARKET_ROLE_REGISTRY, name, "role"))


def capabilities_for_role(name):
    """The tuple of capability slugs a role deploys, each verified to exist
    in the capability registry."""
    entry = _require_map(MARKET_ROLE_REGISTRY, name, "role")
    for slug in entry["capabilities"]:
        if slug not in CAPABILITY_REGISTRY:
            raise KeyError(f"role {name!r} references unregistered "
                           f"capability {slug!r}")
    return tuple(entry["capabilities"])


def roles_for_capability(name):
    """Every market role that deploys the named capability, sorted
    deterministically."""
    capability(name)
    return tuple(sorted(
        role for role, entry in MARKET_ROLE_REGISTRY.items()
        if name in entry["capabilities"]))


def market_overview():
    """Deterministic capability-by-role coverage matrix:
    ``{capability: (roles, ...)}`` sorted by capability slug."""
    return {
        slug: roles_for_capability(slug)
        for slug in sorted(CAPABILITY_REGISTRY)
    }


def _self_check():
    """Import-time integrity: every role references only known capabilities
    and every capability is deployed by at least one role (nothing is
    declared dead weight)."""
    for slug in CAPABILITY_REGISTRY:
        if not roles_for_capability(slug):
            raise AssertionError(
                f"capability {slug!r} is deployed by no market role")
    for name in MARKET_ROLE_REGISTRY:
        capabilities_for_role(name)


_self_check()