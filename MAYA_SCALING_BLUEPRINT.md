# Maya Scaling Blueprint — Phase 5 Platform Expansion

- **Status:** blueprint v1.0 · Phase 5 of the founder trajectory (10 → 100 →
  platform). Backed by a validated scaling-plan registry
  (`maya_identity/scaling/scaling_plan.json`, 75/75 checks).
- **Founder context:** solo, one ThinkPad, AI-assisted builds, verified stable
  runtime, commercially deployed via universal embed.
- **Hard boundary (respect it):** the isolation/sandbox **runtime** is still a
  contract-gap (full-audit finding). This blueprint gates every multi-tenant
  capability on implementing and re-auditing that runtime first. Until then:
  **one company per deployment, isolated by domain**, not by namespace code.

---

## 1. Multi-Company Onboarding

### 1.1 Safe-by-default sequence (Phase 1, pre-isolation-runtime)
The embed runtime already serves one config per domain. Onboarding N companies
in this phase means **N independent configurations** — folder per client,
exact per-company origin, independent quota/TTL. That is *deployment-level*
isolation, not *runtime-level* isolation:

```
clients/<company-a>/   config → origin A  → /embed?origin=A
clients/<company-b>/   config → origin B  → /embed?origin=B
...  (shared process only after isolation runtime lands)
```

### 1.2 Multi-company rules (all phases)
- **Per-tenant identity boundaries:** one `company_id`-scoped profile per
  tenant; profiles resolve only within their tenant slot; CORED and protected
  fields never serialize; identity surfaces site-facing only.
- **Per-tenant persona boundaries:** persona chosen from the web allowlist per
  tenant; no tenant may inject a persona, edit a profile, or override register
  ceilings.
- **Per-tenant embed configuration:** `embed_config.json` is per-tenant; origin
  allowlist, mode, persona, TTL, and quota are set per company and cannot bleed
  across tenants.
- **Domain-based isolation (pre-runtime):** a tenant's namespace today is
  effectively *its own deployment*. Documented in the phase gate P1 as
  `domain_isolation`.

## 2. Maya Studio (Persona Builder)

### 2.1 Concept
A lightweight, web-hosted persona editor for site owners and (later) market
creators, built on the persona-profile schema and the verified ceilings.

### 2.2 Safe persona editing (guided mode)
- **Ceiling-locked:** `channel_ceiling`, `tone_profile.banned_registers`, and
  `hard_rules` are locked for every preset (verified per-persona); a guided
  editor exposes only approved knobs (intro copy, vocabulary additions within
  the closed set, tone accent within allowlist, cadence within bounds).
- **Schema-validated:** every save must validate against the persona profile
  schema (studio `validation_gates: schema, ceiling, vocab, tone`).
- **Presets:** receptionist, tutor, concierge, sales_agent, market_analyst —
  each launching from its validated ceiling (0.38/0.40/0.35/0.42/0.25
  expression, all ≤ CHANNEL_MAX). `market_analyst` additionally locks
  `confidence_cap` and `financial_safety_ruleset`.

### 2.3 Founder-only advanced mode
- `founder_only: true`, `requires_readiness: true`. Advanced edits (raw profile
  fields, new tones wiring, rulesets) are founder-scoped and only go live after
  the success of the verification sweep + readiness gate.

## 3. Persona Marketplace (Phase 5.2)

### 3.1 Creator flow: submit → verify → approve → list
- **Submit:** a creator designs a persona in Maya Studio (guided mode,
  ceiling-locked; or founder-advanced only).
- **Verify:** automated governance checks (validated set of 8): schema,
  ceiling_bounded, vocab_closed, tone_allowlist, no_banned_directive,
  deterministic, no_pii, no_financial_guarantee.
- **Approve:** founder/operator approves; any persona touching special domains
  (e.g., anything resembling market_analyst) uses the required safety
  rulesets and disclaimers before approval.
- **List:** the persona enters a discoverable catalog; installable per tenant
  under per-tenant boundaries.

### 3.2 Governance
- Ceilings cannot exceed CHANNEL_MAX (0.5/0.35/0.012/0.8); banned registers
  stay banned; vocab stays closed; determinism is mandatory; no PII; no
  financial guarantees. Listing quota per creator: 10 personas (bounded, to
  keep review sustainable by a solo team).
- **marketplace is Phase 5.2** — it opens only after verification processing is
  reliable at 10–50-client scale (retainer automation in place).

### 3.3 Revenue split (abstract)
`creator_share_index 0.70 · platform_share_index 0.30` of the persona's
recurring component (validated: indices sum to 1.0). Splits are abstract
indices like all Maya pricing — no currency literals anywhere.

## 4. Maya Cloud Runtime (Phase 5.3)

### 4.1 When it may exist
**Only after both gates:** `isolation_runtime_implemented` and `audit_cleared`
(the full-system audit must re-run with a multi-tenant verdict). The current
`issues_detected` finding on isolation/sandbox is the exact gate.

### 4.2 Hosted layout
- **Per-tenant namespaces:** `NS(t,k)` from the tenant isolation contract (t =
  tenant, k = resource), enforced by the isolation manager runtime.
- **Embed endpoints per domain:** `/embed/<tenant-slug>`; exact-origin checks
  remain; per-tenant token TTL (900 s) and quota.
- **Per-tenant budgets:** max 4 active embeds/tenant, CPU budget 12%/tenant
  (≤ 25% cap), 5 000 calls/day/tenant, memory-only always.
- **Deterministic scaling rule:** add capacity only when **all** active slots
  sit above 80% utilization for a committed window — capacity changes are
  deterministically gated, never reactive guessing.

### 4.3 Safe multi-tenant hosting
Same invariants as single-tenant plus: deny-by-default at every namespace
boundary, kill switch scoped to one tenant, drift-lock per tenant, F1–F10
forbidden cross-tenant actions enforced by the isolation manager (all are
runtime obligations, which is why they wait for the runtime).

## 5. Maya API (Read-Only) — Phase 5.3

### 5.1 Concept
A thin **read-only** API: no write, no memory, no account access. It exposes
verified surfaces to partner sites and the marketplace, not a general compute
surface.

### 5.2 Allowed endpoints (all GET)
| Endpoint | Scope | Notes |
|---|---|---|
| `GET /v1/interpretation` | mpm_interpret | Deterministic MPM interpretation on user-supplied series; interpretation-only framing, disclaimer attached |
| `GET /v1/persona-info` | public_persona_meta | Public persona metadata (name, register, ceiling summary) |
| `GET /v1/embed-status` | embed_health_status | Embed/slot health for a tenant (status, anomalies count) |

Every endpoint: `write=false`, `no_pii`, `no_account`, opaque read-only token
auth, rate limit 60/min. No interpretation caching across requests (stateless),
no persistence of provided series.

## 6. Maya Kiosk Mode (Phase 5.4)

### 6.1 Presets
`kiosk_assistant` (existing training persona, verified ceiling) and
`receptionist` (web allowlist). Kiosk deployments are single-site.

### 6.2 Offline-safe mode
- `offline_safe: true`: the kiosk continues on the deterministic loop after
  connectivity loss (`offline_fallback`), with no remote secrets required.
- **Deterministic kiosk loop:** fixed 2 s cadence, `no_rng`, bounded frames;
  same input window → same loop behavior (parity with the verified runtime).

### 6.3 Physical-deployment boundaries
single_site; verified_runtime_required; no_remote_secrets; physical power-cycle
failure expected to produce the same deterministic boot state; no account or
network egress. Kiosk is Phase 5.4 — after cloud runtime stabilizes, and only
as a deliberate, per-site deployment.

## 7. Scaling Roadmap (10 → 50 → 100+)

| Phase | Range | Gates (validated) | Founder role |
|---|---|---|---|
| P1 | 10–50 | `studio_guided`, `domain_isolation`, `folder_per_client`, `retainer_automation` | Solo operator; domain-based isolation only |
| P2 | 50–100 | `isolation_runtime_implemented`, `audit_cleared`, `cloud_runtime_live`, `read_only_api` | Operator + cloud tenant admin |
| P3 | 100–1000 | `marketplace_open`, `multi_tenant_audited`, `founder_to_operator` | Platform operator (persona creators onboarded) |

### 7.1 When to implement the isolation runtime
**Immediately after P1 KPIs hold.** It is the critical-path gate: cloud runtime,
read-only API, and marketplace all depend on it. Do not start cloud hosting
before the isolation/sandbox modules exist and the audit re-runs clean.

### 7.2 When to move to cloud runtime
At P2, and only with `isolation_runtime_implemented ∧ audit_cleared`. While
this is pending, scale purely with domain-isolated deployments (existing embed
runtime supports this without code changes).

### 7.3 When to open the persona marketplace
At P3 (phase `5.2`), once revenue automation and verification practices are
mature at 50–100 clients; soul of the gate: verify reliably before you list.

### 7.4 KPIs & capacity rules (solo)
- KPI targets: build time ≤ 2 days with studio presets; time-to-READY ≤ 1 day;
  recurring ratio ≥ 0.7; support tickets ≤ 2/client/month; churn < 1/month.
- **Capacity rules (validated):** P1 onboarding max 3 concurrent; P2 support
  ratio 40 clients per founder; **retainer automation required before P3** —
  without automation, a solo founder drowns after ~50 clients, credibly.

### 7.5 Phase-up gate (from the founder playbook, extended)
1. KPIs held at current phase (recurring ratio, tickets, churn).
2. The specific capability gate (studio / isolation+cloud / marketplace) real,
   verified, and audited — not just designed.
3. Capacity rule respected (≤ 3 concurrent builds in P1; ≤ 40 clients/founder
   at P2 before cloud ops assistance).
4. Every market_analyst tenant re-verified against the financial-safety
   ruleset within the last 90 days.

## 8. Verification & File Map

- **Scaling battery:** 75/75 checks — registry schema-valid; studio presets
  match the web allowlist with ceilings equal to the commerce catalog (in-band
  per CHANNEL_MAX); ceilings locked; marketplace split sums to 1.0 with six+
  governance checks; cloud requires both isolation-implemented and audit-
  cleared and has bounded per-tenant budgets; API is 3 GET-only scopes with a
  strict sandbox; kiosk presets exist in registries with offline-safe
  deterministic loop; roadmap gates are correctly ordered (P1 = domain
  isolation, P2 = isolation runtime + cloud + API, P3 = marketplace +
  multi-tenant audit); no secrets or currency literals.
- **Artifacts:** `maya_identity/scaling/scaling_plan.json` ·
  `scaling_plan.schema.json` · blueprint `MAYA_SCALING_BLUEPRINT.md`.
- **Upstream contracts:** tenant isolation contract, isolation manager,
  runtime authority map, commercial catalog, founder playbook, full-system
  audit (issues_detected → single isolation/sandbox gap).