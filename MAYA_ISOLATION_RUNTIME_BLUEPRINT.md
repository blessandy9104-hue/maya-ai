# Maya Isolation Runtime Implementation Blueprint — Phase 7

- **Status:** implementation blueprint v1.0 · Phase 7 of the founder
  trajectory: the **single remaining critical-path dependency**. Backed by a
  validated isolation-runtime registry
  (`maya_identity/isolation/isolation_runtime.json`, 45/45 checks).
- **Non-negotiable gate this blueprint satisfies:** cloud runtime (Phase 5.3),
  marketplace (Phase 5.2), and read-only API hosting (Phase 5/6) open **only**
  after this runtime is implemented and the **full-system audit re-runs clean
  to a multi-tenant verdict.** Until then, the embed runtime is the only
  production host and multi-company scaling is domain-isolated.
- **Relation to precedent:** this is the implementation companion to the
  **Persona Isolation Manager** (`maya_runtime/isolation/*`, spec-only) and the
  **Tenant Isolation Contract** (`NS(t,k)`, F1–F10, J1–J9). It does not redesign
  them; it defines the concrete runnable runtime, its modules, the enforcement
  engine, integration points, and the 12-step verification suite that flips the
  audit verdict from `issues_detected` to READY.

---

## 1. Isolation Model

### 1.1 Tenant = domain-level namespace
A tenant is **not** a code boundary — it is a domain-level namespace. One
tenant = one domain deployment. A session is bound to exactly one tenant at
acquire and that binding is immutable for the session's life. No tenant
namespace overlaps any other (`J1`).

### 1.2 NS(t,k) namespace model (Phase 5)
```
NS(t,k) :: /t/k/*      k ∈ {data, logs, policies, brand, outputs, metadata}
```
Every read/write resolves within exactly one `NS(t,·)`; a cross-tenant leading
segment is a direct deny. Aggregates (multi-tenant summaries) require an
explicit consent marker from **every** contributing tenant (`J2`, consent
check before materialization).

### 1.3 Per-tenant identity boundaries
Session → tenant binding at acquire; data paths namespaced
`data/<t>/*`, `logs/<t>/*`, `brand/<t>/*`, `metadata/<t>/*`,
`outputs/<t>/*`. Policy/brand hooks are tenant-snapshot copies; edits apply to
the snapshot, never the registry (`J9`). Renders expose only the owning
session's own data; no session inherits a prior session's slices.

### 1.4 Per-tenant persona boundaries
Persona **definitions** (bands, tones, vocab, ceilings) are global and shared
read-only core. Persona **configuration** (`profiles/<t>/**`, `brand/<t>/**`)
is tenant-scoped and NS-bound. A session has exactly ONE persona; a switch
reads only from its own tenant-approved set; cross-tenant bundle reads are
blocked by the same namespace guard as data (`J4`). Persona anomalies
drift-lock the session, never a global tenant event.

### 1.5 Per-tenant embed-config boundaries
Each tenant's `embed_config.json` is per-tenant: origin allowlist, mode,
active persona, TTL, and quota are set per company and cannot bleed across
tenants. EMBEDPOST routing is exact-origin and the config is loaded only from
the tenant's own namespace.

## 2. Enforcement Engine

Policy is **deny-by-default**: anything not explicitly authorized is refused,
logged, and surfaced as an anomaly when it repeats (drift / cross-tenant /
identity probes).

### 2.1 Guard predicate (coordinator)
```
guard.can(request):
  request = (actor, action, resource, tenant_id, session_id)
  if not all fields present             -> DENY + log
  if not in_session(request)             -> DENY + log
  if not actor_in_tenant(actor, tenant)  -> DENY + log
  if not resource_in_tenant(resource)    -> DENY + log
  if not role_grants(action, resource)   -> DENY + log
  kill(tenant)?                          -> DENY + log (tenant scope)
  usage(tenant)+cost <= quota(tenant)?   -> DENY (throttle)
  if drift_pending(actor)                -> DENY (drift lock)
  if not surface_whitelisted(sandbox)    -> DENY + log
  else                                   -> ALLOW + audit
```
Guards are **deterministic and ordered**; first failure ends the check (no
bypass chain). `persona` switch, `tenant` namespace, and `tone` drift guards
are called by the coordinator in fixed order via `guard.can/acquire/switch/
record`.

### 2.2 Persona isolation (no cross-tenant persona access)
One active persona per session; construction copies only the active plan;
lookups are state-bound; `switch_allowed(frm, to, session)` returns False on
blocked/forced/uncertain switches and on non-verified runtime for constrained
tenants; a switch error leaves the prior persona active and raises an anomaly
— never a partial hybrid persona.

### 2.3 Identity isolation (no cross-tenant identity leakage)
`identity.json` fields classified `CORED / TENANT / PUBLIC`:
- `CORED` (canonical face geometry, identity statement, protection rule) →
  **never serialized** into any tenant payload, log, render, or audit —
  fingerprints only.
- `TENANT` → readable only through exact-token permission inside the owning
  tenant.
- `PUBLIC` → may surface via branded presentation references, never canonical
  form.
`identity.json` is read-only to all tenants (`J3`); no tenant action writes it.

### 2.4 Sandbox enforcement (no external APIs, no account, no egress)
Sandbox rules per tenant: surface = read `profiles/<t>/**`, `data/<t>/**`,
`brand/<t>/**`; write `metadata/<t>/**`, `outputs/<t>/**`. **Network: none
(deny-by-default).** **Process:** verification launch only, no cross-tenant
process IPC. **No external APIs**, **no account access**, **no network
egress**. Budgets: `usage(t) ≤ quota(t)`, burst bounded, cadence ≤ 30/s;
kill switch checked on every `can_*`, scoped to its tenant. **Fail-closed:**
any sandbox error → deny + log, never "maybe allow" (`J6`).

### 2.5 Message validation (postMessage envelope → type/direction pairing)
MSG.v1 envelope (6 types: `mount`, `ready`, `chat_in`, `chat_out`, `error`,
`status`) with **exact-origin check** and **type→direction pairing**: inbound
client messages must be client→Maya types, outbound Maya messages must be
Maya→client types; an outbound-direction type arriving inbound (or vice-versa)
is rejected by default. Envelopes are size-bounded; any undirected or
cross-tenant-addressed message is denied and logged.

## 3. Runtime Architecture

### 3.1 Module layout — `maya_runtime/isolation/` (8 modules, PROPOSED → built here)
| Module | Interface | Enforces |
|---|---|---|
| `__init__.py` | `guard.can/acquire/switch/record` — facade/coordinator | orchestration, audit |
| `persona.py` | `bound`, `in_band`, `switch_allowed` | persona boundaries |
| `role.py` | `grants`, `can(actor,cap,session)` | role isolation (no compose) |
| `tenant.py` | `tenant_ctx(company_id)` → NS handle | company/tenant isolation |
| `user.py` | `user_ctx(session)` → scoped slice | user isolation |
| `tone.py` | `envelope`, `drift(signal,env,ε)` | tone drift prevention |
| `identity.py` | `key_class`, `redact`, `token_access` | identity leakage prevention |
| `multi.py` | `limit/quota_state/kill_switch` | multi-tenant safety |

### 3.2 Isolation Coordinator
`guard.can(...)` orchestrates every enforcement hop in fixed, deterministic
order (missing fields → session/tenant → role → persona-switch → drift →
quota/kill → sandbox surface). It records outcomes to audit and routes
anomalies to the stabilization self-check feed. It never grants capability.

### 3.3 Isolation Registry
Namespaced registry mapping `tenant_id → NS(t,·)`, persona/role
configuration, and budgets. All lookups are `NS(t)`-bound; shared core persona
definitions are read-only references, never mutated.

### 3.4 Isolation Validator
Deterministic validator implementing `bound`, `quota`, `kill`, `drift`, and
`consent` checks. Pure functions — no RNG, no wall-clock, device-identical
(parity native == headless, `J8`).

### 3.5 Isolation Audit Hooks
Record **every** allow/deny to `NS(t,logs)`; deny-logs are redacted; identity
keys and CORED fields are never written to audit (`J7`). Repeating
drift/leak/tenant probes increment counters surfaced by self-check so
readiness sees isolation health.

### 3.6 Deterministic Fallback Behaviors
**Fail-closed:** any guard/sandbox/loader error → deny + calm/even neutral
output; isolation failure never degrades to "maybe allowed" (`J6`, `J9`).
Severe violation → clean halt with no partial state. Drift neutralizes to
neutral, locks the actor until `drift_reset(session)`, and records the anomaly.

## 4. Integration Points

| Surface | How isolation binds |
|---|---|
| **Embed runtime** | EMBEDPOST exact-origin, per-tenant `embed_config`, message type/direction pairing (§2.5) |
| **Persona loader** | `persona.py` bound/switch gates; persona config resolved only inside the tenant's `NS` |
| **Identity profile loader** | `identity.py` classification; CORED redacted to fingerprints at every load |
| **Cloud runtime (5.3)** | per-tenant `NS(t,k)` namespaces, `/embed/<tenant-slug>`, budgets, kill switch; **gated on this runtime + audit** |
| **Marketplace (5.2)** | installed personas verified against persona-boundary + governance checks before tenant mount |
| **Read-only API (5.5)** | GET-only scopes, opaque read tokens, sandbox surface whitelist, no account/memory/egress |

The embed runtime keeps working today (it already enforces per-config
isolation at the domain level). The cloud runtime, marketplace, and API simply
**gain** the isolation runtime as their enforcement core the moment the audit
passes.

## 5. Verification Pipeline

### 5.1 12-step isolation verification suite
| # | Step | Asserts |
|---|---|---|
| 1 | `module_import` | all 8 modules import cleanly; facade present |
| 2 | `deny_by_default` | empty/partial request denied; no exception path permits |
| 3 | `tenant_namespace_disjoint` | J1: namespaces never intersect |
| 4 | `tenant_read_write_gate` | can_read/write only own NS; cross-tenant denied |
| 5 | `persona_boundary` | cross-band / cross-tenant persona lookup denied |
| 6 | `persona_switch_gate` | blocked/forced/uncertain switches denied; monotone audit |
| 7 | `identity_cored_redact` | CORED absent from payloads/logs; fingerprints only |
| 8 | `identity_token_access` | PUBLIC accessible; TENANT token-gated; CORED denied |
| 9 | `sandbox_surface_whitelist` | reads/writes outside surface denied; no egress/IPC/account |
| 10 | `sandbox_fail_closed` | sandbox error → deny + audit, never allow |
| 11 | `message_type_direction_pairing` | wrong-type/wrong-direction envelope rejected; exact origin |
| 12 | `parity_native_headless` | guard decisions identical native == headless |

### 5.2 Audit-hook checks & regression
- Every step asserts its audit record exists (`NS(t,logs)`) and that deny
  records are redacted and CORED-free.
- Regression: re-run parity native==headless; re-run the **existing verification
  sweep** (18 suites) unchanged; confirm prior single-tenant readiness is
  preserved (isolation must not regress the verified core).

### 5.3 Boundary test groups
- **Persona-boundary:** cross-tenant band/vocab/bundle access denied; switch
  gates; no partial hybrid.
- **Tenant-boundary:** J1/J2/J4 namespaces; F1–F10 map to guard denials;
  quota slot; kill scope; aggregate consent.
- **Sandbox-boundary:** surface whitelist; no network/account/IPC; fail-closed;
  parity.

### 5.4 Audit gate (what "clean" means)
The full-system audit must re-run to a **multi-tenant READY** verdict:
sweep 18/18 clean, all battery suites pass, the isolation/sandbox PROPOSED
modules now EXISTING and covered by the 12-step suite, and zero isolation
anomaly categories. Only then do the phase gates in the Phase-6 roadmap (6.4
cloud, marketplace listing, API hosting) open.

## 6. File Map & Chain

- **Isolation battery:** 45/45 checks — schema-valid; tenant = domain
  namespace; `NS(t,k)` model with six resource kinds; four boundaries
  (tenant_identity, persona, embed_config, namespace); deny-by-default engine;
  persona/identity isolation flags; six sandbox rules incl. no egress/account/
  external-API and fail-closed; MSG.v1 message validation with six types and
  direction pairing; eight isolation modules; coordinator `guard.can`;
  validator covering bound/quota/kill/drift/consent; full audit hooks;
  deterministic fallback; six integration points; 12-step suite with three
  boundary groups and native/headless parity regression; no secret literals.
- **Artifacts:** `maya_identity/isolation/isolation_runtime.json` ·
  `isolation_runtime.schema.json` · blueprint `MAYA_ISOLATION_RUNTIME_BLUEPRINT.md`.
- **Chain:** Isolation Manager spec → Tenant Isolation Contract → Phase-7
  registry → this blueprint → full-system audit (multi-tenant verdict) →
  Phase-6 cloud/marketplace/API gates. **This is the critical path:** nothing
  in cloud/marketplace/API hosting proceeds until this runtime is built and its
  audit passes.