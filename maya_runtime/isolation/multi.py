"""Multi-scope denial: cross-tenant, cross-persona, cross-identity checks.

A single composite predicate over the seal set used by the guard to deny any
operation that crosses a tenant, persona, or identity boundary.
"""
from __future__ import annotations


def cross_tenant_denied(source_tenant, target_tenant):
    return source_tenant != target_tenant


def cross_persona_denied(source_persona_scoped, target_persona_id):
    return source_persona_scoped != target_persona_id


def cross_identity_denied(source_identity, target_identity):
    return source_identity != target_identity


def out_of_thread(source_thread, target_thread):
    return source_thread != target_thread