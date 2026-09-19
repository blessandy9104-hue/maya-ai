"""Persona expression and behavior rules per registered persona."""

PERSONA_RULES = {
    "calm": {
        "amplitude": "low",
        "max_step": 0.05,
        "micro_energy": "quiet",
        "gesture": "small",
        "allowed_gestures": ("nod", "soft_wave", "idle"),
        "banned": ("fast_gesture", "theatrical_motion", "jovial_emote"),
    },
    "warm": {
        "amplitude": "mid",
        "max_step": 0.06,
        "micro_energy": "soft",
        "gesture": "warm_closed",
        "allowed_gestures": ("nod", "open_palm", "lean_in", "idle"),
        "banned": ("theatrical_motion", "exaggerated_motion"),
    },
    "authoritative": {
        "amplitude": "firm",
        "max_step": 0.04,
        "micro_energy": "flat",
        "gesture": "hands_down",
        "allowed_gestures": ("nod", "hold", "idle"),
        "banned": ("playful_emote", "jovial_emote"),
    },
    "playful": {
        "amplitude": "high",
        "max_step": 0.07,
        "micro_energy": "lively",
        "gesture": "animated",
        "allowed_gestures": ("pop", "spin", "smile_wave", "grin", "idle"),
        "banned": (),
    },
}


def rules_for(persona):
    """Return the frozen rule dict for a persona id; unknown ids raise ValueError."""
    if persona not in PERSONA_RULES:
        raise ValueError("unknown persona: %s" % persona)
    return PERSONA_RULES[persona]


def max_step_for(persona):
    """Persona-gated maximum per-frame channel step."""
    return rules_for(persona)["max_step"]


def allowed_gestures_for(persona):
    """Tuple of gesture tokens a persona may use."""
    return rules_for(persona)["allowed_gestures"]


def validate_rules():
    """Registry-level invariants over persona rules."""
    for persona, rule in PERSONA_RULES.items():
        if not (0.0 < rule["max_step"] <= 0.07):
            raise ValueError("invalid max_step for persona: %s" % persona)
        if not rule["allowed_gestures"]:
            raise ValueError("empty allowed gestures for persona: %s" % persona)