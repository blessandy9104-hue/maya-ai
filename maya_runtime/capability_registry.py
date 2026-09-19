"""Maya Runtime: capability registry surface (canonical, loadable headless).

Every attribute is delegated to the single-source-of-truth registry
(``maya_identity.capability_registry``), so values can never drift.
"""
from __future__ import annotations

from . import _loader as _l

_caps = _l.module("capability_registry")


def __getattr__(name: str):
    value = getattr(_caps, name)
    globals()[name] = value
    return value


__all__ = [n for n in dir(_caps) if not n.startswith("_")]