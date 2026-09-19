"""Kiosk renderer adapter (headless fullscreen-aware stub).

Emits a fixed-format layer payload suitable for a kiosk surface; fully
importable on headless hosts, deterministic, no timestamps.
"""
from __future__ import annotations

from ..rendering import RendererAdapter, sample_frame


class KioskRenderer(RendererAdapter):
    kind = "kiosk"
    capabilities = ("headless", "fullscreen")

    # fixed logical surface, independent of any physical device
    resolution = (640, 480)

    def render(self, frame):
        return {
            "context": "kiosk",
            "resolution": self.resolution,
            "layers": [
                {"channel": ch, "value": round(float(value), 6)}
                for ch, value in sorted(frame.channels.items())
            ],
            "underlay": frame.tags,
            "state": "ready",
        }

    def start(self):
        return {"context": "kiosk", "state": "ready", "resolution": self.resolution}

    def stop(self):
        return {"context": "kiosk", "state": "stopped"}


def _boot_ready():
    return sample_frame().as_dict()