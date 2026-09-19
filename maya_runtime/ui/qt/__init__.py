"""Maya Qt desktop interface (PySide6 / Qt Quick) — Batch 8E.

Interface-only layer. It consumes Maya's authoritative state (snapshot,
presence engine, driven FaceState, ``VisualState``, ``shape_math`` projection
and the digest-verified ``[semantic] `` channel) through ``bridge.py`` and only
renders it in Qt Quick/QML. No intelligence, no invented state, no wall clock,
no randomness.

PySide6 is optional: if it is missing (or ``MAYA_QT`` is explicitly disabled)
``maya_app`` falls back to the unchanged Tk window, so this package is never
imported on the fallback path except for the availability probe here.
"""
from __future__ import annotations

import os

__all__ = ["QT_AVAILABLE", "QT_DISABLED", "QtUnavailable", "launch"]

QT_AVAILABLE = True
try:  # pragma: no cover - environment dependent
    import PySide6  # noqa: F401
    from PySide6.QtCore import QTimer  # noqa: F401
    from PySide6.QtQuick import QQuickWindow  # noqa: F401
except Exception:  # noqa: BLE001
    QT_AVAILABLE = False

QT_DISABLED = os.environ.get("MAYA_QT", "1").strip().lower() \
    in {"0", "off", "false", "no"}


class QtUnavailable(RuntimeError):
    """Raised when the Qt interface cannot be used."""


def launch(args=None, qapp=None):
    """Launch the Qt desktop window (blocks until it closes).

    Raises ``QtUnavailable`` when PySide6 is absent or ``MAYA_QT`` disables
    the Qt interface; the caller then falls back to the Tk window.
    """
    if QT_DISABLED:
        raise QtUnavailable("MAYA_QT disables the Qt interface")
    if not QT_AVAILABLE:
        raise QtUnavailable("PySide6 is not installed")
    from .app import run_window
    return run_window(args=args, qapp=qapp)