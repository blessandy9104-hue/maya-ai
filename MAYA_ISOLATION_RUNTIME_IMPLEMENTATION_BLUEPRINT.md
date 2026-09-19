# Maya Isolation Runtime Implementation — Phase 7 IR

- **Status:** implementation blueprint v1.0 · Phase 7 IR (implementation). This
  is the **final missing component required for platform launch**: a concrete,
  fail-closed isolation runtime that enforces **every MUS boundary**. Backed by
  an implementation registry
  (`maya_identity/isolation/impl/ir_impl.json`, 64/64 checks) that is
  cross-locked to the Phase 7 base registry (`isolation_runtime.json`), the MUS
  unified reference, and the scaling registry.
- **Preconditions:** Phases 1–6 and 8–13 complete and validated. The only
  remaining gap before multi-tenant/cloud/marketplace/API can open is this
  isolation runtime. Everything downstream (operator, command, AOL, MUS,
  launch) already assumes it.
- **Consolidation posture:** the IR is the concrete enforcement of the MUS
  boundary order — `safety → isolation → legal → business → operator →
  founder.` It upholds the deny-by-default policy, the CHANNEL_MAX isolation
  ceilings, and the operator-only/founder-only authority caps. When this
  blueprint is implemented and the re-audit is clean, the platform launches.

---

## 1. Isolation Runtime Definition

### 1.1 Purpose
Provide a single, deterministic, fail-closed guard around every tenant,
persona, identity, message, and surface. It is the mechanism that makes
isolation a *concrete* property rather than a policy in a document: any action
not explicitly allowed inside its namespace is denied. With the IR live, the
platform can open multi-tenant cloud, marketplace, and API surfaces; without
it, the platform stays gated.

### 1.2 Enforcement model (deny-by-default)
`enforcement: deny_by_default`. Nothing is reachable unless the IR explicitly
permits it. This mirrors the base registry's enforcement policy, its six
sandbox rules (`no_external_api, no_account_access, no_network_egress,
no_process_ipc, surface_whitelist, fail_closed`), and its `guard.can`
coordinator role. The IR coordinates the guard: it orders guard calls and
denies by default.

### 1.3 MUS boundary integration
`mus_boundary_order: [safety, isolation, legal, business, operator, founder]`.
Every incoming action is classified against the boundary order and handled at
the first matching, mandatory step:

| Order | Boundary | IR behavior |
|---|---|---|
| 1 | **safety** | financial/medical/legal safety → **deny first**, escalate to founder; never auto-decided |
| 2 | **isolation** | deny-by-default namespace/tenant/persona/identity guard; any boundary hit denies |
| 3 | **legal** | contracts/payments/liabilities → escalate founder; no IR auto-approval |
| 4 | **business** | pricing/negotiation → escalate founder |
| 5 | **operator** | non-legal/non-financial ops → IR executes if and only if within operator authority and within ceilings |
| 6 | **founder** | authorized go/no-go override at the operator-to-founder seam, still audit-logged and never bypassing safety/isolation/legal |

The IR enforces this order on every surface; safety and isolation are checked
before any legal/business/operator/founder decision, so nothing can bypass the
guard.

## 2. Isolation Surfaces
Seven surfaces are isolated under the IR:

| Surface | Isolation contract |
|---|---|
| **persona** | tenant-scoped sealing; core shared read-only; cross-tenant personas denied |
| **tenant** | disjoint namespaces; no cross-tenant read or write |
| **creator** | creator content isolated per-tenant; no cross-tenant brand/asset access |
| **marketplace** | listings validated pre-review; creator/tenant boundaries enforced |
| **cloud_runtime** | per-tenant NS(t,k), budgets, quotas enforced at runtime |
| **api** | read-only, boundary-checked before any call executes |
| **embed_runtime** | postMessage v1 envelope, exact-origin, direction-paired, ≤16KB |

All seven are wired to the same guard; none carries its own policy.

## 3. Isolation Rules

### 3.1 Message validation
`postmessage_v1` envelope, validated on: allowed types (mount, ready, chat_in,
chat_out, error, status), exact-origin check, direction pairing (in/out pairs),
and the ≤16KB size limit. Any malformed or misdirected message is dropped.

### 3.2 Identity sealing
`cored_never_serialized`, `readonly_to_tenants`, `fingerprint_only` — identity
CORED is never written to any serialized/log surface; tenants only ever see a
fingerprint, never the core identity, and identity is read-only to tenants.

### 3.3 Persona sealing
`tenant_scoped`, `cross_tenant_denied`, `core_shared_readonly` — a persona is
bound to its tenant; it cannot reach another tenant; the shared core is
read-only.

### 3.4 Tenant sealing
`namespaces_disjoint`, `no_cross_tenant_read`, `no_cross_tenant_write` — each
tenant lives in its own namespace; cross-tenant reads and writes are denied.

### 3.5 Namespace sealing
`NS(t,k) :: /t/k/*` with resource kinds `data, logs, policies, brand, outputs,
metadata`. All six resource kinds are namespaced and disjoint across tenants.

### 3.6 Cross-tenant denial
Any attempt to reach outside the tenant namespace is denied (fail-closed).

### 3.7 Cross-persona denial
A persona cannot invoke or read another persona that is outside its tenant
scope; denied.

### 3.8 Cross-identity denial
`identity_thread_bound` + `no_identity_splice` — conversations/actions are
bound to their identity thread; identities cannot be spliced or crossed.

### 3.9 Fail-closed behavior
On any ambiguity, error, or boundary hit, the IR **denies** (never "maybe
allows"), emits a neutral output, and leaves no partial state.

## 4. Isolation Runtime Architecture

### 4.1 Isolation validator
Deterministic checks: **bound** (namespace/tenant bound), **quota** (cpu/embed/
calls/TTL), **kill_switch**, **drift**, and **consent**. Output is identical on
parity native == headless.

### 4.2 Isolation router
`declarative` + `boundary_ordered` + `no_escape`. Routes every action through
the MUS boundary order with a declarative table of handlers; no path escapes
the guard.

### 4.3 Isolation executor
`isolation_guarded` + `operator_bound` + `namespaced`. Executes operator-scoped
operations inside the tenant namespace only, guarded by the IR at every step.

### 4.4 Isolation audit hooks
`record_all`, `redact_deny`, `cored_never_logged`, `anomaly_feed`. Every run
and every denial is recorded founder-visibly; denials are redacted; CORED never
enters the log; anomalies feed the console.

### 4.5 Fallback behaviors
- **deny**: fail_closed + neutral_output + no_partial_state
- **retry-bounded**: bounded, with cooldown_on_escalate, deterministic
- **escalate-founder**: legal → founder, business → founder, ambiguous → founder

No IR path auto-resolves an out-of-scope or ambiguous case; it escalates.

## 5. Integration Points

| Surface | IR binding |
|---|---|
| **runtime** | guard orders calls (`guard_orders_calls`) — IR coordinates the guard |
| **persona engine** | `tenant_scoped_seal` — personas load and run sealed to tenant |
| **operator engine** | `executor_bound` — the IR bounds every operator task |
| **command system** | `isolation_integration_deny_by_default` — commands route through deny-by-default |
| **AOL loops** | `isolation_guarded_executor` — every loop action is isolation-guarded |
| **platform surfaces** | studio, marketplace, cloud_runtime, api — all wired to the guard |
| **MUS reference** | `authoritative` — the IR resolves against MUS for boundaries/ceilings |

The IR is the shared guard the runtime orders, the persona engine seals against,
the operator engine is bound by, the command system routes through, the AOL
executes under, and the platform surfaces all obey.

## 6. Safety & Boundaries
The IR enforces all MUS boundary groups, disjoint and in order:

| Group | Contents | IR behavior |
|---|---|---|
| **Legal boundaries** | contracts · payments · liabilities | escalate to founder; never auto-approve |
| **Business boundaries** | pricing · negotiation | escalate to founder |
| **Safety boundaries** | financial · medical · legal | deny first, escalate; never auto-decided |
| **Operator-only boundaries** | `nonlegal_nonfinancial` | execute only within operator authority |
| **Founder-only boundaries** | `legal_business_go_no_go` | only authorized overrides; still audited, never bypass safety/isolation/legal |
| **Isolation ceilings** | `CHANNEL_MAX` | every output validator locks to CHANNEL_MAX |

The IR cannot grant legal authority, alter tenant boundaries at will, or exceed
CHANNEL_MAX. It is the enforcement layer, not a decision layer.

## 7. Phase 7 Roadmap

| Stage | Name | Gates | KPIs |
|---|---|---|---|
| **7.1** | Isolation Rules | all_nine_rules_implemented; rules_verification_suite | rules_coverage; rules_verification_pass |
| **7.2** | Isolation Validator | validator_deterministic; bound_quota_kill_drift_consent_checks_live | validator_determinism; bound_check_pass_rate |
| **7.3** | Isolation Router | router_declarative; boundary_ordered_routing; no_escape_verified | route_correctness; escape_attempts_blocked |
| **7.4** | Isolation Executor | executor_isolation_guarded; executor_operator_bound; namespaced_execution | executor_guard_rate; cross_tenant_leaks |
| **7.5** | Platform Integration | all_seven_surfaces_wired; mus_boundary_order_enforced; parity_native_headless | surface_integration_coverage; boundary_order_violations |
| **7.6** | Launch Gate | re_audit_clean; isolation_ceilings_match_channel_max; platform_launch_authorized | reaudit_pass; multi_tenant_readiness; isolation_ceiling_consistency |

### Stage detail
- **7.1 Isolation Rules (current).** Implement the nine rules — message
  validation, identity/persona/tenant/namespace sealing, cross-tenant/cross-
  persona/cross-identity denial, fail-closed — and pass the 12-step rules
  verification suite from the base registry.
- **7.2 Isolation Validator.** Deterministic validator live with bound, quota,
  kill_switch, drift, and consent checks.
- **7.3 Isolation Router.** Declarative, boundary-ordered routing proven to
  block every escape attempt.
- **7.4 Isolation Executor.** Namespaced, isolation-guarded, operator-bound
  executor with zero cross-tenant leaks.
- **7.5 Platform Integration.** All seven surfaces wired; the MUS boundary
  order enforced; native==headless parity preserved.
- **7.6 Launch Gate.** Re-audit clean, isolation ceilings identical to
  CHANNEL_MAX, and platform launch authorized — the moment the platform opens.

### Cross-stage discipline
Real, verified gates at every stage; the deny-by-default policy and the MUS
boundary order are fixed from 7.1 onward and re-verified at 7.5; CHANNEL_MAX
matching is re-verified at 7.6; identity CORED is never logged at any stage;
authority caps (operator-only, founder-only) are enforced at every step.

## 8. Verification & File Map
- **IR implementation battery:** 64/64 checks — schema-valid; deny-by-default;
  exact 6-step MUS boundary order; seven isolation surfaces; the nine rules
  (message validation with exact-origin+direction-pairing, identity sealing
  with cored-never-serialized, persona sealing, tenant sealing, namespace
  formula + six resource kinds, cross-tenant/cross-persona/cross-identity
  denial, fail-closed); validator checks = bound/quota/kill_switch/drift/
  consent + deterministic; router declarative/boundary-ordered/no-escape;
  executor isolation-guarded/operator-bound/namespaced; audit record-all/
  redact-deny/cored-never-logged/anomaly-feed; fallback = deny/retry-bounded/
  escalate-founder; integration to runtime/persona/operator/command/AOL/
  platform-surfaces/MUS; legal/business/safety disjoint; operator-only
  nonlegal-nonfinancial; founder-only legal-business-go-no-go; isolation
  ceilings = CHANNEL_MAX; distributed backlog; roadmap 7.1–7.6 with
  boundary-order gate at 7.5 and launch gate at 7.6; no secrets.
- **Cross-locks:** base isolation registry (deny-by-default, sandbox
  enforcement, guard.can, 12-step suite), MUS (boundary order, CHANNEL_MAX),
  scaling registry (tenant quota).
- **Artifacts:** `maya_identity/isolation/impl/ir_impl.json` ·
  `ir_impl.schema.json` · blueprint `MAYA_ISOLATION_RUNTIME_IMPLEMENTATION_BLUEPRINT.md`.
- **Chain:** this is the final missing component. Implementing the nine rules,
  the deterministic validator/router/executor, the seven surface integrations,
  and passing the clean re-audit at 7.6 **unlocks platform launch** — making
  the Phase 8 multi-tenant cloud, marketplace, API, and the entire downstream
  chain (operator, command, AOL, MUS, Founder Console) genuinely live under one
  fail-closed guard.