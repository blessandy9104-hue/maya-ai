"""Cognitive layer: reasoning, planning, contextual memory, bounded prediction.

Every cognitive operation is math-governed and routes through the canonical
layer (``rig_math`` / ``MATH_AGENT``): no heuristics, no randomness, no model
weight. Reasoning fuses multi-signal evidence with the canonical blend
proportions and the dot-similarity machine; planning is a monotone
no-overshoot path through clamped ``exp_smooth``; contextual memory is a
capacity-capped, unit-normalized weight vector; bounded prediction reuses the
world-prediction algebra (``world.predict``) and refuses any alignment below
its floor.

All outputs are bounded: scalar meanings live on [0, 1], plan steps stay
inside ``[min(current, goal), max(current, goal)]``, memory weights sum to
~1.0. The same input always produces the same output.
"""
from __future__ import annotations

from .wireframe.rig_math import (
    clamp01, lerp, exp_smooth, stable_exp_smooth, math_isclose,
    blend_pose, normalize, dot, magnitude,
)
from .wireframe.math_coordinator import MATH_AGENT, WORLD_DOMAIN

__all__ = [
    "Cognition",
    "COGNITION",
    "REASONING_FLOOR",
    "PLANNING_DEFAULT_ALPHA",
    "PLANNING_DEFAULT_HORIZON",
    "MEMORY_DEFAULT_ALPHA",
    "MEMORY_DEFAULT_CAPACITY",
    "PREDICTION_DEFAULT_ALPHA",
    "PREDICTION_FLOOR",
]

REASONING_FLOOR = 0.6
PLANNING_DEFAULT_ALPHA = 0.3
PLANNING_DEFAULT_HORIZON = 4
PLANNING_CONVERGENCE = 1e-6
MEMORY_DEFAULT_ALPHA = 0.2
MEMORY_DEFAULT_CAPACITY = 8
PREDICTION_DEFAULT_ALPHA = 0.5
PREDICTION_FLOOR = 0.6

# Canonical evidence-strength blend: the same 0.6 / 0.3 / 0.1 proportions as
# the pose blend, used here to weight evidence level / goal alignment / bias.
_REASON_BLEND_E = 0.6
_REASON_BLEND_A = 0.3
_REASON_BLEND_B = 0.1


class Cognition:
    """Deterministic cognitive planning assessed and produced by the
    canonical math agent. Stateless: every method is a pure function of its
    inputs, so identical inputs give identical decisions."""

    # ---- reasoning -------------------------------------------------------
    def reasoning(self, evidence, goal=(1.0, 0.0, 0.0), floor=None):
        """Multi-signal reasoning, bounded and deterministic.

        Evidence is a mapping ``{name: bounded value}``. The evidence level is
        the normalized convex combination of its (clamped) values — a
        deterministic weighted mean, so it always lands in [0, 1]. Goal
        alignment is ``clamp01(dot(normalize(evidence), normalize(goal)))`` —
        the same dot-similarity machine as pattern alignment. The reasoned
        score fuses the two through the canonical 0.6 / 0.3 / 0.1 blend
        proportions (bias 0.0):

            score = clamp01(0.6 * evidence_level + 0.3 * goal_alignment)

        Reasoned decisions must clear ``floor`` (default
        ``REASONING_FLOOR``); nothing below it is accepted."""
        floor_v = REASONING_FLOOR if floor is None else float(floor)
        if not evidence:
            return {"ok": False, "score": 0.0, "evidence_level": 0.0,
                    "goal_alignment": 0.0, "floor": floor_v}
        names = sorted(evidence)
        values = [clamp01(float(evidence[n])) for n in names]
        total = sum(values)
        if total <= 0.0:
            return {"ok": False, "score": 0.0, "evidence_level": 0.0,
                    "goal_alignment": 0.0, "floor": floor_v}
        evidence_level = sum(v * (v / total) for v in values)
        evidence_vec = normalize(tuple(values))
        goal_vec = normalize(tuple(goal)[:len(values)])
        alignment = clamp01(dot(evidence_vec, goal_vec)) \
            if magnitude(goal_vec) > 0.0 else 0.0
        score = clamp01(_REASON_BLEND_E * evidence_level
                        + _REASON_BLEND_A * alignment
                        + _REASON_BLEND_B * 0.0)
        return {"ok": score >= floor_v, "score": score,
                "evidence_level": evidence_level,
                "goal_alignment": alignment,
                "floor": floor_v}

    # ---- planning --------------------------------------------------------
    def planning(self, current, goal, horizon=None, alpha=None):
        """Monotone, no-overshoot plan from ``current`` toward ``goal``.

        Each plan step is one clamped exponential-smoothing step
        ``exp_smooth(step, clamp01(goal), clamp01(alpha))`` — the same
        canonical pattern-state change. Because both endpoints are clamped
        onto [0, 1] and ``alpha`` is clamped onto [0, 1], every intermediate
        step stays inside ``[min(current, goal), max(current, goal)]`` and
        moves monotonically toward the goal: the plan can never overshoot or
        rebound. ``horizon`` (>= 1) is the plan length; ``alpha`` is the
        step size."""
        horizon_v = max(1, int(PLANNING_DEFAULT_HORIZON
                                if horizon is None else horizon))
        alpha_v = clamp01(float(PLANNING_DEFAULT_ALPHA
                                if alpha is None else alpha))
        c = clamp01(current)
        g = clamp01(goal)
        step = c
        steps = []
        for _ in range(horizon_v):
            step = exp_smooth(step, g, alpha_v)
            steps.append(step)
        return {
            "steps": steps,
            "final": steps[-1],
            "converged": math_isclose(steps[-1], g, PLANNING_CONVERGENCE),
            "alpha": alpha_v,
            "horizon": horizon_v,
        }

    # ---- contextual memory ----------------------------------------------
    def contextual_memory(self, contexts, capacity=None, alpha=None):
        """Deterministic, capacity-bounded context recall.

        ``contexts`` is an ordered sequence of ``(name, relevance)`` pairs or
        an iterable; order is the recency order (later = more recent). The
        current window is the last ``capacity`` entries (default
        ``MEMORY_DEFAULT_CAPACITY``). Each relevance is clamped onto [0, 1]
        and smoothed once toward itself by ``stable_exp_smooth`` with the
        clamped ``alpha``; the resulting weights are normalized to a unit
        weight vector (sum ~ 1.0). Recall picks the greatest weight —
        deterministic, with ties broken by recency (last wins).

        Returned weights are bounded, finite, and deterministic."""
        capacity_v = max(1, int(MEMORY_DEFAULT_CAPACITY
                                if capacity is None else capacity))
        alpha_v = clamp01(float(MEMORY_DEFAULT_ALPHA
                                if alpha is None else alpha))
        entries = list(contexts)
        window = entries[-capacity_v:]
        if not window:
            return {"weights": {}, "recall": None, "recall_strength": 0.0,
                    "capacity": capacity_v, "retained": 0}
        raw = {}
        order = []
        for name, relevance in window:
            name = str(name)
            order.append(name)
            raw[name] = stable_exp_smooth(0.0, clamp01(float(relevance)),
                                          alpha_v)
        total = sum(raw.values())
        total_v = total if total > 0.0 else 1.0
        weights = {name: raw[name] / total_v for name in order}
        recall_strength = max(weights.values())
        recall = next(name for name in reversed(order)
                      if weights[name] == recall_strength)
        return {"weights": weights, "recall": recall,
                "recall_strength": recall_strength,
                "capacity": capacity_v, "retained": len(window)}

    # ---- bounded prediction ---------------------------------------------
    def bounded_prediction(self, observed, expected, alpha=None, floor=None):
        """Bounded prediction through the world-prediction algebra.

        Delegates to ``MATH_AGENT.world_predict``: alignment is
        ``clamp01(dot(normalize(observed), normalize(expected)))`` and each
        predicted feature moves toward its expectation through the canonical
        clamped ``lerp`` transition. A prediction is accepted only when its
        alignment clears ``floor`` (default ``PREDICTION_FLOOR``); predictions
        below the floor are rejected — no heuristic drift is ever accepted as
        a predicted truth."""
        alpha_v = PREDICTION_DEFAULT_ALPHA if alpha is None else alpha
        floor_v = PREDICTION_FLOOR if floor is None else floor
        report = MATH_AGENT.world_predict(tuple(observed), tuple(expected),
                                          alpha=alpha_v, floor=floor_v)
        aligned = report.get("aligned")
        bounded = all(clamp01(v) == v for v in aligned) if aligned else True
        return {
            "ok": report["ok"],
            "alignment": report["alignment"],
            "aligned": aligned,
            "alpha": report["alpha"],
            "bounded": bounded,
            "reason": report.get("reason"),
        }


COGNITION = Cognition()