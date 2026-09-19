"""Sandbox enforcement: deny by default with a strict capability allowlist.

Rules enforced: no_external_api, no_account_access, no_network_egress,
no_process_ipc, surface_whitelist, fail_closed. Approved operations are only
those explicitly allowlisted; everything else is denied.
"""
from __future__ import annotations

SURFACE_WHITELIST = (
    "studio",
    "marketplace",
    "cloud_runtime",
    "api",
    "kiosk",
    "embed_runtime",
    "market_analyst",
)

_SANDBOX_RULES = (
    "no_external_api",
    "no_account_access",
    "no_network_egress",
    "no_process_ipc",
    "surface_whitelist",
    "fail_closed",
)


class SandboxPolicy:
    __slots__ = ("allowed_surfaces",)

    def __init__(self, allowed_surfaces=SURFACE_WHITELIST):
        self.allowed_surfaces = frozenset(allowed_surfaces)

    @property
    def rules(self):
        return _SANDBOX_RULES

    def allows(self, operation):
        if isinstance(operation, str):
            return operation in self.allowed_surfaces
        target = operation.get("surface") if isinstance(operation, dict) else None
        return target in self.allowed_surfaces

    def allows_api(self, api_name):
        return api_name in self.allowed_surfaces

    def check_egress(self, url):
        return url is None

    def check_ipc(self, proc):
        return proc is None

    def check_account(self, account):
        return account is None

    def verify(self):
        return {
            "policy": "deny_by_default",
            "rules": list(_SANDBOX_RULES),
            "surface_whitelist": sorted(self.allowed_surfaces),
        }