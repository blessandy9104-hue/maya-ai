"""Report staleness battery: review-only reports cannot present as current.

Proves that file-backed review reports served through ``maya_local_command``
(``:review``, ``:income``, ``:evidence``, ``:continuity``, ``:focus``) carry
a structured staleness block whenever the report's own ``generated_at`` is
older than its freshness window:

  - the served copy gains ``staleness`` + ``staleness_warning``,
  - the on-disk file is never modified (display-time only, alert-only),
  - the served output remains valid JSON (warning lives inside the object),
  - fresh reports and reports without a parseable timestamp are not flagged,
  - classification is a pure function of report content + injectable clock.

Purity: no writes, no network, no model. Real-file cases assert only the
stale verdict (their age grows with the wall clock); synthetic cases pin
exact ages with a fixed clock.
"""
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_chat import (maya_local_command, report_staleness,
                       _apply_report_staleness)

LABELS = {"ok": 0}


def _ok(label):
    LABELS["ok"] += 1
    print(label + "=OK")


_NOW = datetime(2026, 9, 17, 8, 0, 0, tzinfo=timezone.utc)
_FRESH = "2026-09-16T08:00:00+00:00"      # 24h old
_STALE = "2026-08-16T08:00:00+00:00"      # 768h old
_LIMIT = "2026-09-14T08:00:00+00:00"      # exactly 72h old


# ---- 1. fresh report is served unchanged ---------------------------------

fresh = {"generated_at": _FRESH, "status": "review_only", "title": "t"}
served = _apply_report_staleness(fresh, now=_NOW)
assert served is fresh and "staleness" not in served
_ok("staleness_fresh_report_unchanged")


# ---- 2. stale report gains the warning -----------------------------------

stale = {"generated_at": _STALE, "status": "review_only", "title": "t"}
served = _apply_report_staleness(stale, now=_NOW)
assert served is not stale
assert served["staleness"]["stale"] is True
assert served["staleness"]["age_hours"] == 768.0
assert served["staleness"]["max_age_hours"] == 72
assert served["staleness"]["generated_at"] == "2026-08-16T08:00:00Z"
assert served["staleness_warning"].startswith("STALE REPORT:")
assert "historical, not current" in served["staleness_warning"]
_ok("staleness_stale_report_flagged")


# ---- 3. boundary: exactly at the limit is not stale ----------------------

at_limit = {"generated_at": _LIMIT, "status": "review_only"}
served = _apply_report_staleness(at_limit, now=_NOW)
assert "staleness" not in served
verdict = report_staleness(at_limit, now=_NOW)
assert verdict["stale"] is False and verdict["age_hours"] == 72.0
_ok("staleness_boundary_exact_limit_not_stale")


# ---- 4. original payload is never mutated --------------------------------

stale = {"generated_at": _STALE, "status": "review_only"}
snapshot = json.dumps(stale, sort_keys=True)
_apply_report_staleness(stale, now=_NOW)
assert json.dumps(stale, sort_keys=True) == snapshot
_ok("staleness_original_payload_not_mutated")


# ---- 5. served output stays JSON-parseable (warning inside the object) ---

out = maya_local_command(":review")
parsed = json.loads(out)  # must not raise
assert "staleness" in parsed and "staleness_warning" in parsed
assert parsed["status"] == "review_only"
_ok("staleness_served_output_parseable")


# ---- 6. unparseable/missing generated_at is never flagged ----------------

for payload in ({"status": "review_only"},
                {"generated_at": "", "status": "review_only"},
                {"generated_at": "not-a-date", "status": "review_only"},
                {"generated_at": None, "status": "review_only"}):
    served = _apply_report_staleness(payload, now=_NOW)
    assert "staleness" not in served, payload
verdict = report_staleness({"generated_at": 12345}, now=_NOW)
assert verdict["stale"] is False and verdict["age_hours"] is None
_ok("staleness_unparseable_generated_at_not_flagged")


# ---- 7. real review reports currently serve as stale ---------------------

for command in (":review", ":income", ":evidence", ":continuity", ":focus"):
    parsed = json.loads(maya_local_command(command))
    assert parsed.get("staleness", {}).get("stale") is True, command
    assert "STALE REPORT:" in parsed.get("staleness_warning", ""), command
_ok("staleness_real_review_reports_flagged_stale")


# ---- 8. serving never writes the report files ----------------------------

root = Path(__file__).resolve().parent
tracked = ("maya_approval_dashboard.json", "maya_income_report_comparison.json",
           "maya_evidence_cluster.json", "maya_conversation_continuity.json",
           "maya_weekly_focus.json")
before = {name: (root / name).read_bytes() for name in tracked
          if (root / name).exists()}
for command in (":review", ":income", ":evidence", ":continuity", ":focus"):
    maya_local_command(command)
after = {name: (root / name).read_bytes() for name in tracked
         if (root / name).exists()}
assert after == before
_ok("staleness_serving_never_writes_files")


# ---- 9. deterministic with an injected clock -----------------------------

stale = {"generated_at": _STALE, "status": "review_only"}
first = _apply_report_staleness(stale, now=_NOW)
second = _apply_report_staleness(stale, now=_NOW)
assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
later = _apply_report_staleness(stale, now=_NOW + timedelta(hours=24))
assert later["staleness"]["age_hours"] == first["staleness"]["age_hours"] + 24.0
_ok("staleness_deterministic_with_injected_clock")


# ---- 10. non-dict payloads pass through untouched -------------------------

for payload in ([1, 2, 3], "plain text", None):
    assert _apply_report_staleness(payload, now=_NOW) is payload
_ok("staleness_non_dict_passthrough")


print("report_staleness_test_ok=%d" % LABELS["ok"])
print("report_staleness_test_attempts=%d" % LABELS["ok"])
if LABELS["ok"] == 10:
    print("test_report_staleness=PASS")
else:
    print("test_report_staleness=FAIL")
    sys.exit(1)
