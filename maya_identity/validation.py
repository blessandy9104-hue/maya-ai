"""Canonical face validation.

Implements the canonical face validation system:

1. existence / loadability   canonical master + icon exist and open
2. matching naming           files match the expected canonical names
3. valid image format        PNG is a square raster, ICO is a valid icon set
4. GUI rendering compat      resolver produces canonical assets for the widget
5. identity version rules    version fields valid; transition recorded on bump

``run_canonical_checks()`` returns a report with per-check status:

- ``pass``    check satisfied
- ``awaiting`` canonical asset not present yet (pipeline ready, not promoted)
- ``fail``    check violated (must be resolved before promotion)

Overall ``status`` is ``ready`` / ``awaiting`` / ``fail``. This module never
writes or mutates identity state; promotion is owned by
``maya_identity.identity.finalize_canonical_face``.
"""
from __future__ import annotations

import json
import re

from . import identity as _identity


def _text(path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower().strip())


def _check(name: str, status: str, detail: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail}


def _probe_image(path) -> dict:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return {"ok": True, "format": im.format, "width": im.width, "height": im.height}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_canonical_checks() -> dict:
    source = _identity.get_face_source()
    ready = source["canonical_ready"]
    avatar = _identity._avatar_config()
    expected_master = avatar.get("canonical_master") or _identity.DEFAULT_CANONICAL_MASTER
    expected_icon = avatar.get("canonical_icon") or _identity.DEFAULT_CANONICAL_ICON
    master = source.get("master")
    icon = source.get("icon")
    master_missing = master is None

    checks = []

    # 1. matching naming
    naming_ok = (
        source["detected"]["master"] == expected_master
        and source["detected"]["icon"] == expected_icon
    )
    checks.append(_check(
        "canonical_naming",
        "pass" if naming_ok else ("awaiting" if not ready else "fail"),
        detail=expected_master + ", " + expected_icon,
    ))

    # 2. existence / loadability
    exists = bool(master and icon) and not master_missing
    checks.append(_check(
        "canonical_existence",
        "pass" if exists else ("awaiting" if not ready else "fail"),
    ))

    # 3. valid PNG format (square, >= portrait_small)
    png = _probe_image(master) if master else {"ok": False}
    png_ok = (
        png.get("ok") and png.get("format") == "PNG"
        and png["width"] == png["height"] and png["width"] >= 128
    )
    png_detail = str(png.get("error") or f"{png.get('format')} {png.get('width')}x{png.get('height')}")
    checks.append(_check(
        "canonical_png",
        "pass" if png_ok else ("awaiting" if not exists else "fail"),
        detail=png_detail,
    ))

    # 4. valid ICO format
    ico = _probe_image(icon) if icon else {"ok": False}
    ico_ok = ico.get("ok") and ico.get("format") == "ICO"
    ico_detail = str(ico.get("error") or ico.get("format") or "missing")
    checks.append(_check(
        "canonical_ico",
        "pass" if ico_ok else ("awaiting" if not exists else "fail"),
        detail=ico_detail,
    ))

    # 5. GUI rendering compatibility (resolver returns canonical for widget sizes)
    gui_ok = False
    if ready:
        resolved = _identity.get_avatar_path()
        gui_ok = bool(resolved.get("icon_png")) and resolved.get("source") == "canonical"
    checks.append(_check(
        "gui_compatibility",
        "pass" if gui_ok else ("awaiting" if not ready else "fail"),
        detail="resolver resolves canonical assets for GUI sizes" if gui_ok else "",
    ))

    # identity rules referenced in all three files
    rule = _norm(_identity.IDENTITY_RULE)
    token = rule.split(", maintaining")[0]
    identity = _identity.load_identity()
    rule_in_json = token in _norm(identity.get("critical_identity_rule", ""))
    rule_in_prompt = token in _norm(_text(_identity.GENERATION_PROMPT))
    rule_in_rules_md = token in _norm(_text(_identity.CONSISTENCY_RULES))
    checks.append(_check(
        "identity_rule_references",
        "pass" if rule_in_json and rule_in_prompt and rule_in_rules_md else "fail",
        detail=f"json={rule_in_json} prompt={rule_in_prompt} rules_md={rule_in_rules_md}",
    ))

    # version fields present
    fields = ("identity_version", "face_version", "created_date",
              "canonical_name", "consistency_rules_version")
    missing = [f for f in fields if not identity.get(f)]
    checks.append(_check(
        "identity_version_fields",
        "pass" if not missing else "fail",
        detail=",".join(missing),
    ))

    # version control transition record
    face_version = identity.get("face_version", "")
    if face_version == _identity.FACE_VERSION_CANONICAL:
        rows = [json.loads(l) for l in _text(_identity.VERSIONS_LOG).splitlines() if l.strip()]
        events = [
            r for r in rows
            if r.get("event") == "canonical_face_established"
            and r.get("face_version") == face_version
        ]
        required = ("previous_face_version", "face_version", "date", "reason", "asset_names")
        valid = any(all(r.get(k) for k in required) for r in events)
        checks.append(_check(
            "canonical_transition_record",
            "pass" if valid else "fail",
            detail=f"{len(events)} event(s)" if events else "missing transition event",
        ))
    else:
        checks.append(_check(
            "canonical_transition_record",
            "awaiting",
            detail="promotion via finalize_canonical_face() pending",
        ))

    failed = [c for c in checks if c["status"] == "fail"]
    awaiting = [c for c in checks if c["status"] == "awaiting"]
    if failed:
        status = "fail"
    elif awaiting:
        status = "awaiting"
    else:
        status = "ready"

    return {
        "canonical_ready": ready,
        "status": status,
        "face_version": face_version,
        "checks": checks,
        "summary": {
            "passed": len(checks) - len(failed) - len(awaiting),
            "awaiting": len(awaiting),
            "failed": len(failed),
        },
    }


def require_canonical_ready(report: dict | None = None) -> None:
    report = report or run_canonical_checks()
    if not report["canonical_ready"]:
        raise AssertionError("canonical assets (master + icon) not present")
    if report["status"] == "fail":
        failed = [c["name"] for c in report["checks"] if c["status"] == "fail"]
        raise AssertionError(f"canonical validation failed: {failed}")


if __name__ == "__main__":
    import json as _json
    report = run_canonical_checks()
    print(_json.dumps(report, indent=2))