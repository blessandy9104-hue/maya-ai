"""Guard: the isolation coordinator. Role: guard.can -- orders every guard
call and denies by default.

The guard composes validator, router, executor, sandbox, seals, and ceilings
into a single deterministic decision. It coordinates guard calls in the fixed
MUS boundary order and returns deny/allow/escalate for every operation.
"""
from __future__ import annotations

from .ceilings import ALLOW, DENY, ESCALATE, CHANNEL_MAX
from .executor import IsolationExecutor
from .multi import cross_identity_denied, cross_persona_denied, cross_tenant_denied
from .persona import PersonaSeal
from .router import IsolationRouter
from .sandbox import SURFACE_WHITELIST, SandboxPolicy
from .tenant import TenantSeal
from .validator import Validator


class GuardDecision:
    __slots__ = ("verdict", "reason", "boundary", "checks")

    def __init__(self, verdict, reason, boundary, checks=()):
        self.verdict = verdict
        self.reason = reason
        self.boundary = boundary
        self.checks = tuple(checks)

    @property
    def allow(self):
        return self.verdict == ALLOW

    def to_dict(self):
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "boundary": self.boundary,
            "checks": list(self.checks),
        }


class Guard:
    def __init__(self, expected_origin=None, kill_switch=False,
                 boundary_order=("safety", "isolation", "legal", "business", "operator", "founder"),
                 surfaces=None):
        self.expected_origin = expected_origin
        self.kill_switch = kill_switch
        self.validator = Validator(expected_origin=expected_origin, kill_switch=kill_switch)
        self.router = IsolationRouter(boundary_order=boundary_order)
        self.sandbox = SandboxPolicy(surfaces if surfaces is not None else SURFACE_WHITELIST)
        self.executor = IsolationExecutor(self.sandbox)

    def can(self, *, tenant, surface, category, action, context=None,
            message=None, channels=None, trace=None):
        context = dict(context or {})
        context["surface"] = surface
        trace = list(trace or [])
        trace.append("guard:enter")

        if message is not None:
            verdict = self.validator.validate_message(message)
            if not verdict.get("allow"):
                return self._deny(verdict["reason"], "message", trace)

        if not self.validator.check_kill_switch():
            return self._deny("kill_switch_active", "isolation", trace)

        boundary = self.router.boundary_of(category)
        if boundary is None:
            return self._deny("unknown_category", "router", trace)

        trace.append(f"guard:{boundary}")

        if boundary in ("legal", "business", "safety"):
            return GuardDecision(ESCALATE, f"{boundary}_founder_gated", boundary, trace)

        if boundary == "isolation":
            if not self._sealed(context):
                return self._deny("unsealed", "isolation", trace)

        if channels is not None:
            for ch in ("expression", "viseme", "micro", "anatomical"):
                if channels.get(ch, 0.0) > CHANNEL_MAX[ch]:
                    return self._deny(f"ceiling:{ch}", "ceilings", trace)

        if self.validator.check_quota(context):
            pass
        else:
            return self._deny("quota_exceeded", "quota", trace)

        verdict = self.executor.execute(boundary, category, context,
                                        founder_token=context.get("founder_token", False))
        if verdict["verdict"] == DENY:
            return self._deny(verdict["reason"], boundary, trace)
        if verdict["verdict"] == ESCALATE:
            return GuardDecision(ESCALATE, verdict["reason"], boundary, trace)

        return GuardDecision(ALLOW, "ok", boundary, trace)

    def _sealed(self, context):
        tenant = context.get("tenant")
        source = context.get("source")
        target = context.get("target", tenant)
        src_tenant = source.get("tenant") if isinstance(source, dict) else None
        if tenant is None:
            return False
        if cross_tenant_denied(src_tenant, target):
            return False
        return True

    def _deny(self, reason, boundary, trace):
        return GuardDecision(DENY, reason, boundary, trace)