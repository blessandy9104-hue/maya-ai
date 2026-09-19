"""Maya Runtime: expression controller surface (canonical, non-Tk)."""
from __future__ import annotations

from . import _loader

_EC = _loader.module("expression_controller")

_NAMES = ("ExpressionController", "ALL_CONTROLS", "PRESETS")

for _name in _NAMES:
    globals()[_name] = getattr(_EC, _name)

del _name