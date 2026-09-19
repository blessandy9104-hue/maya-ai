"""Robotics renderer adapter (headless actuator frame).

Emits bounded actuator commands strictly inside canonical ``CHANNEL_MAX``
ceilings. No drawing, no GPU, no wall-clock. Deterministic per frame.
"""
from __future__ import annotations

from ..core import CHANNEL_MAX
from ..rendering import RendererAdapter


class RoboticsRenderer(RendererAdapter):
    kind = "robotics"
    capabilities = ("headless", "servo")

    def render(self, frame):
        commands = []
        for ch, value in sorted(frame.channels.items()):
            limit = CHANNEL_MAX.get(ch)
            bounded = value if limit is None else min(float(value), limit)
            commands.append({"channel": ch, "command": round(float(bounded), 6)})
        return {
            "context": "robotics",
            "actuators": commands,
            "bounded": frame.bounded(),
            "state": "ready",
        }

    def start(self):
        return {"context": "robotics", "state": "ready"}

    def stop(self):
        return {"context": "robotics", "state": "stopped"}