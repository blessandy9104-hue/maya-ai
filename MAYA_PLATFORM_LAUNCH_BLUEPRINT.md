# Maya Platform Launch Blueprint — Phase 8

- **Status:** implementation blueprint v1.0 · Phase 8 of the founder journey:
  **"platform architecture" → "platform launch."** Backed by a validated launch
  registry (`maya_identity/launch/launch_plan.json`, 50/50 checks).
- **Precondition met (from Phase 7):** the **isolation runtime is implemented
  and verified**, and the full-system audit re-ran clean to a multi-tenant
  READY verdict. All Phase-6/7 gates are open. The **platform-wide READY gate
  (`platform_ready`) is green** — a mandatory starting condition for every
  surface in this blueprint.
- **Chain:** Phase 5 (scaling) → Phase 6 (platform) → Phase 7 (isolation
  runtime) → Phase 8 (this launch). Phase-8 registries stay numerically
  consistent with Phase 5/7 (per-tenant budget, ceilings, split, MR rules).

---

## 1. Platform Launch Architecture

### 1.1 Transition: founder-only → public platform
Maya moves from solo, single-deployment operation to a public platform: the
**Studio** serves creators, the **Marketplace** distributes verified personas,
the **Cloud Runtime** hosts many tenants in namespaced isolation, the **API**
serves developers, and the **Embed** runtime remains the universal web surface.
The founder graduates from "the only deployer" to "the platform operator," with
verification and audit authority retained.

### 1.2 Platform surfaces (five)
| Surface | Audience | Launch mode |
|---|---|---|
| **Studio** | creators | guided builder, presets-first |
| **Marketplace** | public/tenants | verify-before-list |
| **Cloud Runtime** | tenants | live multi-tenant namespaced |
| **API** | developers | read-only GET |
| **Embed** | any web tenant | exact-origin per-config |

### 1.3 Platform-wide READY gate (post-isolation audit)
Every surface assumes `platform_ready`, which is green **only** after the
isolation runtime is implemented and the full-system audit re-runs clean to a
multi-tenant verdict (Phase 7). No surface opens ahead of this gate. Access is
staged by the launch roadmap (§7) — surface availability widens across stages,
never ahead of verification.

## 2. Multi-Tenant Cloud Runtime (Live Mode)

### 2.1 How tenants are hosted
Live multi-tenant hosting behind the isolation runtime. Tenants share the
process only through namespaced, deny-by-default access — no tenant ever reads,
writes, or borrows across its `NS(t,k)` boundary.

### 2.2 Per-tenant namespaces `NS(t,k)`
`NS(t,k) :: /t/k/*` over `{data, logs, policies, brand, outputs, metadata}`.
Session→tenant binding is immutable at acquire; cross-tenant leading segments
are direct denies; aggregates need explicit consent from every contributing
tenant.

### 2.3 Per-tenant quotas
- **CPU:** 12% budget per tenant.
- **Embeds:** ≤ 4 active embeds per tenant.
- **Calls:** 5 000 calls/day per tenant.
- **Memory:** memory-only always.
- **Tokens:** TTL 900 s, per-domain `/embed/<tenant-slug>`.
(All equal to the Phase-5 scaling registry.)

### 2.4 Deterministic scaling rules
Add capacity only when **all** active slots sit above 80% utilization for a
committed window. Capacity changes are deterministically gated — never reactive
guessing. No tenant can consume another's idle capacity (slot-based,
anti-hoarding).

### 2.5 Fail-closed isolation enforcement
`deny_by_default`; `per_tenant_kill` (kill switch scoped to its tenant, checked
on every `can_*`); `no_idle_borrow`. Any isolation/sandbox error → deny + audit,
never "maybe allow." Parity native == headless holds on every guard decision.

## 3. Marketplace Launch

### 3.1 Creator onboarding
1. Creator applies and passes the eligibility check.
2. Creator builds in Studio guided mode (ceiling-locked).
3. Creator submits the persona for verification.
Listing quota per creator: **10** (keeps a solo/early-operator review queue
sustainable).

### 3.2 Submission → verification → listing
`submit → verify → approve → list`. Auto-verify runs the standard checks;
**founder review is mandatory before any listing** (MR07). Verify-before-list is
a hard governance flag; no persona lists without both.

### 3.3 Moderation workflow (MR01–MR07)
1. Ceilings within CHANNEL_MAX. 2. Vocabulary closed, tone in allowlist.
3. Banned directive / financial-guarantee language → rejection. 4. No PII or
CORED content in listings/profiles. 5. Deterministic, bounded in verification.
6. Market-analyst personas carry the financial-safety ruleset + disclaimer.
7. Founder review required; auto-verify alone insufficient.

### 3.4 Marketplace governance
Verify-before-list + founder-review-required, both enforced. Deterministic
personas, closed vocab, no banned directive, no PII, no financial guarantee.

### 3.5 Abstract revenue model (70/30)
`creator_share_index 0.70 · platform_share_index 0.30` of the persona's
recurring component (indices sum to 1.0). Abstract indices only — no currency.

## 4. Maya Studio (Creator Mode)

### 4.1 Persona builder UX
Guided persona builder: presets first, only approved knobs exposed, live schema
and ceiling feedback as the creator edits. Publishing is `guided_first` and
`validate_before_publish`.

### 4.2 Preset personas (5)
`receptionist`, `tutor`, `concierge`, `sales_agent`, `market_analyst` —
matching the validated preset set, each launching from its verified ceiling.

### 4.3 Advanced mode (founder-only)
`founder_only: true`, `requires_readiness: true`. Raw-profile and ruleset edits
are founder-scoped and only go live after readiness.

### 4.4 Ceiling-locked editing
`ceiling_locked: true`. `channel_ceiling`, `tone_profile.banned_registers`,
and `hard_rules` are locked for every preset; guided editors expose only
allowed knobs.

### 4.5 Schema validation
Every save/export validates against the persona profile schema (`guidance-4`:
schema, ceiling, vocab, tone) before anything can be submitted or listed.

### 4.6 Safe publishing pipeline
Guided-first and validate-before-publish; a persona reaches the Marketplace only
through the §3.2 verification flow, never directly from the Studio.

## 5. Developer API Launch

### 5.1 Read-only endpoints (all GET)
| Endpoint | Scope | Write |
|---|---|---|
| `GET /v1/interpretation` | `mpm_interpret` | no |
| `GET /v1/persona-info` | `public_persona_meta` | no |
| `GET /v1/embed-status` | `embed_health_status` | no |

### 5.2 Rate limits
60 requests/min. No write, no PII, no account access.

### 5.3 Opaque tokens
`opaque_read_token` auth — scoped per tenant, opaque (non-derivable), read-only;
no account or write surface; tokens rotated per the Phase-8 ops schedule.

### 5.4 Safe integration patterns
- Client-side calls with a tenant-scoped opaque read token.
- Server-side caching of static persona-info with token rotation.
- No echo of user-supplied series beyond the in-flight interpretation (stateless).

### 5.5 Developer onboarding flow
1. Developer requests a read token for their tenant.
2. Token is scoped and opaque; no account or write surface.
3. Docs enforce GET-only, rate-limit, and no-PII integration.

## 6. Platform Operations

### 6.1 Monitoring
Per-tenant usage and quota tracking; isolation anomaly counters from audit
hooks; readiness and parity health signals.

### 6.2 Audit cycles
Daily audit rollup plus a **full re-audit at every launch-stage gate** and on
every deploy. Post-isolation audit is the standing baseline for `platform_ready`.

### 6.3 Regression sweeps
Re-run the existing verification sweep and the Phase-7 isolation 12-step suite
on every deploy and at each stage gate. Isolation must not regress the verified
core.

### 6.4 Tenant onboarding workflow
1. Verify company identity and deploy the domain config.
2. Issue per-tenant embed config and quota.
3. Confirm readiness before go-live.

### 6.5 Creator onboarding workflow
1. Creator eligibility check.
2. Guided Studio orientation.
3. First persona submitted and verified before listing.

### 6.6 Support model (solo founder → platform operator)
The solo founder remains primary support through 8.2–8.3; at 8.4 transition to a
platform-operator model with authored runbooks and tiered escalation — the
support-capacity hedge required before the 100→1000 jump.

## 7. Launch Roadmap

| Stage | Name | Creators | Tenants | Access | Gates | KPIs |
|---|---|---|---|---|---|---|
| **8.1** | Internal Launch | 0 | 0 | founder_only | isolation_runtime_verified; platform_ready_gate | studio guided deploy time; isolation suite pass rate |
| **8.2** | Closed Beta | 10 | 10 | invited | internal_launch_ready; invite_controls_in_place | creator activation rate; tenant onboard time; support tickets/week |
| **8.3** | Open Beta | 50 | 50 | approved_application | closed_beta_ready; automation_scales; support_ratio_safe | personas listed; marketplace install rate; api consumers |
| **8.4** | Public Launch | 100 | 100 | public | open_beta_ready; operator_handoff; retainer_automation | platform recurring ratio; churn rate; multi-tenant uptime |

### Stage detail
- **8.1 Internal Launch (founder-only).** All five surfaces live to the founder
  alone. Purpose: prove guided Studio deploys are fast and the isolation suite
  is green at rest. Gate: `isolation_runtime_verified` + `platform_ready_gate`.
- **8.2 Closed Beta (invited).** 10 invited creators, 10 tenants. Purpose:
  validate creator/tenant onboarding and the founder's support load. Gate on
  invite controls; monitor creator activation, tenant onboard time, and weekly
  tickets.
- **8.3 Open Beta (approved application).** 50 creators, 50 tenants. Purpose:
  prove automation scales the verification pipeline and support ratio stays
  safe. Harden marketplace installs and API consumers. **Gate: automation scales
  + support ratio safe** — the solo-bottleneck hedge.
- **8.4 Public Launch (public).** 100+ tenants. Purpose: full marketplace and
  platform economics. **Gate: operator_handoff + retainer_automation** — must be
  real before public scale, otherwise the operator tier (100) is the credible
  ceiling.

### Cross-stage discipline
Access-model widens monotonically (founder_only → invited → approved →
public); stage counts scale monotonically (0→10→50→100). Each stage's KPIs are
monitored forward, not just at the gate, so a solo founder sees support or
verification capacity collapse before it happens. A full re-audit runs at every
stage gate; no stage opens on a stale `platform_ready`.

## 8. Verification & File Map

- **Launch battery:** 50/50 checks — schema-valid; surfaces exactly the five
  platform surfaces; readiness gate green post-isolation; live-multi-tenant
  hosting; per-tenant CPU/embeds/calls/TTL identical to Phase 5; deterministic
  80%-utilization scaling; fail-closed deny-by-default/per-tenant-kill/no-idle-
  borrow; marketplace flow + MR01–MR07 + verify-first governance + 70/30 split
  and creator quota 10; studio presets (5) matching the scaling registry,
  founder-only advanced, ceiling-locked, schema-validated, guided-first
  publishing; API 3 GET-only endpoints, 60/min, opaque read token; ops covers
  monitoring/audit/regression/tenant+creator onboarding/operator transition;
  roadmap 8.1→8.4 with monotonic access (founder-only→public) and scale
  (0→10→50→100), 8.3 gated on automation, 8.4 gated on operator handoff; no
  secrets, no currency.
- **Artifacts:** `maya_identity/launch/launch_plan.json` ·
  `launch_plan.schema.json` · blueprint `MAYA_PLATFORM_LAUNCH_BLUEPRINT.md`.
- **Chain:** Phase-5 scaling numbers and marketplace policy → Phase-6 platform
  surfaces/gates → Phase-7 isolation runtime (verified) → Phase-8 launch. The
  launch is binding: no surface, marketplace, or API hosting proceeds without
  the post-isolation `platform_ready` gate staying green.