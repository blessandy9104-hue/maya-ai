"""Maya Isolation Runtime: deny-by-default guard for every tenant, persona,
identity, message, and surface.

Enforces on disk the Phase 7 isolation implementation registry
(maya_identity/isolation/impl/ir_impl.json): the nine isolation rules, the
fixed MUS boundary chain, CHANNEL_MAX ceilings, per-persona ceilings, tenant
quotas, namespace sealing, and fail-closed fallback behavior.
"""
from __future__ import annotations

from .ceilings import (
    ALLOW,
    CHANNEL_MAX,
    DENY,
    ESCALATE,
    MUS_BOUNDARY_ORDER,
    PERSONA_CEILINGS,
    TENANT_QUOTAS,
    WEB_PERSONA_ALLOWLIST,
)
from .guard import Guard, GuardDecision
from .namespace import Namespace, NAMESPACE_FORMULA, RESOURCE_KINDS
from .persona import PersonaSeal
from .pipeline import AuditHooks, IsolationPipeline
from .role import FOUNDER_ROLE, OPERATOR_ROLE, PLATFORM_ROLE, RoleSeal
from .router import IsolationRouter
from .sandbox import SandboxPolicy, SURFACE_WHITELIST
from .tenant import TenantSeal
from .tone import ToneSeal
from .user import UserSeal
from .validator import Validator, MESSAGE_TYPES
from .identity import IdentitySeal

ISOLATION_VERSION = "7.0.0"
DENY_BY_DEFAULT = True
COORDINATOR_ROLE = "guard.can"


def guard():
    return Guard()


def default_pipeline():
    return IsolationPipeline()


__all__ = [
    "ISOLATION_VERSION",
    "DENY_BY_DEFAULT",
    "COORDINATOR_ROLE",
    "CHANNEL_MAX",
    "PERSONA_CEILINGS",
    "TENANT_QUOTAS",
    "WEB_PERSONA_ALLOWLIST",
    "MUS_BOUNDARY_ORDER",
    "NAMESPACE_FORMULA",
    "RESOURCE_KINDS",
    "SURFACE_WHITELIST",
    "MESSAGE_TYPES",
    "ALLOW",
    "DENY",
    "ESCALATE",
    "Guard",
    "GuardDecision",
    "Namespace",
    "IsolationRouter",
    "SandboxPolicy",
    "Validator",
    "IsolationPipeline",
    "AuditHooks",
    "PersonaSeal",
    "RoleSeal",
    "TenantSeal",
    "UserSeal",
    "ToneSeal",
    "IdentitySeal",
    "OPERATOR_ROLE",
    "FOUNDER_ROLE",
    "PLATFORM_ROLE",
    "guard",
    "default_pipeline",
]