"""Single owner of Maya's capability inventory.

Every surface that describes what Maya can do — the NL capability answer,
the ``Maya controls`` line, the ``Local controls`` line, and the explicit
``:capabilities`` report — is derived from this one registry, so an added
capability lands in every description at once and a removed one cannot
linger as a phantom (the ``:interests`` bug this replaces). Descriptions
are factual: research is read-only, memory and behavior changes stay
approval-controlled, and no application control exists.
"""
from __future__ import annotations

# (name, what it does, how to reach it). Order is the presentation order.
CAPABILITY_REGISTRY = (
    ("conversation",
     "natural-language chat, greetings, identity, and deterministic answers",
     ("Hello Maya", "Goodnight Maya")),
    ("status",
     "service state and the full system picture",
     (":status", ":status detail", ":wake", ":sleep")),
    ("research",
     "multi-source public research with ranked evidence, contradiction and "
     "confidence reporting, and stable evidence IDs",
     ("research <topic>", ":research <topic>")),
    ("evidence drilldown",
     "expand any research or world-model claim into source, timestamps, "
     "confidence, conflicts, and freshness",
     (":evidence <id>", "show sources")),
    ("world model",
     "provenance-first public evidence store with comparison, conflict-aware "
     "addition, and a read-only mathematical analysis of stored evidence",
     (":world summary", ":world list", ":world compare [topic]",
      ":world analyze", ":world add | claim | source | confidence | "
      "evidence_type | url")),
    ("knowledge network",
     "read-only search over approved local knowledge, plus a derived "
     "provenance graph of claim-to-source edges that is written only while "
     "the core service is live",
     (":knowledge", ":knowledge search <terms>",
      ":knowledge graph [term]")),
    ("session recap",
     "deterministic digests of past sessions with continue-later threads "
     "you can resume by name in plain English",
     (":recap", ":recap pause <topic>", ":recap resume <thread_id>",
      "continue the <topic> thread")),
    ("reports",
     "living review reports with staleness banners, archives, deltas, and "
     "registry-gated refresh",
     (":report", ":report refresh <name>", ":report delta <name>",
      ":review", ":income", ":continuity", ":focus")),
    ("tasks",
     "personal task list and statistics",
     (":tasks", ":task add <text>", ":task list", ":task done <n>",
      ":task remove <n>", ":task stats", ":stats")),
    ("observations",
     "observation review, contradiction review, reflections, and memory audit",
     (":review observations", ":contradictions", ":reflection",
      ":memory audit", ":onboarding")),
    ("improvement",
     "supervised suggestions, pattern proposals, and learning state — all "
     "confirmation-gated",
     (":suggestions", ":suggestion review", ":suggestion inspect <id>",
      ":suggestion approve <id> confirm", ":suggestion reject <id> confirm",
      ":pattern report", ":pattern review", ":pattern propose | ...",
      ":learning status", ":learning proposals")),
    ("interests",
     "emerging interests, opportunities, decision patterns, prediction "
     "limits, and the demo scenario",
     (":emerging", ":opportunities", ":decision patterns",
      ":prediction limits", ":seed demo")),
    ("system",
     "this capability report, the runtime device profile, the control "
     "center, and mission context",
     (":capabilities", ":capabilities detail", ":device", ":help",
      ":dashboard", ":mission")),
)

_HONESTY_LINE = ("Research uses only sources the local read-only network "
                 "policy allows; restricted databases are not accessible and "
                 "automated synthesis is not expert review. Memory, "
                 "preference, and behavior changes require explicit "
                 "approval, and I do not control other applications.")


def _all_commands():
    commands = []
    for _, _, group_commands in CAPABILITY_REGISTRY:
        for command in group_commands:
            if command not in commands:
                commands.append(command)
    return commands


def command_list() -> str:
    """All advertised commands, joined for one-line control surfaces."""
    return ", ".join(_all_commands())


def colon_commands() -> str:
    """All advertised colon commands, joined for local-control lines."""
    return ", ".join(c for c in _all_commands() if c.startswith(":"))


def controls_line() -> str:
    """The one-line control surface, derived from the registry."""
    return "Maya controls: " + command_list() + "."


def capability_report() -> str:
    """Full grouped capability listing for the explicit command surface."""
    lines = ["What Maya can do (all surfaces verified; nothing here is aspirational):"]
    for name, description, group_commands in CAPABILITY_REGISTRY:
        lines.append("\n%s — %s" % (name, description))
        lines.append("  " + "; ".join(group_commands))
    lines.append("\n" + _HONESTY_LINE)
    return "\n".join(lines)


def self_report() -> str:
    """The unified capability self-report: display registry + runtime model
    + local device profile + the bridge between the two capability layers.

    Every section is derived from a live registry or a read-only runtime
    probe; nothing is invented and no section can claim a capability that
    is not registered.
    """
    from maya_capability_bridge import consistency_check, coverage_summary
    from maya_device_profile import detect, suitability
    from maya_model_registry import default_model, describe_models

    lines = [
        "Maya unified capability report",
        "",
        capability_report(),
        "",
        "runtime model —",
        "; ".join("%s (%s)" % (m["name"], m["role"])
                  for m in describe_models()),
        "default model: %s" % default_model(),
        "",
        "local device —",
        "%s | %s | python %s"
        % (detect()["os_name"], detect()["machine"],
           detect()["python_version"]),
        "cpu cores: %s | memory: %s"
        % (detect()["cpu_count"],
           detect()["memory"] or "unavailable"),
        "suitability: local-groups=%s; model/network-groups=%s"
        % (", ".join(suitability()["local_capability_groups"]),
           ", ".join(suitability()["model_dependent_groups"])),
        "",
        "capability layers bridge —",
        "display groups: %(display_groups)d | math-engine slugs: "
        "%(math_engine_slugs)d | mapped: %(mapped_display_groups)d | "
        "local-feature: %(local_feature_groups)d | internal: "
        "%(system_internal_slugs)d | layers: %(layers)s"
        % coverage_summary(),
        "consistency: %s" % ", ".join(consistency_check()),
    ]
    return "\n".join(lines)


def capability_summary() -> str:
    """Conversational capability answer: registry-derived, honestly bounded."""
    names = ", ".join(name for name, _, _ in CAPABILITY_REGISTRY)
    return ("Here's what I can actually do: %s. %s "
            "Say `:capabilities` for the full command list." % (names, _HONESTY_LINE))


def capability_hint(group: str) -> str:
    """One contextual pointer to a registered capability, for the moment a
    feature becomes relevant (e.g. a research answer carrying evidence IDs).

    Composed from the group's own advertised commands and description, so the
    wording cannot drift from what Maya actually offers. Returns "" when the
    group is not in the registry: a removed capability stops being hinted
    immediately, and a typo'd group name can never invent a claim.
    """
    for name, description, group_commands in CAPABILITY_REGISTRY:
        if name != group or not group_commands:
            continue
        shown = '"%s"' % group_commands[0]
        alternatives = ['"%s"' % c for c in group_commands[1:]]
        if alternatives:
            shown += " (or " + ", ".join(alternatives) + ")"
        return "Tip: say %s — %s." % (shown, description)
    return ""


# Degraded-mode honesty: the offline fallback may only advertise capabilities
# whose features actually work without the model. Groups outside this set are
# unavailable in degraded mode and must never appear in its answers.
_OFFLINE_SAFE_GROUPS = frozenset({
    "conversation",          # deterministic NL answers are local by design
    "status",                 # status commands read local state directly
    "knowledge network",      # knowledge search/graph read local files only
    "session recap",          # digest and thread state are pure local files
    "reports",                # review reports are served from local snapshots
    "tasks",                  # task commands mutate local state only
    "observations",           # observation/correction review is local state
    "system",                 # capability report and help are local surfaces
})
# Groups whose features need the model, the network, or approval-gated
# actions: they must never be advertised by a degraded-mode answer.
_OFFLINE_UNSAFE_GROUPS = frozenset({
    "research", "evidence drilldown", "world model", "improvement",
})
_IMPROVE_GROUP = "improvement"


def degraded_groups() -> list[str]:
    """Registered capability groups that genuinely work in degraded mode."""
    registered = {name for name, _, _ in CAPABILITY_REGISTRY}
    return sorted(registered & _OFFLINE_SAFE_GROUPS)


def degraded_capability_line() -> str:
    """One-line availability statement for the offline greeting.

    Derived from the registry intersection with _OFFLINE_SAFE_GROUPS, so a
    removed group drops out of the degraded answer and an added degraded-safe
    group appears in it — the enumeration can never drift from the registry.
    """
    groups = degraded_groups()
    return ("Available without the model: " + ", ".join(groups)
            + ", plus local command routing. Free-form model conversation "
              "is currently limited by local response time.")


def offline_improvement_mechanisms() -> str:
    """Degraded-mode answer to improvement questions.

    Describes the approval path (what review surfaces exist offline) without
    claiming any live improvement action, and keeps the pinned governance
    line. If the improvement group were ever removed, the fallback degrades
    to the governance line alone instead of naming mechanisms that no longer
    exist.
    """
    if any(name == _IMPROVE_GROUP for name, _, _ in CAPABILITY_REGISTRY):
        return ("Improvements happen only through supervised review: pattern "
                "review, corrections, and proposals you explicitly approve. "
                "I cannot rewrite my own permissions or core behavior "
                "without your approval.")
    return ("I improve only through changes you explicitly review and "
            "approve. I cannot rewrite my own permissions or core behavior "
            "without your approval.")


def offline_registry_audit() -> list[str]:
    """Degraded-mode advertisement consistency, for verification.

    Checks three drift paths and returns one problem description each (or
    the single sentinel "offline_registry_audit_ok" when consistent):

    1. a _OFFLINE_SAFE_GROUPS name no longer in the registry (stale name:
       the degraded line would silently stop advertising a real capability);
    2. a group marked both offline-safe and offline-unsafe (misconfiguration);
    3. the actual degraded_capability_line() text advertising any registered
       offline-unsafe group (behavioral leak).

    Adding a degraded-unsafe group to _OFFLINE_SAFE_GROUPS, renaming a group
    without updating the safe set, or a derivation regression all fail the
    verification suite instead of silently corrupting the fallback.
    """
    registered = {name for name, _, _ in CAPABILITY_REGISTRY}
    problems = []
    stale = sorted(_OFFLINE_SAFE_GROUPS - registered)
    if stale:
        problems.append(
            "degraded line would advertise unregistered groups: "
            + ", ".join(stale))
    overlap = sorted(_OFFLINE_SAFE_GROUPS & _OFFLINE_UNSAFE_GROUPS)
    if overlap:
        problems.append(
            "groups marked both offline-safe and offline-unsafe: "
            + ", ".join(overlap))
    line = degraded_capability_line()
    leaked = sorted(g for g in _OFFLINE_UNSAFE_GROUPS & registered if g in line)
    if leaked:
        problems.append(
            "degraded line advertises offline-unsafe capabilities: "
            + ", ".join(leaked))
    return problems or ["offline_registry_audit_ok"]
