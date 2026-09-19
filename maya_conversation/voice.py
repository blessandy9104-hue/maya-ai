"""Voice modality adapters (Batch 8G) — interface contracts only.

Honesty invariant (directive section 16-17): STT and TTS here are
*interfaces only*. Neither the engine, nor the audio capture path, nor
synthesis output is implemented. ``available()`` returns False, ``speak()``
and ``transcribe()`` are contract stubs, and ``describe()`` always states
``implemented=False``. There is deliberately no fallback that pretends to
"hear" or "speak".

Purpose of this module in the architecture: give the shared semantic pathway a
stable seam. A future real STT provider producing a :class:`TranscribedTurn`
with ``final=True`` drops that transcript into the exact same interpretation
pipeline as typed text — that is the text/voice parity mechanism, and it is
exercised by the verification suite today via pure factory objects.
"""
from __future__ import annotations

import dataclasses

TTS_STATUS = "INTERFACE ONLY"
STT_STATUS = "INTERFACE ONLY"


@dataclasses.dataclass
class TranscribedTurn:
    """Carrier for an STT-produced turn (final or partial).

    ``final`` must be True before the turn is routed: partial transcripts are
    never treated as completed user input. ``segments`` carries per-segment
    words + confidences when a provider supplies them (opt-in, never assumed).
    """
    text: str
    final: bool
    confidence: float = 1.0
    engine: str = "interface-only"
    segments: tuple = ()  # optional per-segment ("word", confidence)

    def is_routable(self) -> bool:
        """A turn is routable only when it is final and non-empty."""
        return self.final and bool(self.text and self.text.strip())


class SttProvider:
    """Speech-to-text adapter contract. NOT implemented beyond the contract."""

    name = "SttProvider"
    status = STT_STATUS

    def __init__(self, engine=None, device_index=None, sample_rate=None):
        self.engine = engine
        self.device_index = device_index
        self.sample_rate = sample_rate

    def available(self) -> bool:
        """No microphone path, no engine -> never available."""
        return False

    def transcribe(self, audio_or_path):
        """Contract stub. Raises NotImplementedError (no engine exists)."""
        raise NotImplementedError(
            "STT is interface-only in this build; no engine is implemented.")

    def listen_once(self, timeout_s=None):
        """Contract stub; returns None — no capture is attempted."""
        return None

    def start_streaming(self, callback):
        raise NotImplementedError("STT streaming is interface-only.")

    def stop_streaming(self):
        return None

    def describe(self) -> dict:
        return {
            "implemented": False,
            "status": STT_STATUS,
            "engine": self.engine,
            "device_index": self.device_index,
            "sample_rate": self.sample_rate,
        }


class TtsProvider:
    """Text-to-speech adapter contract. NOT implemented beyond the contract."""

    name = "TtsProvider"
    status = TTS_STATUS

    def __init__(self, engine=None, voice=None, rate_wpm=170, volume=1.0):
        self.engine = engine
        self.voice = voice
        self.rate_wpm = rate_wpm
        self.volume = volume

    def available(self) -> bool:
        return False

    def speak(self, text):
        """Contract stub. Raises NotImplementedError (no engine exists)."""
        raise NotImplementedError(
            "TTS is interface-only in this build; no engine is implemented.")

    def supported_voices(self):
        return []

    def describe(self) -> dict:
        return {
            "implemented": False,
            "status": TTS_STATUS,
            "engine": self.engine,
            "voice": self.voice,
            "rate_wpm": self.rate_wpm,
            "volume": self.volume,
        }


def build_voice_adapters(*, engine=None, voice=None):
    """Factory returning ``(SttProvider, TtsProvider)`` — both interface-only."""
    return SttProvider(engine=engine), TtsProvider(engine=engine, voice=voice)


def status_banner() -> str:
    return "voice: STT interface only; TTS interface only (no audio engine)"