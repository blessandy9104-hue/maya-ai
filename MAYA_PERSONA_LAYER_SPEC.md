# Maya Persona Layer — Architecture Specification

- **Status:** Specification (v1.0)
- **Owner:** Maya Identity / Portable Runtime
- **Conformance:** every rule here is verifiable; see "Verification Contract" (§13).
- **Layered guarantees:** deterministic, bounded, device-neutral, math-governed, fail-closed.

This document defines Maya's **Persona Layer**: the subsystem that gives every
role a stable, bounded, expressive voice while keeping all behavior inside the
canonical math, world-model, safety, and stabilization contracts.

---

## 1. Purpose and Position in the Stack

The Persona Layer sits between the **intelligence layers** (cognition,
interaction, domain behavior) and the **production layers** (rendering,
speech, robotics). It converts *who Maya is* into concrete bounded parameters:

```
Cognitive / Interaction / Domain (intent, emotion, domain signals)
        |                              (normalized vectors, [0,1])
        v
PERSONA LAYER  (tone + vocabulary + emotional range + behavior + role + brand)
        |                              (ceiling-clamped channel targets, strings)
        v
Rendering (desktop/web/kiosk/robotics) + world/safety/consistency monitors
```

Persona is **configuration over algebra**: it selects, maps, and bounds
parameters. It never adds randomness, never creates goals, never mutates the
architecture, and never bypasses `CHANNEL_MAX`.

---

## 2. Module Map (clear module definitions)

| Module | Status | Responsibility | Depends on |
|---|---|---|---|
| `maya_runtime/personality.py` | **EXISTING** | Neutral-persona baselines; `PERSONAS` = `calm`, `warm`, `authoritative`, `playful`; `channel_targets()`, `paced_state()`; ceiling-clamped | `maya_runtime/core.py` |
| `maya_runtime/persona/__init__.py` | PROPOSED | `PersonaLayer` facade: active persona, registry, `switch()`, `reset()`, `describe()` | all persona modules |
| `maya_runtime/persona/profiles.py` | PROPOSED | `PERSONA_PROFILES` — the canonical persona registry (id, tone, vocab set, emotional band, constraints, compatible roles) | core, capability_registry |
| `maya_runtime/persona/tone.py` | PROPOSED | `TONE_RULES` — tone → bounded channel targets; `tone_targets(tone)`; determinism check | core |
| `maya_runtime/persona/vocabulary.py` | PROPOSED | `VOCABULARY_SETS` — deterministic term/keyword sets per scope; `expand(set_id, topic)` | profiles |
| `maya_runtime/persona/emotion.py` | PROPOSED | `EMOTIONAL_RANGES` — per-persona bands inside `CHANNEL_MAX`; `clamp_to_range()` | core |
| `maya_runtime/persona/behavior.py` | PROPOSED | `BEHAVIORAL_CONSTRAINTS` — global + per-persona predicate rules; `assert_behavior_ok(signal)` | core, safety_monitor |
| `maya_runtime/persona/roles.py` | PROPOSED | `ROLE_DIRECTIVES` — directive set per role (8 roles); bridges to `domains.ROLE_DOMAIN` | capability_registry, domains |
| `maya_runtime/persona/branding.py` | PROPOSED | `COMPANY_BRANDING_HOOKS` — validated brand constants + override slots | core |
| `maya_runtime/persona/switching.py` | PROPOSED | persona-switch engine: triggers, thresholds, `stable_exp_smooth` transition, cooldown, guard conditions | core, stabilization |
| `maya_runtime/persona/safety.py` | PROPOSED | `PERSONA_SAFETY_BOUNDARIES` — ceilings, floors, prohibited switches, fail-closed persona | safety_monitor, stabilization |

**Existing anchors the spec reuses without modification:** `CHANNEL_MAX`,
`MATH_AGENT`, `WORLD_MODEL`, `SAFETY_MONITOR`, `PATTERN_ALIGNMENT`,
`capability_registry` (11 caps / 8 roles), `interaction`, `domains`,
`stabilization`, `readiness.self_check()`.

---

## 3. Persona Identity Model

A persona is a tuple of seven bounded parts:

```
Persona = ( id, tone, vocabulary_set, emotional_range, behavioral_profile,
            role_directives, brand_look )
```

| Field | Type | Bounded by |
|---|---|---|
| `id` | `str` slug | registry key, immutable |
| `tone` | `str` → tone rule id | `TONE_RULES` key |
| `vocabulary_set` | `str` → vocab set id | `VOCABULARY_SETS` key |
| `emotional_range` | 3-band dict over expression/viseme/micro | [`lo`,`hi`] ⊂ [0, `CHANNEL_MAX[ch]`] |
| `behavioral_profile` | tuple of constraint ids | `BEHAVIORAL_CONSTRAINTS` |
| `role_directives` | tuple of directive ids | `ROLE_DIRECTIVES` |
| `brand_look` | brand accent slot (may be 0 = none) | `COMPANY_BRANDING_HOOKS` |

Invariants enforced by `profiles.py` at import:
1. every referenced tone/vocab/constraint/directive/brand id exists in its registry;
2. every emotional band lies inside `CHANNEL_MAX`; lo ≤ hi;
3. `PERSONA_PROFILES` ids are unique and at least the four EXISTING personas
   (`calm`, `warm`, `authoritative`, `playful`) are present;
4. each profile is deterministic (no RNG/time/hardware references).

---

## 4. Tone Rules (`tone.py`)

A tone is a deterministic mapping to canonical channel targets plus pacing.
`tone_targets(tone) -> {expression, viseme, micro, pace}` must satisfy:
`target[ch] ∈ [0, CHANNEL_MAX[ch]]`, `pace ∈ (0, 1]`.

| Tone id | Character | expression band | viseme band | micro band | pace | Rules |
|---|---|---|---|---|---|---|
| `even` | measured, neutral | 0.20–0.35 | 0.10–0.20 | 0.000–0.004 | 0.60 | default, fail-closed |
| `warm` | supportive, calm | 0.30–0.50 | 0.15–0.28 | 0.002–0.008 | 0.65 | max steps slowed |
| `lively` | bright, energetic | 0.35–0.50 | 0.20–0.35 | 0.004–0.011 | 0.75 | viseme ceiling respected |
| `authoritative` | firm, controlled | 0.25–0.40 | 0.12–0.22 | 0.002–0.006 | 0.50 | lowest pace cap |
| `soothing` | gentle, de-escalating | 0.18–0.30 | 0.08–0.18 | 0.000–0.004 | 0.55 | micro floor 0 |
| `technical` | precise, restrained | 0.20–0.32 | 0.10–0.20 | 0.000–0.003 | 0.58 | vocabulary = technical only |

Tone resolution rules:
1. Unknown tone id → `ValueError` (never silently default).
2. Tone only *shapes* targets; ceiling-clamping always applies last.
3. Tone cannot raise a channel above its `CHANNEL_MAX` (enforced by `emotion.clamp_to_range`).
4. `tone_targets(t)` is a pure function: same input → bit-identical output.

---

## 5. Vocabulary Sets (`vocabulary.py`)

Vocabularies are deterministic, closed sets. `expand(set_id, topic)` returns
only terms from the set (no generation, no guessing). Sets:

| Set id | Scope | Included | Forbidden | Shape |
|---|---|---|---|---|
| `assistive_base` | general support | confirm, clarify, summarize, guide, reassure | slang, profanity, loaded claims | subject-verb-object, ≤ 2 clauses |
| `business_clear` | enterprise/kiosk | state, option, next_step, policy, status | jargon, opinion, hedging | short declaratives |
| `technical_precise` | robotics/dev | parameter, bound, threshold, calibration, limit | anthropomorphism of hardware | metric-first |
| `therapeutic_gentle` | therapy support | reflect, validate, breathe, pace, offer | diagnosis, direction, claims | invitation-only |
| `entertainment_playful` | companion/VTuber | cheer, banter, tease, celebrate | harm, distress, deception | playful but safe |

Constraints:
1. `expand()` is deterministic; ordering stable; no RNG.
2. A vocabulary set must be present in a profile before use; unknown id → `ValueError`.
3. All output is assembled from set terms only — Maya never invents words outside
   the set (mirrors the identity rule: "you derive, you do not guess").
4. Emotional margin: caps on punctuation/exclamation per tone (e.g., `even` ≤ 1,
   `lively` ≤ 3) — bounded, configured per set.

---

## 6. Emotional Ranges (`emotion.py`)

Every persona declares its achievable emotional band inside the canonical
channel ceilings so emotional expression is **always within safe amplitude**.

| Persona | expression band | viseme band | micro band | max step per frame |
|---|---|---|---|---|
| `calm` | 0.15–0.40 | 0.05–0.22 | 0.000–0.006 | 0.05 |
| `warm` | 0.20–0.50 | 0.08–0.28 | 0.002–0.009 | 0.06 |
| `authoritative` | 0.15–0.45 | 0.05–0.25 | 0.001–0.007 | 0.04 |
| `playful` | 0.20–0.50 | 0.10–0.35 | 0.003–0.012 | 0.07 |
| *(future profiles)* | must fit ceilings | must fit ceilings | must fit ceilings | ≤ 0.07 |

Rules:
1. `clamp_to_range(value, range)` clamps into the band **and** the ceiling.
2. Emotional output is only a function of the current state + target (no time).
3. Transitions use `stable_exp_smooth` → monotone, no overshoot, no teleport.
4. Bands automatically constrain to `CHANNEL_MAX` even if band text says wider.

---

## 7. Behavioral Constraints (`behavior.py`)

Global constraints (apply to every persona):

| id | Constraint | Enforcement |
|---|---|---|
| `no_randomness` | no RNG in persona math | import-time scan + runtime predicate |
| `no_hardware_bias` | identical output on every device | cross-process signature test |
| `no_overshoot` | any smoothing never exceeds its target | `stable_exp_smooth` property test |
| `no_ceiling_breach` | channels never exceed `CHANNEL_MAX` | clamp + assert |
| `no_goals_created` | persona may not create goals; only follow user goals within safe limits | directive gating |
| `no_architecture_change` | persona never mutates registry/models/limits | frozen registries |
| `bounded_output` | all scalar outputs finite, in-domain | `determinism.report()` |

Per-persona extensions (profiles may add subset):

| id | Constraint |
|---|---|
| `low_amplitude` | emotional steps ≤ 0.04 (authoritative) |
| `deescalation_only` | soothing motion only downward or flat in load contexts |
| `fast_rapport` | allow upper-half warm band in onboarding contexts |
| `strict_even` | default single tone `even`, no tone excursions |

`assert_behavior_ok(signal)` returns `(ok, reason)` and must never raise on
valid input; violations are logged to the stabilization self-check pipeline as
anomalies (see §13).

---

## 8. Role Directives (`roles.py`)

Bound to the 8 registered roles via `ROLE_DIRECTIVES` + `domains.ROLE_DOMAIN`.
Every role receives the global directive set + role-specific directives.

| Role | Domain | Core directives |
|---|---|---|
| `educational_tutor` | tutoring | scaffold, verify progress, never solve silently, keep pace adaptive |
| `customer_service_agent` | customer_service | state options, follow policy, escalate safely, no invented policy |
| `therapy_support_agent` | therapy_support | reflect/validate only, no diagnosis, flag crisis paths, low-amplitude, de-escalation-only |
| `robotics_interface` | robotics_interface | metric-first vocab, report bounds, command-only what is math-approved |
| `ai_companion` | entertainment | companionship, playful-but-safe, no harmful content |
| `vtuber_avatar` | entertainment | streaming-suitable, brand-accented, bounded performance energy |
| `holographic_assistant` | (domain-agnostic) | neutral `even` tone, business_clear vocab, no role-owned domain behavior |
| `enterprise_assistant` | (domain-agnostic) | clear, cautious, enterprise-policy-abiding, no brand mutation |

Directive structure: `(id, role, domain, rule, safe_override)` — `safe_override`
is the fail-closed branch when the user intent conflicts with safety.

---

## 9. Company Branding Hooks (`branding.py`)

Branding is a set of **validated, bounded constants** — never measurement, never
random:

```
COMPANY_BRANDING_HOOKS = {
  brand_name: str (registry constant),
  brand_accent_color: hex (validated format),
  brand_visual_accents: tuple of safe accent tokens,
  brand_catchphrase: str | None,
  override_slot: dict of replaceable fields (validation on set),
  determinism: "constant",
}
```

Rules:
1. Hooks are read-only by persona math; only `override_slot` fields are
   writable and each write is validated (type/length/format).
2. Catchphrases may be referenced by roles marked `branded=True` (vtuber_avatar,
   ai_companion) and must be absent from `technical_precise` scope.
3. Brand values are constants — importing cannot alter them.
4. No brand hook may influence safety thresholds, ceilings, or world model.

---

## 10. Persona-Switching Logic (`switching.py`)

Switching is a **deterministic, guarded state machine**. It never teleports.

```
Triggers    -> {user_request, context_signal, role_change, emergency}
Validate     -> target persona exists AND switch allowed by safety.py
Transition   -> per-channel stable_exp_smooth over N steps (bounded, monotone)
Cooldown     -> lock-out between switches (bounded count, not wall-clock based)
Record       -> append JSONL (actor, from, to, reason) to metadata
```

Guard conditions (switch is **blocked** when any holds):
1. `safety_monitor.check(...)['safe'] is not True` — no switches under load.
2. Stabilization protocol not in `ready` state for that subsystem context
   (kiosk/robotics personas require verified runtime).
3. Therapy support session active and target persona is not in the
   `deescalation` group.
4. Target persona band conflicts with current dialog context (e.g., playful in
   a crisis path) → `ValueError`-style refusal with recorded reason.

Transition contract:
- `switch(from, to, steps)` returns a bounded series inside **both** `from` and
  `to` bands, monotone per channel, never exceeding `CHANNEL_MAX`.
- Default persona on reset / fail-closed: `calm` (tone `even`).
- Determinism: `switch(a,b,24)` produces the same series on every device.

---

## 11. Persona Safety Boundaries (`safety.py`)

| Boundary | Value / rule |
|---|---|
| Expression ceiling | ≤ 0.50 (`CHANNEL_MAX['expression']`) |
| Viseme ceiling | ≤ 0.35 (`CHANNEL_MAX['viseme']`) |
| Micro ceiling | ≤ 0.012 (`CHANNEL_MAX['micro']`) |
| Step ceiling | ≤ 0.07 per channel per frame |
| Floor | persona never below 0.0 on any channel |
| Fail-closed persona | `calm`/`even`, always valid on reset |
| Prohibited transitions | `{playful -> therapy_support}`, `{lively -> robotics_interface}` |
| Safety-integrated | persona anomalies feed `readiness.self_check()`; boundaries checked by `safety_monitor` algebra |
| Containment | persona math is pure: no registry/world/safety mutation |

A persona that would violate any boundary is rejected at registry-load time
(`ValueError`), so unsafe personas cannot be instantiated.

---

## 12. Deployment Mapping

| Target | Persona applicability |
|---|---|
| Desktop | full persona set, Tk renderer |
| Web | full persona set, JSON payloads |
| Kiosk | tone `even`/`soothing`, `business_clear` vocab, no switch during sessions |
| Robotics | `technical_precise` vocab, `authoritative` bounds, switch requires verified runtime |

All four deployments share the same deterministic persona algebra; only renderer
adapters differ.

---

## 13. Verification Contract (conformance)

New/updated suites (name + labels) validating this spec:

| Suite | Verifies |
|---|---|
| `test_persona_layer.py` | registry completeness (4 existing + new profiles), tone mapping boundedness, vocabulary determinism, emotional bands inside `CHANNEL_MAX`, behavioral constraints (no overshoot/teleport/random), role directives against 8 roles, branding hook validation, switch determinism + monotonicity, safety boundaries (ceilings, fail-closed default, prohibited switches) |

Specific assertions (excerpts):
1. `len(PERSONA_PROFILES) >= 4` and `{"calm","warm","authoritative","playful"} ⊆ ids`.
2. For every persona: `lo ≤ hi`, bands ⊆ ceilings; any out-of-ceiling band raises at import.
3. `switch("calm","playful",24)` → all values finite, monotone, within both bands.
4. `tone_targets(t)` called twice → identical; unknown id → `ValueError`.
5. `expand(vocab, topic)` twice → identical; terms ⊆ set.
6. Prohibited/power-switches blocked; fail-closed persona always available.
7. No `random/time/tkinter` in any persona module namespace.
8. Cross-process headless signature of persona targets identical to native.

---

## 14. Relationship to Existing Guarantees

- The persona layer **preserves** blend weights 0.6/0.3/0.1, world-stability
  logic, safety thresholds, capability registry, and stabilization protocol.
- It **adds** nothing random, no new hardware paths, no goal creation.
- Readiness remains consensus-gated (external sweep + internal self-check);
  persona switching is blocked until the runtime is verified in constrained
  contexts.
- All persona state is serializable and stateless-at-rest; failure defaults to
  `calm`/`even`.