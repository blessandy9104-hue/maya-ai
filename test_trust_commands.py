"""``:trust`` command-surface verification suite.

The runtime control surface must report the honest trust state the registry
holds: read-only inspection first, every mutating command confirmation-gated,
nothing trusted unless validation confirmed availability, revoked tombstones
visible, unknown capabilities shown as pending, scope shown only when present,
and secrets / source digests never rendered.

This suite exercises the command module directly with temporary registry and
action paths and the real router for dispatch parity. The real registry and
action log are only read (and asserted absent at the end); no suite writes
them.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_capabilities
import maya_chat
import maya_trust as trust
import maya_trust_commands as tc

ROOT = Path(__file__).resolve().parent


def _ok(label: str) -> None:
    print(label + " =OK")


_tmp = Path(tempfile.mkdtemp())
EMPTY = _tmp / "empty.jsonl"
LIVE = _tmp / "live.jsonl"
APPR = _tmp / "approval.jsonl"
REV = _tmp / "revoked.jsonl"
GATE = _tmp / "gate.jsonl"
ACT = _tmp / "actions.jsonl"
MISSING_LOG = _tmp / "no_actions.jsonl"

trust.set_clock(lambda: 1234.0)

GOOD = json.loads(json.dumps(trust.DECLARED_PROVIDERS[0]))
GOOD["identity"]["source_digest"] = "d1"
PROBE_OK = {"available": True, "source_digest": "d1"}

# ---- 1. router dispatch parity -------------------------------------------

assert isinstance(maya_chat.maya_local_command(":trust"), str)
assert maya_chat.maya_local_command(":trust").startswith(
    "Maya trusted-capability registry")
_ok("trust_router_dispatches")

assert maya_chat.maya_local_command(":trustless") is None
assert maya_chat.maya_local_command(":nonexistent-verb") is None
_ok("trust_router_unknown_none")

# ---- 2. every subcommand returns a string --------------------------------

for text in (":trust", ":trust list", ":trust show language_model",
             ":trust pending", ":trust revoked", ":trust actions",
             ":trust validate language_model", ":trust revoke language_model",
             ":trust grant language_model", ":trust show"):
    out = tc.trust_command(text, registry_path=EMPTY, actions_path=ACT)
    assert isinstance(out, str) and out, (text, out)
_ok("trust_subcommands_all_strings")

unknown = tc.trust_command(":trust bogus", registry_path=EMPTY)
assert "Unknown :trust subcommand" in unknown
assert any(word in unknown for word in ("validate", "grant", "revoke"))
_ok("trust_unknown_subcommand_usage")

# ---- 3. empty registry: everything pending, nothing trusted ---------------

empty_list = tc.trust_command(":trust", registry_path=EMPTY)
assert "available=0" in empty_list, empty_list
assert "pending_validation=" in empty_list
empty_pending = tc.trust_command(":trust pending", registry_path=EMPTY)
assert "pending_validation capabilities (" in empty_pending
assert "(not validated)" in empty_pending
_ok("trust_empty_registry_all_pending")

assert "trust=trusted" not in empty_list, empty_list
assert "trust=not_trusted" in empty_list
_ok("trust_empty_registry_none_trusted")

# ---- 4. listed-but-unvalidated capability stays pending, never trusted ----

show_unknown = tc.trust_command(":trust show conversation", registry_path=EMPTY)
assert "state=pending_validation" in show_unknown
assert "trust=not_trusted" in show_unknown
_ok("trust_show_before_validation")

# ---- 5. available only after the full battery passes ----------------------

stored = trust.refresh(dict(GOOD), probe=PROBE_OK, path=LIVE)
assert stored["status"] == trust.AVAILABLE, stored["status"]
live_list = tc.trust_command(":trust list", registry_path=LIVE)
assert "trust=trusted" in live_list
assert "state=available" in live_list
_ok("trust_list_marks_trusted")

live_show = tc.trust_command(":trust show language_model", registry_path=LIVE)
assert "trust=trusted" in live_show
assert "verification=" in live_show
_ok("trust_show_marks_trusted")

# ---- 6. pending view excludes the validated serving provider --------------

live_pending = tc.trust_command(":trust pending", registry_path=LIVE)
assert "conversation:" not in live_pending, live_pending
empty_pending2 = tc.trust_command(":trust pending", registry_path=EMPTY)
assert "conversation:" in empty_pending2
_ok("trust_pending_excludes_validated")

# ---- 7. revocation is a visible tombstone ---------------------------------

trust.revoke("calendar_booking", "local_calendar",
             reason="user revoked", path=REV)
rev_list = tc.trust_command(":trust revoked", registry_path=REV)
assert "calendar_booking" in rev_list
assert "state=revoked" in rev_list
assert "tombstone" in rev_list
_ok("trust_revoked_listed")

rev_show = tc.trust_command(":trust show calendar_booking", registry_path=REV)
assert "state=revoked" in rev_show
assert "trust=not_trusted" in rev_show
_ok("trust_show_revoked_state")

# ---- 8. every mutating command is confirmation-gated ----------------------

for verb in ("validate", "grant", "revoke"):
    gated = tc.trust_command(f":trust {verb} language_model",
                             registry_path=GATE)
    assert "Explicit confirmation required" in gated, (verb, gated)
    assert f":trust {verb} language_model confirm" in gated
_ok("trust_confirm_required_validate")
_ok("trust_confirm_required_grant")
_ok("trust_confirm_required_revoke")

assert not GATE.exists()
assert not _tmp.joinpath("gate_actions.jsonl").exists()
_ok("trust_no_write_without_confirm")

# ---- 9. scope is shown only when actually present -------------------------

SCOPED = json.loads(json.dumps(trust.DECLARED_PROVIDERS[0]))
SCOPED["owner"] = "alice"
SCOPED_PATH = _tmp / "scoped.jsonl"
trust.refresh(dict(SCOPED), probe=PROBE_OK, path=SCOPED_PATH)
scoped_view = tc.safe_record(SCOPED)
assert scoped_view["scope"]["owner"] == "alice"
assert scoped_view["scope"]["context"] == "personal"
scoped_show = tc.trust_command(":trust show language_model",
                               registry_path=SCOPED_PATH)
assert "owner=alice" in scoped_show
_ok("trust_scope_owner_shown")

assert "organization" not in scoped_view["scope"]
assert "organization=" not in scoped_show
_ok("trust_scope_no_fabricated_org")

# ---- 10. secrets and digests are never rendered ---------------------------

SECRET = "f" * 64
leaky = json.loads(json.dumps(trust.DECLARED_PROVIDERS[0]))
leaky["trust_basis"] = ["verified", f"digest={SECRET}", SECRET, "token=abc123"]
leaky["reason"] = "rejected: secret=xyz"
view = tc.safe_record(leaky)
rendered = json.dumps(view, sort_keys=True)
assert SECRET not in rendered
assert "digest=[redacted]" in rendered
assert "[redacted-digest]" in rendered
_ok("trust_redacts_digest")

assert "abc123" not in rendered
assert "token=[redacted]" in rendered
_ok("trust_redacts_token")

assert "xyz" not in rendered
assert "secret=[redacted]" in rendered
_ok("trust_redacts_secret_kv")

ident = tc.safe_record(GOOD)["identity"]
assert ident["source_digest_recorded"] is True
assert "d1" not in json.dumps(ident)
assert "source_digest" not in ident
_ok("trust_identity_no_digest_value")

# ---- 11. action records carry decision, approval, result, verification ----

decided = trust.authorize("language_model", "generate_text", "personal",
                          path=LIVE, action_log=ACT)
assert decided["verdict"] == "allowed", decided
actions_text = tc.trust_command(":trust actions", actions_path=ACT)
assert "decision=allowed" in actions_text
assert "verification_supported=True" in actions_text
_ok("trust_actions_render_decision")

APPREC = json.loads(json.dumps(trust.DECLARED_PROVIDERS[0]))
APPREC["identity"]["source_digest"] = "d1"
APPREC["approval"] = {"generate_text": {"required": True},
                      "read_status": {"required": False}}
trust.refresh(APPREC, probe=PROBE_OK, path=APPR)
ap = trust.authorize("language_model", "generate_text", "personal",
                     path=APPR, action_log=ACT)
assert ap["verdict"] == "requires_approval", ap
ap_text = tc.trust_command(":trust actions", actions_path=ACT)
assert "decision=requires_approval" in ap_text
assert "approval_required=True" in ap_text
_ok("trust_actions_render_approval")

assert "result=authorized_not_executed" in actions_text
assert "result=blocked_pending_approval" in ap_text
_ok("trust_actions_render_result")

absent = tc.trust_command(":trust actions", actions_path=MISSING_LOG)
assert "no action records" in absent
_ok("trust_actions_absent_honest")

# ---- 12. advertised surfaces are unchanged --------------------------------

assert ":trust" not in maya_capabilities.colon_commands()
assert ":trust" not in maya_capabilities.command_list()
_ok("trust_unadvertised")

help_text = maya_chat.maya_local_command(":help")
assert isinstance(help_text, str) and help_text
assert ":trust" not in help_text
_ok("trust_help_unchanged")

caps = maya_chat.maya_local_command(":capabilities")
assert isinstance(caps, str) and "What Maya can do" in caps
_ok("trust_capabilities_surface_unchanged")

# ---- 13. the real registry / action log were never written ----------------

assert not (ROOT / "trusted_capabilities.jsonl").exists()
assert not (ROOT / "maya_trust_actions.jsonl").exists()
_ok("trust_real_registry_untouched")

print("test_trust_commands=PASS")
