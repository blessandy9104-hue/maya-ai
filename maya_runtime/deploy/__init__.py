"""Maya Runtime deployment targets.

Each target is a declared, testable deployment surface that binds one renderer
kind to the platform-neutral core. Manifests are static constants -- no
hardware probing at import time.
"""
from __future__ import annotations

from . import desktop, kiosk, robotics, web

DEPLOYMENT_TARGETS = ("desktop", "web", "kiosk", "robotics")

_TARGETS = {
    "desktop": desktop.PLAN,
    "web": web.PLAN,
    "kiosk": kiosk.PLAN,
    "robotics": robotics.PLAN,
}


def target(name):
    if name not in _TARGETS:
        raise KeyError(f"unknown deployment target: {name!r}")
    return dict(_TARGETS[name])


def manifest():
    return [dict(_TARGETS[name]) for name in DEPLOYMENT_TARGETS]


__all__ = ["DEPLOYMENT_TARGETS", "target", "manifest"]