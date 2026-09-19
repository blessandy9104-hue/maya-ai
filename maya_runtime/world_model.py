"""Maya Runtime: world model facade -- deterministic, device-neutral.

Pure delegation to the canonical ``MATH_AGENT`` world-* methods. No RNG, no
wall-clock, no GPU. Every output is finite and confined to the world domain.
"""
from __future__ import annotations

from .core import MATH_AGENT, WORLD_DOMAIN, WORLD_STATE_PATTERNS


class WorldModel:
    """Read-only, stateless gateway to the world model algebra."""

    domain = WORLD_DOMAIN
    patterns = WORLD_STATE_PATTERNS

    def stability(self, series, lo=None, hi=None, max_std=0.05):
        return MATH_AGENT.world_stability(series, lo=lo, hi=hi, max_std=max_std)

    def drift(self, series, alpha=0.03, tolerance=0.35, lo=None, hi=None):
        return MATH_AGENT.world_drift(series, alpha=alpha, tolerance=tolerance, lo=lo, hi=hi)

    def coherence(self, observed, equilibrium=None, floor=0.6):
        return MATH_AGENT.world_coherence(observed, equilibrium=equilibrium, floor=floor)

    def classify(self, vector, floor=0.6):
        return MATH_AGENT.world_classify(vector, floor=floor)

    def evaluate(self, vector, floor=0.6):
        return MATH_AGENT.world_evaluate(vector, floor=floor)

    def predict(self, predicted, expected, alpha=0.5, floor=0.6):
        return MATH_AGENT.world_predict(predicted, expected, alpha=alpha, floor=floor)

    def normalize(self, vector):
        return MATH_AGENT.world_normalize(vector)

    def index(self, value, ceiling):
        return MATH_AGENT.world_index(value, ceiling)

    def state_ok(self, mapping, domain=WORLD_DOMAIN):
        return MATH_AGENT.world_state_ok(mapping, domain=domain)


WORLD_MODEL = WorldModel()