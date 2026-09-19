# Maya Identity Profile — Format Notes

- **Schema:** `maya_identity/profiles/identity_profile.schema.json` (JSON Schema draft-07)
- **Reference profile:** `maya_identity/profiles/maya-default.profile.json`
- **Version:** 1.0.0 — draft for design review; registry-checked, bounded, deterministic.
- **In scope:** company_id, persona, theme, tone, vocabulary, constraints,
  allowed/forbidden behaviors, brand personality, runtime persona loader, isolation rules.
- **Out of scope (protected):** math core, channel ceilings, safety thresholds, world
  stability, capability registry, stabilization protocol, `identity.json`, face geometry.

---

## 1. Field-by-field explanation

| Field | Type | Meaning | Enforcement |
|---|---|---|---|
| `$schema`, `$id` | string | Draft-07 URI; canonical profile URL | `const` / pattern |
| `version` | semver string | Profile version, x.y.z | pattern |
| `company_id` | "MAYA"-style token | Legal operating entity / business id. Upper-case token, 2–64 chars. | pattern |
| `persona` | enum | Active identity persona: `authoritative`, `calm`, `playful`, `warm` (must exist in the persona registry) | schema enum |
| `theme` | slug | Visual/UX theme id applied by render adapters (e.g. `maya-core`) | pattern |
| `tone` | enum | Tone rule applied to all expression: `even`, `warm`, `lively`, `authoritative`, `soothing`, `technical` | schema enum |
| `vocabulary` | enum | Closed vocabulary set: `assistive_base`, `business_clear`, `technical_precise`, `therapeutic_gentle`, `entertainment_playful` | schema enum |
| `emotional_range` | object | Per-channel expression/viseme/micro bands. Every `hi` is hard-bounded by its true ceiling (0.5 / 0.35 / 0.012) | schema `maximum` |
| `constraints` | array | Behavior constraint ids (global set from the Persona Layer spec). Extensions allowed only with the reserved `x-` prefix | enum ∪ `x-` pattern |
| `allowed_behaviors` | array | Behavior references the profile may use: capabilities (11), `domain:<name>` (5), `directive:<id>`, `feature:<id>` | `anyOf` refs |
| `forbidden_behaviors` | array | Same reference grammar; loader MUST reject any overlap with `allowed_behaviors` | loader invariant |
| `brand_personality` | object | Validated brand constants (see §3) | strict object |
| `runtime_persona_loader` | object | Loader contract this profile expects (see §4) | strict object |
| `isolation_rules` | object | What the profile may influence vs. what is protected (see §5) | strict object |
| `metadata` | object (optional) | author + created_date; informational only | loose |

## 2. Behavior reference grammar

References are strings resolved against three registries at load time:

```
capability:<11 capabilities>        # e.g. "adaptive_interaction"
domain:<5 domains>                  # tutoring|customer_service|therapy_support|robotics_interface|entertainment
directive:<id>                      # role/behavior directive, e.g. "invent_policy" (used mainly in forbidden)
feature:<id>                        # interaction feature knob
```

Rules:
1. An unknown id is a hard validation failure — never silently dropped.
2. `allowed_behaviors` and `forbidden_behaviors` are each `uniqueItems` at the
   schema level; their **disjointness** (allowed ∩ forbidden = ∅) is a loader
   invariant because JSON Schema cannot express set intersection across arrays.
3. Forbidden entries should be mostly directives/features/domains; revoking a
   base capability requires an `x-` constraint too, so no profile can silently
   shed `safety_monitoring`.

## 3. `brand_personality` rules

- `brand_name`, `brand_accent_color` (`#RGB`/`#RRGGBB`), `brand_visual_accents`
  (≤12 tokens), `brand_catchphrase` (nullable, ≤120 chars, printable ASCII only).
- `branded: false` = neutral default assistant; `true` = brand-accented roles
  (vtuber, companion). When `false`, the override slot must stay empty and the
  catchphrase cannot be surfaced.
- `override_slot` is the *only* mutable field: allowed to override
  catchphrase/accent_color/visual_accents, each re-validated on write.
- Brand constants can never influence safety thresholds, ceilings, world model,
  or the stabilization protocol (they are presentation-level).

## 4. `runtime_persona_loader` contract

The proposed loader module `maya_runtime/persona/loader.py` implements:

1. **Strict schema validation** (draft-07) via this schema.
2. **Registry resolution** — every persona/tone/vocabulary/constraint/behavior
   id must already exist or be part of the same atomic profile bundle.
3. **Ordered checks:** JSON Schema → registry existence → allowed/forbidden
   disjointness → band lo ≤ hi → ceiling clamp re-check → brand validation.
4. **Determinism:** loading the same profile bytes yields the same runtime
   persona parameters every time on every device (no RNG, no wall-clock, no
   hardware probes).
5. **Fail-closed:** any validation failure leaves the runtime on the
   `calm`/`even` default persona, records the anomaly to the self-check engine,
   and never partial-loads (all-or-nothing).

`engine` is pinned to `maya_runtime.persona.loader`, `validation` is pinned to
`fail_closed`, `strict`/`deterministic` are pinned `true` — a profile cannot
propose a looser loader.

## 5. Isolation rules

- **`affected_domains`** — the only systems a profile may configure: render,
  voice, pacing, emotional_range, vocabulary, interaction, domain_behaviors.
- **`protected_subsystems`** — pinned read-only: math_core, channel_ceilings,
  safety_thresholds, world_stability, capability_registry, stabilization_protocol,
  identity.json, face_geometry. The schema enumerates them; the loader hard-rejects
  any profile that tries to add a configuration key targeting them.
- **`no_architecture_mutation: true`**, **`no_world_mutation: true`**,
  **`fail_closed_on_error: true`** — all pinned: a profile is configuration
  over algebra; it never changes what Maya is, only how Maya presents within
  bounded limits.

## 6. Relationship to other identities

| Artifact | Role |
|---|---|
| `identity.json` | Immutable canonical identity (protected; sources `role`, `tagline`, `canonical_face`) |
| `MAYA_PERSONA_LAYER_SPEC.md` | Defines the registries this profile references (tone rules, vocab sets, emotional ranges, constraints, directives, branding, switching, safety) |
| `maya_runtime/personality.py` | Existing persona engine the loader animates |
| stabilization protocol | Persona switching stays blocked until runtime is verified in constrained contexts |

## 7. Verification

The schema was compiled with `fastjsonschema` (draft-07) and exercised:

- `maya-default.profile.json` → **valid**.
- Negative cases — invalid tone/persona, micro band above 0.012, unknown
  capability, unknown constraint, non-strict loader, architecture mutation,
  bad isolation enums, phantom top-level keys, overlapping allowed/forbidden
  (caught at loader level as specified) → **all rejected**.

A full chained test (`test_identity_profile.py`) is recommended as part of the
persona layer suite: schema compile, example valid, N negatives, loader
all-or-nothing + fail-closed behavior, and cross-device determinism of loaded
persona parameters.