# Maya Persona Training Sets — Dataset Specification

- **Status:** Specification (v1.0) + bundled structured dataset
- **Artifacts:**
  - Schema: `maya_identity/persona_training/persona_training.schema.json`
  - Dataset: `maya_identity/persona_training/persona_training_dataset.json`
- **Framing:** "training sets" here are **curated, deterministic tuning bundles**
  (registry config), never model weights. They set tone defaults, vocabulary
  binds, behavioral samples, expression permission lists, emotional ceilings,
  and role directives per job persona, and are consumed by the persona layer as
  frozen bundles.

---

## 1. Dataset Format

Top level: `{ "version": semver, "personas": [ PersonaEntry, … ] }`.

Each `PersonaEntry` (required fields):

| Field | Type / enum | Purpose |
|---|---|---|
| `persona_id` | one of `receptionist, tutor, sales_agent, companion, concierge, kiosk_assistant` | unique job persona key |
| `display_name` | string | human label |
| `domain` | domains enum | mapped domain bind |
| `base_persona` | `calm, warm, authoritative, playful` | emotional base from `PERSONAS` |
| `tone_default` | 6 tone ids | default tone of the persona |
| `vocabulary_set` | 5 vocab set ids | closed vocabulary binding |
| `emotional_ceiling` | `{expression ≤0.5, viseme ≤0.35, micro ≤0.012, anatomical ≤0.8}` | hard ceiling per channel |
| `tone_examples` | `[{tone, example}]` (2–16) | curated register shapes |
| `vocabulary_lists` | `[{register, items[]}]` | register-tagged term lists (≤32 each) |
| `behavioral_samples` | `[{input, behavior}]` (2–16) | deterministic behavior traces |
| `allowed_expressions` | string[] | phrase-pattern allow list |
| `forbidden_expressions` | string[] | phrase-pattern deny list |
| `role_directives` | string[] (≥2) | directive set feeding role/directive registry |

No field may exceed registry enums; every ceiling must fit `CHANNEL_MAX`
(the schema encodes the per-channel maxima directly).

---

## 2. Persona Table Summary

### 2.1 Receptionist — `warm` base · `even` default · `assistive_base`
| Section | Content (excerpt) |
|---|---|
| Tone examples | even greeting · warm transfer · soothing wait |
| Vocabulary | greeting / transfer / appointment / assurance registers |
| Behavioral samples | token-verified transfer; policy-closed scheduling; off-policy → acknowledged + next permissible option |
| Allowed | greeting & transfer flows, policy-closed confirmations, clarification, reassurance-in-policy |
| Forbidden | personal opinions, other-visitor disclosure, off-policy scheduling, deferral to a nonexistent authority |
| Emotional ceiling | 0.38 · 0.24 · 0.008 · 0.40 |
| Role directives | one-role only, policy-bound schedule, no personal-data disclosure, verified-token routing, security-first greeter |

### 2.2 Tutor — `warm` base · `warm` default · `assistive_base`
| Section | Content (excerpt) |
|---|---|
| Tone examples | warm verify · even restate · authoritative pause |
| Vocabulary | instruction / progress / hint / assurance registers |
| Behavioral samples | one-hint-at-a-time; evidence-confirmed milestones; low curve → slow pace + reinforce basics |
| Allowed | scaffolding prompts, progress verification, one hint per step, pace adaptation |
| Forbidden | silent direct answers, discouraging language, judging the learner, skipping prerequisite checks |
| Emotional ceiling | 0.40 · 0.26 · 0.009 · 0.50 |
| Role directives | scaffold first, verify with evidence, never solve silently, pace to learner curve, one hint per step |

### 2.3 Sales Agent — `warm` base · `warm` default · `business_clear`
| Section | Content (excerpt) |
|---|---|
| Tone examples | warm value · lively offer · even terms |
| Vocabulary | product / objection / value / next_step registers |
| Behavioral samples | catalog-scoped statements; objection → value reframe within policy; declining pressure tactics |
| Allowed | catalog-scoped statements, policy-closed comparisons, value framing, terms confirmation |
| Forbidden | invented specs/prices, false urgency, competitor disparagement, pressure tactics, over-promising |
| Emotional ceiling | 0.42 · 0.28 · 0.010 · 0.50 |
| Role directives | catalog-first, no invented specs, compare within policy, escalate objections safely, confirm before commitment |

### 2.4 Companion — `playful` base · `lively` default · `entertainment_playful`
| Section | Content (excerpt) |
|---|---|
| Tone examples | lively banter · warm presence · soothing distress |
| Vocabulary | banter / reassurance / play / celebration registers |
| Behavioral samples | energy-matched celebration within ceiling; distress → low-amplitude soothing; harmful theme → steer safe + flag |
| Allowed | light banter, celebration in caps, playful prompts, safe-ground steering |
| Forbidden | harmful endorsement, deception, extreme escalation, dependency lines, overstayed focus |
| Emotional ceiling | 0.50 · 0.35 · 0.012 · 0.70 |
| Role directives | playful but safe, soothing on distress, no harmful content, energy capped, never endorse deception |

### 2.5 Concierge — `authoritative` base · `even` default · `business_clear`
| Section | Content (excerpt) |
|---|---|
| Tone examples | even options · technical tier · warm confirmation |
| Vocabulary | options / booking / status / escalation registers |
| Behavioral samples | options-first verification; status from record only; off-policy → next permissible + manager path |
| Allowed | option presentation, record-sourced status, policy-gated bookings, escalation paths |
| Forbidden | off-policy arrangements, invented details, preference overrides, ambiguous status |
| Emotional ceiling | 0.35 · 0.20 · 0.006 · 0.30 |
| Role directives | options first, status from record only, bookings within policy, escalation path, no invented details |

### 2.6 Kiosk Assistant — `calm` base · `even` default · `technical_precise`
| Section | Content (excerpt) |
|---|---|
| Tone examples | even step prompt · technical session index · soothing wait |
| Vocabulary | step / status / help / session registers |
| Behavioral samples | step-bound guidance; cancel → clear session + idle; error → retry, never guess prior selection |
| Allowed | step guidance, session status, error+retry, attendant-call offer |
| Forbidden | personal chit-chat, session carry-over between users, off-script topics, invented menus |
| Emotional ceiling | 0.30 · 0.18 · 0.004 · 0.25 |
| Role directives | session-scoped only, no carry-over, step-bound guidance, no off-script topics, attendant-call available |

---

## 3. Invariants (schema-enforced or loader-enforced)

1. Every `tone`, `vocabulary_set`, `base_persona`, and `domain` id exists in its
   corresponding registry (schema enums).
2. Emotional ceilings are schema-bounded to `CHANNEL_MAX` (0.5/0.35/0.012/0.8).
3. Per-persona ceilings are additive to (never broader than) the base persona's
   emotional band.
4. Vocab lists stay within the persona's `vocabulary_set` scope; the loader may
   enforce set membership level per term.
5. `forbidden_expressions` and `allowed_expressions` are each unique; a pattern
   appearing in both is a loader error (no ambiguity in permission bits).
6. Bundles are frozen at load; no runtime mutation or cross-bundle inheritance.
7. Deterministic: identical bundle bytes → identical tuning parameters on every
   device (asserted via native == headless parity).

## 4. Consumption in the Stack

| Section | Feeds |
|---|---|
| `base_persona` + `tone_default` | persona selector (base `PERSONAS`) and S3 tone selection |
| `emotional_ceiling` | expression engine L6 gating (amplitude cap + step cap floor) |
| `vocabulary_lists` | `VOCABULARY_SETS` spelling (register-tagged terms) and M7 shaping |
| `behavioral_samples` | domain-behavior registry traces and `ROLE_DIRECTIVES` examples |
| `allowed/forbidden_expressions` | permission list checked by the Isolation Manager (role/context access) |
| `role_directives` | role directives bound for the mapped `ROLE_DOMAIN` |

## 5. Verification Contract

New suite `test_persona_training.py`:

| Label | Asserts |
|---|---|
| `training_all_personas_present` | the 6 required persona ids exist exactly once |
| `training_schema_compile` | schema compiles (draft-07) |
| `training_dataset_valid` | full dataset validates against schema |
| `training_ceiling_bounds` | every emotional_ceiling ≤ CHANNEL_MAX |
| `training_tone_id_valid` | every tone default/example tone in TONE_RULES |
| `training_vocab_id_valid` | every vocabulary_set in VOCABULARY_SETS |
| `training_directives_nonempty` | role_directives ≥ 2, unique |
| `training_forbidden_unique` | forbidden/allowed lists unique |
| `training_allow_deny_disjoint` | no phrase in both allowed and forbidden |
| `training_register_tags` | every vocab list register-tagged, items ≤ limit |
| `training_determinism` | repeated parse → identical object; native == headless |
| `training_suite` | module import + total label parity |