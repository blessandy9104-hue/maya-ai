"""Maya identity loader and version control.

Identity files are the ONE source of truth for Maya's appearance:

- identity.json                    canonical identity + versioning
- configuration/appearance.json   colors, lighting, style, holographic effects, avatar assets
- configuration/animation.json    animation behaviour (phase-1 architecture only)
- metadata/identity_versions.jsonl  identity evolution history
- avatar/                         asset directory (placeholder -> canonical)

Canonical face pipeline:

- ``get_avatar_path()``           auto-detects canonical assets. When the
                                  canonical master + icon exist they are used
                                  automatically over placeholders.
- ``get_face_source()``           reports whether the canonical face is present
                                  and which files were detected.
- ``finalize_canonical_face()``   validation-gated, idempotent promotion:
                                  face_version 0.0.0-placeholder -> 1.0.0,
                                  materializes size variants, records the
                                  transition in identity_versions.jsonl.
- ``validation.run_canonical_checks()`` full canonical face validation report.
- ``rollback.py`` read-only DESIGN SUPPORT for identity evolution rollback
  (planning only; no autonomous rollback; activation requires operator
  approval).

Public interface (re-exported by maya_identity/__init__.py):

- ``load_identity()``          canonical identity dict
- ``get_appearance_config()``  appearance/rendering configuration
- ``get_render_config()``      backward-compatible alias of get_appearance_config
- ``get_animation_config()``   animation configuration
- ``get_avatar_path()``        resolved avatar asset paths (canonical preferred)
- ``get_face_source()``        canonical face detection report
- ``get_identity_context()``   canonical identity text
- ``capabilities()``           phase-1 capability report
- ``identity_version()``       (identity_version, face_version)
- ``log_identity_version()``   append an identity evolution record
- ``finalize_canonical_face()`` canonical face promotion (gated & idempotent)
"""
from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IDENTITY_FILE = ROOT / "identity.json"
APPEARANCE_FILE = ROOT / "configuration" / "appearance.json"
ANIMATION_FILE = ROOT / "configuration" / "animation.json"
EFFECTS_FILE = ROOT / "configuration" / "effects.json"
AVATAR_DIR = ROOT / "avatar"
GEOMETRY_DIR = ROOT / "geometry"
EXPRESSION_DIR = ROOT / "expressions"
VERSIONS_LOG = ROOT / "metadata" / "identity_versions.jsonl"
GENERATION_PROMPT = ROOT / "prompts" / "maya_face_generation.md"
CONSISTENCY_RULES = ROOT / "metadata" / "consistency_rules.md"

FACE_VERSION_CANONICAL = "1.0.0"
DEFAULT_CANONICAL_MASTER = "maya_face_canonical.png"
DEFAULT_CANONICAL_ICON = "maya_face_canonical.ico"
IDENTITY_RULE = (
    "The face remains consistent across all future generations, maintaining the "
    "same identity, facial structure, recognizable presence, and emotional signature."
)
GEOMETRY_RULE = (
    "Maya's visual identity must remain consistent across all future generations "
    "and transformations. The same underlying geometry, facial proportions, "
    "structural patterns, recognizable presence, and emotional signature must "
    "always be preserved."
)

_GEOMETRY_MODELS = (
    ("identity", "maya_geometry.json"),
    ("facial_structure", "facial_structure.json"),
    ("symmetry", "symmetry_rules.json"),
    ("neural_pattern", "neural_pattern.json"),
)

_ENGINE_CONFIG_FILES = {
    "expression_engine": ("configuration", "expression_engine.json"),
    "voice": ("voice_sync", "voice_config.json"),
    "awareness": ("awareness", "awareness_config.json"),
    "evolution": ("evolution", "evolution_rules.json"),
    "nervous_mapping": ("nervous_system", "cognitive_mapping.json"),
    "nervous_patterns": ("nervous_system", "response_patterns.json"),
    "visual_symbols": ("visual_language", "symbols.json"),
    "visual_patterns": ("visual_language", "patterns.json"),
    "visual_meanings": ("visual_language", "meaning_map.json"),
}

_identity_cache: dict | None = None
_appearance_cache: dict | None = None
_animation_cache: dict | None = None
_effects_cache: dict | None = None
_bundle_cache: dict | None = None
_expression_cache: dict | None = None
_engine_cache: dict | None = None


def _load_json(path: Path, default: dict | None = None) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default or {})


def load_identity() -> dict:
    global _identity_cache
    if _identity_cache is None:
        _identity_cache = _load_json(IDENTITY_FILE)
    return _identity_cache


def get_appearance_config() -> dict:
    global _appearance_cache
    if _appearance_cache is None:
        _appearance_cache = _load_json(APPEARANCE_FILE)
    return _appearance_cache


def get_render_config() -> dict:
    return get_appearance_config()


def get_animation_config() -> dict:
    global _animation_cache
    if _animation_cache is None:
        _animation_cache = _load_json(ANIMATION_FILE)
    return _animation_cache


def load_effects_config() -> dict:
    global _effects_cache
    if _effects_cache is None:
        _effects_cache = _load_json(EFFECTS_FILE)
    return _effects_cache


def load_geometry_bundle() -> dict:
    global _bundle_cache
    if _bundle_cache is None:
        bundle = {}
        for key, filename in _GEOMETRY_MODELS:
            bundle[key] = _load_json(GEOMETRY_DIR / filename)
        if not bundle.get("identity"):
            bundle["identity"] = {"seed": 21098}
        _bundle_cache = bundle
    return _bundle_cache


def load_expression(state: str) -> dict:
    global _expression_cache
    if _expression_cache is None:
        _expression_cache = {}
    if state not in _expression_cache:
        _expression_cache[state] = _load_json(EXPRESSION_DIR / f"{state}.json")
    return _expression_cache[state]


def geometry_version() -> str:
    return load_identity().get("geometry_version", "0.0.0")


def load_engine_config(name: str) -> dict:
    global _engine_cache
    if _engine_cache is None:
        _engine_cache = {}
    parts = _ENGINE_CONFIG_FILES.get(name)
    if parts is None:
        return {}
    if name not in _engine_cache:
        _engine_cache[name] = _load_json(ROOT.joinpath(*parts))
    return _engine_cache[name]


def identity_version() -> tuple[str, str]:
    identity = load_identity()
    return identity.get("identity_version", ""), identity.get("face_version", "")


def _avatar_config() -> dict:
    return get_appearance_config().get("avatar", {})


def _candidate_names(key: str) -> list:
    avatar = _avatar_config()
    names = []
    for source_key in ("canonical_names", "legacy_canonical_names"):
        mapping = avatar.get(source_key) or {}
        if key in mapping:
            names.append(mapping[key])
    master = avatar.get("canonical_master") or DEFAULT_CANONICAL_MASTER
    if key != "icon":
        names.append(master)
    return names


def get_avatar_path() -> dict:
    avatar = _avatar_config()
    placeholders = avatar.get("placeholder_names", {})
    avatar_keys = ("portrait", "portrait_medium", "portrait_small", "icon_png", "awake", "dim", "icon")

    resolved = {}
    canonical_hit = False
    placeholder_hit = False
    for key in avatar_keys:
        chosen = None
        for name in _candidate_names(key):
            candidate = AVATAR_DIR / name
            if candidate.exists():
                chosen = candidate
                canonical_hit = True
                break
        if chosen is None:
            placeholder_name = placeholders.get(key)
            if placeholder_name:
                placeholder = AVATAR_DIR / placeholder_name
                if placeholder.exists():
                    chosen = placeholder
                    placeholder_hit = True
        resolved[key] = chosen

    if canonical_hit:
        source, is_placeholder = "canonical", False
    elif placeholder_hit:
        source, is_placeholder = "placeholder", True
    else:
        source, is_placeholder = "unknown", False

    return {
        **{k: resolved[k] for k in avatar_keys},
        "is_placeholder": is_placeholder,
        "source": source,
    }


def get_face_source() -> dict:
    avatar = _avatar_config()
    master_name = avatar.get("canonical_master") or DEFAULT_CANONICAL_MASTER
    icon_name = avatar.get("canonical_icon") or DEFAULT_CANONICAL_ICON
    master = AVATAR_DIR / master_name
    icon = AVATAR_DIR / icon_name
    canonical_ready = master.exists() and icon.exists()
    return {
        "source": "canonical" if canonical_ready else "placeholder",
        "canonical_ready": canonical_ready,
        "is_placeholder": not canonical_ready,
        "master": str(master) if master.exists() else None,
        "icon": str(icon) if icon.exists() else None,
        "master_name": master_name,
        "icon_name": icon_name,
        "detected": {
            "master": master_name,
            "icon": icon_name,
            "master_present": master.exists(),
            "icon_present": icon.exists(),
        },
    }


def get_identity_context() -> str:
    identity = load_identity()
    version = identity_version()
    return (
        f"Identity: {identity.get('canonical_name', 'Maya')} "
        f"v{version[0]} face {version[1]} "
        f"(consistency_rules v{identity.get('consistency_rules_version', '?')})"
    )


_PHASE2_CAPABILITIES = (
    "blink",
    "breath",
    "gaze",
    "micro_expression",
    "voice_sync",
    "microphone",
    "webcam",
)


def capabilities() -> dict:
    animation = get_animation_config()
    caps = animation.get("capabilities", {})
    installed = {name: bool(caps.get(name, False)) for name in _PHASE2_CAPABILITIES}
    installed["eye_tracking"] = bool(caps.get("eye_tracking", False))
    return {
        "face_rendering": "animated",
        "animation": {
            "use_animation_driver": True,
            "installed_capabilities": installed,
        },
    }


def log_identity_version(entry: dict) -> None:
    row = {
        "identity_version": entry.get("identity_version", ""),
        "face_version": entry.get("face_version", ""),
        "date": entry.get("date", ""),
        "created_by": entry.get("created_by", ""),
        "change": entry.get("change", ""),
        "canonical": bool(entry.get("canonical", False)),
    }
    _append_jsonl(VERSIONS_LOG, row)


def _append_jsonl(path: Path, row: dict) -> None:
    previous = ""
    if path.exists():
        previous = path.read_text(encoding="utf-8")
    separator = "\n" if previous and not previous.endswith("\n") else ""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(separator + json.dumps(row) + "\n")


def _materialize_variants(master: Path) -> list:
    from PIL import Image

    avatar = _avatar_config()
    created = []
    try:
        with Image.open(master) as im:
            im = im.convert("RGBA")
            for name, size in (avatar.get("canonical_variants") or {}).items():
                target = AVATAR_DIR / name
                if target.exists():
                    created.append(name)
                    continue
                resized = im.resize((size, size), Image.Resampling.LANCZOS)
                resized.save(target, format="PNG")
                created.append(name)
    except Exception:
        pass
    return created


def _asset_names() -> list:
    avatar = _avatar_config()
    names = []
    master = avatar.get("canonical_master") or DEFAULT_CANONICAL_MASTER
    icon = avatar.get("canonical_icon") or DEFAULT_CANONICAL_ICON
    names.append(master)
    names.append(icon)
    for variant in (avatar.get("canonical_variants") or {}):
        names.append(variant)
    return names


def finalize_canonical_face(
    reason: str | None = None,
    generation_reference: str = "prompts/maya_face_generation.md",
    created_by: str = "operator",
) -> dict:
    from . import validation as _validation

    report = _validation.run_canonical_checks()
    if not report["canonical_ready"]:
        return {
            "status": "skipped",
            "reason": "canonical_assets_not_present",
            "canonical_ready": False,
            "report": report["summary"],
        }
    if report["status"] == "fail":
        return {"status": "validation_failed", "report": report["summary"]}

    identity = load_identity()
    previous = identity.get("face_version", "")
    if previous == FACE_VERSION_CANONICAL:
        return {"status": "already_established", "face_version": previous}

    source = get_face_source()
    asset_names = _asset_names()
    identity["face_version"] = FACE_VERSION_CANONICAL
    identity["canonical_face"] = {
        "status": "established",
        "face_version": FACE_VERSION_CANONICAL,
        "previous_face_version": previous,
        "established_date": _date.today().isoformat(),
        "generation_reference": generation_reference,
        "created_by": created_by,
        "assets": asset_names,
        "identity_rules_applied": [IDENTITY_RULE],
    }
    with IDENTITY_FILE.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(identity, indent=2, ensure_ascii=False) + "\n")

    created_variants = []
    if source.get("master"):
        created_variants = _materialize_variants(Path(source["master"]))

    entry = {
        "event": "canonical_face_established",
        "identity_version": identity.get("identity_version", ""),
        "previous_face_version": previous,
        "face_version": FACE_VERSION_CANONICAL,
        "date": _date.today().isoformat(),
        "reason": reason or "Canonical face established per Phase 2 pipeline",
        "generation_reference": generation_reference,
        "asset_names": asset_names,
        "materialized_variants": created_variants,
        "identity_rules_applied": [IDENTITY_RULE],
        "consistency_rules_version": identity.get("consistency_rules_version", ""),
        "created_by": created_by,
    }
    _append_jsonl(VERSIONS_LOG, entry)

    try:
        rules_text = CONSISTENCY_RULES.read_text(encoding="utf-8")
        marker = "Canonical Face Established** only after promotion completes | pending |"
        if marker in rules_text:
            CONSISTENCY_RULES.write_text(
                rules_text.replace(marker, "Canonical Face Established** | established |"),
                encoding="utf-8",
            )
    except Exception:
        pass

    global _identity_cache
    _identity_cache = None

    return {
        "status": "established",
        "face_version": FACE_VERSION_CANONICAL,
        "previous_face_version": previous,
        "assets": asset_names,
        "materialized_variants": created_variants,
    }


if __name__ == "__main__":
    print(json.dumps({
        "identity": load_identity().get("canonical_name"),
        "version": identity_version(),
        "context": get_identity_context(),
        "avatar": {k: (str(v) if v else None) for k, v in get_avatar_path().items()},
        "face_source": get_face_source(),
        "capabilities": capabilities(),
    }, indent=2))