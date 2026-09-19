"""Deployment target: web application.

Runtime core + web renderer stub (Canvas/WebGL-ready payloads). Runs in any
browser host; payloads are pure JSON, no GPU work server-side.
"""
from __future__ import annotations

from ..rendering import get_renderer, sample_frame

PLAN = {
    "name": "web",
    "renderer_kind": "web",
    "platforms": ("browser", "server"),
    "requires_display": False,
    "headless_ok": True,
}


def run():
    frame = sample_frame()
    renderer = get_renderer("web")
    return {
        "target": "web",
        "renderer": renderer.describe(),
        "payload": renderer.render(frame),
        "status": "ready",
    }