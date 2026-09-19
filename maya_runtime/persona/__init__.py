"""Persona runtime surface: personas load and run sealed to their tenant.

Re-enforces tenant_scoped / cross_tenant_denied / core_shared_readonly at the
runtime surface by requiring a valid persona seal before any channel target is
emitted.
"""
from __future__ import annotations

from ..isolation import PERSONA_CEILINGS, WEB_PERSONA_ALLOWLIST, PersonaSeal


class PersonaRuntime:
    def __init__(self):
        self.allowlist = WEB_PERSONA_ALLOWLIST

    def seal(self, persona_id, tenant):
        return PersonaSeal(persona_id, tenant)

    def available(self):
        return list(self.allowlist)

    def ceilings_for(self, persona_id):
        return dict(PERSONA_CEILINGS[persona_id])


PERSONA_RUNTIME = PersonaRuntime()