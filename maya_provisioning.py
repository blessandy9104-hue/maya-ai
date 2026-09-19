"""Active provisioning: install a missing dependency, then re-validate trust.

Maya may discover that a capability it needs is *declared* but not *present* —
its backing module cannot be imported, so the trusted-capability record for
that provider validates as ``unavailable`` and every action is refused. This
module owns the one sanctioned way out of that state: a gated, owner-confirmed
provisioning action that installs the missing dependency and re-runs the trust
validation so the record can recover ``unavailable -> available``.

Safety model (all must hold; anything else is a refusal with no side effect):

- **Default deny.** Nothing runs unless the trusted registry approves the
  ``dependency_provisioning`` / ``install_dependency`` action. If the
  provisioning provider has no validated record, ``authorize`` refuses and
  the module returns without touching the filesystem.
- **Owner confirmation.** A caller must pass the exact
  :func:`confirmation_token` for the dependency; a missing or wrong token is
  a refusal that runs nothing. The token is deterministic and bound to both
  the capability and the dependency, so a token for one dependency can never
  authorise another.
- **Explicit execution.** ``execute`` defaults to ``False``: the default is a
  read-only plan (``prepared_not_executed``). Even with confirmation, no
  runner means no execution (``runner_unavailable``).
- **Allowlisted, sandboxed runner.** Only dependencies named in
  :data:`PROVISIONABLE` are addressable, and installation is delegated to the
  injected ``runner`` callable. This module never shells out and never imports
  the target itself; it only probes importability before and after, so the
  effect is observable and independently re-checkable.
- **No phantom success.** A run is reported ``installed`` only when the
  dependency is importable afterwards; otherwise ``validation_failed``.

This module does not modify :data:`maya_trust.DECLARED_PROVIDERS` or any
authoritative inventory; it defines its own provider record and validates it
into whichever (temporary) registry the caller supplies.
"""
from __future__ import annotations

import importlib.util
from typing import Any, Callable

SCHEMA = "maya/provisioning/1.0.0"

CAPABILITY = "dependency_provisioning"
ACTION = "install_dependency"
CONTEXT = "personal"
PROVIDER = "maya_provisioning_engine"

# Package managers this module is *willing* to describe. Metadata only: the
# module itself never invokes any of them, it delegates to the injected runner.
MANAGERS: dict[str, dict[str, str]] = {
    "sandbox": {"kind": "injected", "note": "test runner; writes a module on sys.path"},
    "pip": {"kind": "python", "note": "python package index"},
    "npm": {"kind": "node", "note": "node package registry"},
}

# The allowlisted dependency catalog. Only names here are ever addressable, so
# a caller cannot smuggle an arbitrary package name into a provisioning action.
PROVISIONABLE: tuple[dict[str, Any], ...] = (
    {
        "dependency": "maya_demo_spectral_backend",
        "module": "maya_demo_spectral_backend",
        "package": "maya-demo-spectral-backend",
        "manager": "sandbox",
        "capability": "spectral_backend",
        "reason": "synthetic dependency for provisioning-recovery validation",
    },
    {
        "dependency": "maya_demo_frequency_index",
        "module": "maya_demo_frequency_index",
        "package": "maya-demo-frequency-index",
        "manager": "sandbox",
        "capability": "frequency_index",
        "reason": "synthetic dependency for provisioning-recovery validation",
    },
)

STATUS_ALREADY = "already_available"
STATUS_INSTALLED = "installed"
STATUS_VALIDATION_FAILED = "validation_failed"
STATUS_REFUSED = "refused"
STATUS_UNKNOWN = "unknown_dependency"
STATUS_CONFIRMATION = "confirmation_required"
STATUS_RUNNER = "runner_unavailable"
STATUS_PREPARED = "prepared_not_executed"
STATUS_FAILED = "failed"
STATUSES = (STATUS_ALREADY, STATUS_INSTALLED, STATUS_VALIDATION_FAILED,
            STATUS_REFUSED, STATUS_UNKNOWN, STATUS_CONFIRMATION, STATUS_RUNNER,
            STATUS_PREPARED, STATUS_FAILED)


def _catalog() -> dict[str, dict[str, Any]]:
    return {entry["dependency"]: dict(entry) for entry in PROVISIONABLE}


def descriptor(dependency: str) -> dict[str, Any] | None:
    """Allowlisted catalog entry for ``dependency`` (or ``None``)."""
    entry = _catalog().get(str(dependency))
    return dict(entry) if entry else None


def import_available(module: str) -> bool:
    """Fail-closed importability probe for ``module`` (never imports it).

    Returns ``False`` on any error, so an unknown or broken dependency can
    never be reported as present.
    """
    try:
        importlib.invalidate_caches()
        return importlib.util.find_spec(str(module)) is not None
    except Exception:
        return False


def missing_dependency(dependency: str) -> bool:
    """True when an allowlisted dependency's module is not importable."""
    entry = descriptor(dependency)
    module = entry["module"] if entry else str(dependency)
    return not import_available(module)


def confirmation_token(dependency: str, capability: str = CAPABILITY) -> str:
    """Deterministic owner-confirmation token bound to capability+dependency."""
    return f"provision:{capability}:{dependency}"


def plan(dependency: str, registry_path: Any = None) -> dict[str, Any]:
    """Read-only provisioning plan. Performs no write and no execution."""
    entry = descriptor(dependency)
    if entry is None:
        return {
            "schema": SCHEMA,
            "ok": False,
            "known": False,
            "dependency": str(dependency),
            "status": STATUS_UNKNOWN,
            "executed": False,
            "reason": "dependency not in the provisioning allowlist",
        }
    module = entry["module"]
    missing = not import_available(module)
    return {
        "schema": SCHEMA,
        "ok": True,
        "known": True,
        "dependency": entry["dependency"],
        "module": module,
        "package": entry["package"],
        "manager": entry["manager"],
        "manager_known": entry["manager"] in MANAGERS,
        "capability": entry["capability"],
        "capability_context": CAPABILITY,
        "action": ACTION,
        "context": CONTEXT,
        "missing": missing,
        "available": not missing,
        "status": "missing" if missing else STATUS_ALREADY,
        "confirmation_token": confirmation_token(entry["dependency"]),
        "executed": False,
    }


def provisioning_record(provider: str = PROVIDER,
                        owner: str = "default") -> dict[str, Any]:
    """A well-formed, approval-required trusted-capability record.

    The record is *declared*, not trusted: it must be validated through
    :func:`maya_trust.refresh` (with an availability probe) before
    ``authorize`` will approve anything.
    """
    return {
        "capability": CAPABILITY,
        "provider": provider,
        "owner": owner,
        "context": CONTEXT,
        "permissions": {ACTION: True, "read_status": True},
        "actions": (ACTION, "read_status"),
        "approval": {ACTION: {"required": True},
                     "read_status": {"required": False}},
        "boundaries": {"input": "project", "output": "project",
                       "cross_context_denied": True},
        "auth": {"method": "owner", "state": "valid"},
        "result_confirmation": {"supported": True, "method": "module_probe"},
        "failure": {"fail_closed": True},
        "trust_basis": ["owner-approved provisioning",
                        "sandboxed reversible writes"],
        "identity": {"provider": provider, "version": "1",
                     "source_digest": None},
    }


def register_provisioning_provider(registry_path: Any = None,
                                   action_log: Any = None,
                                   provider: str = PROVIDER,
                                   probe: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate and store the provisioning provider into a registry.

    Returns the stored record. ``probe`` defaults to ``{"available": True}``.
    Callers pass a temporary ``registry_path`` so the real registry is never
    written.
    """
    import maya_trust

    record = provisioning_record(provider=provider)
    return maya_trust.refresh(record, probe=probe if probe is not None
                              else {"available": True},
                              path=registry_path, action_log=action_log)


def revalidate_dependent(record: dict[str, Any], available: bool,
                         registry_path: Any = None,
                         action_log: Any = None) -> dict[str, Any]:
    """Re-run trust validation for a dependent provider record.

    Used to observe ``unavailable -> available`` recovery after a successful
    provisioning action.
    """
    import maya_trust

    stored = dict(record)
    return maya_trust.refresh(stored, probe={"available": bool(available)},
                              path=registry_path, action_log=action_log)


def _authorize(registry_path: Any, action_log: Any,
               user: str = "default",
               owner_approval: bool = True) -> dict[str, Any]:
    import maya_trust

    return maya_trust.authorize(
        capability=CAPABILITY, action=ACTION, context=CONTEXT, user=user,
        owner_approval=owner_approval, provider=PROVIDER,
        path=registry_path, action_log=action_log)


def provision(dependency: str, confirmation: str | None = None,
              execute: bool = False, runner: Callable[..., Any] | None = None,
              registry_path: Any = None, action_log: Any = None,
              dependent_record: dict[str, Any] | None = None,
              user: str = "default") -> dict[str, Any]:
    """Gated provisioning of one allowlisted dependency.

    Order of gates (each is a refusal that returns before any side effect):
    allowlist membership, owner confirmation token, trusted-registry
    authorization, explicit ``execute``, and a usable runner. On success the
    dependency is installed through ``runner`` and re-probed; when a
    ``dependent_record`` is supplied it is re-validated so its trust status
    can recover.
    """
    entry = descriptor(dependency)
    if entry is None:
        return {"schema": SCHEMA, "ok": False, "status": STATUS_UNKNOWN,
                "dependency": str(dependency), "executed": False,
                "reason": "dependency not in the provisioning allowlist"}
    dependency = entry["dependency"]
    module = entry["module"]

    expected = confirmation_token(dependency)
    if confirmation != expected:
        return {"schema": SCHEMA, "ok": False, "status": STATUS_CONFIRMATION,
                "dependency": dependency, "executed": False,
                "reason": "owner confirmation token required",
                "confirmation_token": expected}

    available_before = import_available(module)
    decision = _authorize(registry_path, action_log, user=user,
                          owner_approval=True)
    if decision.get("verdict") != "allowed":
        return {
            "schema": SCHEMA, "ok": False, "status": STATUS_REFUSED,
            "dependency": dependency, "executed": False,
            "available_before": available_before,
            "reason": "provisioning refused by trust gate",
            "authorization": decision,
        }

    if available_before:
        return {"schema": SCHEMA, "ok": True, "status": STATUS_ALREADY,
                "dependency": dependency, "executed": False,
                "available_before": True, "available_after": True,
                "authorization": decision}

    if not execute:
        return {
            "schema": SCHEMA, "ok": True, "status": STATUS_PREPARED,
            "dependency": dependency, "executed": False,
            "available_before": False, "available_after": False,
            "plan": plan(dependency),
            "authorization": decision,
            "reason": "execute=False; nothing installed",
        }

    if runner is None:
        return {"schema": SCHEMA, "ok": False, "status": STATUS_RUNNER,
                "dependency": dependency, "executed": False,
                "available_before": False,
                "reason": "no provisioning runner supplied",
                "authorization": decision}

    try:
        runner_result = runner(dict(entry))
    except Exception as exc:
        return {"schema": SCHEMA, "ok": False, "status": STATUS_FAILED,
                "dependency": dependency, "executed": False,
                "available_before": False,
                "reason": "runner raised: " + str(exc),
                "authorization": decision}

    available_after = import_available(module)
    status = STATUS_INSTALLED if available_after else STATUS_VALIDATION_FAILED
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": available_after,
        "status": status,
        "dependency": dependency,
        "module": module,
        "executed": True,
        "available_before": False,
        "available_after": available_after,
        "runner_result": runner_result,
        "authorization": decision,
    }
    if dependent_record is not None:
        stored = revalidate_dependent(dependent_record, available_after,
                                      registry_path=registry_path,
                                      action_log=action_log)
        result["dependent"] = {
            "provider": stored.get("provider"),
            "capability": stored.get("capability"),
            "status": stored.get("status"),
            "supported": bool((stored.get("verification") or {}).get("supported")),
        }
    return result
