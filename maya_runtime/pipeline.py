"""Pipeline facade: the runtime-level entry point into the isolation pipeline.

Delegates to the canonical isolation pipeline (validator -> router -> guard ->
executor) with fail-closed fallback and audit hooks.
"""
from __future__ import annotations

from .isolation.pipeline import AuditHooks, IsolationPipeline
from .isolation.guard import Guard


def default_pipeline():
    return IsolationPipeline()


def guard():
    return Guard()


def run(*, tenant, surface, category, action, context=None, message=None,
        channels=None, founder_token=False):
    return default_pipeline().run(
        tenant=tenant,
        surface=surface,
        category=category,
        action=action,
        context=context,
        message=message,
        channels=channels,
        founder_token=founder_token,
    )


__all__ = ["AuditHooks", "IsolationPipeline", "Guard", "default_pipeline", "guard", "run"]