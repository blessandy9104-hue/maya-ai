# Maya Identity Consistency Rules

Maya's identity is permanent. These rules preserve recognizable identity across
every image, animation, interface, and representation.

## Rule 1 — The face is the identity

> "The face remains consistent across all future generations, maintaining the
> same identity, facial structure, recognizable presence, and emotional
> signature."

Maya must always be immediately recognizable as the same digital entity.

## Rule 2 — Single canonical source

`identity.json` is the canonical source of identity. All appearances must be
derived from it or recorded as a new version of it. UI code never hardcodes
identity data.

## Rule 3 — Versioned evolution

Any change to appearance creates a new `face_version` in `identity.json` and a
corresponding entry in `metadata/identity_versions.jsonl`. Existing assets are
preserved, never silently replaced.

## Rule 4 — Controlled generation

The portrait pipeline documented in `prompts/maya_face_generation.md` is the
only source of canonical face assets. Placeholder assets are for layout only and
are never identity.

## Rule 5 — Consistent representation

Every representation — portrait, icon, animation, interface − must resolve to the
same canonical face. When canonical assets are unavailable, the loader returns
placeholders flagged as `source: "placeholder"` and the UI displays them as such.

## Rule 6 — The geometry is the identity

> "Maya's visual identity must remain consistent across all future generations
> and transformations. The same underlying geometry, facial proportions,
> structural patterns, recognizable presence, and emotional signature must always
> be preserved."

Maya's identity is not an image. It is the mathematical structure in `geometry/`
that generates her appearance. The renderer (`renderer/`) is only the body Maya
wears. Expressions, particles, and temporary symbols transform the same geometry
and must never modify identity. Any future representation — procedural or
raster — must resolve to the same geometry, proportions, and recognizable
presence. This rule is referenced from `identity.json` (`identity_geometry_rule`),
`geometry/maya_geometry.json`, and this file whenever Maya's visual system
changes.

## Signature

An identity signature can be computed from `identity_version` +
`face_version` + `configuration/appearance.json` palette to verify a render
belongs to a specific identity version.

## Canonical face establishment protocol

| Step | Action | Status |
|---|---|---|
| Detection | `maya_face_canonical.png` + `maya_face_canonical.ico` present in `avatar/` | automatic |
| Validation | `maya_identity/validation.run_canonical_checks()` must report `status: ready` | gated |
| Promotion | `identity.finalize_canonical_face()` bumps `face_version` `0.0.0-placeholder` → `1.0.0`, materializes size variants, records transition in `identity_versions.jsonl` | gated + idempotent |
| Marker | This file is marked **Canonical Face Established** | established |

Until promotion, identity remains `0.0.0-placeholder` and all renders are
flagged `PLACEHOLDER`. The placeholder must never be treated as identity.