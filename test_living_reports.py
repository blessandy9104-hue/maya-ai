"""Living reports verification suite.

Pins the report lifecycle: pure structural deltas, stamp-based idempotent
archives, registry-gated refresh (no fabricated data without a registered
generator), the :report command surface, and the invariant that serving a
report never writes anything. Write-mode checks run in a temporary root;
real report files are only read.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_chat
import maya_report_lifecycle as lifecycle


def _ok(label: str) -> None:
    print(label + " =OK")


TRACKED_REPORTS = (
    "maya_approval_dashboard.json", "maya_income_report_comparison.json",
    "maya_evidence_cluster.json", "maya_conversation_continuity.json",
    "maya_weekly_focus.json",
)


def check_delta_purity() -> None:
    old = {"status": "review_only", "count": 3, "source": "tasks.json",
           "items": [1, 2, 3], "generated_at": "2026-08-16T08:00:00+00:00"}
    new = {"status": "review_only", "count": 5, "source": "tasks.json",
           "items": [1, 2], "extra": True, "generated_at": "2026-09-15T08:00:00+00:00"}
    old_json = json.dumps(old, sort_keys=True)
    new_json = json.dumps(new, sort_keys=True)
    delta = lifecycle.report_delta(old, new)
    assert delta["status"] == "ok" and delta["changed"] is True
    assert delta["keys_added"] == ["extra"]
    assert delta["keys_removed"] == []
    assert {"key": "count", "old": 3, "new": 5} in delta["scalar_changes"]
    assert {"key": "items", "old_count": 3, "new_count": 2} in delta["list_changes"]
    assert not any(c["key"] == "generated_at" for c in delta["scalar_changes"])
    assert json.dumps(old, sort_keys=True) == old_json
    assert json.dumps(new, sort_keys=True) == new_json
    same = lifecycle.report_delta(old, old)
    assert same["changed"] is False and same["summary"] == "unchanged"
    _ok("delta pure, structural, bookkeeping excluded")
    _ok("delta unchanged case detected")


def check_archive_stamp_and_idempotence() -> None:
    stamp = lifecycle._parse_stamp("2026-08-16T08:55:23.329937+00:00")
    assert stamp == "20260816T085523Z", stamp
    assert lifecycle._parse_stamp("") == "unknown"
    assert lifecycle._parse_stamp(None) == "unknown"
    assert lifecycle._parse_stamp("garbage") == "unknown"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "demo.json").write_text(json.dumps(
            {"generated_at": "2026-08-16T08:55:23+00:00", "value": 1}), encoding="utf-8")
        first = lifecycle.archive_report("demo.json", root=root)
        assert first["status"] == "ok" and first["already_archived"] is False
        archives = list((root / "report_archive").glob("demo-*.json"))
        assert len(archives) == 1 and archives[0].name == "demo-20260816T085523Z.json"
        original = (root / "demo.json").read_bytes()
        second = lifecycle.archive_report("demo.json", root=root)
        assert second["status"] == "ok" and second["already_archived"] is True
        assert (root / "demo.json").read_bytes() == original
        assert len(list((root / "report_archive").glob("demo-*.json"))) == 1
    _ok("archive stamp deterministic and idempotent")


def check_refresh_without_generator_is_honest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "maya_weekly_focus.json").write_text(json.dumps(
            {"generated_at": "2026-08-16T08:00:00+00:00", "value": 1}), encoding="utf-8")
        original = (root / "maya_weekly_focus.json").read_bytes()
        result = lifecycle.refresh_report("maya_weekly_focus.json", root=root)
        assert result["status"] == "archived_no_generator", result
        assert result["already_archived"] is False
        assert "no new data was fabricated" in result["detail"]
        assert (root / "maya_weekly_focus.json").read_bytes() == original
        unknown = lifecycle.refresh_report("demo.json", root=root)
        assert unknown["status"] == "error" and "Unknown report" in unknown["detail"]
        (root / "demo.json").write_text(json.dumps(
            {"generated_at": "2026-08-16T09:00:00+00:00", "v": 1}), encoding="utf-8")
        injected = lifecycle.refresh_report(
            "demo.json", generate=lambda moment: {"generated_at": str(moment), "v": 2},
            root=root, now="2026-09-15T10:00:00+00:00")
        assert injected["status"] == "ok", injected
        assert injected["delta"]["scalar_changes"] == [{"key": "v", "old": 1, "new": 2}]
    _ok("refresh without generator archives and changes nothing")
    _ok("unknown report errors without generator, works with injected one")


def check_refresh_with_injected_generator() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "demo.json").write_text(json.dumps(
            {"generated_at": "2026-08-16T08:00:00+00:00", "value": 1,
             "rows": [1, 2, 3]}), encoding="utf-8")
        now = "2026-09-15T10:00:00+00:00"

        def generator(moment):
            return {"generated_at": str(moment), "value": 7, "rows": [1, 2], "fresh": True}

        result = lifecycle.refresh_report("demo.json", generate=generator, root=root, now=now)
        assert result["status"] == "ok", result
        assert result["generated_at"] == now
        assert result["delta"]["keys_added"] == ["fresh"]
        assert {"key": "value", "old": 1, "new": 7} in result["delta"]["scalar_changes"]
        assert {"key": "rows", "old_count": 3, "new_count": 2} in result["delta"]["list_changes"]
        new_data = json.loads((root / "demo.json").read_text(encoding="utf-8"))
        assert new_data["value"] == 7 and new_data["generated_at"] == now
        archives = list((root / "report_archive").glob("demo-*.json"))
        assert len(archives) == 1
        archived = json.loads(archives[0].read_text(encoding="utf-8"))
        assert archived["value"] == 1
        broken = lifecycle.refresh_report("demo.json", generate=lambda moment: "not-a-dict", root=root, now=now)
        assert broken["status"] == "error"
        assert json.loads((root / "demo.json").read_text(encoding="utf-8"))["value"] == 7
    _ok("refresh regenerates via registered/injected generator with delta")
    _ok("non-dict generator output rejected, report preserved")


def check_registry_covers_report_surface() -> None:
    assert set(lifecycle.SHORT_NAMES.values()) == set(TRACKED_REPORTS)
    assert set(lifecycle.REPORT_REGISTRY) == set(TRACKED_REPORTS)
    for name, registration in lifecycle.REPORT_REGISTRY.items():
        assert isinstance(registration.get("label"), str) and registration["label"]
        assert registration.get("generator") is None or callable(registration["generator"])
    assert lifecycle.resolve_report_name("review") == "maya_approval_dashboard.json"
    assert lifecycle.resolve_report_name("maya_weekly_focus.json") == "maya_weekly_focus.json"
    assert lifecycle.resolve_report_name("bogus") is None
    _ok("registry maps the full review-report surface")


def check_command_surface() -> None:
    status = json.loads(lifecycle.report_command(":report"))
    assert status["status"] == "ok" and len(status["reports"]) == 5
    assert lifecycle.report_command(":report help").startswith("Usage: :report")
    assert lifecycle.report_command(":report refresh").startswith("Usage: :report refresh")
    assert lifecycle.report_command(":report refresh bogus").startswith("Unknown report: bogus")
    assert lifecycle.report_command(":report nonsense").startswith("Usage:")
    assert lifecycle.report_command("what is a black hole") is None
    _ok("command surface complete with usage fallbacks")


def check_real_delta_against_probe_archive() -> None:
    out = lifecycle.report_command(":report delta review")
    parsed = json.loads(out)
    assert parsed["status"] == "ok"
    assert parsed["report"] == "maya_approval_dashboard.json"
    missing = json.loads(lifecycle.report_command(":report delta continuity"))
    assert missing["status"] == "no_archive"
    _ok("delta command compares live report against latest archive")


def check_serving_and_status_write_free() -> None:
    root = Path(__file__).resolve().parent
    before = {name: (root / name).read_bytes() for name in TRACKED_REPORTS
              if (root / name).exists()}
    for command in (":review", ":income", ":evidence", ":continuity", ":focus"):
        maya_chat.maya_local_command(command)
    maya_chat.maya_local_command(":report")
    maya_chat.maya_local_command(":report delta review")
    after = {name: (root / name).read_bytes() for name in TRACKED_REPORTS
             if (root / name).exists()}
    assert before == after
    review = json.loads(maya_chat.maya_local_command(":review"))
    assert review.get("staleness", {}).get("stale") is True
    assert "STALE REPORT:" in review.get("staleness_warning", "")
    _ok("serving and status remain byte-write-free, banners intact")


def main() -> int:
    check_delta_purity()
    check_archive_stamp_and_idempotence()
    check_refresh_without_generator_is_honest()
    check_refresh_with_injected_generator()
    check_registry_covers_report_surface()
    check_command_surface()
    check_real_delta_against_probe_archive()
    check_serving_and_status_write_free()
    print("test_living_reports=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
