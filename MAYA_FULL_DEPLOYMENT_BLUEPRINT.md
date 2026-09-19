# Maya Full Deployment Blueprint — Unified Architecture Document

- **Status:** Blueprint (v1.0) — superset architecture uniting ten governed
  subsystems into one deployable system.
- **Usage:** single entry document; each subsystem retains its own spec
  (index in §10); this blueprint fixes the **integration, boundaries,
  invariants, and deployment matrix** that make them a single runtime.
- **Status legend:** `EXISTING` = built & verified; `PROPOSED` = module path
  defined by specs, to implement behind the persona layer.

---

## 1. Master System Diagram

```
                          ┌────────────────────────────────────────────────────┐
   input ──► [C5 Market]  │                                                    │
             (slang, dia, │   ┌── [C3 Expression] ──► [C6 Isolation]          │
              tone, lang, │   │      L0–L7 lanes          persona/role/tenant │
              culture)    │   │                                                │
                          │   └──► [C4 Pipeline]          ┌► [C7 Demo Runtime] │
   [C2 Identity] ──► [C1 Persona Layer] ──► (S1–S8) ──►──┴─► render targets     │
   (schemas, loader)  (profiles, tones,      tones,        (frames, sandbox,   │
    profiles/bundles)  vocab, switching,      emotions,     READY gate)        │
                        governance, fail-     expression,                      │
                        closed)               vocab                            │
                          │                                                   │
   [C9 Tenant Contract] ◄─┴─ [C6 Isolation] ──► [C8 Enterprise Kit]           │
   (namespaces, quotas,      (deny-by-default,  (profile template, persona    │
    kill-switch, CORED)       drift lock,        guide, read-only API,        │
                              identity gating)   checklist, tenancy)          │
   ──────────────────────────► [C10 Governance] (authority map, escalation,   │
                              invariants, readiness authority) ◄──────────────┘
```

Single deterministic track: inputs → adapt → filter → interpret → select →
express → gate → render → audit, with governance supervising every crossing.

## 2. The Ten Subsystems

### C1 · Persona Layer
- **Purpose:** bounded personas (band/tone/vocab/constraints/directives) and
  switching.
- **Binding:** `maya_runtime/personality.py` (EXISTING) +
  `maya_runtime/persona/*` (PROPOSED: profiles, tone, vocabulary, emotion,
  behavior, roles, branding, switching, safety).
- **Key surfaces:** `PERSONA_PROFILES`, `TONE_RULES`, `VOCABULARY_SETS`,
  switching state machine (7 states), fail-closed `calm/even`.
- **Boundary:** presentation config only; never mutates math/safety/identity.

### C2 · Identity Profiles
- **Purpose:** deterministic, validated identity per company/session.
- **Binding:** `maya_identity/profiles/identity_profile.schema.json` +
  template (EXISTING data) + profile loader (PROPOSED).
- **Key surfaces:** schema; `company_id`, persona, tone, vocab, brand,
  `runtime_persona_loader` (pinned fail-closed), `isolation_rules` (pinned).
- **Boundary:** profile is all-or-nothing; CORED never serialized; protected
  fields non-editable.

### C3 · Expression Engine
- **Purpose:** L0–L7 intensity calibration → bounded frames.
- **Binding:** Expression Engine L1/L2/L4 orchestration (PROPOSED) over
  `interaction` + `math_coordinator` (EXISTING: `CHANNEL_MAX`,
  `TASK_BLEND_WEIGHTS (0.6,0.3,0.1)`, `stable_exp_smooth`).
- **Key surfaces:** calibration tables, persona ceilings, weight→level mapping,
  rendering constraints, fail-closed neutral frames.

### C4 · Semantic→Persona→Expression Pipeline
- **Purpose:** end-to-end S1–S8 for a given context.
- **Binding:** `maya_runtime/pipeline.py` (PROPOSED) over the C1/C3 surfaces
  + `interaction` (EXISTING).
- **Key surfaces:** `SemanticVector → PersonaPlan → ToneTargets →
  EmotionWeights → FrameLanes → BlendPose → RenderFrame → VocabOut`; worked
  deterministic trace; module boundaries per step.

### C5 · Market Adaptation Layer
- **Purpose:** language/register adaptation on input; register-safe shaping.
- **Binding:** `maya_runtime/market/*` (PROPOSED) + executable ruleset
  `maya_identity/adaptation/semantic_adaptation_rules.json` (EXISTING data).
- **Key surfaces:** `MarketGate` (normalized text, dialect, tone, language
  route, cultural cues, urgency, shaped output); priority-5 overrides
  (urgency/taboo/fail-closed).

### C6 · Persona Isolation Manager
- **Purpose:** deny-by-default isolation for persona/role/company/user/tone/
  identity/tenant.
- **Binding:** `maya_runtime/isolation/*` (PROPOSED) + guard primitives;
  enforced by sandbox + audits; drift-lock surfaces to self-check.
- **Key surfaces:** `AccessControlVector`, `guard.can()`, `envelope/drift`,
  identity `key_class/redact/token_access`, tenant kill-switch/quota.

### C7 · Demo Runtime
- **Purpose:** public-demo composite: math, world model, safety, expression,
  persona selector, identity loader, rendering loop, UI wrapper, sandbox,
  deployment constraints.
- **Binding:** maya_runtime core (EXISTING: loader, world_model, safety_monitor,
  rendering, ui, deploy) + sandbox/demo orchestrator (PROPOSED).
- **Key gate:** READY only via verification sweep + controlled launch +
  self-check consensus.

### C8 · Enterprise Deployment Kit
- **Purpose:** onboarding package for enterprises: template, selection guide,
  branding rules, read-only API surface, sandbox rules, deployment checklist,
  multi-tenant rules.
- **Binding:** Company Integration Kit (document + validated template
  `company_template.profile.json`).
- **Key surface:** read-only posture — outputs published, inputs whitelisted,
  no outbound/callbacks/secrets.

### C9 · Tenant Isolation Contract
- **Purpose:** formal multi-tenant safety: namespaces NS(t,k), obligations,
  invariants J1–J9, forbidden actions F1–F10, slot-based quotas, kill switchers
  scoped to one tenant, CORED protection.
- **Binding:** Isolation Manager + sandbox; conformance suite.

### C10 · Governance Model
- **Purpose:** formal governance: persona boundaries, role safety, ceilings,
  escalation E0–E3, fallbacks, neutralization triggers, authority map
  (runtime/sandbox/tenant/user/persona/readiness), switching protocol.
- **Binding:** Governance spec + Runtime Authority Map + Persona Switching
  Protocol + Calibration + Ruleset files.

---

## 3. Unified Data Flow (cross-component)

```
 input text
   → C5 (M1–M6) MarketGate: normalize, dialect, tone, language route, cues, urgency
   → C4 pipeline S1 (semantic vector on normalized text; C2 persona plan)
   → S3 tone (C1 TONE_RULES; C5 tone override; urgency force → even/soothing)
   → C4 S4–S5 (emotional weighting; expression mapping via C3 calibration incl. C5)
   → C3 L6 persona gates (ceilings, step caps) → blend (TASK_BLEND_WEIGHTS)
   → C7 render loop → RenderFrame → UI adapters
   → C6/C9 isolation every hop: sandbox can() + tenant namespace + drift check
   → C10 governance: audit, anomalies → self-check → readiness status
```

Output side: C5 M7 shaping + C7 vocabulary layer constrain all phrasing to
closed sets; every hop is bounded and audited.

## 4. Runtime Lifecycles

### Boot (demo & enterprise)
```
 sandbox.init → identity loader (profiles) → math engine → world model →
 safety → expression engine → persona selector (calm/even default) →
 rendering loop + UI attach → READY gate (external sweep ∧ self-check)
```

### Persona switch
```
 trigger → guards C6 + C1 → SWITCHING(prev→next) → reset S1 tone, S2 expression,
 S3 world slice → SETTLING → ACTIVE; failure → ladder → revert / calm/even
```

### Incident path
```
 anomaly/drift/taboo/urgency → C10 escalation E0→E1→E2→E3
   (E0 counter, E1 neutralize+audit, E2 revoke READY, E3 clean halt)
```

### Multi-tenant event
```
 tenant action → C9 can_read/can_write + quota + kill switch → C6 guard → audit
```

## 5. Deployment Matrix

| Context | Targets | Persona set | Tenancy | Isolation | READY gate |
|---|---|---|---|---|---|
| Public demo | desktop/web/kiosk | full (calm/.../playful) | single-tenant | demo sandbox | required |
| Robotics demo | robotics/ kiosk | kiosk, authoritative | single-tenant | sandbox + verified runtime | required |
| Enterprise | desktop/web/holo | per selection guide | multi-tenant | C6 + C9 full | per-tenant |

Constraints (universal): no outbound network, no secrets, whitelist fs,
cadence ≤ 30/s, CPU-light, native==headless parity, CORED never leaves.

## 6. Mandatory Architecture Invariants (pan-architecture)

```
V1 ∀ frame·∀ch· value ≤ CHANNEL_MAX ; V2 no randomness in core
V3 TASK_BLEND_WEIGHTS (0.6,0.3,0.1) preserved
V4 deny-by-default at every authority/namespace boundary
V5 READY only by consensus (no self-declaration)
V6 no persona/tenant can mutate math/safety/identity/registries
V7 drift/taboo/urgency flatten, never raise
V8 all outputs closed-set and persona-bounded
V9 same inputs ⇒ same outputs native == headless (parity)
V10 any failure ⇒ valid neutral fallback or clean halt (never partial)
```

## 7. Readiness & Verification

- **Gate:** `python -m verification.sweep` → 18 suites clean + 206 ok-labels +
  controlled launch native==headless==(0.5,1.0,0.0,4) → cleanup →
  `stabilization.confirm(report)` → READY (consensus of external + internal).
- **Master contract suites** (each subsystem's test_* documented in its spec):
  persona_layer, identity_profile, expression_engine, semantic_persona_expression,
  market_adaptation, semantic_adaptation_rules, persona_isolation,
  persona_switching_protocol, persona_governance, persona_expression_calibration,
  persona_training, demo_content, demo_runtime_blueprint, tenant_isolation_contract,
  runtime_authority_map, company_integration_kit.
- **Parity:** every sub-suite asserts native == headless; failures funnel into
  self-check counters and can revoke READY.

## 8. Change Control

- Subsystem specs are versioned; any numerical/behavior change requires
  re-running the affected contract suite + the full sweep before re-entering
  READY (R12 in calibration: "changes require re-verification").
- Profile/bundle versions bump on any content change; the loader records active
  bundle in `info/status.json`.

## 9. Companion Document Index

| # | Subsystem | Document |
|---|---|---|
| C1 | Persona Layer | `MAYA_PERSONA_LAYER_SPEC.md` |
| C2 | Identity Profiles | `MAYA_IDENTITY_PROFILE_FORMAT.md` |
| C3 | Expression Engine | `MAYA_EXPRESSION_ENGINE_SPEC.md` · `MAYA_PERSONA_EXPRESSION_CALIBRATION.md` |
| C4 | Pipeline | `MAYA_SEMANTIC_PERSONA_EXPRESSION_PIPELINE.md` |
| C5 | Market Adaptation | `MAYA_MARKET_ADAPTATION_LAYER.md` · `MAYA_SEMANTIC_ADAPTATION_RULES.md` |
| C6 | Isolation Manager | `MAYA_PERSONA_ISOLATION_MANAGER.md` |
| C7 | Demo Runtime | `MAYA_DEMO_RUNTIME_BLUEPRINT.md` · `MAYA_DEMO_CONTENT_LAYER.md` · `MAYA_PERSONA_TRAINING_SETS.md` |
| C8 | Enterprise Kit | `MAYA_COMPANY_INTEGRATION_KIT.md` |
| C9 | Tenant Contract | `MAYA_TENANT_ISOLATION_CONTRACT.md` |
| C10 | Governance | `MAYA_PERSONA_GOVERNANCE_MODEL.md` · `MAYA_RUNTIME_AUTHORITY_MAP.md` · `MAYA_PERSONA_SWITCHING_PROTOCOL.md` |