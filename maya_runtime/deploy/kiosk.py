"""Deployment target: kiosk runtime.

Headless; drives a fixed logical surface. No display required -- safe on
CI / signage boards with a minimal Python install.
"""
from __future__ import annotations

from ..rendering import get_renderer, sample_frame

PLAN = {
    "name": "kiosk",
    "renderer_kind": "kiosk",
    "platforms": ("embedded", "linux", "windows"),
    "requires_display": False,
    "headless_ok": True,
}


def run():
    frame = sample_frame()
    renderer = get_renderer("kiosk")
    return {
        "target": "kiosk",
        "renderer": renderer.describe(),
        "payload": renderer.render(frame),
        "status": "ready",
    }