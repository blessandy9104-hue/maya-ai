"""Trusted-capability registry for Maya.

A trusted application is never trusted merely because it is installed,
reachable, previously used, or listed in configuration. Before Maya relies on
any application, connector, device, local service, or external system for
execution it validates:

- identity and provenance of the provider (source digest / declared origin)
- current availability
- declared capabilities and permission scope
- personal / work / shared context
- supported actions and per-action permissions
- approval requirements
- input and output boundaries
- authentication and authorization state
- result-confirmation ability
- failure and exception behaviour
- whether it can access or expose information outside its assigned scope

A provider is ``available`` only when the full validation battery reports
``verification.supported == True`` and every check passes. Any record that is
missing, disabled, revoked, capability-changed, unauthenticated, out-of-scope,
unverified, timing out, malformed, contradictory, or cross-context is marked
``untrusted`` or ``unavailable`` and is refused for autonomous execution.

A record may declare an explicit set of safe *prepare-only* actions (for
example ``create_draft``) that are never execution. Those may be offered as
preparation when the record itself can be verified to be read-only and
in-project; the default prepare set is empty, so nothing is offered unless the
record says so.

Every decision is written to the trust action log. The registry composes with
the existing capability registries (``maya_capabilities`` display registry and
``maya_identity.capability_registry`` math slugs) by exposing a per-capability
trust status overlay; it does not modify those authoritative inventories.

State: the registry file is a JSONL of validated records. The runtime default
path is ``trusted_capabilities.jsonl`` in the project root; tests inject a
temporary path so the real registry is never written by a suite.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

import maya_trust_cache as _trust_cache

ROOT = Path(__file__).resolve().parent
TRUST_FILE = ROOT / "trusted_capabilities.jsonl"
ACTION_LOG = ROOT / "maya_trust_actions.jsonl"

# Caches ONLY parsed registry metadata. It never stores an authorization
# decision; ``authorize`` still evaluates current status/owner/context/scope/
# approval/revocation on every request. See ``maya_trust_cache`` for the
# invalidation policy.
_REGISTRY_CACHE = _trust_cache.TrustMetadataCache()

# Canonical statuses. ``available`` is granted ONLY by successful validation.
AVAILABLE = "available"
UNAVAILABLE = "unavailable"
UNTRUSTED = "untrusted"
PENDING_VALIDATION = "pending_validation"
STATUSES = (AVAILABLE, UNAVAILABLE, UNTRUSTED)

# Known contexts. A record must declare exactly one.
CONTEXTS = ("personal", "work", "shared")

# Known action vocabulary. A permission/action name outside this set makes the
# record malformed (fail closed) because it cannot be bounded or reviewed.
ACTION_VOCABULARY = frozenset({
    "generate_text", "list_available", "read_status", "read_evidence",
    "create_draft", "send_message", "confirm_booking", "edit_calendar",
    "delete_item", "activate_skill", "control_device", "read_context",
    "write_memory", "export_report", "open_link", "query_web",
    "install_dependency",
})

REQUIRED_FIELDS = ("capability", "provider", "context",
                   "permissions", "trust_basis")

# Installation-only providers that are present but were never validated are
# probed by the default availability probe as present yet still UNTRUSTED.
DECLARED_PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "capability": "language_model",
        "provider": "local_model",
        "context": "personal",
        "status": UNTRUSTED,
        "permissions": {"generate_text": True, "read_status": True},
        "actions": ("generate_text", "read_status"),
        "approval": {"generate_text": {"required": False},
                     "read_status": {"required": False}},
        "boundaries": {"input": "localhost", "output": "project",
                       "cross_context_denied": True},
        "auth": {"method": "loopback", "state": "valid"},
        "result_confirmation": {"supported": True, "method": "session_sync"},
        "failure": {"fail_closed": True},
        "trust_basis": ["locally installed", "local network only"],
        "identity": {"provider": "local_model", "version": "1",
                     "source_digest": None},
    },
    {
        "capability": "evidence_retrieval",
        "provider": "local_evidence_store",
        "context": "personal",
        "status": UNTRUSTED,
        "permissions": {"read_evidence": True, "list_available": True},
        "actions": ("read_evidence", "list_available"),
        "approval": {"read_evidence": {"required": False},
                     "list_available": {"required": False}},
        "boundaries": {"input": "project", "output": "project",
                       "cross_context_denied": True},
        "auth": {"method": "local", "state": "valid"},
        "result_confirmation": {"supported": True, "method": "content_digest"},
        "failure": {"fail_closed": True},
        "trust_basis": ["locally installed", "single writer ownership"],
        "identity": {"provider": "local_evidence_store", "version": "1",
                     "source_digest": None},
    },
)

# External application surfaces that are NOT installed. They are recorded as
# UNAVAILABLE with a truthful reason and no execution. Safe prepare-only is
# explicitly disabled (empty set) for all of them.
EXTERNAL_NOT_INSTALLED: tuple[dict[str, Any], ...] = (
    {
        "capability": "calendar_booking",
        "provider": "local_calendar",
        "context": "personal",
        "status": UNAVAILABLE,
        "permissions": {"create_draft": False, "confirm_booking": False},
        "actions": ("create_draft", "confirm_booking"),
        "approval": {"create_draft": {"required": True},
                     "confirm_booking": {"required": True}},
        "boundaries": {"input": "none", "output": "none",
                       "cross_context_denied": True},
        "auth": {"method": "none", "state": "invalid"},
        "result_confirmation": {"supported": False},
        "failure": {"fail_closed": True},
        "trust_basis": [],
        "identity": {"provider": "local_calendar", "version": None,
                     "source_digest": None},
        "reason": "connector not installed; not validated; cannot execute",
    },
)

# Default: no prepare-only actions are ever offered unless a record defines
# this explicit set (which is never execution).
SAFE_PREPARE_ONLY_DEFAULT: frozenset[str] = frozenset()

_now = time.time


def set_clock(clock: Callable[[], float]) -> None:
    """Inject a deterministic clock (``None`` restores ``time.time``)."""
    global _now
    _now = clock if clock is not None else time.time


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _source_digest(identity: dict[str, Any], provider: str) -> str | None:
    """Digest of the identity block only (provenance of the origin record)."""
    if not isinstance(identity, dict):
        return None
    block = {k: identity.get(k) for k in
             ("provider", "version", "source_digest")}
    block["capability_provider"] = provider
    return _digest(block)


# ---------------------------------------------------------------------------
# Validation battery
# ---------------------------------------------------------------------------

class TrustCheck:
    """One named check in the validation battery."""

    __slots__ = ("name", "ok", "detail")

    def __init__(self, name: str, ok: bool, detail: str = "") -> None:
        self.name = name
        self.ok = bool(ok)
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


def _well_formed(record: dict[str, Any]) -> list[str]:
    """Structural malformation reasons (fail closed on any)."""
    reasons = []
    if not isinstance(record, dict):
        return ["record is not a dict"]
    for field in REQUIRED_FIELDS:
        if field not in record:
            reasons.append(f"missing required field {field!r}")
    if "actions" not in record:
        reasons.append("missing supported actions list")
    if not isinstance(record.get("permissions"), dict):
        reasons.append("permissions is not a dict")
    if record.get("context") not in CONTEXTS:
        reasons.append(f"context not in {CONTEXTS}")
    perms = record.get("permissions") or {}
    declared_actions = set(record.get("actions") or ())
    unknown_perms = set(perms) - ACTION_VOCABULARY
    if unknown_perms:
        reasons.append("permissions reference unregistered actions: "
                       + ", ".join(sorted(unknown_perms)))
    unknown_actions = declared_actions - ACTION_VOCABULARY
    if unknown_actions:
        reasons.append("actions reference unregistered actions: "
                       + ", ".join(sorted(unknown_actions)))
    # Contradiction: an action listed as a granted permission must be a
    # supported action, and a supported action must have a permission entry.
    granted = {a for a, ok in perms.items() if ok}
    if granted - declared_actions:
        reasons.append("granted permission not declared as supported action: "
                       + ", ".join(sorted(granted - declared_actions)))
    if declared_actions - set(perms):
        reasons.append("supported action without permission entry: "
                       + ", ".join(sorted(declared_actions - set(perms))))
    return reasons


def _identity_ok(record: dict[str, Any], probe: dict[str, Any] | None) -> str:
    identity = record.get("identity")
    if not isinstance(identity, dict) or not identity.get("provider"):
        return "provider identity not declared"
    declared = identity.get("source_digest") or _source_digest(identity, record["provider"])
    if probe is not None:
        observed = probe.get("source_digest")
        if observed is None:
            return ""
        if observed != declared:
            return "provider source digest mismatch"
    return ""


def _auth_ok(record: dict[str, Any]) -> str:
    auth = record.get("auth") or {}
    if auth.get("state") not in ("valid", "not_required"):
        return "authentication state not valid"
    if not auth.get("method"):
        return "authentication method not declared"
    return ""


def _boundaries_ok(record: dict[str, Any]) -> str:
    bounds = record.get("boundaries") or {}
    if not isinstance(bounds, dict) or not bounds.get("input") or not bounds.get("output"):
        return "input/output boundaries not declared"
    if bounds.get("cross_context_denied") is not True:
        return "cross-context access not denied"
    return ""


def _confirmation_ok(record: dict[str, Any]) -> str:
    conf = record.get("result_confirmation") or {}
    if conf.get("supported") is not True:
        return "result confirmation not supported"
    if not conf.get("method"):
        return "result confirmation method not declared"
    return ""


def _failure_ok(record: dict[str, Any]) -> str:
    failure = record.get("failure") or {}
    if failure.get("fail_closed") is not True:
        return "provider does not fail closed"
    return ""


def _approval_ok(record: dict[str, Any]) -> str:
    """Approval map must be well-formed for every action the record names.

    Whether a given action actually requires owner approval is enforced at
    authorization time (``authorize``), not here; this check only rejects
    malformed approval declarations so a record cannot smuggle an
    unmanageable approval surface.
    """
    approval = record.get("approval") or {}
    for action, cfg in approval.items():
        if not isinstance(cfg, dict) or "required" not in cfg:
            return f"approval entry malformed for {action!r}"
    return ""


def _cross_context_ok(record: dict[str, Any], probe: dict[str, Any] | None) -> str:
    if probe is None:
        return ""
    if probe.get("cross_context_attempted") and not probe.get("cross_context_denied"):
        return "provider exposed another context on request"
    if probe.get("context_exposed") not in (None, record.get("context")):
        return f"provider exposed context {probe.get('context_exposed')!r}"
    return ""


def _probe_failure(probe: dict[str, Any] | None) -> str:
    if probe is None:
        return ""
    if probe.get("timed_out"):
        return "availability probe timed out"
    if probe.get("raised"):
        return "availability probe raised: " + str(probe.get("raised"))
    return ""


def _signal_samples(record: dict[str, Any],
                    probe: dict[str, Any] | None) -> Any:
    """Locate the declared spectral evidence for a record, if any.

    A record may carry the observed series as a top-level ``signal`` or inside
    a ``frequency`` block; the probe may also supply it as an observed fact.
    ``None`` means no spectral evidence was declared (the check is then
    not-applicable and passes), so adding this check stays strictly additive.
    """
    frequency = record.get("frequency")
    candidates = [record.get("signal")]
    if isinstance(frequency, dict):
        candidates.append(frequency.get("signal"))
    if isinstance(probe, dict):
        candidates.append(probe.get("signal"))
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return None


def _signal_ok(record: dict[str, Any],
               probe: dict[str, Any] | None) -> str:
    """Frequency-domain integrity of declared spectral evidence.

    Not-applicable (no signal declared) passes. A declared signal must clear
    the architectural frequency gate — enough coherent periodic content and
    bounded broadband noise — or the record fails closed.
    """
    samples = _signal_samples(record, probe)
    if samples is None:
        return ""
    frequency = record.get("frequency")
    config = frequency if isinstance(frequency, dict) else {}
    try:
        from maya_frequency import signal_quality
    except Exception as exc:  # pragma: no cover - defensive fail-closed
        return "frequency layer unavailable: " + str(exc)
    kwargs: dict[str, Any] = {}
    for key in ("min_snr_db", "min_periodicity", "max_noise",
                "sample_rate", "min_samples"):
        if key in config and config[key] is not None:
            kwargs[key] = config[key]
    quality = signal_quality(samples, **kwargs)
    if quality.get("ok"):
        return ""
    return ("spectral evidence insufficient: "
            + str(quality.get("reason") or "unclassified"))


def validate_record(record: dict[str, Any],
                    probe: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the full validation battery for one provider record.

    ``probe`` is an optional dict of observed runtime facts about the provider
    (availability, source digest, timeout/exception markers, cross-context
    attempts). ``None`` uses only the declared record (identity/scope check).
    The result is a ``verification`` dict recording every check and the
    resulting status. Fail-closed: any check failure yields ``untrusted``
    unless the provider is factually absent (``unavailable``).
    """
    checks: list[TrustCheck] = []
    structural = _well_formed(record)
    checks.append(TrustCheck("structural", not structural, "; ".join(structural)))

    reason_identity = _identity_ok(record, probe)
    checks.append(TrustCheck("identity_provenance", not reason_identity,
                             reason_identity))
    checks.append(TrustCheck("auth_state", not _auth_ok(record), _auth_ok(record)))
    checks.append(TrustCheck("boundaries", not _boundaries_ok(record),
                             _boundaries_ok(record)))
    checks.append(TrustCheck("result_confirmation",
                             not _confirmation_ok(record),
                             _confirmation_ok(record)))
    checks.append(TrustCheck("failure_behavior", not _failure_ok(record),
                             _failure_ok(record)))
    appr = _approval_ok(record)
    checks.append(TrustCheck("approval_requirements", not appr, appr))
    cross = _cross_context_ok(record, probe)
    checks.append(TrustCheck("cross_context", not cross, cross))
    probe_fail = _probe_failure(probe)
    checks.append(TrustCheck("availability_probe", not probe_fail, probe_fail))
    availability_confirmed = (probe is not None and probe.get("available") is True)
    checks.append(TrustCheck("availability_confirmed", availability_confirmed,
                             "availability not confirmed by probe"))
    revoked = record.get("revoked") is True or record.get("disabled") is True
    checks.append(TrustCheck("not_revoked", not revoked,
                             "provider revoked or disabled"))
    signal_reason = _signal_ok(record, probe)
    checks.append(TrustCheck("signal_integrity", not signal_reason,
                             signal_reason))

    failed = [c for c in checks if not c.ok]
    present = probe is not None and probe.get("available") is False
    if present:
        status = UNAVAILABLE
    elif failed:
        status = UNTRUSTED
    else:
        status = AVAILABLE

    return {
        "supported": status == AVAILABLE,
        "status": status,
        "checks": [c.as_dict() for c in checks],
        "failures": [c.as_dict() for c in failed],
    }


def _revoked_keys(path: Path | str | None) -> set[tuple[str, str]]:
    """Keys (provider, capability) whose NEWEST record is a revocation
    tombstone. Once an explicit grant supersedes the tombstone, the key is no
    longer revoked and the provider re-enters the normal validation lifecycle.
    """
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in load_registry(path=path):
        if not isinstance(row, dict) or row.get("malformed"):
            continue
        key = (str(row.get("provider") or "?"),
               str(row.get("capability") or "?"))
        newest[key] = row
    return {key for key, row in newest.items() if row.get("revoked") is True}


def refresh(record: dict[str, Any],
            probe: dict[str, Any] | None = None,
            path: Path | None = None,
            action_log: Path | None = None) -> dict[str, Any]:
    """Validate a record and persist it with ``status``/``verification``/
    ``last_checked``. Returns the stored record. Immutable on failure: a
    provider that fails validation is recorded ``untrusted``/``unavailable``.
    A provider under an active revocation (newest record is a tombstone) can
    never be promoted to ``available`` by routine re-validation; only an
    explicit ``grant`` (``granted: True``) supersedes a tombstone and returns
    the provider to the normal lifecycle.
    """
    verification = validate_record(record, probe)
    stored = dict(record)
    stored["status"] = verification["status"]
    stored["verification"] = verification
    stored["last_checked"] = _now()
    key = (str(stored.get("provider") or "?"),
           str(stored.get("capability") or "?"))
    if (stored["status"] == AVAILABLE
            and record.get("granted") is not True
            and key in _revoked_keys(path)):
        stored["status"] = UNTRUSTED
        stored["revoked_pending_grant"] = True
        stored["reason"] = "revoked; explicit grant required to restore trust"
        verification["supported"] = False
        verification["status"] = UNTRUSTED
    if stored["status"] != AVAILABLE and "reason" not in stored:
        stored["reason"] = ("validation failed: "
                            + "; ".join(f["detail"] or f["name"]
                                        for f in verification["failures"])
                            or "provider not validated")
    store_record(stored, path=path)
    return stored


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def _as_path(path: Path | str | None, default: Path) -> Path:
    if path is None:
        return default
    return path if isinstance(path, Path) else Path(path)


def load_registry(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load all records from the JSONL registry (absent file -> empty list).

    Reads through ``_REGISTRY_CACHE``, which caches only parsed metadata and
    validates it on every access (explicit mutation, file identity/size/mtime,
    content hash, malformed transition, TTL). The returned list is a fresh list
    of the parsed row dicts; callers must treat the rows as read-only.
    """
    p = _as_path(path, TRUST_FILE)
    rows = _REGISTRY_CACHE.rows(p)
    # Fresh list of independent top-level row copies: a caller mutating a
    # returned row can never corrupt the cached metadata.
    return [dict(row) if isinstance(row, dict) else row for row in rows]


def store_record(record: dict[str, Any], path: Path | str | None = None) -> None:
    p = _as_path(path, TRUST_FILE)
    # Invalidate before and after the append so no concurrent reader can serve
    # metadata that predates this mutation.
    _REGISTRY_CACHE.invalidate()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False)
                     + "\n")
    _REGISTRY_CACHE.invalidate()


# ---------------------------------------------------------------------------
# Cache control (additive diagnostics/ops surface; never affects decisions)
# ---------------------------------------------------------------------------

def cache_stats() -> dict[str, Any]:
    """Bounded, content-free counters describing the metadata cache."""
    return _REGISTRY_CACHE.stats()


def cache_invalidate() -> int:
    """Force the next registry read to re-parse (used after out-of-band
    mutations). Called automatically by ``store_record``."""
    return _REGISTRY_CACHE.invalidate()


def cache_reset() -> None:
    """Drop all cached metadata and counters (runtime/test reset)."""
    _REGISTRY_CACHE.reset()


def cache_configure(**kwargs: Any) -> None:
    """Adjust cache policy (``ttl_seconds``, ``max_entries``,
    ``verify_content``, ``enabled``, ``clock``). Never weakens authorization:
    decisions are always recomputed from the returned metadata."""
    _REGISTRY_CACHE.configure(**kwargs)


def latest_records(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Index of the newest record per (provider, capability) key."""
    index: dict[str, dict[str, Any]] = {}
    for row in load_registry(path=path):
        if not isinstance(row, dict) or row.get("malformed"):
            continue
        key = (str(row.get("provider") or "?"), str(row.get("capability") or "?"))
        index[key] = row
    return index


def lookup(capability: str, provider: str | None = None,
           path: Path | str | None = None) -> dict[str, Any] | None:
    """Most recent record for a capability (optionally scoped by provider)."""
    rows = load_registry(path=path)
    for row in reversed(rows):
        if not isinstance(row, dict) or row.get("malformed"):
            continue
        if row.get("capability") != capability:
            continue
        if provider is not None and row.get("provider") != provider:
            continue
        return row
    return None


def _known_capability_names() -> set[str]:
    """Union of the authoritative capability inventories (math slugs plus the
    display-group labels). Fails open to an empty set so the overlay can never
    hard-fail if an inventory is temporarily unimportable."""
    names: set[str] = set()
    try:
        from maya_identity import capability_registry as canon
        names |= set(getattr(canon, "CAPABILITY_REGISTRY", {}) or {})
    except Exception:
        pass
    try:
        import maya_capabilities as display
        groups = getattr(display, "CAPABILITY_REGISTRY", ()) or ()
        for group in groups:
            if isinstance(group, (list, tuple)) and group:
                names.add(str(group[0]))
    except Exception:
        pass
    return names


# Which trust providers serve which advertised inventory capabilities. The
# overlay resolves a capability name to the STRONGEST deny status among the
# records of its serving providers; a served-but-unrecorded name stays
# ``pending_validation``.
PROVIDER_SERVES_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "local_model": ("conversation",),
    "local_evidence_store": ("research", "world model", "evidence drilldown"),
    "local_calendar": (),
}


def _deny_rank(status: str) -> int:
    return {AVAILABLE: 0, UNTRUSTED: 1, UNAVAILABLE: 2,
            PENDING_VALIDATION: 3}[status]


def registry_overview(path: Path | str | None = None) -> dict[str, Any]:
    """Trust-status overlay for the capability inventories (read-only).

    Returns two views plus counts:

    - ``systems``: per recorded provider-capability the trust status with a
      reference to its provider, verification supported flag, and
      ``last_checked`` — the trusted-application record surface.
    - ``capabilities``: every advertised inventory capability (math slugs from
      ``maya_identity.capability_registry`` and display groups from
      ``maya_capabilities``) resolved to a trust status via
      ``PROVIDER_SERVES_CAPABILITIES``. A name served by a recorded provider
      takes the strongest deny status among its servers; a served but
      unrecorded name, and any name that is merely listed, stays
      ``pending_validation`` — being advertised never grants availability.
    """
    rows = load_registry(path=path)
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("malformed") is not True:
            newest[(str(row.get("provider") or "?"),
                    str(row.get("capability") or "?"))] = row
    systems: dict[str, dict[str, Any]] = {}
    for (provider, capability), row in newest.items():
        systems[capability] = {
            "provider": provider,
            "status": row.get("status", PENDING_VALIDATION),
            "verification_supported": bool(isinstance(row.get("verification"),
                                                      dict)
                                           and row["verification"].get(
                                               "supported") is True),
            "last_checked": row.get("last_checked"),
        }

    servers_by_name: dict[str, list[str]] = {}
    for provider, names in PROVIDER_SERVES_CAPABILITIES.items():
        for name in names:
            servers_by_name.setdefault(name, []).append(provider)
    provider_status: dict[str, str] = {}
    for (provider, _capability), row in newest.items():
        status = row.get("status", PENDING_VALIDATION)
        if status not in STATUSES:
            status = PENDING_VALIDATION
        if (provider not in provider_status
                or _deny_rank(status) > _deny_rank(provider_status[provider])):
            provider_status[provider] = status

    capabilities: dict[str, str] = {}
    for name in _known_capability_names():
        servers = servers_by_name.get(name, ())
        statuses = [provider_status[p] for p in servers
                    if p in provider_status]
        if not statuses:
            capabilities[name] = PENDING_VALIDATION
        else:
            capabilities[name] = max(statuses, key=_deny_rank)

    counts = {s: 0 for s in STATUSES + (PENDING_VALIDATION,)}
    for status in capabilities.values():
        counts[status] += 1
    return {"schema": "trusted_capability.v1",
            "systems": dict(sorted(systems.items())),
            "capabilities": dict(sorted(capabilities.items())),
            "counts": counts}


# ---------------------------------------------------------------------------
# Authorization decisions + action records
# ---------------------------------------------------------------------------

def _safe_prepare_only(record: dict[str, Any]) -> frozenset[str]:
    allowed = record.get("safe_prepare_only")
    if isinstance(allowed, (list, tuple, frozenset, set)):
        return frozenset(allowed) & ACTION_VOCABULARY
    return frozenset()


def authorize(capability: str, action: str, context: str,
              user: str = "default", owner_approval: bool = False,
              prepare_only: bool = False, provider: str | None = None,
              path: Path | str | None = None,
              action_log: Path | str | None = None) -> dict[str, Any]:
    """Gate one action against the trusted registry before execution.

    Rules (all must hold for ``allowed``):
    - a record for the capability must exist and be validated (status
      ``available``); missing/revoked/untrusted/unavailable -> refused;
    - the action must be within the record's permission scope;
    - a revoked/disputed grant (a later record that denies the action) is
      observed as the newest record wins and the action is refused;
    - execution actions must not be a prepare-only request;
    - the requested context must equal the record's declared context;
    - if the record marks the action approval-required, ``owner_approval``
      must be true, else the decision is ``requires_approval``;

    ``prepare_only=True`` may only run when the record declares the action in
    its explicit ``safe_prepare_only`` set; the default permits nothing.
    Every decision is appended to the action log.
    """
    record = lookup(capability, provider=provider, path=path)

    def _d(verdict, reasons, prepare_only=False):
        return _decision(capability, action, context, user, verdict, reasons,
                         prepare_only, action_log,
                         record=record, owner_approval=owner_approval)

    if record is None or record.get("malformed"):
        return _d("refused", ["no validated record for capability"])
    status = record.get("status")
    if status != AVAILABLE:
        return _d("refused", [f"capability status {status!r}"])
    owner = record.get("owner")
    if owner is not None and str(user) != str(owner):
        return _d("refused", ["user not authorized for this context"])
    if record.get("context") != context:
        return _d("refused", ["context mismatch"])
    perms = record.get("permissions") or {}
    if not perms.get(action):
        return _d("refused", ["action outside permission scope"])
    approval = (record.get("approval") or {})
    cfg = approval.get(action) or {}
    if cfg.get("required") and not owner_approval:
        return _d("requires_approval",
                  ["owner approval required for action"],
                  prepare_only=(action in _safe_prepare_only(record)))
    prepare_allowed = action in _safe_prepare_only(record)
    if prepare_only and not prepare_allowed:
        return _d("refused", ["prepare-only not declared safe for action"])
    if prepare_only and prepare_allowed:
        return _d("prepare_only", ["safe prepare-only; not execution"],
                  prepare_only=True)
    verified = isinstance(record.get("verification"), dict) and \
        record["verification"].get("supported") is True
    if not verified:
        return _d("refused", ["verification not supported"])
    # Newest-record-wins: the record looked up is already the latest; but a
    # later record that revokes this provider would shadow it above. Here we
    # require the record we found to be the newest to prevent stale trust.
    newest = lookup(capability, provider=record.get("provider"), path=path)
    if newest is None or newest.get("last_checked") != record.get("last_checked"):
        return _d("refused", ["trust record superseded"])
    return _d("allowed", [f"validated provider {record.get('provider')}"])


# Verdict -> result label. ``authorize`` is a gate: an allowed verdict is an
# authorization, never an execution, so the result never claims a committed
# external action.
_RESULT_BY_VERDICT = {
    "allowed": "authorized_not_executed",
    "prepare_only": "prepared_not_committed",
    "requires_approval": "blocked_pending_approval",
    "refused": "blocked",
}


def _decision(capability: str, action: str, context: str, user: str,
              verdict: str, reasons: list[str], prepare_only: bool,
              path: Path | str | None,
              record: dict[str, Any] | None = None,
              owner_approval: bool = False) -> dict[str, Any]:
    approval = (record.get("approval") or {}) if isinstance(record, dict) else {}
    cfg = approval.get(action) or {}
    verification = record.get("verification") if isinstance(record, dict) else None
    row = {
        "timestamp": _now(),
        "capability": capability,
        "action": action,
        "context": context,
        "user": user,
        "verdict": verdict,
        "decision": verdict,
        "prepare_only": prepare_only,
        "approval_required": bool(cfg.get("required")),
        "owner_approval": bool(owner_approval),
        "verification_supported": bool(isinstance(verification, dict)
                                       and verification.get("supported") is True),
        "status": (record.get("status") if isinstance(record, dict)
                   else PENDING_VALIDATION),
        "result": _RESULT_BY_VERDICT.get(verdict, "blocked"),
        "reasons": reasons,
    }
    log = _as_path(path, ACTION_LOG)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return row


def record_action(capability: str, action: str, context: str,
                  user: str, verdict: str, detail: str = "",
                  path: Path | str | None = None) -> dict[str, Any]:
    """Explicit audit row, separate from the decision log, for action records
    and independent validation reports."""
    row = {
        "timestamp": _now(),
        "capability": capability,
        "action": action,
        "context": context,
        "user": user,
        "verdict": verdict,
        "detail": detail,
    }
    log = _as_path(path, ACTION_LOG)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return row


# ---------------------------------------------------------------------------
# Revocation: a tombstone that can never be auto-regranted.
# ---------------------------------------------------------------------------

def revoke(capability: str, provider: str, reason: str,
           path: Path | str | None = None,
           action_log: Path | str | None = None) -> dict[str, Any]:
    """Revoke/disable a capability's trust. Writes a tombstone record with
    status ``untrusted``; ``validate_record`` treats ``revoked``/``disabled``
    as a failing check, so validation can never restore it accidentally.
    The tombstone is the newest record, so authorization immediately refuses.
    """
    tomb = {
        "capability": capability,
        "provider": provider,
        "context": CONTEXTS[0],
        "status": UNTRUSTED,
        "permissions": {},
        "actions": (),
        "approval": {},
        "boundaries": {"input": "none", "output": "none",
                       "cross_context_denied": True},
        "auth": {"method": "none", "state": "invalid"},
        "result_confirmation": {"supported": False},
        "failure": {"fail_closed": True},
        "trust_basis": [],
        "identity": {"provider": provider, "version": None,
                     "source_digest": None},
        "revoked": True,
        "revoke_reason": reason,
        "last_checked": _now(),
    }
    refresh(tomb, probe=None, path=path, action_log=action_log)
    return tomb


def grant(record: dict[str, Any], probe: dict[str, Any] | None = None,
          path: Path | str | None = None,
          action_log: Path | str | None = None,
          owner_approval: str = "explicit") -> dict[str, Any]:
    """Explicitly re-establish trust for a revoked/disabled provider.

    Only this call can supersede a revocation tombstone. The supplied record
    must still pass the full validation battery; it is stored with
    ``granted: True`` and becomes the newest record for its key.
    """
    explicit = dict(record)
    explicit["granted"] = True
    explicit["grant_note"] = owner_approval
    stored = refresh(explicit, probe=probe, path=path, action_log=action_log)
    if stored["status"] != AVAILABLE:
        stored["reason"] = (stored.get("reason") or "")
        stored["reason"] += ("" if "grant rejected" in stored["reason"]
                             else " grant rejected: record did not validate")
    return stored


# ---------------------------------------------------------------------------
# Bootstrap: prime the registry with declared providers so that later
# execution paths consult a bounded, honest trust state.
# ---------------------------------------------------------------------------

def bootstrap(path: Path | str | None = None,
              probe: dict[str, Any] | None = None):
    """Validate all declared providers and record the external surfaces that
    are NOT installed as unavailable. Idempotent at the record level: a
    provider that already has a validated record is refreshed in place.
    Returns the registry overview. Write-mode only; suites use a temp path.
    """
    for declared in DECLARED_PROVIDERS:
        refresh(dict(declared), probe=probe, path=path)
    for external in EXTERNAL_NOT_INSTALLED:
        refresh(dict(external), probe={"available": False}, path=path)
    return registry_overview(path=path)


if __name__ == "__main__":
    import sys
    tmp = Path(sys.argv[1]) if len(sys.argv) > 1 else TRUST_FILE
    print(json.dumps(bootstrap(path=tmp), indent=2, ensure_ascii=False))