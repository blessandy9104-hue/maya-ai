"""Speech/viseme adapter — drives mouth and jaw from speech signals.

Provides a procedural speaking animation when no real audio is available,
and converts named visemes into bounded mouth-shape deltas. All outputs are
clamped to 0.0–1.0. Viseme state changes are pattern-driven state changes:
they converge through ``exp_smooth`` computed by the Math Coordination Agent
(:meth:`MathAgent.pattern_state`), never through raw increments.
"""
from __future__ import annotations

from .interp import clamp01, clamp
from .rig_math import wave01, oscillate, lerp
from .math_coordinator import MATH_AGENT

VISEMES = {
    "REST":    {"open": 0.02, "spread": 0.0, "round": 0.0},
    "CLOSED":  {"open": 0.00, "spread": 0.05, "round": 0.0},
    "OPEN":    {"open": 0.52, "spread": 0.05, "round": 0.0},
    "WIDE":    {"open": 0.28, "spread": 0.12, "round": 0.0},
    "NARROW":  {"open": 0.14, "spread": 0.0,  "round": 0.08},
    "ROUND":   {"open": 0.32, "spread": 0.0,  "round": 0.14},
}

_PROC_OPEN_SEQ = [
    (0.08, 0.36, 0.30), (0.20, 0.48, 0.44), (0.42, 0.55, 0.52),
    (0.58, 0.42, 0.38), (0.72, 0.50, 0.48), (0.88, 0.32, 0.28),
    (1.00, 0.08, 0.06),
]


class SpeechAdapter:
    """Stateful adapter: smooths viseme/procedural transitions."""

    def __init__(self, alpha=0.40):
        self._alpha = alpha
        self._phase = 0.0
        self._open = 0.0
        self._spread = 0.0
        self._round = 0.0
        self._speak_level = 0.0
        self._cycle_speed = 3.8

    def drive(self, viseme=None, amplitude=None, speaking=None, dt=1.0,
              elapsed=None):
        """Produce bounded speech deltas from inputs.

        Returns dict with speaking, voice_intensity, open, spread, round.
        """
        speaking = clamp01(speaking) if speaking is not None else 0.0
        amplitude = clamp01(amplitude) if amplitude is not None else 0.0
        if elapsed is None:
            elapsed = self._phase
        self._phase += dt * 0.02

        if viseme and isinstance(viseme, str):
            viseme_key = viseme.strip().upper()
            vd = VISEMES.get(viseme_key, VISEMES["REST"])
            tgt_open = vd["open"] * speaking
            tgt_spread = vd["spread"]
            tgt_round = vd["round"]
            tgt_speak = speaking
        elif amplitude > 0.01 or speaking > 0.05:
            a = self._phase * self._cycle_speed
            base_open = _interpolate_procedural(a % 1.0) * speaking
            pulse = oscillate(a * 2.7, 0.0, amplitude * 0.18)
            tgt_open = clamp01(base_open + pulse)
            tgt_spread = clamp01(0.02 + amplitude * 0.06)
            tgt_round = clamp01(amplitude * 0.08 * wave01(a * 1.9))
            tgt_speak = clamp01(speaking * 0.5 + amplitude * 0.5)
        else:
            tgt_open = 0.0
            tgt_spread = 0.0
            tgt_round = 0.0
            tgt_speak = 0.0

        a = self._alpha
        self._open = MATH_AGENT.pattern_state(self._open, tgt_open, a)
        self._spread = MATH_AGENT.pattern_state(self._spread, tgt_spread, a)
        self._round = MATH_AGENT.pattern_state(self._round, tgt_round, a)
        self._speak_level = MATH_AGENT.pattern_state(self._speak_level, tgt_speak, a)

        return {
            "speaking": clamp01(self._speak_level),
            "voice_intensity": clamp01(self._speak_level * 0.9 + amplitude * 0.1),
            "open": clamp01(self._open),
            "spread": clamp01(self._spread),
            "round": clamp01(self._round),
        }


def _interpolate_procedural(t):
    t = clamp01(t)
    for i in range(len(_PROC_OPEN_SEQ) - 1):
        t0, v0, _ = _PROC_OPEN_SEQ[i]
        t1, v1, _ = _PROC_OPEN_SEQ[i + 1]
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return lerp(v0, v1, u)
    return _PROC_OPEN_SEQ[-1][1]