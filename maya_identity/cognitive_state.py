"""Maya Cognitive State Layer.

Bridges the Intelligence Core and the Identity Presentation / Visual Interface
layers through a defined state interface only.

Responsibilities:
- accept state signals from Maya's core (presence, activity, learning,
  conversation, processing, research, resource)
- coerce them into a small validated set of visual states
  (awake / processing / listening / research / sleeping / offline)
- expose the resulting presentation state to the visual layer

Guarantees:
- this layer never executes commands, touches memory, security, or permissions.
- it cannot influence Maya's intelligence.
- if the visual layer is absent, the core keeps functioning (state slot just goes
  unused). If the core is absent, the visual layer defaults to "sleeping".
"""
from __future__ import annotations

from .animation import ALLOWED as _ALLOWED

VISUAL_LABELS = {
    "awake": "presence · awake · aware",
    "processing": "presence · processing · focused",
    "listening": "presence · listening · attentive",
    "research": "presence · research · analytical",
    "sleeping": "presence · sleeping · dormant",
    "offline": "presence · offline · inactive",
}


def resolve_visual_state(
    service: str = "sleeping",
    learning: str = "off",
    presence: str = "off",
    processing: bool = False,
    listening: bool = False,
    research: bool = False,
) -> str:
    if service == "offline":
        return "offline"
    if processing:
        return "processing"
    if research:
        return "research"
    if listening:
        return "listening"
    if service == "awake":
        return "awake"
    return "sleeping"


def normalize_visual_state(state: str) -> str:
    if state in _ALLOWED:
        return state
    return "sleeping"


def build_state_signal(**core_signals) -> dict:
    visual = resolve_visual_state(
        service=core_signals.get("service", "sleeping"),
        learning=core_signals.get("learning", "off"),
        presence=core_signals.get("presence", "off"),
        processing=bool(core_signals.get("processing", False)),
        listening=bool(core_signals.get("listening", False)),
        research=bool(core_signals.get("research", False)),
    )
    return {
        "visual_state": visual,
        "visual_label": VISUAL_LABELS.get(visual, VISUAL_LABELS["sleeping"]),
        "presence_state": core_signals.get("service", "sleeping"),
        "activity_state": core_signals.get("activity", "idle"),
        "learning_state": core_signals.get("learning", "off"),
        "conversation_state": core_signals.get("conversation", "idle"),
        "resources": core_signals.get("resources", "unavailable"),
    }


def apply(core_signals: dict) -> dict:
    signal = build_state_signal(**core_signals)
    signal["layer"] = "cognitive_state"
    signal["result"] = "visual_state_set"
    signal["visual_state"] = normalize_visual_state(signal["visual_state"])
    return signal