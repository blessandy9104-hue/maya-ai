"""Language generation: speech is derived only from the meaning vector.

The utterance is selected deterministically from a fixed, persona-neutral
vocabulary by quantizing the meaning components. Raw input never reaches
this module; the only input is the meaning produced by the stabilized
loop, so restriction "produces reserved, brief output instead of
elaborating on uncertain states."
"""
from __future__ import annotations

from .feature_map import _neutral

_STEM_BY_BUCKET = {
    0: "neutral",
    1: "cautious",
    2: "steady",
    3: "assured",
}

_STEM_TEXT = {
    "neutral": "I have no signal to report.",
    "cautious": "I would verify this before acting.",
    "steady": "State is stable; here is what I observed.",
    "assured": "I am confident in this reading.",
}


def _bucket(value, width=0.25):
    v = _neutral(value)
    index = min(int(v / width), 3)
    return _STEM_BY_BUCKET.get(index, "neutral")


class LanguageEngine:
    """Deterministic, meaning-only utterance generation."""

    def generate(self, meaning=None, register=None):
        meaning = meaning or {}
        scalar = _neutral(meaning.get("meaning_scalar", 0.0))
        stability = _neutral(meaning.get("stability", 0.0))
        bucket = _bucket(scalar)
        stem = _STEM_TEXT[bucket]
        if not meaning.get("ok", False):
            stem = "I am holding this frame until it stabilizes."
        elif stability < 0.5:
            stem = stem + " (I am watching drift, so I am keeping it short.)"
        tone = "reserved" if scalar < 0.5 else "measured"
        return {
            "text": stem,
            "tone": tone,
            "register": register if register is not None else tone,
            "bucket": bucket,
            "meaning_scalar": scalar,
            "meaning_sha": _meaning_fingerprint(meaning),
        }


def _meaning_fingerprint(meaning):
    vector = meaning.get("meaning_vector") or ()
    if isinstance(vector, (list, tuple)) and vector:
        quantized = "".join("%.2f" % _neutral(v) for v in vector)
    else:
        quantized = "%.2f" % _neutral(meaning.get("meaning_scalar", 0.0))
    return "m-" + quantized.replace(".", "")


LANGUAGE = LanguageEngine()


def generate(*args, **kwargs):
    return LANGUAGE.generate(*args, **kwargs)