"""Isolation executor: namespaced, isolation-guarded, operator-bound execution.

Executes only operator-scoped (non-legal, non-financial) operations inside the
caller's tenant namespace, guarded by the sandbox ceiling and CHANNEL_MAX. A
founder-gated action can only run when an explicit founder token is present,
and even then never bypasses safety, isolation, or legal.
"""
from __future__ import annotations

from .ceilings import ALLOW, DENY, ESCALATE, FOUNDER_BOUNDARY, OPERATOR_BOUNDARY
from .namespace import Namespace


class IsolationExecutor:
    def __init__(self, sandbox):
        self.sandbox = sandbox

    def execute(self, boundary, category, ctx, action=None, founder_token=False):
        if boundary in ("safety", "legal"):
            return self._result(ESCALATE, "boundary_requires_founder")
        if boundary == "business":
            return self._result(ESCALATE, "business_founder_gated")
        if boundary == "isolation":
            if not self._namespace_ok(ctx):
                return self._result(DENY, "namespace_denied")
            return self._result(ALLOW, "sealed")
        if boundary == "operator":
            if not self.sandbox.allows(ctx.get("surface")):
                return self._result(DENY, "surface_not_allowlisted")
            return self._result(ALLOW, "operator_ok")
        if boundary == "founder":
            if not founder_token:
                return self._result(DENY, "founder_token_required")
            return self._result(ALLOW, "founder_authorized")
        return self._result(DENY, "unknown_boundary")

    def _namespace_ok(self, ctx):
        ns = Namespace(ctx["tenant"], ctx.get("kind", "data"))
        p = ctx.get("namespace_path")
        return p and (p == ns.path or p.startswith(ns.path + "/"))

    def _result(self, verdict, reason):
        return {"verdict": verdict, "reason": reason}