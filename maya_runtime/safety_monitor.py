"""Maya Runtime: safety monitor facade -- fail-closed, device-neutral.

Pure delegation to the canonical ``MATH_AGENT`` safety methods so thresholds
and ceilings can never diverge from the classic shell.
"""
from __future__ import annotations

from .core import MATH_AGENT


class SafetyMonitor:
    """Stateless safety gateway. Always returns bounded, finite decisions."""

    def margin(self, cpu_percent, memory_percent, process_count, launches, policy=None):
        return MATH_AGENT.pattern_safety_margin(
            cpu_percent, memory_percent, process_count, launches, policy=policy
        )

    def check(self, cpu_percent, memory_percent, process_count, launches,
              stop_active=False, policy=None, cumulative=True):
        return MATH_AGENT.check_limits(
            cpu_percent, memory_percent, process_count, launches,
            stop_active=stop_active, policy=policy, cumulative=cumulative,
        )

    def resource_anomaly(self, series, current, z_threshold=2.0, limit=1.0,
                         lo=0.0, hi=100.0):
        return MATH_AGENT.resource_anomaly(
            series, current, z_threshold=z_threshold, limit=limit, lo=lo, hi=hi
        )

    def evaluate(self, cpu_percent, memory_percent, process_count, launches,
                 stop_active=False, policy=None, cpu_history=None,
                 memory_history=None, motion_series=None, world_series=None):
        return MATH_AGENT.safety_evaluate(
            cpu_percent, memory_percent, process_count, launches,
            stop_active=stop_active, policy=policy, cpu_history=cpu_history,
            memory_history=memory_history, motion_series=motion_series,
            world_series=world_series,
        )


SAFETY_MONITOR = SafetyMonitor()