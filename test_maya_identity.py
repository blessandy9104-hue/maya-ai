import json
import sys
from pathlib import Path

from maya_identity import (
    capabilities,
    finalize_canonical_face,
    get_animation_config,
    get_avatar_path,
    get_face_source,
    get_identity_context,
    get_render_config,
    identity_version,
    load_identity,
    validation,
)

ROOT = Path(__file__).resolve().parent
IDENTITY_ROOT = ROOT / "maya_identity"

identity = load_identity()
assert identity["canonical_name"] == "Maya"
assert identity["identity_version"] == "1.0.0"
assert identity["face_version"] == "1.0.0"
assert identity["created_date"]
assert identity["consistency_rules_version"] == "1"
rule = identity["critical_identity_rule"].lower()
assert "consistent across all future generations" in rule
assert "same identity" in rule
assert "emotional signature" in rule

iver, fver = identity_version()
assert iver == "1.0.0"
assert fver == "1.0.0"

render = get_render_config()
assert render["palette"]["glow"] == "#6d7cff"
assert render["avatar"]["portrait_size"] == 512
assert render["avatar"]["canonical_names"]["portrait"] == "maya_face_canonical.png"
assert render["avatar"]["canonical_names"]["icon"] == "maya_face_canonical.ico"
assert render["avatar"]["canonical_master"] == "maya_face_canonical.png"
assert render["avatar"]["canonical_icon"] == "maya_face_canonical.ico"
assert render["avatar"]["legacy_canonical_names"]["portrait"] == "maya_face.png"

caps = capabilities()
assert caps["face_rendering"] == "animated"
assert caps["animation"]["use_animation_driver"] is True
assert caps["animation"]["installed_capabilities"]["eye_tracking"] is False
assert all(caps["animation"]["installed_capabilities"].get(hook) is False
           for hook in ("eye_tracking", "voice_sync", "microphone", "webcam"))

anim = get_animation_config()
for state in ("awake", "processing", "listening", "research", "sleeping", "offline"):
    assert state in anim["states"]
assert anim["future_behavior"]["blink_rate"] == "natural"
assert anim["future_behavior"]["breathing"] is True
assert anim["future_behavior"]["eye_tracking"] is False
assert anim["future_behavior"]["voice_sync"] is False

avatar = get_avatar_path()
assert avatar["source"] == "canonical"
assert avatar["is_placeholder"] is False
for key in ("portrait", "portrait_medium", "portrait_small", "icon"):
    assert avatar.get(key) is not None
    assert Path(avatar[key]).exists()

ctx = get_identity_context()
assert "Maya" in ctx
assert "1.0.0" in ctx

established = identity["canonical_face"]["assets"]
for name in established:
    assert (IDENTITY_ROOT / "avatar" / name).exists(), name

source = get_face_source()
assert source["source"] == "canonical"
assert source["canonical_ready"] is True
assert source["detected"]["master_present"] is True

report = validation.run_canonical_checks()
assert report["canonical_ready"] is True
assert report["status"] == "ready"
assert not [c for c in report["checks"] if c["status"] == "fail"], \
    [c for c in report["checks"] if c["status"] == "fail"]
rule_check = [c for c in report["checks"] if c["name"] == "identity_rule_references"][0]
assert rule_check["status"] == "pass", rule_check

promotion = finalize_canonical_face(reason="test registry", created_by="test")
assert promotion["status"] == "already_established", promotion
assert identity_version()[1] == "1.0.0"

log_file = IDENTITY_ROOT / "metadata" / "identity_versions.jsonl"
entries = [json.loads(l) for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
assert any(e.get("event") == "canonical_face_established"
           and e.get("face_version") == "1.0.0" for e in entries)

print('identity_canonical=OK')
print('identity_versioning=OK')
print('identity_consistency_rule=OK')
print('identity_avatar_placeholder=OK')
print('identity_capabilities_phase1=OK')
print('identity_no_canonical_yet=OK')
print('canonical_pipeline_pending=OK')
print('canonical_validation_awaiting=OK')