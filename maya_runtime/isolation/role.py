"""Role sealing: capability grants are role-scoped and tenant-bound.

A role grants a deterministic set of allowed actions inside one tenant. Roles
never escape their tenant namespace.
"""
from __future__ import annotations


class RoleSeal:
    __slots__ = ("role", "tenant", "allowed")

    def __init__(self, role, tenant, allowed=()):
        self.role = role
        self.tenant = tenant
        self.allowed = frozenset(allowed)

    def allows(self, action):
        return action in self.allowed

    def verify(self):
        return {
            "role": self.role,
            "tenant": self.tenant,
            "allowed": sorted(self.allowed),
        }


OPERATOR_ROLE = "operator"
FOUNDER_ROLE = "founder"
PLATFORM_ROLE = "platform"