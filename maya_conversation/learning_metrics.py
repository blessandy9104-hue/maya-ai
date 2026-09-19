"""Batch 8I phase 11: learning-quality metrics.

Measures HOW WELL Maya learns, beyond raw test accuracy:
  - memory_efficiency   runs compressed per task fingerprint
  - similarity_fidelity how faithfully similarity reflects key identity
  - hypothesis_validity promoted / (promoted + rejected)
  - evidence_efficiency cases required per promotion (lower is better)
  - transfer_benefit    learned accuracy minus un-learned baseline
  - stability           determinism across repeating metric batches

All metrics are deterministic continuations of recorded statistics.
Threshold tables are static; ``evaluate()`` marks health per metric.

Purity:
- No clock, no randomness, no IO, no network.
- Never raises; malformed values degrade to neutral metric rows.
"""
from __future__ import annotations


def _finite(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _mean(values):
    values = [_finite(v) for v in values]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values):
    values = [_finite(v) for v in values]
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance ** 0.5


def _perf_metric(value):
    ranking = {1: "poor", 2: "below_average", 3: "average",
               4: "above_average", 5: "good"}
    return ranking.get(max(1, min(5, int(value))), "average")


_THRESHOLDS = {
    "memory_efficiency":      lambda v: v >= 2.0,
    "similarity_fidelity":    lambda v: v >= 0.7,
    "hypothesis_validity":    lambda v: v >= 0.5,
    "evidence_efficiency":    lambda v: v <= 3.0,
    "transfer_benefit":       lambda v: v >= 0.1,
    "stability":              lambda v: v >= 0.8,
}


class LearningMetrics:
    """Accumulates learning evidence and emits a quality snapshot."""

    def __init__(self):
        self._runs = 0
        self._fingerprints = 0
        self._promoted = 0
        self._rejected = 0
        self._promotion_cases = []
        self._reward = 0.0
        self._baseline = 0.0
        self._groups = []

    def record_memory(self, fingerprints, runs):
        self._fingerprints = max(self._fingerprints,
                                 int(_finite(fingerprints)))
        self._runs = max(self._runs, int(_finite(runs)))

    def record_hypothesis_outcome(self, status):
        status = str(status or "")
        if status == "promoted":
            self._promoted += 1
        elif status == "rejected":
            self._rejected += 1

    def record_promotion_cost(self, cases_needed):
        self._promotion_cases.append(max(1, int(_finite(cases_needed, 1))))

    def record_transfer(self, learned_accuracy, baseline_accuracy):
        self._reward = max(self._reward, _finite(learned_accuracy))
        self._baseline = max(self._baseline, _finite(baseline_accuracy))

    def record_stability_batch(self, batch_key, values):
        self._groups.append({"batch_key": str(batch_key),
                             "values": [_finite(v) for v in values]})

    def memory_efficiency(self):
        if self._fingerprints <= 0:
            return 0.0
        return self._runs / self._fingerprints

    def hypothesis_validity(self):
        total = self._promoted + self._rejected
        if total <= 0:
            return 0.0
        return self._promoted / total

    def evidence_efficiency(self):
        if not self._promotion_cases:
            return 0.0
        return _mean(self._promotion_cases)

    def transfer_benefit(self):
        return self._reward - self._baseline

    def similarity_fidelity(self, pairs):
        """1.0 - mean absolute gap between target and computed similarity."""
        if not pairs:
            return 0.0
        gaps = []
        for target, actual in pairs:
            gaps.append(abs(_finite(actual) - _finite(target)))
        return max(0.0, 1.0 - _mean(gaps))

    def stability(self):
        """1.0 - normalized spread across recorded metric batches."""
        if len(self._groups) < 2:
            return 0.0
        sizes = sorted(set(len(g["values"]) for g in self._groups))
        if len(sizes) < 1:
            return 0.0
        per_index_stdev = []
        for index in range(sizes[0]):
            per_index_stdev.append(_std([g["values"][index]
                                         for g in self._groups
                                         if len(g["values"]) > index]))
        if not per_index_stdev:
            return 0.0
        return max(0.0, 1.0 - _mean(per_index_stdev))

    def evaluate(self, key, value):
        healthy = _THRESHOLDS[key](_finite(value))
        return {
            "metric": key,
            "value": _finite(value),
            "healthy": bool(healthy),
            "threshold": key.replace("_", " "),
            "performance": _perf_metric(_finite(value)),
        }

    def snapshot(self, pairs=None):
        metrics = [
            self.evaluate("memory_efficiency", self.memory_efficiency()),
            self.evaluate("similarity_fidelity",
                          self.similarity_fidelity(pairs or ())),
            self.evaluate("hypothesis_validity", self.hypothesis_validity()),
            self.evaluate("evidence_efficiency", self.evidence_efficiency()),
            self.evaluate("transfer_benefit", self.transfer_benefit()),
            self.evaluate("stability", self.stability()),
        ]
        health_count = sum(1 for m in metrics if m["healthy"])
        return {
            "metrics": metrics,
            "summary": {
                "total_metrics": len(metrics),
                "healthy_metrics": health_count,
                "learning_health": ("healthy" if health_count == len(metrics)
                                    else "partial"),
            },
            "raw": {
                "runs": self._runs,
                "fingerprints": self._fingerprints,
                "promoted": self._promoted,
                "rejected": self._rejected,
                "promotion_cases": list(self._promotion_cases),
                "reward": self._reward,
                "baseline": self._baseline,
            },
        }