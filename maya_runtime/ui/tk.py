"""Desktop (Tkinter) renderer adapter.

Tkinter is fully quarantined here. Importing this module is safe on headless
hosts; constructing the widget (``make_widget`` / ``start``) requires a real
display and raises ``RuntimeError`` otherwise.
"""
from __future__ import annotations

from ..rendering import RendererAdapter


class TkRenderer(RendererAdapter):
    kind = "desktop"
    capabilities = ("tk", "canvas")

    def render(self, frame):
        # Deterministic command model; actual drawing happens only when a
        # display-backed widget exists (start/make_widget).
        channels = frame.as_dict()["channels"]
        return {
            "context": "desktop",
            "backend": "tkinter",
            "canvas_commands": [
                {"op": "clear"},
                {"op": "blend", "expression": channels.get("expression", 0.0)},
                {"op": "viseme", "target": channels.get("viseme", 0.0)},
                {"op": "micro_glow", "gain": channels.get("micro", 0.0)},
            ],
            "state": "ready",
        }

    def make_widget(self, root=None):
        try:
            import tkinter as tk
        except ImportError as exc:  # pragma: no cover - host-dependent
            raise RuntimeError("desktop renderer requires Tkinter") from exc
        if root is None:
            try:
                root = tk.Tk()
            except Exception as exc:  # no display available
                raise RuntimeError(
                    "desktop renderer requires a display (kiosk/robotics: use headless targets)"
                ) from exc
        from maya_identity.wireframe.face3d import MayaWireframeFace  # noqa: F401

        widget = MayaWireframeFace(root)
        return widget

    def start(self):
        widget = self.make_widget()
        widget.pack()
        return widget

    def stop(self):
        return {"context": "desktop", "state": "stopped"}