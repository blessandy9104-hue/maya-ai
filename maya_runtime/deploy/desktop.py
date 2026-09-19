"""Deployment target: desktop application.

Runtime core + Tkinter desktop renderer. Requires a display; headless hosts
should use the kiosk or robotics target.
"""
from __future__ import annotations

from ..rendering import get_renderer, sample_frame

PLAN = {
    "name": "desktop",
    "renderer_kind": "desktop",
    "platforms": ("windows", "macos", "linux"),
    "requires_display": True,
    "headless_ok": False,
}


def run():
    frame = sample_frame()
    renderer = get_renderer("desktop")
    return {
        "target": "desktop",
        "renderer": renderer.describe(),
        "frame": frame.as_dict(),
        "status": "ready",
    }