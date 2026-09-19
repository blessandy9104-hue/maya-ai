"""Maya Runtime UI adapters: renderer targets + registration.

Importing this package never touches Tkinter. The desktop adapter defers its
Tk dependency to ``start()``/``make_widget()`` so headless hosts keep the
web / kiosk / robotics targets fully importable.
"""
from __future__ import annotations

from .. import rendering as _rendering
from ..rendering import RenderFrame, RendererAdapter, render_engine
from .kiosk import KioskRenderer
from .robotics import RoboticsRenderer
from .tk import TkRenderer
from .web import WebRenderer

render_engine.register(TkRenderer())
render_engine.register(WebRenderer())
render_engine.register(KioskRenderer())
render_engine.register(RoboticsRenderer())

__all__ = [
    "RenderFrame",
    "RendererAdapter",
    "render_engine",
    "TkRenderer",
    "WebRenderer",
    "KioskRenderer",
    "RoboticsRenderer",
]