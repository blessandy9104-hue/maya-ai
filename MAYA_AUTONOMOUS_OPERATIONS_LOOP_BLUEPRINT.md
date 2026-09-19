# Maya Autonomous Operations Loop Blueprint — Phase 12 AOL

- **Status:** implementation blueprint v1.0 · Phase 12 of the founder journey:
  Maya runs **continuous, autonomous operational loops** to keep the platform
  healthy. Backed by a validated AOL registry
  (`maya_identity/aol/aol_plan.json`, 44/44 checks).
- **Preconditions met:** Phase 8 platform launched; Phase 9 operator mode active;
  Phase 10 monetization defined; Phase 11 command system provides the invocation
  interface. Phase 7 isolation runtime is implemented and verified.
- **Autonomy posture (non-negotiable):** AOL autonomy is **strictly
  non-legal-only and non-financial-only**, capped at
  `operator_only_nonlegal_nonfinancial`, under **operator-only autonomy with
  founder-only gating**. No loop can approve a contract, authorize a payment,
  set pricing, negotiate, or act on financial/medical/legal safety. Every loop
  action is isolation-guarded, deterministic, ceiling-locked, founder-visible,
  and auditable. This is continuous operational automation, **not** delegation
  of judgment.

---

## 1. AOL Definition

### 1.1 Purpose
Maya autonomously executes the operational loops that keep the platform
healthy: monitoring, verification, moderation pre-review, maintenance,
deployment prep, and ecosystem operations. The AOL is the driver layer; the
Phase-11 command system is how the founder invokes and audits loops; the
Phase-7 isolation runtime guards every loop action.

### 1.2 Boundaries (non-legal-only, non-financial-only)
`non_legal_only: true`, `non_financial_only: true`. The AOL never touches legal
tasks (contracts, payments, liabilities, terms), business decisions (pricing,
negotiation), or financial/medical/legal safety. Within those bounds it is
autonomous; at the boundary it stops and escalates.

### 1.3 Authority map (operator-only autonomy vs founder-only gating)
| Actor | Owns | Cannot |
|---|---|---|
| **Operator autonomy** | autonomous execution of non-legal operational loops: monitoring, verification, moderation pre-review, maintenance, deployment prep, ecosystem operations | approve legal commands; commit payments or pricing; act on financial/medical/legal safety; exceed the loop registry; invoke founder-only gates autonomously |
| **Founder gating** | gates beyond operator autonomy: legal approval, payment authorization, proposal, pricing, go/no-go on out-of-scope exceptions | be bypassed by any loop; run without founder auth and audit |

Autonomy is bounded and non-escalating: an autonomous loop cannot grant itself
a founder-only gate, and every out-of-scope exception is escalated to the
founder, never auto-resolved.

## 2. AOL Loop Categories

| Category | Loops | Notes |
|---|---|---|
| **monitoring** | `runtime`, `embed`, `cloud`, `api` | health, quota, SLO, anomaly counters |
| **verification** | `persona`, `identity`, `isolation` | regression/re-verify, identity CORED integrity, isolation checks |
| **moderation** | `marketplace_prereview` | MR01–MR06 auto pre-review; MR07 founder review preserved |
| **maintenance** | `audit`, `regression`, `drift_checks` | continuous audit, sweep, drift/parity checks |
| **deployment** | `config_prep`, `embed_prep`, `persona_prep` | deterministic prep inside tenant NS |
| **ecosystem** | `creator`, `tenant`, `kiosk` | non-legal onboarding loops; kiosk offline-safe health |

The moderation loop is deliberately scoped: it pre-reviews MR01–MR06
autonomously and prepares the packet, but **MR07 founder review stays human** —
auto-verify alone never lists a persona (the same rule as Phases 5–9).

## 3. AOL Loop Architecture

### 3.1 Loop scheduler (deterministic, fixed cadence)
`deterministic` + `fixed_cadence` + `no_realtime` + `cooldown_on_escalate`.
Loops run on fixed, predetermined cadence with no wall-clock-reactive
branching; after an escalation a loop enters cooldown rather than retrying
hot. Deterministic, device-identical (parity native == headless).

### 3.2 Loop registry (declarative, operator-only)
Every loop is a declarative operator-only entry in the registry — declared,
schema-validated, ceiling-locked, and explicitly non-legal/non-financial. A
loop not in the registry cannot run; a loop cannot be extended to a
founder-only action by itself.

### 3.3 Loop executor (isolation-guarded)
`isolation_guarded: true`, `operator_bound: true`. Every loop action passes
through the isolation runtime's deny-by-default; no cross-tenant access, no
CORED emission; the executor is bound to operator capability and cannot issue
legal commands.

### 3.4 Loop validator (safety ceilings)
Validates each loop output against the platform safety ceilings (`expression
0.5 · viseme 0.35 · micro 0.012 · anatomical 0.8`) and is deterministic.
Anything exceeding a ceiling is rejected before execution proceeds.

### 3.5 Loop audit hooks (founder-visible)
`founder_visible: true`, `record_all: true`, `no_cored_log: true`. Every loop
run and outcome is logged and founder-reviewable; identity CORED is never
written to logs.

### 3.6 Fallback behaviors (fail-closed, retry, escalate)
`fail_closed` (any error → deny, never "maybe allow"), `retry_bounded` (bounded
deterministic retries with cooldown), `escalate_founder` (any non-legal
exception or boundary approach → founder gate). No loop auto-resolves an
out-of-scope or ambiguous case.

## 4. Integration Points

| Surface | AOL binding |
|---|---|
| **Command System (11)** | the founder invocation + audit interface; loops are command-routable |
| **Operator Engine (9)** | the executor that runs each loop's non-legal operations |
| **Platform Surfaces** | Studio / Marketplace / Cloud Runtime / API — loop targets (monitoring, moderation, deployment) |
| **Isolation Runtime (7)** | deny-by-default guard on every loop action |
| **Persona Loader** | persona prep/verify loops run inside tenant NS |
| **Identity Loader** | identity verification loops emit fingerprints only, never CORED |

The AOL rides the Operator Engine as executor over the command system as
interface, with the isolation runtime as the guard on every surface it touches.

## 5. Safety & Boundaries

### 5.1 Legal boundaries (contracts, payments, liabilities)
No loop auto-approves a contract, authorizes a payment, or accepts a liability.
All legal-scope items escalate to the founder gate.

### 5.2 Business boundaries (pricing, negotiation)
No loop sets or negotiates pricing. Business decisions stay founder-only.

### 5.3 Safety boundaries (financial, medical, legal)
No loop acts on financial, medical, or legal safety. Market-analyst-category
handling keeps its financial-safety ruleset and founder review (MR06); nothing
financial is auto-decided.

### 5.4 Isolation boundaries (deny-by-default)
`isolation_boundaries: deny_by_default` — every loop action runs under the
isolation runtime's fail-closed deny-by-default.

### 5.5 Operator-only autonomy cap
`autonomy_cap: operator_only_nonlegal_nonfinancial`. The upper bound of AOL
autonomy is explicitly non-legal, non-financial, operator-scoped operations;
founder-only gating is preserved for everything above it.

## 6. AOL Roadmap

| Stage | Name | Gates | KPIs |
|---|---|---|---|
| **12.1** | Monitoring Loop | aol_engine_ready; runtime_embed_cloud_api_monitoring_live; isolation_guarded_executor | monitoring coverage; anomaly detection latency |
| **12.2** | Verification Loop | persona_identity_isolation_verification_live; verification_suite_automated | persona verify rate; isolation check pass rate |
| **12.3** | Moderation Loop | marketplace_prereview_live; mr07_founder_review_preserved | personas pre-reviewed/week; pre-review→founder time |
| **12.4** | Maintenance Loop | audit_regression_drift_live; regression_sweep_automated | sweep pass rate; drift check latency |
| **12.5** | Deployment Loop | config_embed_persona_prep_live; deployment_prep_validated | deploy prep time; config validation rate |
| **12.6** | Ecosystem Loop | creator_tenant_kiosk_loops_live; nonlegal_nonfinancial_bound_reverified | tenant+creator onboard time; kiosk loop uptime |

### Stage detail
- **12.1 Monitoring Loop (current).** AOL engine live behind the isolation
  runtime; monitoring loops for runtime, embed, cloud, and API.
- **12.2 Verification Loop.** Persona, identity, and isolation verification
  loops automated against the existing suites.
- **12.3 Moderation Loop.** Marketplace MR01–MR06 pre-review automated; **MR07
  founder review preserved** (gate).
- **12.4 Maintenance Loop.** Audit, regression sweep, and drift checks run
  continuously.
- **12.5 Deployment Loop.** Config/embed/persona prep fully automated inside
  tenant NS.
- **12.6 Ecosystem Loop.** Creator, tenant, and kiosk loops live — with the
  non-legal/non-financial bound re-verified as the entry gate for the widest
  autonomy.

### Cross-stage discipline
Real, verified gates at every stage. The autonomy cap
(`operator_only_nonlegal_nonfinancial`) is fixed from 12.1 onward and
re-verified at 12.6; isolation deny-by-default guards every loop from the
engine stage on; MR07 stays human at every stage; audit is continuous and
founder-visible. A loop never self-escalates its authority.

## 7. Verification & File Map

- **AOL battery:** 44/44 checks — schema-valid; non-legal + non-financial
  boundaries; operator autonomy owns autonomous operational loops and cannot
  approve legal/commit payments/act on safety/exceed the registry/invoke
  founder gates; founder gating owns legal and cannot be bypassed; all 6 loop
  categories with their enumerated loops (moderation = single
  marketplace_prereview); loop scheduler deterministic/fixed-cadence/no-realtime/
  cooldown-on-escalate; declarative operator-only registry; isolation-guarded
  operator-bound executor; validator with CHANNEL_MAX ceilings + deterministic;
  founder-visible record-all no-CORED audit hooks; fail-closed/retry-bounded/
  escalate-founder fallback; 6 integration points incl. command system +
  isolation runtime; legal/business/safety boundaries disjoint; isolation
  deny-by-default; autonomy cap = operator-only-nonlegal-nonfinancial; roadmap
  12.1–12.6 with MR07 preserved at 12.3 and bound reverified at 12.6; no
  secrets.
- **Artifacts:** `maya_identity/aol/aol_plan.json` · `aol_plan.schema.json` ·
  blueprint `MAYA_AUTONOMOUS_OPERATIONS_LOOP_BLUEPRINT.md`.
- **Chain:** Phase-7 isolation runtime → Phase-8 platform → Phase-9 operator →
  Phase-10 monetization → Phase-11 command system → Phase-12 AOL. The AOL is
  the highest-autonomy layer and the most strictly bounded: continuous
  operational loops that stop at the non-legal/non-financial boundary and
  escalate to the founder, never auto-deciding judgment.