"""Visual nervous system — converts cognitive signals into visual responses.

Cognitive Event -> Visual Interpretation -> Expression / Geometry Transformation

Read-only: interprets bounded signals and returns a visual command dict. It
cannot execute commands, access private data, modify memory, or change any
identity file.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..identity import load_engine_config
from ..wireframe.math_coordinator import MATH_AGENT

_FALLBACK_ACTIVITY = "idle"

# Pattern-driven visual fields are interpreted state changes. When a bounded
# response pattern contributes a value, it is merged into the live signal as
# an exponential-smoothing state change (via the Math Coordination Agent) so
# the visual state converges to the pattern baseline without a hard jump,
# overshoot, or raw ``max`` comparison. All outputs stay on the canonical
# [0, 1] domain.
PATTERN_MERGE_ALPHA = 0.5


class VisualInterpreter:
    """Maps cognitive signals to visual command fields (all bounded 0..1)."""

    def __init__(self, mapping=None, patterns=None):
        self.mapping = mapping if mapping is not None else load_engine_config("nervous_mapping")
        self.patterns = patterns if patterns is not None else load_engine_config("nervous_patterns")

    @staticmethod
    def _clip(value, lo=0.0, hi=1.0):
        try:
            return max(lo, min(hi, float(value)))
        except (TypeError, ValueError):
            return lo

    def _activity(self, signals):
        key = self.mapping.get("activity_key", "activity")
        value = signals.get(key, _FALLBACK_ACTIVITY)
        if value is None:
            return _FALLBACK_ACTIVITY
        text = str(value).strip().lower()
        return text if text else _FALLBACK_ACTIVITY

    def _pattern(self, activity):
        table = self.patterns.get("patterns", {})
        candidate = table.get(activity) or table.get(self.patterns.get("default")) or {}
        return candidate or {}

    def interpret(self, signals=None) -> dict:
        signals = signals or {}
        inputs = self.mapping.get("inputs", {})
        fallback = self.mapping.get("fallback", {})

        values = {}
        for key, cfg in inputs.items():
            if key in signals and signals[key] is not None:
                values[key] = self._clip(signals[key])

        activity = self._activity(signals)
        pattern = self._pattern(activity)

        out = {}
        for field in ("eye_focus", "neural_activity", "particle_density",
                      "glow_intensity", "micro", "breath", "distortion"):
            acc, weight = 0.0, 0.0
            for key, cfg in inputs.items():
                if cfg.get("target") == field:
                    w = float(cfg.get("weight", 1.0))
                    b = float(cfg.get("bias", 0.0))
                    if key in values:
                        # weighted evidence, bounded on the live signal value
                        acc += MATH_AGENT.control(values[key]) * w + b
                        weight += w
            baseline = float(pattern.get(field, fallback.get(field, 0.0)))
            if weight > 0:
                # blend the bounded weighted evidence with the pattern
                # baseline as a stable state change (no raw jump)
                current = self._clip(acc / weight)
                out[field] = MATH_AGENT.pattern_state(current, baseline,
                                                      PATTERN_MERGE_ALPHA)
            else:
                out[field] = baseline
            out[field] = self._clip(out[field])

        out["symbol_mode"] = pattern.get("symbol_mode") or fallback.get("symbol_mode", "none")
        out["gaze_x"] = self._clip(signals.get("gaze_x", 0.0), -1.0, 1.0)
        gy = signals.get("gaze_y", 0.0)
        out["gaze_y"] = self._clip(gy if gy is not None else 0.0, -1.0, 1.0)
        out["activity"] = activity
        out["source"] = "visual_interpreter"
        return out


if __name__ == "__main__":
    import json as _json
    sample = {"attention": 0.8, "curiosity": 0.7, "confidence": 0.9, "activity": "solving"}
    print(_json.dumps(VisualInterpreter().interpret(sample), indent=2))