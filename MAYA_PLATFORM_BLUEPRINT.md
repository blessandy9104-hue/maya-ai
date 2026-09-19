# Maya Platform Blueprint — Phase 6 Ecosystem Architecture

- **Status:** blueprint v1.0 · Phase 6 of the founder trajectory: product →
  platform → ecosystem. Backed by a validated platform registry
  (`maya_identity/platform/platform_blueprint.json`, 52/52 checks) and fully
  consistent with the Phase-5 scaling registry.
- **Precondition (honest):** Maya is stable, verified, commercialized, and
  scalable. The **isolation runtime is the only remaining critical-path
  dependency.** Every multi-tenant capability in this blueprint is gated on
  implementing that runtime and re-auditing. Until then, platform breadth grows
  on **domain-isolated deployments**, never on concurrent-tenant hosting code.

---

## 1. Platform Core

### 1.1 Definition
Maya as a platform = **validated personas on a deterministic runtime, built in
the Studio, distributed through a governed marketplace, deployed via the embed
and cloud runtimes, extended by the read-only API and physical kiosks.** The
platform's value is the *verified, bounded, deterministic persona layer* — a
single trustworthy substrate that creators, businesses, and developers all
build against.

### 1.2 Boundaries (what Maya is / is not)
Maya **is**: a persona platform with a verified runtime; an interpretation
engine (including market-pattern interpretation); an embed + cloud runtime with
per-tenant isolation; a verify-first marketplace for personas.

Maya **is not**: a financial advisor or trading system; human labor or a
professional-equivalency service; an autonomous decision-making agent;
general-purpose compute or an account-access service. Every actor and surface
must respect this boundary.

### 1.3 Platform Authority Map
| Actor | Owns | Cannot |
|---|---|---|
| **Runtime** | execution, verification, ceilings, readiness gate | change tenant boundaries; self-declare readiness; exceed platform ceilings |
| **Tenant** | its domain deployment and mounted persona choice | edit profiles or ceilings; access other tenants; bypass origin checks |
| **Creator** | persona designs within guided Studio constraints | exceed CHANNEL_MAX ceilings; ship unverified personas; add banned/directive language |
| **Founder** | runtime core, marketplace approval, Studio advanced mode, platform fees | grant runtime authority over other tenants; skip verification and readiness gates |

Authority is strict-scope and non-escalating: no actor may delegate or expand
another's scope. Founder is the only verifier and remains the accountability
owner of the runtime.

## 2. Ecosystem Architecture

Four ecosystems share one verified substrate:

### 2.1 Creator ecosystem
- **Actors:** persona creators, Studio guided-mode users.
- **Surface:** Maya Studio.
- **Guardrails:** ceiling-locked editing; schema + governance checks before any
  listing; listing quota per creator (10).

### 2.2 Business ecosystem
- **Actors:** companies deploying personas, site owners.
- **Surface:** embed runtime + cloud runtime.
- **Guardrails:** per-tenant namespaces and quotas; exact-origin domain
  isolation; memory-only sessions.

### 2.3 Developer ecosystem
- **Actors:** read-only API consumers, partner sites.
- **Surface:** Maya API.
- **Guardrails:** GET-only endpoints; opaque read tokens; no PII, no account,
  rate-limited.

### 2.4 Marketplace ecosystem
- **Actors:** creators submitting personas; tenants installing personas.
- **Surface:** Maya Marketplace.
- **Guardrails:** submit→verify→approve→list pipeline; eight governance checks
  incl. no financial guarantee; moderation rules with founder review.

## 3. Platform Services

One entry per surface, all sitting on the verified core:

| Service | Facing | Key obligation |
|---|---|---|
| **Maya Studio** | creator-facing | guided, ceiling-locked editorial tool; founder-only advanced mode |
| **Maya Marketplace** | public-facing | verify-first persona listings with 8 governance checks |
| **Maya Cloud Runtime** | tenant-facing | per-tenant namespaces `NS(t,k)`, `/embed/<tenant-slug>`, bounded budgets; **gated on isolation runtime** |
| **Maya API** | developer-facing | 3 read-only GET endpoints (`/v1/interpretation`, `/v1/persona-info`, `/v1/embed-status`) |
| **Maya Kiosk Mode** | physical deployment | offline-safe deterministic loop, single-site, verified-runtime-required |
| **Maya Embed Runtime** | web deployment | exact-origin, memory-only, per-config (`/embed`) |

The embed runtime is today's production surface; the cloud runtime is the
future host and stays behind the isolation gate.

## 4. Governance & Safety

### 4.1 Multi-layer governance (runtime, marketplace, studio)
Governance is layered so a failure at one layer cannot reach a tenant: the
**Studio** constrains what a creator can express; the **Marketplace**
constrains what can be listed; the **Runtime** constrains what can actually
execute. All three are configured from one governance policy.

### 4.2 Persona verification pipeline
`submit → auto_verify → founder_review → approve → list`. Auto-verify runs the
standard governance checks; founder review is **mandatory** — auto-verify alone
never lists a persona (MR07).

### 4.3 Marketplace moderation rules (MR01–MR07)
1. Ceilings stay within CHANNEL_MAX. 2. Vocabulary closed, tone in allowlist.
3. Banned directive / financial-guarantee language → rejection. 4. No PII or
CORED content in any listing or profile. 5. Personas must be deterministic and
bounded in verification. 6. Market-analyst-category personas carry the
financial-safety ruleset + disclaimer. 7. Founder review required before any
listing.

### 4.4 Isolation runtime enforcement (post-implementation)
Enforcement is a real, running obligation — not a contract promise. It engages
only after both gates (`isolation_runtime_implemented`, `audit_cleared`):
deny-by-default at every namespace boundary, per-tenant kill switch, drift-lock
per tenant, F1–F10 forbidden cross-tenant actions enforced in code. The full
audit must re-run to a clean multi-tenant verdict before cloud hosting starts.

### 4.5 Platform-wide safety ceilings
Single ceiling policy chain, equal to CHANNEL_MAX everywhere:
`expression 0.5 · viseme 0.35 · micro 0.012 · anatomical 0.8`. No persona,
studio output, listing, or runtime execution may exceed these. Market-analyst
locks (confidence cap 0.5, financial-safety ruleset) hold platform-wide.

## 5. Platform Economics (abstract — no currency)

All indices, all abstract, no currency literals anywhere.

### 5.1 Marketplace revenue split
`creator 0.70 · platform 0.30` of each persona's recurring component (indices
sum to 1.0; matches the Phase-5 scaling registry).

### 5.2 Platform fees (abstract indices)
- **Embed rent:** 0.05 index per deployment (small — keep embed the frictionless
  on-ramp).
- **Cloud tenant:** 0.10 index per tenant (for hosted isolation + namespace
  enforcement after the runtime lands).
Fees are strictly below the 0.30 platform share of marketplace revenue.

### 5.3 Creator incentives
70% of the persona recurring component; higher listing position for top-listed
personas; vetted status for creators with verified, deterministic personas.

### 5.4 Founder incentives
30% platform share plus embed rent and cloud tenant fees; bundled deployment
revenue from marketplace personas; a platform reserve that grows with tenant
count to fund verification capacity (the solo-bottleneck hedge).

### 5.5 Scaling economics (10 → 100 → 1000)
| Tier | Tenants | Cost scale | Revenue index | Revenue/cost |
|---|---|---|---|---|
| solo | 10 | 1.0 | 1.0 | 1.00 |
| operator | 100 | 3.0 | 6.5 | 2.17 |
| platform | 1000 | 10.0 | 28.0 | 2.80 |

Cost grows sub-linearly (automation, retainer, cloud) while revenue outpaces
it — leverage improves across every tier, which is the whole point of
platformizing rather than freelancing. **Gated note:** the 100→1000 jump
presumes the isolation runtime and its prosocial verification capacity exist;
otherwise the operator tier is the credible ceiling for a solo founder.

## 6. Platform Roadmap

| Phase | Name | Gates | KPIs |
|---|---|---|---|
| **6.1** | Platform Core | studio_guided_live; domain_isolation_preserved | studio guided edits/week; time-to-deploy guided |
| **6.2** | Creator Ecosystem | creator_onboarding_open; verification_pipeline_automated | creators onboarded; pipeline auto-verify rate |
| **6.3** | Marketplace Launch | marketplace_governance_verified; founder_review_capacity | personas listed; marketplace install rate |
| **6.4** | Cloud Runtime Expansion | **isolation_runtime_implemented; audit_cleared**; multi_tenant_hosting_live | tenants on cloud; namespace enforcement rate |
| **6.5** | Developer API Growth | read_only_api_live; sandbox_compliance_verified | api consumers; api slo rate |
| **6.6** | Kiosk + Physical | cloud_runtime_stable; kiosk_verification_available | kiosk deployments; offline-safe uptime |

### Phase detail
- **6.1 Platform Core — now.** Studio guided mode live; keep domain isolation
  as the only form of multi-company hosting. KPI drives down deployment time
  with presets. **This is the current working phase.**
- **6.2 Creator Ecosystem.** Open creator onboarding; automate the
  verification pipeline so a solo founder can review but not hand-run every
  check. Gate on automated auto-verify rate.
- **6.3 Marketplace Launch.** Open listings only when governance is verified
  and founder review capacity exists — the MR07 gate. Ranking and installs
  become the marketplace's pull.
- **6.4 Cloud Runtime Expansion — the critical-path phase.** Nothing here
  moves until `isolation_runtime_implemented ∧ audit_cleared`. Then live
  multi-tenant hosting with per-tenant namespaces, quotas, and kill switches.
- **6.5 Developer API Growth.** Ship the read-only API behind its 3 GET
  endpoints and sandbox compliance; grow consumers with SLO reporting.
- **6.6 Kiosk + Physical.** Once cloud runtime is stable, roll kiosk
  deployments (offline-safe deterministic loop) as deliberate, verified,
  single-site installs.

### Cross-phase discipline
Every phase gate must be **real and verified**, not a design checkbox. Phases
before 6.4 may not touch multi-tenant hosting code; the embed runtime remains
the only production host until the isolation audit is clean. Each phase's KPIs
are monitored forward, not just at the gate, so a solo founder sees capacity
collapse coming before it happens.

## 7. Verification & File Map

- **Platform battery:** 52/52 checks — schema-valid; boundaries closed (4 is/4
  is-not); authority map complete with non-escalating cannot-sets; four
  ecosystems with surfaces and guardrails; all six services present;
  governance three-layer, pipeline correctly ordered, 7 MR rules, isolation
  gates equal to the Phase-5 scaling gates; ceilings == CHANNEL_MAX; marketplace
  split sums to 1.0 and matches Phase 5; embed/cloud fees bounded; scaling
  economics monotonic with improving revenue/cost (1.00 → 2.17 → 2.80); roadmap
  correctly ordered 6.1→6.6 with per-phase gates and KPIs; no secrets, no
  currency literals.
- **Artifacts:** `maya_identity/platform/platform_blueprint.json` ·
  `platform_blueprint.schema.json` · blueprint `MAYA_PLATFORM_BLUEPRINT.md`.
- **Chain:** Phase-5 scaling registry (studio/marketplace/cloud/API/kiosk) →
  full-system audit (isolation/sandbox gap) → Phase-6 platform registry. The
  platform inherits Phase-5's honest boundary: cloud hosting and marketplace
  listing open only behind the isolation-runtime gate.