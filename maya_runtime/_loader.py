"""Canonical module loader for the portable Maya Runtime.

Brings the single-source-of-truth math modules from ``maya_identity`` into a
platform-neutral package. Two modes:

- Standard (display-capable host, e.g. desktop): import through the real
  package. ``maya_runtime`` then uses exactly the same module objects as the
  classic shell -- zero duplication, zero behavior change.
- Headless: forced with ``MAYA_RUNTIME_HEADLESS=1`` for CI / kiosk / robotics,
  or selected automatically when importing ``maya_identity`` fails because
  Tkinter is absent. The pure-math subgraph is loaded by file location while
  the widget path (``face3d``, ``hologram_renderer``) is never touched, so the
  runtime core stays importable on minimal hosts.

Every module loaded here is deterministic: no ``random``, ``time`` or
``tkinter`` anywhere in the core graph.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import types

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BASE = _ROOT / "maya_identity"
_WIRE = _BASE / "wireframe"

_FORCE_HEADLESS = os.environ.get("MAYA_RUNTIME_HEADLESS", "0") in {"1", "true", "True", "yes"}

_MODULES = None
_USED_FALLBACK = False


def _install_placeholder_package(name: str, path: pathlib.Path) -> types.ModuleType:
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(path)]
    pkg.__package__ = name
    sys.modules[name] = pkg
    return pkg


def _load_standalone(module_name: str, file: pathlib.Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {module_name} from {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_headless() -> None:
    global _USED_FALLBACK
    _USED_FALLBACK = True
    _install_placeholder_package("maya_identity", _BASE)
    _install_placeholder_package("maya_identity.wireframe", _WIRE)
    _load_standalone("maya_identity.wireframe.rig_math", _WIRE / "rig_math.py")
    _load_standalone(
        "maya_identity.wireframe.math_coordinator",
        _WIRE / "math_coordinator.py",
    )
    if "maya_identity.wireframe.expression_controller" not in sys.modules:
        _load_standalone(
            "maya_identity.wireframe.expression_controller",
            _WIRE / "expression_controller.py",
        )
    _load_standalone(
        "maya_identity.capability_registry",
        _BASE / "capability_registry.py",
    )


def load_platform() -> dict:
    """Load the canonical runtime modules (keyed by name) exactly once."""
    global _MODULES, _USED_FALLBACK
    if _MODULES is not None:
        return _MODULES
    if _FORCE_HEADLESS:
        _load_headless()
    else:
        try:
            import maya_identity.capability_registry  # noqa: F401
            import maya_identity.wireframe.expression_controller  # noqa: F401
            import maya_identity.wireframe.math_coordinator  # noqa: F401
            import maya_identity.wireframe.rig_math  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            _load_headless()
    import maya_identity.capability_registry as _caps
    import maya_identity.wireframe.expression_controller as _ec
    import maya_identity.wireframe.math_coordinator as _mcoord
    import maya_identity.wireframe.rig_math as _rig
    _MODULES = {
        "rig_math": _rig,
        "math_coordinator": _mcoord,
        "expression_controller": _ec,
        "capability_registry": _caps,
    }
    return _MODULES


def module(name: str):
    return load_platform()[name]


HEADLESS = _FORCE_HEADLESS