"""capabilities.py — legacy compatibility surface (derived, read-only).

The single source of truth for what Maya can and cannot do is
``maya_capabilities.py`` (its ``CAPABILITY_REGISTRY``); every live surface
reads from that registry. This module no longer keeps its own inventory —
it derives the historical ``CAPABILITIES`` list straight from the registry
so a second, drift-prone registry cannot exist. The three fixed
"not available" entries are genuine structural limits (no arbitrary
browsing, no screen/file access outside the project, no self-modification).

A pinned verification test re-derives this module from the registry, so if
the registry ever changes, this surface changes with it or the suite fails.
"""
from __future__ import annotations

from maya_capabilities import CAPABILITY_REGISTRY

_NOT_AVAILABLE = (
    ("Unrestricted web browsing",
     "I cannot browse arbitrary websites, log in, post, purchase, or send "
     "messages."),
    ("Screen or file access",
     "I do not have access to your screen, camera, microphone, or files "
     "outside this project folder."),
    ("Self-modification",
     "I cannot change or activate my own code without your explicit review "
     "and approval."),
)


def _derived_available():
    items = []
    for name, description, commands in CAPABILITY_REGISTRY:
        items.append({
            "name": name.title(),
            "available": True,
            "description": description,
            "commands": list(commands),
        })
    return items


def _derived():
    items = _derived_available()
    for name, description in _NOT_AVAILABLE:
        items.append({
            "name": name,
            "available": False,
            "description": description,
            "commands": [],
        })
    return items


CAPABILITIES = _derived()


def available_capabilities():
    return [c for c in CAPABILITIES if c["available"]]


def unavailable_capabilities():
    return [c for c in CAPABILITIES if not c["available"]]


def capabilities_summary_text():
    """Human-readable summary for Maya to speak aloud."""
    lines = ["Here is what I can actually do right now:"]
    for c in available_capabilities():
        lines.append("- %s: %s" % (c["name"], c["description"]))

    lines.append("")
    lines.append("Here is what I cannot do yet:")
    for c in unavailable_capabilities():
        lines.append("- %s: %s" % (c["name"], c["description"]))

    return "\n".join(lines)


def capabilities_prompt_text():
    """Compact version for the AI model's system prompt."""
    parts = []
    for c in CAPABILITIES:
        status = "AVAILABLE" if c["available"] else "NOT AVAILABLE"
        parts.append("- %s [%s]: %s" % (c["name"], status, c["description"]))
    return "\n".join(parts)