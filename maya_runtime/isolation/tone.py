"""Tone sealing: tone-profile constraints stay under the persona ceiling.

Tone is an interior governor over channel targets; it can never raise a
channel above the bound persona ceiling.
"""
from __future__ import annotations

from .ceilings import within_channel


class ToneSeal:
    __slots__ = ("tone_id", "profile")

    def __init__(self, tone_id, profile):
        if profile is not None and not isinstance(profile, dict):
            raise TypeError("tone profile must be a dict")
        self.tone_id = tone_id
        self.profile = dict(profile or {})

    def allows_channels(self, ceiling, channels):
        return within_channel(ceiling, channels) and within_channel(self.profile, channels)

    def verify(self):
        return {
            "tone_id": self.tone_id,
            "profile": dict(self.profile),
        }