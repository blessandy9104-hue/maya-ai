# Maya Unified Specification — Phase 13 MUS

- **Status:** implementation blueprint v1.0 · Phase 13 / capstone of the Maya
  founder journey. MUS is the **single authoritative reference** consolidating
  all of Phases 1–12 into one specification: twelve systems, six boundary
  groups, consolidated ceilings, seven schemas, unified tier-index pricing,
  and Founder Console integration. Backed by a validated MUS registry
  (`maya_identity/mus/mus.json`, 71/71 checks, including cross-registry
  consistency against the commerce catalog, scaling registry, and Phases 9, 11,
  12 records).
- **Preconditions met:** Phase 12 AOL live; all upstream registries
  individually validated. MUS does not add new behavior — it consolidates and
  cross-locks the existing truth so every surface, boundary, and ceiling is
  defined once and consistently.
- **Consolidation posture:** MUS is authoritative — the Founder Console
  resolves every command, operator action, launch/embed/page, moderation, and
  AOL loop against it. No surface invents its own boundary, ceiling, schema, or
  pricing index.

---

## 1. MUS Definition

### 1.1 Purpose
Provide a single source of truth: every system, boundary, ceiling, schema, and
pricing index the platform relies on, defined in one place and numerically
cross-consistent with the phase registries. At the Founder Console, MUS is the
only reference a user or operator needs to interpret state, boundaries, and
allowable actions.

### 1.2 Consolidation scope
`consolidation_scope: phases_1_to_12`. MUS subsumes the runtime, isolation,
persona, embed/cloud, marketplace, studio, API, kiosk, operator engine, command
system, and AOL registries into a single coherent keyed reference. Nothing in
MUS contradicts an upstream phase; it is the consolidation, not a redefinition.

### 1.3 Authority map (founder-only vs operator-only vs platform-only)

| Actor | Owns | Cannot |
|---|---|---|
| **Founder-only** | legal authority, contract approval, payment authorization, pricing, negotiation, go/no-go, final marketplace approval | delegate legal authority; be bypassed by any loop or command; skip audit |
| **Operator-only** | non-legal, non-financial operational execution: onboarding, setup, deployment prep, monitoring, verification, moderation pre-review, maintenance | approve legal; commit payments or pricing; act on financial/medical/legal safety; exceed ceilings or scope |
| **Platform-only** | the deterministic shared runtime, ceilings, marketplace governance, tenant-boundary enforcement | grant legal authority; alter per-tenant boundaries at will; exceed platform ceilings |

The three authorities are disjoint and non-escalating: platform enforces the
runtime contract, operator runs within non-legal/non-financial bounds, founder
holds all legal/business/go-no-go authority and cannot be bypassed.

## 2. System Consolidation
MUS enumerates all **twelve** systems in one keyed reference:

| # | System | Consolidation role |
|---|---|---|
| 1 | **Runtime** | deterministic Maya core: blends, channels, ceilings |
| 2 | **Isolation Runtime** | deny-by-default NS(t,k) guard around every tenant scope |
| 3 | **Persona System** | the 5 web personas + their ceilings and commerce linkage |
| 4 | **Embed Runtime** | MSG.v1 postMessage envelope; web persona allowlist |
| 5 | **Cloud Runtime** | per-tenant NS, endpoint, budgets, quotas |
| 6 | **Marketplace** | listing, moderation MR01–MR07, creator split |
| 7 | **Studio** | authoring surface; presets = the 5 personas |
| 8 | **API** | programmatic surface (embed/cloud facing) |
| 9 | **Kiosk** | offline-safe standalone surface |
| 10 | **Operator Engine** | executor of non-legal/non-financial operations |
| 11 | **Command System** | table-based invocation + isolation integration |
| 12 | **AOL Loops** | autonomous operational loops (monitoring→ecosystem) |

All twelve are defined once in MUS; each maps back to its originating phase
registry for implementation detail.

## 3. Boundary Consolidation
Six mutually-disjoint boundary groups, defined once:

| Group | Members (enforced) |
|---|---|
| **Legal boundaries** | contracts · payments · liabilities · terms |
| **Business boundaries** | pricing · negotiation |
| **Safety boundaries** | financial · medical · legal |
| **Isolation boundaries** | `deny_by_default` |
| **Operator-only boundaries** | `nonlegal_nonfinancial` |
| **Founder-only boundaries** | `legal_business_go_no_go` |

- No overlap: legal / business / safety sets are disjoint; a given decision
  belongs to exactly one group.
- Ordering for enforcement: **safety → isolation → legal → business → operator
  scope → founder go/no-go.** Any action touching a higher group than operator
  scope escalates to the founder gate; any action reaching safety or isolation
  denies first.

## 4. Ceiling Consolidation
Ceilings are consolidated so every surface references one shared truth.

### 4.1 CHANNEL_MAX (the global ceiling)
`expression 0.5 · viseme 0.35 · micro 0.012 · anatomical 0.8`. The absolute
cap; operator, AOL, platform, and validator ceilings all reference CHANNEL_MAX.

### 4.2 Persona ceilings (per-web-persona, match the commerce catalog)
| Persona | expression | viseme | micro |
|---|---|---|---|
| receptionist | 0.38 | 0.24 | 0.008 |
| tutor | 0.40 | 0.26 | 0.009 |
| concierge | 0.35 | 0.20 | 0.006 |
| sales_agent | 0.42 | 0.28 | 0.010 |
| market_analyst | 0.25 | 0.12 | 0.002 |

All persona ceilings are within CHANNEL_MAX; a persona can never exceed its own
ceiling, and no persona exceeds the global cap.

### 4.3 Operator / AOL / platform ceilings (via CHANNEL_MAX)
`operator_ceilings`, `aol_ceilings`, `platform_ceilings` all reference
CHANNEL_MAX (battery-verified in MUS and in the Phase 9/11/12 registries). Any
output validator — command, operator, AOL loop — locks against CHANNEL_MAX.

### 4.4 Tenant quotas (match the scaling registry)
`cpu_budget_pct 12` · `max_active_embeds_per_tenant 4` · `quota_calls_per_day
5000` · `token_ttl_seconds 900`. Cross-locked to the scaling per_tenant record.

## 5. Schema Consolidation
Seven canonical schemas are referenced once under MUS (`schema_consolidation`):
`identity` · `persona` · `command` · `operator_task` · `aol_loop` ·
`marketplace_listing` · `tenant`. Each has a resolvable canonical path in the
phase registries; no surface defines a competing shape. MUS is the index that
guarantees the seven schemas are the only ones that exist.

## 6. Pricing Consolidation
`model: unified_tier_index` — **all** pricing is expressed in abstract
tier-index terms, never currency literals.

| Group | Indices |
|---|---|
| persona_indices | per-persona tier indices (market_analyst flagged MR06/financial-safety) |
| bundle_indices | per-bundle tier indices |
| platform_indices | platform tier indices (revenue/split) |
| marketplace_indices | marketplace tier indices (creator share) |
| cloud_runtime_indices | cloud runtime tier indices (per-tenant) |

MUS consolidates all five groups under `unified_tier_index`; tier→price
conversion is founder-defined in a private ledger outside the repo. No USD/GBP/
EUR or currency symbol appears anywhere in MUS.

## 7. Founder Console Integration

### 7.1 MUS ↔ Command System (invocation interface)
The command system is the **invocation interface** into MUS. Every command
that queries state, changes a config, or triggers a loop resolves against MUS
first: authority (founder/operator/platform), boundary group, and ceiling are
all checked from the consolidated reference before execution.

### 7.2 MUS ↔ Operator Mode (executor)
Operator mode is the **executor** for the operational tasks defined in the
Phase-9 operator registry. At the console, each operator action validated
against MUS boundaries (`operator_only = nonlegal_nonfinancial`) and MUS
ceilings (CHANNEL_MAX) — so the operator can never execute a legal/business or
ceiling-exceeding action, consistent with the Phase-9 cap.

### 7.3 MUS ↔ AOL (autonomous driver)
The AOL is the **autonomous driver** over the operational loops. At the
console, every loop run is checked against the MUS authority map (operator-only
autonomy, founder-only gating) and the MUS ceilings/schemas, preserving the
`operator_only_nonlegal_nonfinancial` autonomy cap and the MR07 human review.

### 7.4 MUS as the authoritative reference
`authoritative: true`. At the Founder Console:
- **Read paths** resolve state against MUS (single source of truth).
- **Write/invoke paths** (commands, operator actions, AOL loops) are validated
  against MUS authority, boundary, and ceiling before any effect.
- **Cross-consistency** is enforced: MUS is battery-checked against the
  commerce catalog, scaling registry, and Phases 9/11/12 registries, so the
  console never sees a drift between a surface and its spec.

## 8. Phase 13 Roadmap

| Stage | Name | Gates | KPIs |
|---|---|---|---|
| **13.1** | System Consolidation | all_twelve_systems_enumerated; phase_chain_integrity | system_reference_completeness; consistency_violations |
| **13.2** | Boundary Consolidation | boundary_groups_complete; boundaries_disjoint | boundary_reference_completeness; overlap_detected |
| **13.3** | Ceiling Consolidation | channel_max_verified; persona_ceilings_match_catalog; tenant_quotas_match_scaling | ceiling_consistency_rate; ceiling_violations |
| **13.4** | Schema Consolidation | seven_schemas_referenced; schema_paths_resolve | schema_reference_coverage; schema_validation_pass_rate |
| **13.5** | Pricing Consolidation | tier_index_model_verified; pricing_groups_consistent | pricing_consistency_rate; index_scope_coverage |
| **13.6** | Founder Console Integration | console_authoritative; command_operator_aol_wired | authoritative_reference_coverage; console_consistency_latency |

### Stage detail
- **13.1 System Consolidation (current).** The twelve systems are enumerated
  once in MUS and cross-locked to their phase registries.
- **13.2 Boundary Consolidation.** All six boundary groups defined once,
  verified disjoint, with the enforcement order (safety → isolation → legal →
  business → operator scope → founder go/no-go).
- **13.3 Ceiling Consolidation.** CHANNEL_MAX + per-persona + tenant quotas all
  consolidated and battery-matched to the catalog and scaling registry.
- **13.4 Schema Consolidation.** The seven canonical schemas indexed and their
  paths resolved.
- **13.5 Pricing Consolidation.** All five pricing groups unified under the
  tier-index model with no currency literals.
- **13.6 Founder Console Integration.** MUS becomes the authoritative reference
  the command system, operator mode, and AOL all resolve against.

### Cross-stage discipline
Real, verified gates at every stage; MUS is battery-validated end to end
(71/71). Authority stays disjoint and non-escalating; ceilings stay locked to
CHANNEL_MAX; MR07 stays human; pricing stays abstract tier-index with no
currency; MUS never contradicts an upstream phase — it is the single
authoritative consolidation for the Founder Console.

## 9. Verification & File Map
- **MUS battery:** 71/71 checks — schema-valid; authority map founder/operator/
  platform with legal/pricing founder-only, non-legal/non-financial
  operator-only, runtime/ceiling platform-only; twelve systems; six disjoint
  boundary groups with enforcement order; CHANNEL_MAX exact; all five persona
  ceilings match the commerce catalog and sit within CHANNEL_MAX; operator/AOL/
  platform ceilings all reference CHANNEL_MAX; tenant quotas match scaling;
  seven schemas; five pricing groups under unified_tier_index; console wiring
  (command=invocation, operator=executor, AOL=driver, authoritative=true);
  roadmap 13.1–13.6 with catalog gate at 13.3 and console-wiring gate at 13.6;
  cross-registry consistency (AOL/operator ceiling, command isolation); no
  secrets; no currency literals.
- **Artifacts:** `maya_identity/mus/mus.json` · `mus.schema.json` · blueprint
  `MAYA_UNIFIED_SPECIFICATION_BLUEPRINT.md`.
- **Chain:** MUS is the capstone of Phases 1–12 — one authoritative
  specification the Founder Console resolves every command, operator action,
  and AOL loop against, with every boundary, ceiling, schema, and pricing index
  defined once and cross-consistent.