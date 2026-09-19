"""Trusted-capability registry verification suite.

Maya must never trust an application/connector/device/local service/external
system merely because it is installed, reachable, previously used, or listed
in configuration. Every execution-relevant capability is validated (identity
and provenance, current availability, declared capabilities, permission
scope, context, supported actions, approval requirements, input/output
boundaries, authentication state, result confirmation, failure/exception
behaviour, and cross-scope isolation) before it can be ``available``.

A record is ``available`` only when the full battery reports
``verification.supported``. Missing, disabled, revoked, capability-changed,
unauthenticated, out-of-scope, unverified, timing-out, malformed,
contradictory, or cross-context records are refused. ``pending_validation``
means "declared/listed but never validated" and is itself a refuse state:
being advertised never grants availability. Explicit owner approval is
required wherever a record declares it, and an optional record ``owner``
blocks cross-user access.

Every decision is written to the trust action log (temporary path here); the
real registry and action log on disk are only read, never written.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_trust as trust


def _ok(label: str) -> None:
    print(label + " =OK")


_tmpdir = tempfile.mkdtemp()
REGISTRY = Path(_tmpdir) / "trust.jsonl"
ACTIONS = Path(_tmpdir) / "actions.jsonl"
trust.set_clock(lambda: 1234.0)

# A fully declared local provider, validated under a healthy availability
# probe with a stable declared+observed source digest.
GOOD = dict(trust.DECLARED_PROVIDERS[0])
GOOD["identity"]["source_digest"] = "d1"
PROBE_OK = {"available": True, "source_digest": "d1"}
CROSS_PROBE = {"available": True, "source_digest": "d1",
               "cross_context_attempted": True, "cross_context_denied": False}

# ---- 1. available once (and only when) the battery validates --------------

healthy = trust.refresh(dict(GOOD), probe=PROBE_OK, path=REGISTRY)
assert healthy["status"] == trust.AVAILABLE, healthy["status"]
assert healthy["verification"]["supported"] is True
assert healthy["last_checked"] == 1234.0
_ok("available_validated")

decided = trust.authorize("language_model", "generate_text", "personal",
                          path=REGISTRY, action_log=ACTIONS)
assert decided["verdict"] == "allowed", decided
_ok("verified_authorize_allowed")

# ---- 2. missing systems / installed-but-not-validated ---------------------

missing = trust.authorize("calendar_booking", "confirm_booking", "personal",
                          path=REGISTRY, action_log=ACTIONS)
assert missing["verdict"] == "refused", missing
assert any("no validated record" in r for r in missing["reasons"]), missing
_ok("missing_system_refused")

external = dict(trust.EXTERNAL_NOT_INSTALLED[0])
external_stored = trust.refresh(external, probe={"available": False},
                                path=REGISTRY)
assert external_stored["status"] == trust.UNAVAILABLE, external_stored["status"]
assert external_stored["verification"]["supported"] is False
denied = trust.authorize("calendar_booking", "confirm_booking", "personal",
                         path=REGISTRY, action_log=ACTIONS)
assert denied["verdict"] == "refused", denied
_ok("not_installed_unavailable")

# Declared providers are installed yet NEVER auto-trusted before validation:
# a plain refresh without a probe (declaration-only) cannot promote them.
declared_only = trust.refresh(dict(GOOD), probe={}, path=REGISTRY)
assert declared_only["status"] != trust.AVAILABLE, declared_only["status"]
_ok("installed_never_auto_trusted")

# ---- 3. disabled / revoked / explicit grant -------------------------------

trust.revoke("language_model", "local_model", "owner revoked",
             path=REGISTRY, action_log=ACTIONS)
revoked = trust.authorize("language_model", "generate_text", "personal",
                          path=REGISTRY, action_log=ACTIONS)
assert revoked["verdict"] == "refused", revoked
_ok("revoked_refused")

retry = trust.refresh(dict(GOOD), probe=PROBE_OK, path=REGISTRY)
assert retry["status"] == trust.UNTRUSTED, retry["status"]
assert retry.get("revoked_pending_grant") is True
bypassed = trust.authorize("language_model", "generate_text", "personal",
                           path=REGISTRY, action_log=ACTIONS)
assert bypassed["verdict"] == "refused", bypassed
_ok("revocation_survives_validation")

restored = trust.grant(dict(GOOD), probe=PROBE_OK, path=REGISTRY,
                       action_log=ACTIONS)
assert restored["status"] == trust.AVAILABLE, restored["status"]
granted = trust.authorize("language_model", "generate_text", "personal",
                          path=REGISTRY, action_log=ACTIONS)
assert granted["verdict"] == "allowed", granted
_ok("explicit_grant_restores")

invalid_grant = dict(GOOD)
invalid_grant["auth"] = {"method": "token", "state": "expired"}
rejected = trust.grant(invalid_grant, probe=PROBE_OK, path=REGISTRY,
                       action_log=ACTIONS)
assert rejected["status"] != trust.AVAILABLE, rejected["status"]
_ok("grant_rejected_if_invalid")

# ---- 4. capability changes, scope, auth, confirmation, failure ------------

changed = dict(GOOD)
changed["permissions"] = {"generate_text": True, "confirm_booking": True}
cap_changed = trust.refresh(changed, probe=PROBE_OK, path=REGISTRY)
assert cap_changed["status"] == trust.UNTRUSTED, cap_changed["status"]
_ok("capability_change_fail_closed")

scoped = dict(GOOD)
scoped["permissions"] = {"generate_text": False, "read_status": True}
scoped_ok = trust.refresh(scoped, probe=PROBE_OK, path=REGISTRY)
assert scoped_ok["status"] == trust.AVAILABLE, scoped_ok["status"]
scoped_denied = trust.authorize("language_model", "generate_text", "personal",
                                path=REGISTRY, action_log=ACTIONS)
assert scoped_denied["verdict"] == "refused", scoped_denied
assert any("permission scope" in r for r in scoped_denied["reasons"])
_ok("scope_denial_refused")

bad_auth = dict(GOOD)
bad_auth["auth"] = {"method": "token", "state": "expired"}
auth_fail = trust.refresh(bad_auth, probe=PROBE_OK, path=REGISTRY)
assert auth_fail["status"] == trust.UNTRUSTED, auth_fail["status"]
_ok("invalid_auth_denied")

open_fail = dict(GOOD)
open_fail["failure"] = {"fail_closed": False}
open_record = trust.refresh(open_fail, probe=PROBE_OK, path=REGISTRY)
assert open_record["status"] == trust.UNTRUSTED, open_record["status"]
_ok("fail_open_forbidden")

unverified = dict(GOOD)
unverified["result_confirmation"] = {"supported": False}
unverified_record = trust.refresh(unverified, probe=PROBE_OK, path=REGISTRY)
assert unverified_record["status"] == trust.UNTRUSTED
_ok("unverified_results_denied")

timed = trust.refresh(dict(GOOD), probe={"available": True, "timed_out": True},
                      path=REGISTRY)
assert timed["status"] == trust.UNTRUSTED, timed["status"]
_ok("timeout_fail_closed")

raised = trust.refresh(dict(GOOD),
                       probe={"available": True, "raised": "ConnectionRefused"},
                       path=REGISTRY)
assert raised["status"] == trust.UNTRUSTED, raised["status"]
_ok("exception_fail_closed")

malformed = trust.validate_record({"capability": "x", "provider": "p"},
                                  probe={"available": True})
assert malformed["status"] == trust.UNTRUSTED, malformed["status"]
assert any(c["name"] == "structural" and not c["ok"]
           for c in malformed["checks"])
_ok("malformed_record_denied")

contradictory = dict(GOOD)
contradictory["permissions"] = {"generate_text": True, "smuggle_billing": True}
contra = trust.refresh(contradictory, probe=PROBE_OK, path=REGISTRY)
assert contra["status"] == trust.UNTRUSTED, contra["status"]
_ok("contradictory_record_denied")

# ---- 5. context and user isolation -----------------------------------------

_ok_base = trust.refresh(dict(GOOD), probe=PROBE_OK, path=REGISTRY)
assert _ok_base["status"] == trust.AVAILABLE
cross_context = trust.authorize("language_model", "generate_text", "work",
                                path=REGISTRY, action_log=ACTIONS)
assert cross_context["verdict"] == "refused", cross_context
assert any("context" in r for r in cross_context["reasons"])
_ok("cross_context_refused")

leak = trust.refresh(dict(GOOD), probe=CROSS_PROBE, path=REGISTRY)
assert leak["status"] == trust.UNTRUSTED, leak["status"]
_ok("cross_context_leak_fail_closed")

owned = dict(GOOD)
owned["owner"] = "alice"
owned_stored = trust.refresh(owned, probe=PROBE_OK, path=REGISTRY)
assert owned_stored["status"] == trust.AVAILABLE, owned_stored["status"]
other_user = trust.authorize("language_model", "generate_text", "personal",
                             user="bob", path=REGISTRY, action_log=ACTIONS)
assert other_user["verdict"] == "refused", other_user
owner_user = trust.authorize("language_model", "generate_text", "personal",
                             user="alice", path=REGISTRY, action_log=ACTIONS)
assert owner_user["verdict"] == "allowed", owner_user
_ok("cross_user_default_deny")

# ---- 6. prepare-only and approval gates ------------------------------------

prep = dict(GOOD)
prep["safe_prepare_only"] = ["generate_text"]
prep_stored = trust.refresh(prep, probe=PROBE_OK, path=REGISTRY)
assert prep_stored["status"] == trust.AVAILABLE
prepared = trust.authorize("language_model", "generate_text", "personal",
                           prepare_only=True, path=REGISTRY,
                           action_log=ACTIONS)
assert prepared["verdict"] == "prepare_only", prepared
assert prepared["prepare_only"] is True
forbidden_prep = trust.authorize("language_model", "read_status", "personal",
                                 prepare_only=True, path=REGISTRY,
                                 action_log=ACTIONS)
assert forbidden_prep["verdict"] == "refused", forbidden_prep
_ok("prepare_only_bounded")

calendar = {
    "capability": "calendar_booking",
    "provider": "local_calendar",
    "context": "personal",
    "permissions": {"create_draft": True, "confirm_booking": True},
    "actions": ("create_draft", "confirm_booking"),
    "approval": {"create_draft": {"required": False},
                 "confirm_booking": {"required": True}},
    "boundaries": {"input": "calendar", "output": "calendar",
                   "cross_context_denied": True},
    "auth": {"method": "oauth", "state": "valid"},
    "result_confirmation": {"supported": True, "method": "server_echo"},
    "failure": {"fail_closed": True},
    "trust_basis": ["user approved connector", "explicit grant"],
    "identity": {"provider": "local_calendar", "version": "2",
                 "source_digest": "cal-d1"},
    "owner": "alice",
    "granted": True,
}
cal_stored = trust.refresh(calendar, probe={"available": True,
                                            "source_digest": "cal-d1"},
                           path=REGISTRY)
assert cal_stored["status"] == trust.AVAILABLE, cal_stored["status"]
unapproved = trust.authorize("calendar_booking", "confirm_booking", "personal",
                             user="alice", owner_approval=False,
                             path=REGISTRY, action_log=ACTIONS)
assert unapproved["verdict"] == "requires_approval", unapproved
approved = trust.authorize("calendar_booking", "confirm_booking", "personal",
                           user="alice", owner_approval=True,
                           path=REGISTRY, action_log=ACTIONS)
assert approved["verdict"] == "allowed", approved
_ok("approval_required_honored")

# ---- 7. action records and independent-validation evidence -----------------

rows = [line for line in ACTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()]
assert len(rows) >= 6, len(rows)
import json as _json
verdicts = []
for line in rows:
    row = _json.loads(line)
    assert {"capability", "action", "context", "user", "verdict",
            "timestamp"} <= set(row), row
    verdicts.append(row["verdict"])
assert "allowed" in verdicts and "refused" in verdicts, verdicts
_ok("action_records_written")

audit = trust.record_action("language_model", "generate_text", "personal",
                            "alice", "allowed",
                            detail="independent validation evidence",
                            path=ACTIONS)
assert audit["detail"] == "independent validation evidence"
assert audit["timestamp"] == 1234.0
canonical = _json.dumps(audit, sort_keys=True, ensure_ascii=False)
assert canonical == ACTIONS.read_text(encoding="utf-8").splitlines()[-1]
_ok("decision_in_record")

# ---- 8. registry overlay covers the authoritative inventories ---------------

trust.set_clock(lambda: 2222.0)
overlay = trust.registry_overview(path=REGISTRY)
assert overlay["schema"] == "trusted_capability.v1"
systems = overlay["systems"]
assert systems["language_model"]["status"] == trust.AVAILABLE, systems
assert systems["language_model"]["verification_supported"] is True
assert "calendar_booking" in systems
known = overlay["capabilities"]
# A capability served by a validated provider resolves ``available``.
assert known["conversation"] == trust.AVAILABLE, known["conversation"]
# Served-but-unrecorded and merely-listed capabilities stay in a refuse state.
assert any(st == trust.PENDING_VALIDATION for st in known.values()), known
counts = overlay["counts"]
assert counts[trust.AVAILABLE] >= 1
assert counts[trust.PENDING_VALIDATION] >= 1
_ok("registry_overview_composes")

# The live (default) registry keeps every advertised capability in a refuse
# state: no capability is ``available`` until it is actually validated, so
# merely being listed never grants trust.
live = trust.registry_overview()
assert live["systems"] == {}, live["systems"]
assert live["counts"][trust.AVAILABLE] == 0, live["counts"]
assert live["counts"][trust.PENDING_VALIDATION] > 0, live["counts"]
_ok("live_registry_fail_closed")

# ---- 9. deterministic metadata + no writes to real files -------------------

original_registry = (trust.TRUST_FILE.read_bytes() if trust.TRUST_FILE.exists()
                     else None)
original_actions = (trust.ACTION_LOG.read_bytes() if trust.ACTION_LOG.exists()
                    else None)
before = (trust.ACTION_LOG.stat().st_size if trust.ACTION_LOG.exists() else 0)
trust.authorize("language_model", "generate_text", "personal",
                path=REGISTRY, action_log=ACTIONS)
after = (trust.ACTION_LOG.stat().st_size if trust.ACTION_LOG.exists() else 0)
current_registry = (trust.TRUST_FILE.read_bytes() if trust.TRUST_FILE.exists()
                    else None)
current_actions = (trust.ACTION_LOG.read_bytes() if trust.ACTION_LOG.exists()
                   else None)
assert current_registry == original_registry
assert current_actions == original_actions
assert after == before
_ok("real_registry_untouched")

print("test_trusted_capabilities=PASS")