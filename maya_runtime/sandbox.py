"""Sandbox facade: the six deny-by-default sandbox rules for the runtime.

Re-exports the canonical isolation sandbox policy so callers can enforce the
surface allowlist and fail-closed behavior from the runtime root.
"""
from __future__ import annotations

from .isolation.sandbox import SURFACE_WHITELIST, SandboxPolicy

DENY_BY_DEFAULT = True
POLICY = "deny_by_default"
RULES = SandboxPolicy().rules


def check(op):
    return SandboxPolicy().allows(op)


__all__ = ["SURFACE_WHITELIST", "SandboxPolicy", "DENY_BY_DEFAULT", "POLICY", "RULES", "check"]