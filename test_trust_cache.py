"""Trust-runtime metadata cache: contract, security/ethics and cross-layer suite.

The cache is *metadata only*. It must never turn cached metadata into cached
permission, never mask a revocation, never infer approval, and never let a
different user/owner/context/action reuse another decision. This suite proves
those properties through the public ``maya_trust`` surface plus the cache's own
bounded control surface, and cross-checks the intelligence-core, ``:trust``
diagnostics and the action log for agreement.

All registry/action paths are temporary; the real trust artifacts are never
written.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_trust as trust
import maya_trust_cache as cache_mod
import maya_trust_commands as tc

ROOT = Path(__file__).resolve().parent


def _ok(label: str) -> None:
    print(label + " =OK")


_TMP = Path(tempfile.mkdtemp())
REG = _TMP / "trust.jsonl"
MISSING = _TMP / "missing.jsonl"
MAL = _TMP / "malformed.jsonl"
ACT = _TMP / "actions.jsonl"
CH = _TMP / "content.jsonl"


def _record(**over):
    rec = json.loads(json.dumps(trust.DECLARED_PROVIDERS[0]))
    rec["identity"]["source_digest"] = "d1"
    rec.update(over)
    return rec


def _authorize(capability="language_model", action="generate_text",
               context="personal", **kw):
    kw.setdefault("path", REG)
    kw.setdefault("action_log", ACT)
    return trust.authorize(capability, action, context, **kw)


PROBE_OK = {"available": True, "source_digest": "d1"}

trust.set_clock(lambda: 1234.0)
trust.cache_reset()

# ==========================================================================
# A. Unit and contract
# ==========================================================================

# -- 1. cache miss then hit ------------------------------------------------
trust.cache_reset()
before = trust.cache_stats()
trust.refresh(_record(), probe=PROBE_OK, path=REG)
trust.cache_reset()
first = trust.load_registry(path=REG)
after_miss = trust.cache_stats()
second = trust.load_registry(path=REG)
after_hit = trust.cache_stats()
assert after_miss["misses"] >= 1, after_miss
assert after_hit["hits"] >= 1, after_hit
assert first == second and len(second) == 1
_ok("trustcache_miss_and_hit_ok")


# -- 2. valid registry: lookup + authorize allowed -------------------------
record = trust.lookup("language_model", provider="local_model", path=REG)
assert isinstance(record, dict) and record["status"] == trust.AVAILABLE
allowed = _authorize()
assert allowed["verdict"] == "allowed", allowed
assert allowed["verification_supported"] is True
_ok("trustcache_valid_registry_ok")


# -- 3. missing registry ---------------------------------------------------
assert trust.load_registry(path=MISSING) == []
missing = _authorize(capability="calendar_booking", action="confirm_booking")
assert missing["verdict"] == "refused", missing
assert any("no validated record" in r for r in missing["reasons"])
# creation is noticed after being cached as absent
trust.cache_reset()
assert trust.load_registry(path=MISSING) == []
trust.refresh(_record(capability="calendar_booking", provider="local_calendar"),
              probe=PROBE_OK, path=MISSING)
assert len(trust.load_registry(path=MISSING)) == 1
MISSING.unlink()
_ok("trustcache_missing_registry_ok")


# -- 4. malformed JSONL ----------------------------------------------------
MAL.write_bytes(b'{"capability": "language_model"\n')
mal_rows = trust.load_registry(path=MAL)
assert any(r.get("malformed") for r in mal_rows), mal_rows
assert trust.lookup("language_model", path=MAL) is None
mal_dec = _authorize(path=MAL)
assert mal_dec["verdict"] == "refused" and "no validated record" in \
    mal_dec["reasons"][0]
_ok("trustcache_malformed_jsonl_ok")


# -- 5. malformed record ---------------------------------------------------
BAD = _TMP / "bad_record.jsonl"
trust.refresh({"capability": "language_model", "provider": "local_model"},
              probe=PROBE_OK, path=BAD)
bad = _authorize(path=BAD)
assert bad["verdict"] == "refused", bad
assert trust.lookup("language_model", path=BAD)["status"] != trust.AVAILABLE
_ok("trustcache_malformed_record_ok")


# -- 6. registry file change is seen immediately ---------------------------
trust.cache_reset()
assert len(trust.load_registry(path=REG)) == 1
trust.revoke("language_model", "local_model", "file-change drill",
             path=REG, action_log=ACT)  # explicit mutation + file append
assert len(trust.load_registry(path=REG)) == 2
assert _authorize()["verdict"] == "refused"
_ok("trustcache_registry_file_change_ok")


# -- 7. content change with unchanged timestamp (strict verify) ------------
CH.write_bytes(b'{"capability": "alpha", "n": 1}\n')
stat0 = CH.stat()
trust.cache_configure(verify_content=True, ttl_seconds=1000.0)
assert trust.load_registry(path=CH)[0]["capability"] == "alpha"
CH.write_bytes(b'{"capability": "bravo", "n": 1}\n')  # same byte length
os.utime(CH, ns=(stat0.st_atime_ns, stat0.st_mtime_ns))  # restore mtime
assert CH.stat().st_size == stat0.st_size
seen = trust.load_registry(path=CH)[0]["capability"]
assert seen == "bravo", seen
# a size change is detected even without strict content verification
trust.cache_configure(verify_content=False)
CH.write_bytes(b'{"capability": "charlie", "n": 2}\n')
assert trust.load_registry(path=CH)[0]["capability"] == "charlie"
trust.cache_configure(verify_content=False, ttl_seconds=cache_mod.DEFAULT_TTL_SECONDS)
_ok("trustcache_content_change_unchanged_timestamp_ok")


# -- 8. explicit grant becomes visible after invalidation ------------------
trust.cache_reset()
granted = trust.grant(_record(), probe=PROBE_OK, path=REG, action_log=ACT)
assert granted["status"] == trust.AVAILABLE, granted
assert _authorize()["verdict"] == "allowed"
_ok("trustcache_explicit_grant_ok")


# -- 9. explicit revoke / tombstone ----------------------------------------
trust.cache_reset()
pre = _authorize()
assert pre["verdict"] == "allowed"
trust.revoke("language_model", "local_model", "owner revoked",
             path=REG, action_log=ACT)
post = _authorize()
assert post["verdict"] == "refused", post
tomb = trust.lookup("language_model", provider="local_model", path=REG)
assert tomb.get("revoked") is True and tomb["status"] == trust.UNTRUSTED
# a later routine validation can never heal the tombstone
retry = trust.refresh(_record(), probe=PROBE_OK, path=REG)
assert retry["status"] != trust.AVAILABLE and retry.get("revoked_pending_grant")
# only an explicit grant restores it (used by the later checks on this path)
assert trust.grant(_record(), probe=PROBE_OK, path=REG)["status"] == \
    trust.AVAILABLE
_ok("trustcache_explicit_revoke_tombstone_ok")


# -- 10/11/12. owner, context, scope mismatches ----------------------------
OWN = _TMP / "owner.jsonl"
SCOPE = _TMP / "scope.jsonl"
trust.cache_reset()
trust.refresh(_record(owner="alice"), probe=PROBE_OK, path=OWN)
assert _authorize(path=OWN, user="alice")["verdict"] == "allowed"
assert _authorize(path=OWN, user="bob")["verdict"] == "refused"
_ok("trustcache_owner_mismatch_ok")

trust.cache_reset()
trust.refresh(_record(), probe=PROBE_OK, path=REG)
assert _authorize()["verdict"] == "allowed"
assert _authorize(context="work")["verdict"] == "refused"
_ok("trustcache_context_mismatch_ok")

trust.cache_reset()
scoped = _record(permissions={"generate_text": False, "read_status": True})
trust.refresh(scoped, probe=PROBE_OK, path=SCOPE)
assert _authorize(path=SCOPE)["verdict"] == "refused"
assert _authorize(path=SCOPE, action="read_status")["verdict"] == "allowed"
_ok("trustcache_scope_mismatch_ok")


# -- 13. unknown capability ------------------------------------------------
trust.cache_reset()
unknown = _authorize(capability="does_not_exist", action="read_status")
assert unknown["verdict"] == "refused"
assert any("no validated record" in r for r in unknown["reasons"])
_ok("trustcache_unknown_capability_ok")


# -- 14. approval-required action is never inferred ------------------------
APPR = _TMP / "appr.jsonl"
trust.cache_reset()
appr = _record(approval={"generate_text": {"required": True},
                         "read_status": {"required": False}})
trust.refresh(appr, probe=PROBE_OK, path=APPR)
first_block = _authorize(path=APPR)
assert first_block["verdict"] == "requires_approval"
second_block = _authorize(path=APPR)
assert second_block["verdict"] == "requires_approval"
assert second_block["owner_approval"] is False
approved = _authorize(path=APPR, owner_approval=True)
assert approved["verdict"] == "allowed" and approved["owner_approval"] is True
# a later request without approval is still blocked (no caching of the allow)
assert _authorize(path=APPR)["verdict"] == "requires_approval"
_ok("trustcache_approval_required_ok")


# -- 15. unsafe / unavailable state is never a permanent fact --------------
TRANS = _TMP / "transient.jsonl"
trust.cache_reset()
trust.refresh(_record(), probe={"available": False}, path=TRANS)
assert _authorize(path=TRANS)["verdict"] == "refused"
# the cache must not have memorized the refusal: restoring the provider and
# re-validating yields allowed immediately
trust.refresh(_record(), probe=PROBE_OK, path=TRANS)
assert _authorize(path=TRANS)["verdict"] == "allowed"
_ok("trustcache_unsafe_core_not_permanent_ok")


# -- 16. empty trust state -------------------------------------------------
EMPTY = _TMP / "empty.jsonl"
trust.cache_reset()
assert trust.load_registry(path=EMPTY) == []
empty_dec = _authorize(path=EMPTY)
assert empty_dec["verdict"] == "refused"
overview = trust.registry_overview(path=EMPTY)
assert overview["systems"] == {}
assert overview["counts"][trust.AVAILABLE] == 0
assert overview["counts"][trust.PENDING_VALIDATION] > 0
_ok("trustcache_empty_trust_state_ok")


# -- 17. TTL expiry (metadata lifetime is bounded) -------------------------
clock = {"t": 0.0}
trust.cache_configure(verify_content=False, ttl_seconds=10.0,
                      clock=lambda: clock["t"])
trust.cache_reset()
trust.load_registry(path=REG)
trust.load_registry(path=REG)
hits_at_start = trust.cache_stats()["hits"]
assert hits_at_start >= 1
clock["t"] = 11.0  # past the declared lifetime
trust.load_registry(path=REG)
assert trust.cache_stats()["misses"] >= 2
trust.cache_configure(clock=None, ttl_seconds=cache_mod.DEFAULT_TTL_SECONDS)
_ok("trustcache_ttl_expiry_ok")


# -- 18. cache clear -------------------------------------------------------
trust.cache_reset()
trust.load_registry(path=REG)
assert trust.cache_stats()["entries"] >= 1
trust.cache_configure()  # any policy call also drops entries
assert trust.cache_stats()["entries"] == 0
trust.load_registry(path=REG)
assert trust.cache_stats()["entries"] >= 1
_ok("trustcache_clear_ok")


# -- 19. concurrent lookup -------------------------------------------------
CONC = _TMP / "conc.jsonl"
trust.cache_reset()
trust.store_record(_record(), path=CONC)
errors = []
stop = threading.Event()
barrier = threading.Barrier(6)


def _reader():
    barrier.wait()
    while not stop.is_set():
        try:
            rows = trust.load_registry(path=CONC)
            if not isinstance(rows, list) or not all(
                    isinstance(r, dict) for r in rows):
                errors.append("bad rows")
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))


threads = [threading.Thread(target=_reader) for _ in range(5)]
for t in threads:
    t.start()
barrier.wait()
for i in range(20):
    trust.store_record(_record(capability="c%d" % i), path=CONC)
stop.set()
for t in threads:
    t.join()
assert not errors, errors[:3]
assert len(trust.load_registry(path=CONC)) == 21
_ok("trustcache_concurrent_lookup_ok")


# -- 20. cache corruption fails closed to the uncached read ----------------
def _boom():
    raise RuntimeError("corrupt clock")


broken = cache_mod.TrustMetadataCache(clock=_boom)
try:
    rows = broken.rows(REG)
finally:
    pass
assert isinstance(rows, list) and len(rows) >= 1
assert broken.stats()["errors"] >= 1
_ok("trustcache_corruption_fallback_ok")


# -- 21. bounded cache size -------------------------------------------------
small = cache_mod.TrustMetadataCache(max_entries=2)
paths = []
for i in range(4):
    p = _TMP / ("bound%d.jsonl" % i)
    p.write_bytes(json.dumps({"capability": "c%d" % i}).encode("utf-8") + b"\n")
    small.rows(p)
    paths.append(p)
st = small.stats()
assert st["entries"] == 2, st
assert st["evictions"] >= 2, st
_ok("trustcache_bounded_size_ok")


# -- 21b. bounded total rows (resident footprint, not just path count) ------
row_budget = cache_mod.TrustMetadataCache(max_entries=100, max_total_rows=3)
for i in range(5):
    p = _TMP / ("rows%d.jsonl" % i)
    p.write_bytes(json.dumps({"capability": "c%d" % i}).encode("utf-8") + b"\n")
    row_budget.rows(p)
rb = row_budget.stats()
assert rb["rows"] <= 3 and rb["max_total_rows"] == 3, rb
assert rb["evictions"] >= 2, rb
_ok("trustcache_bounded_rows_ok")


# -- 22. process / runtime restart -----------------------------------------
fresh = cache_mod.TrustMetadataCache()
assert len(fresh.rows(REG)) >= 1
assert fresh.stats()["hits"] == 0 and fresh.stats()["misses"] >= 1
trust.cache_reset()
assert trust.cache_stats()["hits"] == 0 and trust.cache_stats()["entries"] == 0
_ok("trustcache_process_restart_ok")


# -- 23. no stale authorization result -------------------------------------
STALE = _TMP / "stale.jsonl"
trust.cache_reset()
trust.refresh(_record(), probe=PROBE_OK, path=STALE)
assert _authorize(path=STALE)["verdict"] == "allowed"
trust.revoke("language_model", "local_model", "mid-flight revoke",
             path=STALE, action_log=ACT)
# exactly the same request must now be refused; the prior allow cannot be
# replayed from metadata
assert _authorize(path=STALE)["verdict"] == "refused"
_ok("trustcache_no_stale_authorization_ok")


# ==========================================================================
# B. Security and ethics
# ==========================================================================

# -- 24. cached metadata never becomes cached permission -------------------
trust.cache_reset()
trust.refresh(_record(), probe=PROBE_OK, path=REG)
assert _authorize()["verdict"] == "allowed"
snapshot = trust.cache_stats()
assert "verdict" not in json.dumps(snapshot)
rows = trust.load_registry(path=REG)
assert all("verdict" not in json.dumps(r) for r in rows)
# mutating a returned row must not change a later decision source
rows[0]["status"] = trust.UNTRUSTED
assert _authorize()["verdict"] == "allowed"
_ok("trustcache_metadata_not_permission_ok")


# -- 25. revocation takes effect immediately --------------------------------
trust.cache_reset()
trust.refresh(_record(), probe=PROBE_OK, path=REG)
assert _authorize()["verdict"] == "allowed"
trust.revoke("language_model", "local_model", "immediate", path=REG,
             action_log=ACT)
assert _authorize()["verdict"] == "refused"
_ok("trustcache_revocation_immediate_ok")


# -- 26. approval is never inferred from a prior request --------------------
trust.cache_reset()
appr = _record(approval={"generate_text": {"required": True},
                         "read_status": {"required": False}})
trust.refresh(appr, probe=PROBE_OK, path=APPR)
assert _authorize(path=APPR, owner_approval=True)["verdict"] == "allowed"
assert _authorize(path=APPR)["verdict"] == "requires_approval"
_ok("trustcache_approval_not_inferred_ok")


# -- 27. a different user/context/action cannot reuse another decision ------
CROSS = _TMP / "cross.jsonl"
trust.cache_reset()
trust.refresh(_record(owner="alice"), probe=PROBE_OK, path=CROSS)
assert _authorize(path=CROSS, user="alice")["verdict"] == "allowed"
assert _authorize(path=CROSS, user="bob")["verdict"] == "refused"
assert _authorize(path=CROSS, user="alice", context="work")["verdict"] == \
    "refused"
assert _authorize(path=CROSS, user="alice",
                  action="send_message")["verdict"] == "refused"
_ok("trustcache_cross_scope_not_reused_ok")


# -- 28. malformed / ambiguous data stays untrusted -------------------------
assert trust.lookup("language_model", path=MAL) is None
trust.store_record({"malformed": True, "line": "not-json"}, path=MAL)
assert trust.load_registry(path=MAL)[0].get("malformed") is True
assert _authorize(path=MAL)["verdict"] == "refused"
_ok("trustcache_malformed_ambiguous_untrusted_ok")


# -- 29. unavailable state never becomes silently trusted -------------------
UNAV = _TMP / "unav.jsonl"
trust.cache_reset()
trust.refresh(dict(trust.EXTERNAL_NOT_INSTALLED[0]),
              probe={"available": False}, path=UNAV)
assert _authorize(capability="calendar_booking", action="confirm_booking",
                  path=UNAV)["verdict"] == "refused"
assert trust.lookup("calendar_booking", path=UNAV)["status"] == \
    trust.UNAVAILABLE
_ok("trustcache_unavailable_not_silently_trusted_ok")


# -- 30. the response distinguishes all four honest outcomes ----------------
LIVE = _TMP / "live.jsonl"
trust.cache_reset()
trust.refresh(_record(), probe=PROBE_OK, path=LIVE)
allowed = _authorize(path=LIVE)
blocked = _authorize(capability="does_not_exist", action="read_status")
approval = None
appr2 = _record(approval={"generate_text": {"required": True},
                          "read_status": {"required": False}})
trust.refresh(appr2, probe=PROBE_OK, path=APPR)
approval = _authorize(path=APPR)
unavail = _authorize(capability="calendar_booking", action="confirm_booking",
                     path=UNAV)
assert allowed["verdict"] == "allowed"
assert blocked["verdict"] == "refused"
assert approval["verdict"] == "requires_approval"
assert unavail["verdict"] == "refused"
assert allowed["result"] == "authorized_not_executed"
assert approval["result"] == "blocked_pending_approval"
assert blocked["result"] == "blocked"
assert unavail["status"] in (trust.UNAVAILABLE, trust.PENDING_VALIDATION)
_ok("trustcache_response_distinguishes_ok")


# -- 31. diagnostics never expose secrets or identifying material -----------
SECRET = "f" * 64
leaky_path = _TMP / "leaky.jsonl"
leaky = _record(trust_basis=["verified", "digest=%s" % SECRET, SECRET,
                             "token=abc123"])
leaky["reason"] = "rejected: secret=xyz"
trust.refresh(leaky, probe=PROBE_OK, path=leaky_path)
stats_text = json.dumps(trust.cache_stats(), sort_keys=True)
assert SECRET not in stats_text and "abc123" not in stats_text
show = tc.trust_command(":trust show language_model", registry_path=leaky_path)
assert SECRET not in show and "abc123" not in show and "xyz" not in show
_ok("trustcache_diagnostics_no_secrets_ok")


# ==========================================================================
# E. Cross-layer agreement
# ==========================================================================
import maya_intelligence_core as core  # noqa: E402

# -- 32. trust runtime and the action log agree ----------------------------
XL = _TMP / "crosslayer.jsonl"
trust.cache_reset()
trust.refresh(_record(), probe=PROBE_OK, path=XL)
decision = _authorize(path=XL)
log_rows = [r for r in trust.load_registry(path=ACT) if isinstance(r, dict)]
last = log_rows[-1]
assert last["verdict"] == decision["verdict"] == "allowed"
assert last["result"] == decision["result"] == "authorized_not_executed"
assert last["verification_supported"] is True
required = ("capability", "user", "context", "decision", "approval_required",
            "owner_approval", "verification_supported", "result", "timestamp")
assert all(k in last for k in required)
_ok("trustcache_crosslayer_trust_actionlog_ok")


# -- 33. core never shows success while trust refuses or waits -------------
trust.revoke("language_model", "local_model", "cross-layer", path=XL,
             action_log=ACT)
refused = _authorize(path=XL)
overview = trust.registry_overview(path=XL)
view = core.build_core_view(activity="idle", resources="safe", trust=overview,
                            authority=refused)
assert refused["verdict"] == "refused"
assert view["state"] in ("unavailable", "error"), view["state"]
assert view["implies_success"] is False
assert all(not ind["active"] for ind in view["indicators"])
assert view["authority"]["verdict"] == "refused"
_ok("trustcache_crosslayer_core_no_false_success_ok")


# -- 34. overview, revoked diagnostics and the runtime agree ---------------
overview = trust.registry_overview(path=XL)
assert overview["systems"]["language_model"]["status"] == trust.UNTRUSTED
assert overview["capabilities"]["conversation"] == trust.UNTRUSTED
revoked_view = tc.trust_command(":trust revoked", registry_path=XL)
assert "language_model" in revoked_view and "state=revoked" in revoked_view
assert trust.lookup("language_model", path=XL)["status"] == trust.UNTRUSTED
_ok("trustcache_crosslayer_overview_consistent_ok")


# -- 35. real trust artifacts were never written ---------------------------
assert not (ROOT / "trusted_capabilities.jsonl").exists()
assert not (ROOT / "maya_trust_actions.jsonl").exists()
assert not any(ROOT.glob("*.trustcache*"))
_ok("trustcache_real_artifacts_absent_ok")


print("test_trust_cache=PASS")
