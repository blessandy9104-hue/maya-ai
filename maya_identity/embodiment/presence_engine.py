"""Presence engine — the coordinator of Maya's visual embodiment.

Composes the nervous system response, attention model, environment awareness,
and (disabled) voice sync into a single read-only visual command for the
procedural renderer. It represents state only — it creates no intelligence.
"""
from __future__ import annotations

from ..awareness import AwarenessState
from ..nervous_system import VisualInterpreter
from ..voice_sync import VoiceMapper
from ..visual_language import SymbolComposer
from ..wireframe.math_coordinator import MATH_AGENT
from ..wireframe import presentation_math as PresentationMath
from .attention_model import AttentionModel

# Pattern-derived visual fields (interpreter response, voice shape, awareness
# contribution) are interpreted state changes. They merge through the Math
# Coordination Agent as exponential-smoothing state changes
# (``pattern_state``, i.e. ``exp_smooth``) so richer signals pull the visual
# state toward them without a raw ``max`` jump or an unbounded transition.
# All fields stay on the canonical [0, 1] domain.
PRESENCE_MERGE_ALPHA = 0.5


class PresenceEngine:
    def __init__(self, interpreter=None, attention=None, awareness=None,
                 voice=None, composer=None):
        self.interpreter = interpreter if interpreter is not None else VisualInterpreter()
        self.attention = attention if attention is not None else AttentionModel()
        self.awareness = awareness if awareness is not None else AwarenessState()
        self.voice = voice if voice is not None else VoiceMapper()
        self.composer = composer if composer is not None else SymbolComposer()
        self._step = 0

    def feed(self, signals: dict) -> dict:
        """Accept safe read-only awareness signals only (allowlist enforced)."""
        return self.awareness.update(signals or {})

    def tick(self, visual_state=None, signals=None, step=1.0, persona=None) -> dict:
        signals = signals or {}
        # Optional Batch #7 persona bridge (off by default, additive).
        # Runs only when a FusedPersonaState is supplied; NO_ACTIVE_PERSONA and
        # unresolved conflicts surface as a no-op (identity-locked neutrality).
        if persona is not None:
            from maya_runtime.intelligence.visual_bridge import (
                merged_interpreter_inputs as _merge_interpreter,
            )

            signals = _merge_interpreter(signals, persona)
        self._step += step

        response = self.interpreter.interpret(signals)

        # attention from gaze signals or awareness contribution
        gx, gy = response.get("gaze_x", 0.0), response.get("gaze_y", 0.0)
        focus = PresentationMath.gaze_focus(gx, gy)
        attention = self.attention.update(x=focus[0], y=focus[1],
                                          intensity=response.get("eye_focus"))
        att_snap = attention["intensity"]

        contrib = self.awareness.contribution()
        alpha = PRESENCE_MERGE_ALPHA
        if contrib.get("attention") is not None:
            att_snap = MATH_AGENT.pattern_state(att_snap,
                                                contrib["attention"], alpha)
        if contrib.get("interaction_timing") is not None:
            att_snap = MATH_AGENT.pattern_state(
                att_snap, PresentationMath.scale(contrib["interaction_timing"], 0.5), alpha)

        voice = self.voice.map_voice(
            volume=signals.get("volume", 0.0),
            rhythm=signals.get("rhythm", 0.0),
            pause=signals.get("pause", 0.0),
            emphasis=signals.get("emphasis", 0.0),
        )

        g = attention["gaze_x"]
        gy_scan = attention["gaze_y"]
        command = {
            "eye_focus": PresentationMath.clip(MATH_AGENT.pattern_state(
                response.get("eye_focus", 0.0), att_snap, alpha),
                on_error=0.0),
            "neural_activity": PresentationMath.clip(MATH_AGENT.pattern_state(
                response.get("neural_activity", 0.0),
                voice.get("neural_activity", 0.0), alpha),
                on_error=0.0),
            "particle_density": response.get("particle_density", 0.4),
            "glow_intensity": PresentationMath.clip(MATH_AGENT.pattern_state(
                response.get("glow_intensity", 0.0),
                voice.get("glow_intensity", 0.0), alpha),
                on_error=0.0),
            "micro": response.get("micro", 0.0),
            "breath": response.get("breath", 0.4),
            "distortion": response.get("distortion", 0.0),
            "gaze_x": PresentationMath.clip(
                PresentationMath.scale(g, 0.5), -1.0, 1.0, on_error=-1.0),
            "gaze_y": PresentationMath.clip(
                PresentationMath.scale(gy_scan, 0.5), -1.0, 1.0, on_error=-1.0),
            "symbol_mode": self.composer.mode_for(response.get("activity", visual_state or "idle")),
            "voice_linked": bool(voice.get("voice_linked")),
            "step": int(self._step),
            "source": "presence_engine",
        }
        return command


if __name__ == "__main__":
    import json as _json
    engine = PresenceEngine()
    cmd = engine.tick(visual_state="processing",
                      signals={"attention": 0.8, "curiosity": 0.7,
                               "confidence": 0.9, "activity": "solving"})
    print(_json.dumps(cmd, indent=2))