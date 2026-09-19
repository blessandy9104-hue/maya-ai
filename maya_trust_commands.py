"""Runtime ``:trust`` command surface for the trusted-capability registry.

Read-only inspection over the registry that ``maya_trust`` maintains, plus a
narrow, confirmation-gated control path. This module never re-implements or
weakens trust: it renders the honest state the registry already holds.

Read-only:

- ``:trust`` / ``:trust list``    registry + capability inventory
- ``:trust show <capability>``    one capability's records and trust state
- ``:trust pending``              everything still unvalidated
- ``:trust revoked``              revocation tombstones
- ``:trust actions``              recent authorization decisions

Mutating (the trailing ``confirm`` token is mandatory; without it nothing is
written and the caller is told exactly what to type):

- ``:trust validate <capability> confirm``
- ``:trust grant <capability> confirm``
- ``:trust revoke <capability> confirm``

``grant`` restores a registry permission only; it never authorizes a runtime
action, and every action still passes through ``maya_trust.authorize`` before
execution. Secrets, tokens, credentials, and private source digests are never
rendered; identity is shown as provider/version plus whether a digest was
recorded.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import maya_trust as trust

SCHEMA = "trusted_capability.v1"

STATUS_TRUSTED = "available"
STATUS_PENDING = "pending_validation"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNTRUSTED = "untrusted"
STATUS_REVOKED = "revoked"

TRUSTED = "trusted"
NOT_TRUSTED = "not_trusted"

STATES = (STATUS_TRUSTED, STATUS_PENDING, STATUS_UNAVAILABLE, STATUS_UNTRUSTED,
          STATUS_REVOKED)

_SENSITIVE_KEYS = ("digest", "token", "secret", "credential", "password",
                   "passwd", "private_key", "api_key", "apikey", "auth_token")
_HEX = re.compile(r"[0-9a-fA-F]{32,}")
_SECRET_KV = re.compile(
    r"(?i)\b(" + "|".join(_SENSITIVE_KEYS) + r")\s*[:=]\s*\S+")

LEGEND = ("states: trusted=validated+permitted (execution still gated by "
          "authorize) | available | pending_validation=not validated | "
          "unavailable | untrusted | revoked")

USAGE = ("Use :trust, :trust list, :trust show <capability>, :trust pending, "
         ":trust revoked, :trust actions, or the confirmation-gated "
         ":trust validate|grant|revoke <capability> confirm.")


# ---------------------------------------------------------------------------
# Safe projections (never expose secrets, tokens, or source digests)
# ---------------------------------------------------------------------------

def _is_trusted(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    verification = record.get("verification")
    return (record.get("status") == STATUS_TRUSTED
            and isinstance(verification, dict)
            and verification.get("supported") is True)


def _state(record: dict[str, Any] | None) -> str:
    if not isinstance(record, dict):
        return STATUS_PENDING
    if record.get("revoked") is True or record.get("disabled") is True:
        return STATUS_REVOKED
    status = record.get("status")
    return status if status in STATES else STATUS_UNTRUSTED


def _scrub(value: Any) -> Any:
    """Redact secret-looking material from a free-text scalar.

    Never render an inline digest, token, or credential even if a record or a
    failure detail happens to embed one.
    """
    if not isinstance(value, str):
        return value
    value = _SECRET_KV.sub(r"\1=[redacted]", value)
    return _HEX.sub("[redacted-digest]", value)


def _safe_verification(record: dict[str, Any]) -> dict[str, Any]:
    verification = record.get("verification")
    if not isinstance(verification, dict):
        return {"supported": False, "status": STATUS_PENDING,
                "failed": [], "checks": []}
    failures = [c.get("name") for c in (verification.get("failures") or [])
                if isinstance(c, dict)]
    checks = [c.get("name") for c in (verification.get("checks") or [])
              if isinstance(c, dict)]
    return {
        "supported": verification.get("supported") is True,
        "status": verification.get("status", STATUS_PENDING),
        "failed": sorted(f for f in failures if f),
        "checks": sorted(c for c in checks if c),
    }


def _safe_identity(record: dict[str, Any]) -> dict[str, Any]:
    identity = record.get("identity") if isinstance(record.get("identity"),
                                                    dict) else {}
    digest = record.get("source_digest") or identity.get("source_digest")
    return {
        "provider": identity.get("provider") or record.get("provider"),
        "version": identity.get("version"),
        "source_digest_recorded": bool(digest),
    }


def safe_record(record: dict[str, Any] | None) -> dict[str, Any]:
    """A displayable view of one registry record with secrets stripped."""
    if not isinstance(record, dict):
        return {"state": STATUS_PENDING, "trusted": False,
                "reason": "no validated record"}
    perms = record.get("permissions") or {}
    approval = record.get("approval") or {}
    prepare = record.get("safe_prepare_only")
    scope = {"context": record.get("context")}
    if record.get("owner") is not None:
        scope["owner"] = str(record.get("owner"))
    scope["capability"] = record.get("capability")
    for extra in ("organization", "tenant", "workspace"):
        if record.get(extra) is not None:
            scope[extra] = record.get(extra)
    return {
        "capability": record.get("capability"),
        "provider": record.get("provider"),
        "state": _state(record),
        "trusted": _is_trusted(record),
        "scope": scope,
        "trust_basis": [_scrub(item) for item in (record.get("trust_basis") or [])],
        "permissions": sorted(a for a, ok in perms.items() if ok),
        "approval_required": sorted(a for a, cfg in approval.items()
                                    if isinstance(cfg, dict)
                                    and cfg.get("required")),
        "safe_prepare_only": sorted(prepare) if isinstance(
            prepare, (list, tuple, set, frozenset)) else [],
        "verification": _safe_verification(record),
        "identity": _safe_identity(record),
        "last_checked": record.get("last_checked"),
        "reason": _scrub(record.get("reason", "")),
    }


def _system_line(record: dict[str, Any]) -> str:
    view = safe_record(record)
    scope = view["scope"]
    scope_text = ",".join(f"{k}={scope[k]}" for k in
                          ("context", "owner", "capability", "organization",
                           "tenant", "workspace") if k in scope)
    trust_text = TRUSTED if view["trusted"] else NOT_TRUSTED
    return (f"{view['capability']} via {view['provider']}  "
            f"state={view['state']} trust={trust_text}  "
            f"scope={scope_text}  "
            f"verification={view['verification']['status']}  "
            f"approval={','.join(view['approval_required']) or 'none'}  "
            f"prepare_only={','.join(view['safe_prepare_only']) or 'none'}  "
            f"last_checked={view['last_checked']}")


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _newest(path: Path | str | None) -> dict[tuple[str, str], dict[str, Any]]:
    return trust.latest_records(path=path)


def _serving_records(capability: str,
                     path: Path | str | None) -> list[dict[str, Any]]:
    rows = [r for r in _newest(path).values()
            if r.get("capability") == capability]
    return sorted(rows, key=lambda r: str(r.get("provider")))


def _declared_for(capability: str) -> dict[str, Any] | None:
    for declared in (*trust.DECLARED_PROVIDERS, *trust.EXTERNAL_NOT_INSTALLED):
        if declared.get("capability") == capability:
            return declared
    return None


def render_registry(path: Path | str | None = None) -> str:
    overview = trust.registry_overview(path=path)
    counts = overview.get("counts", {})
    lines = ["Maya trusted-capability registry",
             f"schema: {overview.get('schema', SCHEMA)}",
             "counts: " + " ".join(
                 f"{name}={counts.get(name, 0)}" for name in
                 (STATUS_TRUSTED, STATUS_PENDING, STATUS_UNAVAILABLE,
                  STATUS_UNTRUSTED)),
             LEGEND, "", "capabilities:"]
    records = _newest(path)
    capabilities = overview.get("capabilities", {})
    if not capabilities:
        lines.append("  (none advertised)")
    for name in sorted(capabilities):
        state = capabilities[name]
        trust_text = TRUSTED if _is_trusted(
            _strongest_record(name, records)) else NOT_TRUSTED
        lines.append(f"  {name}: state={state} trust={trust_text}")
    lines.append("")
    lines.append("systems (validated applications / connectors / devices / "
                 "local services / external systems):")
    if not records:
        lines.append("  (none recorded; every listed capability is pending "
                     "validation)")
    for key in sorted(records):
        lines.append("  " + _system_line(records[key]))
    lines.append("")
    lines.append(LEGEND)
    return "\n".join(lines)


def _strongest_record(
        capability: str,
        records: dict[tuple[str, str], dict[str, Any]] | None = None,
        path: Path | str | None = None) -> dict[str, Any] | None:
    index = records if records is not None else _newest(path)
    rows = sorted((r for r in index.values()
                   if r.get("capability") == capability),
                  key=lambda r: str(r.get("provider")))
    if not rows:
        return None
    rank = {STATUS_TRUSTED: 0, STATUS_UNTRUSTED: 1, STATUS_UNAVAILABLE: 2,
            STATUS_REVOKED: 3, STATUS_PENDING: 4}
    return max(rows, key=lambda r: rank.get(_state(r), 4))


def render_show(capability: str, path: Path | str | None = None) -> str:
    if not capability:
        return "Use `:trust show <capability>`. " + USAGE
    rows = _serving_records(capability, path)
    if not rows:
        declared = _declared_for(capability)
        if declared is not None:
            return (f"{capability}: state={STATUS_PENDING} trust={NOT_TRUSTED}\n"
                    f"  declared provider {declared.get('provider')} has no "
                    "validated record yet; being listed never grants trust.")
        return (f"{capability}: state={STATUS_PENDING} trust={NOT_TRUSTED}\n"
                "  not recorded by any provider; not validated.")
    blocks = [f"{capability}: {len(rows)} provider record(s)"]
    for record in rows:
        view = safe_record(record)
        trust_text = TRUSTED if view["trusted"] else NOT_TRUSTED
        scope = view["scope"]
        blocks.append(f"  provider={view['provider']} state={view['state']} "
                      f"trust={trust_text}")
        blocks.append("    scope=" + ",".join(
            f"{k}={scope[k]}" for k in ("context", "owner", "capability",
                                        "organization", "tenant", "workspace")
            if k in scope))
        blocks.append(f"    trust_basis={view['trust_basis']}")
        blocks.append(f"    permissions={view['permissions']}")
        blocks.append(f"    approval_required={view['approval_required']}")
        blocks.append(f"    safe_prepare_only={view['safe_prepare_only']}")
        blocks.append(f"    verification={view['verification']}")
        blocks.append(f"    identity={view['identity']}")
        blocks.append(f"    last_checked={view['last_checked']}")
        if view["reason"]:
            blocks.append(f"    reason={view['reason']}")
    blocks.append("  note: trust is shown as trusted only when validation "
                  "confirmed availability; execution still passes through "
                  "authorize().")
    return "\n".join(blocks)


def render_pending(path: Path | str | None = None) -> str:
    overview = trust.registry_overview(path=path)
    pending = sorted(name for name, state in
                     (overview.get("capabilities") or {}).items()
                     if state == STATUS_PENDING)
    lines = [f"pending_validation capabilities ({len(pending)}):"]
    if not pending:
        lines.append("  (none)")
    for name in pending:
        lines.append(f"  {name}: state={STATUS_PENDING} trust={NOT_TRUSTED} "
                     "(not validated)")
    lines.append("Note: a capability that appears in an inventory but has no "
                 "validated provider record is pending, never trusted.")
    return "\n".join(lines)


def render_revoked(path: Path | str | None = None) -> str:
    rows = [r for r in _newest(path).values() if _state(r) == STATUS_REVOKED]
    rows.sort(key=lambda r: (str(r.get("capability")), str(r.get("provider"))))
    lines = [f"revoked systems ({len(rows)}):"]
    if not rows:
        lines.append("  (none)")
    for record in rows:
        lines.append(f"  {record.get('capability')} via "
                     f"{record.get('provider')}  state={STATUS_REVOKED} "
                     f"revoke_reason={_scrub(record.get('revoke_reason', ''))}  "
                     f"last_checked={record.get('last_checked')}")
    lines.append("Note: a revocation is a tombstone; routine validation can "
                 "never restore trust, only an explicit grant.")
    return "\n".join(lines)


def _path(path: Path | str | None, default: Path) -> Path:
    if path is None:
        return default
    return path if isinstance(path, Path) else Path(path)


def render_actions(path: Path | str | None = None, tail: int = 10) -> str:
    log = _path(path, trust.ACTION_LOG)
    lines = [f"trust action log: {log}"]
    if not log.exists():
        lines.append("  no action records")
        return "\n".join(lines)
    rows = []
    with log.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                rows.append({"malformed": True})
    rows = rows[-max(1, tail):] if tail else rows
    lines.append(f"  {len(rows)} most recent:")
    for row in rows:
        if row.get("malformed"):
            lines.append("  (malformed action record)")
            continue
        lines.append(
            f"  capability={row.get('capability')} action={row.get('action')} "
            f"context={row.get('context')} user={row.get('user')} "
            f"decision={row.get('decision', row.get('verdict'))} "
            f"approval_required={row.get('approval_required')} "
            f"owner_approval={row.get('owner_approval')} "
            f"verification_supported={row.get('verification_supported')} "
            f"result={row.get('result')} timestamp={row.get('timestamp')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Confirmation-gated control path
# ---------------------------------------------------------------------------

def _confirmation_required(verb: str, capability: str) -> str:
    return (f"Explicit confirmation required. Use "
            f"`:trust {verb} {capability or '<capability>'} confirm`. "
            "No change was made.")


def _mutate(verb: str, capability: str, path: Path | str | None,
            probe: dict[str, Any] | None) -> str:
    declared = _declared_for(capability)
    if declared is None:
        existing = _serving_records(capability, path)
        if not existing:
            return (f"{capability}: no declared or recorded provider; nothing "
                    "to change.")
        provider = str(existing[0].get("provider"))
    else:
        provider = str(declared.get("provider"))

    if verb == "revoke":
        trust.revoke(capability, provider,
                     reason="revoked by user via :trust", path=path)
        record = trust.lookup(capability, provider=provider, path=path)
        return (f"revoked {capability} via {provider}: "
                f"state={_state(record)} trust={NOT_TRUSTED}\n"
                "A revocation tombstone can only be lifted by an explicit "
                "grant; routine validation cannot restore it.")

    record = dict(declared) if declared is not None else dict(
        _serving_records(capability, path)[0])
    if verb == "validate":
        stored = trust.refresh(record, probe=probe, path=path)
        return (f"re-validated {capability} via {provider}: "
                f"state={_state(stored)} trust="
                f"{TRUSTED if _is_trusted(stored) else NOT_TRUSTED}\n"
                "Availability is confirmed only by a live probe; without it "
                "the provider stays not trusted. Execution is always gated by "
                "authorize().")

    stored = trust.grant(record, probe=probe, path=path)
    return (f"grant {capability} via {provider}: state={_state(stored)} "
            f"trust={TRUSTED if _is_trusted(stored) else NOT_TRUSTED}\n"
            "A grant restores the registry permission only; every runtime "
            "action still passes through authorize() before execution.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def trust_command(raw_text: str, registry_path: Path | str | None = None,
                  actions_path: Path | str | None = None,
                  probe: dict[str, Any] | None = None,
                  tail: int = 10) -> str:
    """Dispatch one ``:trust`` command. Always returns a string."""
    parts = (raw_text or "").strip().split()
    sub = parts[1].lower() if len(parts) > 1 else "list"
    arg = parts[2] if len(parts) > 2 else ""
    confirmed = len(parts) > 3 and parts[-1].lower() == "confirm"

    if sub in ("list", ""):
        return render_registry(path=registry_path)
    if sub == "show":
        return render_show(arg, path=registry_path)
    if sub == "pending":
        return render_pending(path=registry_path)
    if sub == "revoked":
        return render_revoked(path=registry_path)
    if sub == "actions":
        count = int(arg) if arg.isdigit() else tail
        return render_actions(path=actions_path, tail=count)
    if sub in ("validate", "grant", "revoke"):
        if not arg:
            return _confirmation_required(sub, "")
        if not confirmed:
            return _confirmation_required(sub, arg)
        return _mutate(sub, arg, registry_path, probe)
    return "Unknown :trust subcommand. " + USAGE
