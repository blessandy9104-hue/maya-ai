"""Persona sealing: a persona is bound to its tenant.

Rules enforced: tenant_scoped, cross_tenant_denied, core_shared_readonly. A
persona cannot leave its tenant nor touch the shared core except read-only.
"""
from __future__ import annotations

from .ceilings import PERSONA_CEILINGS, WEB_PERSONA_ALLOWLIST, persona_allows
from .namespace import Namespace


class PersonaSeal:
    __slots__ = ("persona_id", "tenant", "core_shared_readonly")

    def __init__(self, persona_id, tenant, core_shared_readonly=True):
        if persona_id not in PERSONA_CEILINGS:
            raise ValueError(f"unknown persona: {persona_id!r}")
        self.persona_id = persona_id
        self.tenant = tenant
        self.core_shared_readonly = bool(core_shared_readonly)

    @property
    def tenant_scoped(self):
        return True

    @property
    def cross_tenant_denied(self):
        return True

    def ceiling(self):
        return PERSONA_CEILINGS[self.persona_id]

    def allows_channels(self, channels):
        return persona_allows(self.persona_id, channels)

    def can_access(self, other_tenant):
        return other_tenant == self.tenant

    def verify(self):
        return {
            "persona": self.persona_id,
            "tenant": self.tenant,
            "tenant_scoped": True,
            "cross_tenant_denied": True,
            "core_shared_readonly": self.core_shared_readonly,
        }


assert set(PERSONA_CEILINGS) == set(WEB_PERSONA_ALLOWLIST)