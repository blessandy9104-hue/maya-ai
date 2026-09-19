"""Canonical face pipeline: detection, validation, versioned promotion.

Runs in two modes:

- real repository (canonical established): detection must report canonical,
  validation must be ready, promotion must already be established and
  idempotent (no mutation on repeat calls).
- temporary simulated repository (canonical present): detection must switch to
  canonical, validation must pass, promotion must bump face_version 0.0.0 ->
  1.0.0 with a full transition record, and be idempotent.

The simulation patches maya_identity.identity module globals ONLY and restores
them afterwards. Real identity.json / metadata / avatar are never written.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

import maya_identity as maya
import maya_identity.identity as idm

PACKAGE = ROOT / "maya_identity"


def _strip_established_events(log):
    """Simulated repo must start pre-establishment: drop any recorded
    canonical_face_established events copied from the real history."""
    lines = log.read_text(encoding="utf-8").splitlines()
    kept = [l for l in lines
            if l.strip() and "canonical_face_established" not in l]
    if kept:
        log.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _reset_to_placeholder(identity_file):
    """The simulated repo's copied identity.json records the real repo's
    established state; rewind it to the pre-promotion placeholder state so
    the simulation exercises the 0.0.0 -> 1.0.0 transition record path."""
    data = json.loads(identity_file.read_text(encoding="utf-8"))
    data["face_version"] = "0.0.0-placeholder"
    data["canonical_face"] = {
        "status": "pending",
        "face_version": "0.0.0-placeholder",
    }
    identity_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _restore(keys, caches):
    for name, value in keys:
        setattr(idm, name, value)
    for name in caches:
        setattr(idm, name, None)


def test_canonical_established_is_non_mutating():
    before_log = idm.VERSIONS_LOG.read_text(encoding="utf-8") if idm.VERSIONS_LOG.exists() else ""
    before_identity = idm.IDENTITY_FILE.read_text(encoding="utf-8")

    report = maya.validation.run_canonical_checks()
    assert report["canonical_ready"] is True
    assert report["status"] == "ready", report["status"]
    assert report["summary"]["failed"] == 0

    promotion = maya.finalize_canonical_face(reason="should be skipped", created_by="test")
    assert promotion["status"] == "already_established", promotion

    after_log = idm.VERSIONS_LOG.read_text(encoding="utf-8") if idm.VERSIONS_LOG.exists() else ""
    after_identity = idm.IDENTITY_FILE.read_text(encoding="utf-8")
    assert before_log == after_log, "versions log mutated in established state"
    assert before_identity == after_identity, "identity.json mutated in established state"
    assert idm.identity_version()[1] == "1.0.0"


def test_simulated_canonical_detection_and_promotion():
    from PIL import Image

    tmp = Path(tempfile.mkdtemp(prefix="maya_canonical_"))
    package = tmp / "maya_identity"
    avatar = package / "avatar"
    for sub in ("configuration", "metadata", "prompts", "avatar"):
        (package / sub).mkdir(parents=True, exist_ok=True)

    shutil.copy2(PACKAGE / "identity.json", package / "identity.json")
    _reset_to_placeholder(package / "identity.json")
    shutil.copy2(PACKAGE / "configuration" / "appearance.json", package / "configuration" / "appearance.json")
    shutil.copy2(PACKAGE / "configuration" / "animation.json", package / "configuration" / "animation.json")
    shutil.copy2(PACKAGE / "metadata" / "identity_versions.jsonl", package / "metadata" / "identity_versions.jsonl")
    _strip_established_events(package / "metadata" / "identity_versions.jsonl")
    shutil.copy2(PACKAGE / "metadata" / "consistency_rules.md", package / "metadata" / "consistency_rules.md")
    shutil.copy2(PACKAGE / "prompts" / "maya_face_generation.md", package / "prompts" / "maya_face_generation.md")
    for ph in PACKAGE.glob("avatar/*placeholder*"):
        shutil.copy2(ph, avatar / ph.name)

    master = avatar / "maya_face_canonical.png"
    icon = avatar / "maya_face_canonical.ico"
    Image.new("RGBA", (512, 512), (40, 50, 90, 255)).save(master, format="PNG")
    img = Image.new("RGBA", (256, 256), (40, 50, 90, 255))
    img.save(icon, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])

    keys = [
        ("ROOT", idm.ROOT),
        ("IDENTITY_FILE", idm.IDENTITY_FILE),
        ("APPEARANCE_FILE", idm.APPEARANCE_FILE),
        ("ANIMATION_FILE", idm.ANIMATION_FILE),
        ("AVATAR_DIR", idm.AVATAR_DIR),
        ("VERSIONS_LOG", idm.VERSIONS_LOG),
        ("GENERATION_PROMPT", idm.GENERATION_PROMPT),
        ("CONSISTENCY_RULES", idm.CONSISTENCY_RULES),
    ]
    caches = ("_identity_cache", "_appearance_cache", "_animation_cache")
    saved = [(n, getattr(idm, n)) for n, _ in keys]

    try:
        idm.ROOT = package
        idm.IDENTITY_FILE = package / "identity.json"
        idm.APPEARANCE_FILE = package / "configuration" / "appearance.json"
        idm.ANIMATION_FILE = package / "configuration" / "animation.json"
        idm.AVATAR_DIR = avatar
        idm.VERSIONS_LOG = package / "metadata" / "identity_versions.jsonl"
        idm.GENERATION_PROMPT = package / "prompts" / "maya_face_generation.md"
        idm.CONSISTENCY_RULES = package / "metadata" / "consistency_rules.md"
        for name in caches:
            setattr(idm, name, None)

        source = maya.get_face_source()
        assert source["canonical_ready"] is True
        assert source["source"] == "canonical"
        assert source["detected"]["master"] == "maya_face_canonical.png"
        assert source["detected"]["icon"] == "maya_face_canonical.ico"

        resolved = maya.get_avatar_path()
        assert resolved["source"] == "canonical"
        assert resolved["is_placeholder"] is False

        report = maya.validation.run_canonical_checks()
        assert report["canonical_ready"] is True
        assert report["status"] == "awaiting", report["status"]

        promotion = maya.finalize_canonical_face(
            reason="Phase 2 canonical face established",
            generation_reference="prompts/maya_face_generation.md",
            created_by="pipeline_test",
        )
        assert promotion["status"] == "established", promotion
        assert promotion["face_version"] == "1.0.0"
        assert promotion["previous_face_version"] == "0.0.0-placeholder"

        assert (avatar / "maya_face_canonical_256.png").exists()
        assert (avatar / "maya_face_canonical_128.png").exists()
        assert (avatar / "maya_face_canonical_48.png").exists()

        identity = json.loads(idm.IDENTITY_FILE.read_text(encoding="utf-8"))
        assert identity["face_version"] == "1.0.0"
        assert identity["canonical_face"]["status"] == "established"
        assert identity["canonical_face"]["previous_face_version"] == "0.0.0-placeholder"

        rows = [json.loads(l) for l in idm.VERSIONS_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        events = [r for r in rows if r.get("event") == "canonical_face_established"]
        assert len(events) == 1
        ev = events[0]
        for field in ("previous_face_version", "face_version", "date", "reason",
                      "asset_names", "identity_rules_applied", "created_by"):
            assert ev.get(field), field
        assert ev["previous_face_version"] == "0.0.0-placeholder"
        assert ev["face_version"] == "1.0.0"
        assert "maya_face_canonical.png" in ev["asset_names"]
        assert "maya_face_canonical.ico" in ev["asset_names"]

        report2 = maya.validation.run_canonical_checks()
        assert report2["status"] == "ready", report2["summary"]

        second = maya.finalize_canonical_face(reason="duplicate call", created_by="test")
        assert second["status"] == "already_established", second
        rows_after = [json.loads(l) for l in idm.VERSIONS_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len([r for r in rows_after if r.get("event") == "canonical_face_established"]) == 1

        rules = idm.CONSISTENCY_RULES.read_text(encoding="utf-8")
        assert "Canonical Face Established** | established |" in rules
    finally:
        _restore(saved, caches)
        shutil.rmtree(tmp, ignore_errors=True)


def test_pending_rule_referenced_three_places():
    token = idm.IDENTITY_RULE.split(", maintaining")[0].lower()
    identity = json.loads(idm.IDENTITY_FILE.read_text(encoding="utf-8"))
    prompt = idm.GENERATION_PROMPT.read_text(encoding="utf-8").lower() if idm.GENERATION_PROMPT.exists() else ""
    rules = idm.CONSISTENCY_RULES.read_text(encoding="utf-8").lower() if idm.CONSISTENCY_RULES.exists() else ""
    assert token in identity["critical_identity_rule"].lower()
    assert token in prompt
    assert token in rules


for _name, _fn in sorted(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        _fn()
print("canonical_pipeline=OK")
print("canonical_detection_auto=OK")
print("canonical_promotion_gated=OK")
print("canonical_promotion_idempotent=OK")
print("canonical_identity_preserved=OK")
print("canonical_validation_pass=OK")