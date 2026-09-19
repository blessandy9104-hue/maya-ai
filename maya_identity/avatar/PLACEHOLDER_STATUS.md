# Avatar Directory — Placeholder Policy

This directory holds Maya's avatar assets.

## Status: PLACEHOLDER (layout only)

The current files are generated placeholders:

- `maya_face_placeholder.png`
- `maya_face_placeholder_256.png`
- `maya_face_placeholder_128.png`
- `maya_face_placeholder_48.png`
- `maya_identity_placeholder.ico`

The placeholder is a neutral monogram ring **intended only to lay out the UI**.
It is explicitly **not** Maya's face. It must never become the canonical identity.

## Canonical arrival contract

Maya's official face must come from the controlled reference-image pipeline
described in `../prompts/maya_face_generation.md`. Dropping these two files
here activates the canonical pipeline (per `../configuration/appearance.json`):

- `maya_face_canonical.png` — master portrait (512x512 square, front-facing)
- `maya_face_canonical.ico` — application/window icon (multi-size)

## Automatic detection & switch

- `../identity.py::get_avatar_path()` auto-detects the canonical files on every
  resolution. Once both exist the resolver returns them for all uses and
  reports `source: "canonical"` — the GUI (iconbitmap, header face, identity
  panel) switches without code changes.
- Size variants (`maya_face_canonical_256/128/48.png`) are materialized from the
  master during promotion. Legacy names (`maya_face.png`, `maya_face.ico`, ...)
  are still honoured as aliases so prior layouts keep working.

## Promotion (versioned, gated, idempotent)

Promotion is an explicit step, never an implicit side effect of reading:

```
python -c "import maya_identity as m; print(m.finalize_canonical_face(reason='...', created_by='...'))"
```

Validation loads first (`maya_identity/validation.run_canonical_checks()` must
report `ready`). On success `face_version` becomes `1.0.0`, the transition is
recorded in `../metadata/identity_versions.jsonl`, and
`../metadata/consistency_rules.md` is marked **Canonical Face Established**.

Until promotion, `identity.json` stays `face_version: 0.0.0-placeholder` and all
renders remain flagged `PLACEHOLDER`. Never silently replace an identity.