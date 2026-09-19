"""Report lifecycle — archives, deltas, and on-demand refresh for review reports.

The five file-backed review reports (``:review``, ``:income``, ``:evidence``,
``:continuity``, ``:focus``) are point-in-time snapshots. This module makes
them living documents without inventing data:

- **Archive**: ``archive_report`` copies the current snapshot to
  ``report_archive/<stem>-<generated_at stamp>.json``. Naming comes from the
  report's own ``generated_at`` field, so archiving is deterministic and
  idempotent (the same snapshot always archives to the same file).
- **Delta**: ``report_delta`` compares two report payloads (or a report and
  its latest archive) and reports added/removed keys, changed top-level
  scalars, and list-size changes. Bookkeeping keys injected at serve time
  (staleness) and the generation timestamp itself are excluded.
- **Refresh**: ``refresh_report`` archives the current snapshot and then
  regenerates the report **only** through a generator registered in
  ``REPORT_REGISTRY``. No in-tree generator exists for these snapshots today,
  so an unregistered refresh honestly reports ``archived_no_generator`` and
  changes nothing — a fabricated "fresh" report would defeat the staleness
  banners this lifecycle exists to support. Registering a real derivation is
  a one-entry change.

Only ``refresh_report`` (an explicit user command) writes the report file and
its archive. Serving a report never writes anything.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
ARCHIVE_DIR = ROOT / "report_archive"

# Short command names -> report files (single owner; maya_chat serves the
# same files through its file-report branch).
SHORT_NAMES = {
    "review": "maya_approval_dashboard.json",
    "income": "maya_income_report_comparison.json",
    "evidence": "maya_evidence_cluster.json",
    "continuity": "maya_conversation_continuity.json",
    "focus": "maya_weekly_focus.json",
}

# Keys that describe the snapshot rather than its content. Excluded from
# deltas; generated_at also drives archive naming.
_BOOKKEEPING_KEYS = {"generated_at", "staleness", "staleness_warning", "delta"}

# Generators: report filename -> callable(now) -> report payload dict.
# Empty today: the five snapshots have no in-tree derivation. A registered
# generator must be deterministic given ``now`` and write nothing itself.
REPORT_REGISTRY: dict[str, dict[str, Any]] = {
    SHORT_NAMES["review"]: {"label": "approval dashboard", "generator": None},
    SHORT_NAMES["income"]: {"label": "income comparison", "generator": None},
    SHORT_NAMES["evidence"]: {"label": "evidence clusters", "generator": None},
    SHORT_NAMES["continuity"]: {"label": "conversation continuity", "generator": None},
    SHORT_NAMES["focus"]: {"label": "weekly focus", "generator": None},
}


def _norm(value: Any) -> Any:
    return value


def _parse_stamp(value: Any) -> str:
    """Deterministic archive stamp from a report's generated_at field."""
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    text = value.strip().replace("Z", "+00:00")
    date_part = text.split(".")[0].split("+")[0]
    clean = "".join(ch for ch in date_part if ch.isdigit() or ch in "T-:")
    clean = clean.replace("-", "").replace(":", "")
    return clean[:15] + "Z" if clean else "unknown"


def read_report(name: str, root: Path = ROOT):
    path = Path(root) / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def archive_report(name: str, root: Path = ROOT) -> dict[str, Any]:
    """Archive the current snapshot; idempotent per generated_at stamp.

    Writes only inside ``report_archive/``. Never modifies the report itself.
    """
    data = read_report(name, root)
    if not isinstance(data, dict):
        return {"status": "error", "detail": f"Report not readable: {name}"}
    stamp = _parse_stamp(data.get("generated_at"))
    stem = Path(name).stem
    archive_dir = Path(root) / "report_archive"
    target = archive_dir / f"{stem}-{stamp}.json"
    if target.exists():
        return {"status": "ok", "archive": target.name, "already_archived": True,
                "generated_at": data.get("generated_at")}
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "detail": f"Archive write failed: {exc}"}
    return {"status": "ok", "archive": target.name, "already_archived": False,
            "generated_at": data.get("generated_at")}


def latest_archive(name: str, root: Path = ROOT):
    """Most recent archived payload for a report, or None."""
    stem = Path(name).stem
    archive_dir = Path(root) / "report_archive"
    candidates = sorted(archive_dir.glob(f"{stem}-*.json")) if archive_dir.exists() else []
    if not candidates:
        return None
    try:
        return json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def report_delta(old: Any, new: Any) -> dict[str, Any]:
    """Pure structural delta between two report payloads.

    Top-level only, by design: reports are heterogeneous snapshots, and a
    shallow comparison is honest about what changed without pretending to
    understand each report's schema. Container values are summarized by size.
    """
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}
    old_keys = set(old) - _BOOKKEEPING_KEYS
    new_keys = set(new) - _BOOKKEEPING_KEYS
    keys_added = sorted(new_keys - old_keys)
    keys_removed = sorted(old_keys - new_keys)
    scalar_changes = []
    list_changes = []
    for key in sorted(old_keys & new_keys):
        old_value, new_value = _norm(old[key]), _norm(new[key])
        if isinstance(old_value, (dict, list)) or isinstance(new_value, (dict, list)):
            if isinstance(old_value, list) and isinstance(new_value, list) and len(old_value) != len(new_value):
                list_changes.append({"key": key, "old_count": len(old_value), "new_count": len(new_value)})
            elif isinstance(old_value, dict) and isinstance(new_value, dict) and old_value != new_value:
                scalar_changes.append({"key": key, "change": "object content changed"})
            elif isinstance(old_value, list) != isinstance(new_value, list):
                scalar_changes.append({"key": key, "change": "value type changed"})
            continue
        if old_value != new_value:
            scalar_changes.append({"key": key, "old": old_value, "new": new_value})
    changed_count = len(keys_added) + len(keys_removed) + len(scalar_changes) + len(list_changes)
    summary = "unchanged" if changed_count == 0 else (
        f"{changed_count} top-level change(s): "
        f"{len(keys_added)} added, {len(keys_removed)} removed, "
        f"{len(scalar_changes)} changed, {len(list_changes)} list-size"
    )
    return {
        "status": "ok",
        "keys_added": keys_added,
        "keys_removed": keys_removed,
        "scalar_changes": scalar_changes,
        "list_changes": list_changes,
        "summary": summary,
        "changed": changed_count > 0,
    }


def refresh_report(name: str, generate: Callable[[Any], dict] | None = None,
                   root: Path = ROOT, now: Any = None) -> dict[str, Any]:
    """Archive the current snapshot, then regenerate through the registry.

    With no registered (or injected) generator the snapshot is archived and
    the report is left untouched — an honest no-op that keeps the staleness
    banner truthful. With a generator, the new payload is written to the
    report file and the structural delta against the archived snapshot is
    returned. ``generate`` may be injected for hermetic verification.
    """
    registration = REPORT_REGISTRY.get(name)
    generator = generate or (registration or {}).get("generator")
    if registration is None and generator is None:
        return {"status": "error", "detail": f"Unknown report: {name}"}
    current = read_report(name, root)
    if not isinstance(current, dict):
        return {"status": "error", "detail": f"Report not readable: {name}"}
    archived = archive_report(name, root)
    if archived.get("status") != "ok":
        return archived
    if generator is None:
        return {
            "status": "archived_no_generator",
            "report": name,
            "label": (registration or {}).get("label", name),
            "archive": archived.get("archive"),
            "already_archived": archived.get("already_archived", False),
            "detail": "Snapshot archived. No generator is registered for this "
                      "report, so no new data was fabricated; the served "
                      "snapshot keeps its staleness banner until a real "
                      "derivation is registered.",
        }
    new_data = generator(now)
    if not isinstance(new_data, dict):
        return {"status": "error", "detail": "Generator returned a non-dict payload; report left unchanged"}
    if "generated_at" not in new_data and now is not None:
        new_data = dict(new_data)
        new_data["generated_at"] = str(now)
    path = Path(root) / name
    try:
        path.write_text(json.dumps(new_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "detail": f"Report write failed: {exc}"}
    delta = report_delta(current, new_data)
    return {
        "status": "ok",
        "report": name,
        "label": (registration or {}).get("label", name),
        "archive": archived.get("archive"),
        "delta": delta,
        "generated_at": new_data.get("generated_at"),
    }


def report_status(root: Path = ROOT) -> dict[str, Any]:
    """One-line lifecycle status per registered report."""
    rows = []
    for short, name in sorted(SHORT_NAMES.items()):
        data = read_report(name, root)
        registration = REPORT_REGISTRY.get(name, {})
        generated = data.get("generated_at") if isinstance(data, dict) else None
        rows.append({
            "short": short,
            "report": name,
            "label": registration.get("label", name),
            "generated_at": generated,
            "readable": isinstance(data, dict),
            "generator_registered": registration.get("generator") is not None,
        })
    return {"status": "ok", "reports": rows,
            "note": "Snapshots are review-only. Refresh archives the current "
                    "snapshot; regeneration requires a registered generator."}


def resolve_report_name(token: str) -> str | None:
    token = str(token or "").strip().lower()
    if token in SHORT_NAMES:
        return SHORT_NAMES[token]
    if token in REPORT_REGISTRY:
        return token
    for name in REPORT_REGISTRY:
        if Path(name).stem == token:
            return name
    return None


def report_command(user_text: str) -> str | None:
    """Handle :report subcommands; None when input is not a :report command."""
    text = str(user_text or "").strip()
    lowered = text.lower()
    if lowered in (":report", "report status", "show report status"):
        return json.dumps(report_status(), indent=2, ensure_ascii=False)
    if lowered.startswith(":report refresh"):
        token = text[len(":report refresh"):].strip()
        if not token:
            return "Usage: :report refresh <review|income|evidence|continuity|focus>"
        name = resolve_report_name(token)
        if name is None:
            return "Unknown report: {token}. Known reports: {names}".format(
                token=token, names=", ".join(sorted(SHORT_NAMES)))
        return json.dumps(refresh_report(name), indent=2, ensure_ascii=False)
    if lowered.startswith(":report delta"):
        token = text[len(":report delta"):].strip()
        if not token:
            return "Usage: :report delta <review|income|evidence|continuity|focus>"
        name = resolve_report_name(token)
        if name is None:
            return "Unknown report: {token}. Known reports: {names}".format(
                token=token, names=", ".join(sorted(SHORT_NAMES)))
        current = read_report(name)
        archived = latest_archive(name)
        if not isinstance(current, dict):
            return json.dumps({"status": "error", "detail": f"Report not readable: {name}"},
                              indent=2, ensure_ascii=False)
        if archived is None:
            return json.dumps({"status": "no_archive",
                               "detail": "No archive yet. Run :report refresh "
                                         f"{token} to archive the current snapshot first."},
                              indent=2, ensure_ascii=False)
        delta = report_delta(archived, current)
        delta["report"] = name
        return json.dumps(delta, indent=2, ensure_ascii=False)
    if lowered == ":report help":
        return ("Usage: :report — lifecycle status of all review reports; "
                ":report refresh <name> — archive the snapshot and regenerate "
                "when a generator is registered; :report delta <name> — what "
                "changed since the latest archive; :report help.")
    if lowered.startswith(":report"):
        return "Usage: :report, :report refresh <name>, :report delta <name>, or :report help"
    return None
