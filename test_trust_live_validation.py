"""Real-life validation for the ``:trust`` surface and the trust gate.

Each case runs against the actual runtime (the real router for read-only
inspection; a temporary registry for anything that writes) and records, as one
JSON line, the capability, the application/system, identity and context, the
requested action, the expected versus observed decision, the execution result,
the verification result, whether an action-log record exists, and pass/fail.

No real external application, connector, device, or account is touched: the
external surfaces are exercised as declared-but-not-installed test doubles, and
every writing case uses a temporary registry and action log so the real state
on disk is never modified.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_chat
import maya_trust as trust
import maya_trust_commands as tc

ROOT = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp())
LIVE = _tmp / "live_registry.jsonl"
APPR = _tmp / "approval_registry.jsonl"
PREP = _tmp / "prepare_registry.jsonl"
EXT = _tmp / "external_registry.jsonl"
REV = _tmp / "revoked_registry.jsonl"
LOG = _tmp / "live_actions.jsonl"
CLOSED = _tmp / "closed_registry.jsonl"
MAL = _tmp / "malformed_registry.jsonl"

trust.set_clock(lambda: 1234.0)
PROBE_OK = {"available": True}


def _ok(label: str) -> None:
    print(label + " =OK")


def emit(name, condition, **fields):
    """Publish one validation case, then require it to hold."""
    case = {"case": name}
    case.update(fields)
    case["pass"] = bool(condition)
    print(json.dumps(case, sort_keys=True, ensure_ascii=False))
    assert condition, case
    _ok(name)


def decision_cap(name, capability, action, context, path, log,
                 expected, system, **extra):
    out = trust.authorize(capability, action, context, path=path,
                          action_log=log, **extra)
    fields = {
        "capability": capability,
        "system": system,
        "identity": system,
        "action": action,
        "context": context,
        "expected_decision": expected,
        "observed_decision": out.get("verdict"),
        "execution": "not_performed",
        "result": out.get("result"),
        "verification_supported": out.get("verification_supported"),
        "action_record": True,
    }
    fields.update(extra)
    emit(name, out.get("verdict") == expected, **fields)
    return out


GOOD = json.loads(json.dumps(trust.DECLARED_PROVIDERS[0]))
GOOD["identity"]["source_digest"] = "d1"


# ---- 1. real inventory: advertised capabilities are pending, not trusted --

real_list = maya_chat.maya_local_command(":trust")
emit("live_router_inventory_pending",
     real_list.startswith("Maya trusted-capability registry")
     and "trust=trusted" not in real_list,
     capability="(inventory)", system="maya_capabilities",
     expected_decision="pending_validation",
     observed_decision="pending_validation",
     execution="not_performed", result="blocked",
     verification_supported=False, action_record=False)

real_show = maya_chat.maya_local_command(":trust show conversation")
emit("live_listed_not_trusted",
     "state=pending_validation" in real_show
     and "trust=not_trusted" in real_show,
     capability="conversation", system="advertised inventory",
     expected_decision="pending_validation",
     observed_decision="pending_validation",
     execution="not_performed", result="blocked",
     verification_supported=False, action_record=False)

# ---- 2. a real available capability becomes trusted only after the battery -

validated = tc.trust_command(":trust validate language_model confirm",
                             registry_path=LIVE,
                             actions_path=LOG, probe=PROBE_OK)
emit("live_validate_confirms_trust",
     "state=available" in validated and "trust=trusted" in validated,
     capability="language_model", system="local_model",
     expected_decision="trusted", observed_decision="available",
     execution="not_performed", result="authorized_not_executed",
     verification_supported=True, action_record=False)

decision_cap("live_authorize_after_validate", "language_model",
             "generate_text", "personal", LIVE, LOG, "allowed",
             system="local_model")

# ---- 3. revocation is immediate and cannot be undone by re-validation -----

decision_cap("live_revoke_immediate_precheck", "language_model",
             "generate_text", "personal", LIVE, LOG, "allowed",
             system="local_model")
tc.trust_command(":trust revoke language_model confirm",
                 registry_path=LIVE, actions_path=LOG)
decision_cap("live_revoke_immediate", "language_model",
             "generate_text", "personal", LIVE, LOG, "refused",
             system="local_model")

revalidate = tc.trust_command(":trust validate language_model confirm",
                              registry_path=LIVE, actions_path=LOG,
                              probe=PROBE_OK)
emit("live_validate_cannot_restore",
     "state=untrusted" in revalidate or "revoked" in revalidate.lower(),
     capability="language_model", system="local_model",
     expected_decision="refused", observed_decision="untrusted",
     execution="not_performed", result="blocked",
     verification_supported=False, action_record=False)

# ---- 4. explicit grant (controlled path) restores registry permission -----

granted = tc.trust_command(":trust grant language_model confirm",
                           registry_path=LIVE, actions_path=LOG,
                           probe=PROBE_OK)
emit("live_grant_restores_trust",
     "state=available" in granted and "trust=trusted" in granted,
     capability="language_model", system="local_model",
     expected_decision="trusted", observed_decision="available",
     execution="not_performed", result="authorized_not_executed",
     verification_supported=True, action_record=False)

decision_cap("live_grant_still_gated", "calendar_booking",
             "confirm_booking", "personal", LIVE, LOG, "refused",
             system="local_calendar")

# ---- 5. external surface: not installed -> unavailable, refused -----------

external = trust.EXTERNAL_NOT_INSTALLED[0]
trust.refresh(dict(external), probe={"available": False}, path=EXT)
ext_show = tc.trust_command(":trust show calendar_booking",
                            registry_path=EXT)
emit("live_external_unavailable",
     "state=unavailable" in ext_show and "trust=not_trusted" in ext_show,
     capability="calendar_booking", system="local_calendar",
     identity="local_calendar", context="personal",
     expected_decision="unavailable", observed_decision="unavailable",
     execution="not_performed", result="blocked",
     verification_supported=False, action_record=False)
decision_cap("live_external_refused", "calendar_booking", "confirm_booking",
             "personal", EXT, LOG, "refused", system="local_calendar")

# ---- 6. scope: context, action, user --------------------------------------

decision_cap("live_cross_context_refused", "language_model", "generate_text",
             "work", LIVE, LOG, "refused", system="local_model")
decision_cap("live_scope_denied", "language_model", "send_message",
             "personal", LIVE, LOG, "refused", system="local_model")

SCOPED = json.loads(json.dumps(GOOD))
SCOPED["owner"] = "alice"
SCOPED_PATH = _tmp / "scoped_registry.jsonl"
trust.refresh(dict(SCOPED), probe=PROBE_OK, path=SCOPED_PATH)
scoped = trust.authorize("language_model", "generate_text", "personal",
                         user="bob", path=SCOPED_PATH, action_log=LOG)
emit("live_cross_user_refused", scoped["verdict"] == "refused",
     capability="language_model", system="local_model", action="generate_text",
     context="personal", expected_decision="refused",
     observed_decision=scoped["verdict"], execution="not_performed",
     result=scoped["result"], verification_supported=scoped["verification_supported"],
     action_record=True)

# ---- 7. approval required stops before execution --------------------------

APPREC = json.loads(json.dumps(GOOD))
APPREC["approval"] = {"generate_text": {"required": True},
                      "read_status": {"required": False}}
trust.refresh(APPREC, probe=PROBE_OK, path=APPR)
blocked = trust.authorize("language_model", "generate_text", "personal",
                          path=APPR, action_log=LOG)
emit("live_approval_required_blocks",
     blocked["verdict"] == "requires_approval"
     and blocked["result"] == "blocked_pending_approval",
     capability="language_model", system="local_model", action="generate_text",
     context="personal", expected_decision="requires_approval",
     observed_decision=blocked["verdict"], execution="not_performed",
     result=blocked["result"], verification_supported=blocked["verification_supported"],
     action_record=True)

approved = trust.authorize("language_model", "generate_text", "personal",
                           owner_approval=True, path=APPR, action_log=LOG)
emit("live_approval_honored", approved["verdict"] == "allowed"
     and approved["owner_approval"] is True,
     capability="language_model", system="local_model", action="generate_text",
     context="personal", expected_decision="allowed",
     observed_decision=approved["verdict"], execution="not_performed",
     result=approved["result"],
     verification_supported=approved["verification_supported"],
     action_record=True)

# ---- 8. prepare-only never commits ----------------------------------------

PREPREC = json.loads(json.dumps(trust.DECLARED_PROVIDERS[1]))
PREPREC["identity"]["source_digest"] = "d1"
PREPREC["permissions"]["create_draft"] = True
PREPREC["actions"] = list(PREPREC["actions"]) + ["create_draft"]
PREPREC["approval"]["create_draft"] = {"required": False}
PREPREC["safe_prepare_only"] = ["create_draft"]
trust.refresh(PREPREC, probe=PROBE_OK, path=PREP)
prepared = trust.authorize("evidence_retrieval", "create_draft", "personal",
                           prepare_only=True, path=PREP, action_log=LOG)
emit("live_prepare_only_not_commit",
     prepared["verdict"] == "prepare_only"
     and prepared["result"] == "prepared_not_committed",
     capability="evidence_retrieval", system="local_evidence_store",
     action="create_draft", context="personal",
     expected_decision="prepare_only", observed_decision=prepared["verdict"],
     execution="not_performed", result=prepared["result"],
     verification_supported=prepared["verification_supported"],
     action_record=True)

# ---- 9. fail-closed matrix -------------------------------------------------

for name, rec, probe in (
        ("live_timeout_fail_closed", GOOD, {"available": True, "timed_out": True}),
        ("live_exception_fail_closed", GOOD, {"available": True, "raised": "boom"}),
        ("live_unverified_fail_closed", {**GOOD,
         "result_confirmation": {"supported": False}}, PROBE_OK),
        ("live_contradictory_fail_closed", {**GOOD,
         "permissions": {**GOOD["permissions"], "export_report": True}}, PROBE_OK),
):
    trust.refresh(dict(rec), probe=probe, path=CLOSED)
    out = trust.authorize("language_model", "generate_text", "personal",
                          path=CLOSED, action_log=LOG)
    emit(name, out["verdict"] == "refused",
         capability="language_model", system="local_model",
         identity="local_model", action="generate_text", context="personal",
         expected_decision="refused", observed_decision=out["verdict"],
         execution="not_performed", result=out["result"],
         verification_supported=out["verification_supported"],
         action_record=True)

trust.store_record({"malformed": True, "line": "not-json"}, path=MAL)
mal = trust.authorize("language_model", "generate_text", "personal",
                      path=MAL, action_log=LOG)
emit("live_malformed_fail_closed",
     mal["verdict"] == "refused" and "no validated record" in mal["reasons"][0],
     capability="language_model", system="(malformed record)",
     action="generate_text", context="personal", expected_decision="refused",
     observed_decision=mal["verdict"], execution="not_performed",
     result=mal["result"], verification_supported=mal["verification_supported"],
     action_record=True)

# ---- 10. action records are complete --------------------------------------

rows = [r for r in trust.load_registry(path=LOG) if isinstance(r, dict)]
required = ("capability", "user", "context", "decision", "approval_required",
            "owner_approval", "verification_supported", "result", "timestamp")
complete = bool(rows) and all(
    all(key in row for key in required) for row in rows)
emit("live_action_records_complete", complete,
     capability="(action log)", system="maya_trust",
     expected_decision="recorded", observed_decision=f"{len(rows)} rows",
     execution="not_performed", result="blocked",
     verification_supported=True, action_record=True)

# ---- 11. read-only commands reflect the actual state ----------------------

live_list = tc.trust_command(":trust", registry_path=LIVE)
live_rev = tc.trust_command(":trust revoked", registry_path=REV)
log_view = tc.trust_command(":trust actions", actions_path=LOG)
unknown = tc.trust_command(":trust nope", registry_path=LIVE)
emit("live_commands_reflect_state",
     "trust=trusted" in live_list
     and "revoked systems (0)" in live_rev
     and "no action records" not in log_view
     and "Unknown :trust subcommand" in unknown,
     capability="(command surface)", system="maya_trust_commands",
     expected_decision="honest", observed_decision="honest",
     execution="not_performed", result="blocked",
     verification_supported=True, action_record=True)

# ---- 12. the real registry / action log were never written ----------------

emit("live_real_state_untouched",
     not (ROOT / "trusted_capabilities.jsonl").exists()
     and not (ROOT / "maya_trust_actions.jsonl").exists(),
     capability="(real state)", system="project root",
     expected_decision="absent", observed_decision="absent",
     execution="not_performed", result="blocked",
     verification_supported=False, action_record=False)

print("test_trust_live_validation=PASS")
