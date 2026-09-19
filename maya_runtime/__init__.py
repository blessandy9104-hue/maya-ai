"""Maya Runtime -- portable, device-neutral runtime core for Maya.

Bundles the canonical math layer, world model, safety monitor, pattern
alignment, expression controller, rendering engine, capability registry and a
new deterministic personality layer behind one import.

Cross-device guarantees:
- no hardware-specific behavior          (no hardware probes)
- no GPU dependencies                    (pure CPU math, optional adapters)
- no timing drift                        (no wall-clock in the core graph)
- no randomness                          (no RNG in the core graph)

Preserves every canonical guarantee of ``maya_identity``: blend weights,
semantic correctness, world stability, safety boundaries, CPU-light behavior.
"""
from __future__ import annotations

from . import _loader
from . import core
from . import capability_registry
from . import determinism
from . import expression_controller
from . import pattern_alignment
from . import personality
from . import rendering
from . import safety_monitor
from . import world_model
from . import isolation
from . import intelligence
from . import ui as _ui  # registers desktop/web/kiosk/robotics adapters
from .deploy import DEPLOYMENT_TARGETS, manifest, target

RUNTIME_VERSION = "1.0.0"
PORTABLE = True

MATH_AGENT = core.MATH_AGENT
WORLD_MODEL = world_model.WORLD_MODEL
SAFETY_MONITOR = safety_monitor.SAFETY_MONITOR
PATTERN_ALIGNMENT = pattern_alignment.PATTERN_ALIGNMENT
RENDER_ENGINE = rendering.render_engine
PERSONALITY = personality.PERSONALITY  # PRESENTATION personality (never cognitive/identity)
INTELLIGENCE = intelligence.INTELLIGENCE

# re-exports for convenience
EXP = expression_controller.ExpressionController  # alias (usage optional)
get_renderer = rendering.get_renderer
RenderFrame = rendering.RenderFrame


def runtime_profile():
    """Deterministic, non-hardware metadata about the loaded runtime."""
    return {
        "runtime_version": RUNTIME_VERSION,
        "portable": PORTABLE,
        "headless_loader": bool(_loader.HEADLESS),
        "deployment_targets": list(DEPLOYMENT_TARGETS),
        "channels": len(core.CHANNEL_MAX),
        "personas": list(PERSONALITY.available()),
        "intelligence_version": intelligence.VERSION,
        "loop_stages": list(intelligence.STAGES),
    }


def readiness_status():
    """Operational state of the stabilized Maya runtime (identity layer).

    ``ready`` is held to the dual-verification protocol: it is true only after
    an explicit external ``clean`` verdict and a stable internal self-check.
    ``stabilized`` and ``status_code`` are derived from live verification
    state; a fresh process that has not completed verification never reports
    the ``maya-stabilized-ready`` status code.
    """
    from maya_identity import readiness, stabilization

    ready = stabilization.is_ready()
    return {
        "stabilized": readiness.stabilized(),
        "status_code": "maya-stabilized-ready" if ready else "maya-unverified",
        "ready": ready,
        "operational_state": stabilization.state(),
        "internal_self_check": stabilization.status()["self_check"],
        "portable_loader": runtime_profile(),
    }


__all__ = [
    "RUNTIME_VERSION",
    "PORTABLE",
    "runtime_profile",
    "MATH_AGENT",
    "WORLD_MODEL",
    "SAFETY_MONITOR",
    "PATTERN_ALIGNMENT",
    "RENDER_ENGINE",
    "PERSONALITY",
    "INTELLIGENCE",
    "get_renderer",
    "RenderFrame",
    "DEPLOYMENT_TARGETS",
    "manifest",
    "target",
    "readiness_status",
    "core",
    "capability_registry",
    "determinism",
    "expression_controller",
    "personality",
    "rendering",
    "world_model",
    "safety_monitor",
    "pattern_alignment",
    "isolation",
    "intelligence",
]