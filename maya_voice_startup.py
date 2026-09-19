"""Voice-startup preparation for Maya.

This module deliberately does not access a microphone or run continuously.
Future speech recognition should call prepare_voice_command() and route only
approved wake actions through the existing launcher and safety walls.
"""
from __future__ import annotations

VOICE_LISTENING_ENABLED = False
WAKE_PHRASES = ("hello maya", "maya wake", "wake maya")
PRIVILEGED_ACTIONS_REQUIRE_CONFIRMATION = True


def prepare_voice_command(transcript: str) -> dict[str, object]:
    text = " ".join(transcript.lower().strip().split())
    matched = next((phrase for phrase in WAKE_PHRASES if text == phrase), None)
    return {
        "enabled": VOICE_LISTENING_ENABLED,
        "transcript_received": bool(text),
        "wake_phrase_matched": matched,
        "action": "wake_and_launch" if matched else "none",
        "microphone_started": False,
        "privileged_action_allowed": False,
        "requires_explicit_confirmation": PRIVILEGED_ACTIONS_REQUIRE_CONFIRMATION,
        "note": "Preparation only; microphone listening remains disabled.",
    }


def status() -> dict[str, object]:
    return {
        "voice_startup_prepared": True,
        "microphone_listening_enabled": VOICE_LISTENING_ENABLED,
        "wake_phrases": list(WAKE_PHRASES),
        "privileged_actions_require_confirmation": PRIVILEGED_ACTIONS_REQUIRE_CONFIRMATION,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(status(), indent=2))
