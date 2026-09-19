# Maya Runtime Authority Map — Governance Specification

- **Status:** Specification (v1.0) — governance diagram + ruleset
- **Model:** six authorities with **separation of powers**. No single authority
  may mutate identity, math, safety, or the shared registries; readiness is
  **consensus-issued**, never self-declared.
- **Principles:** (1) deny-by-default, (2) separation of powers,
  (3) consensus readiness, (4) immutable core.

---

## 1. Governance Diagram

```
                        ┌─────────────────────────────────────────┐
                        │  MAYA RUNTIME AUTHORITY                 │  owns canonical runtime:
                        │  math · world · expression · render     │  execute, produce, consume
                        └───────────────┬─────────────────────────┘
                                        │  commands only within sandbox verdict
                                        v
        ┌───────────────────────────────┴───────────────────────────────┐
        │                        SANDBOX AUTHORITY                      │
        │  deny-by-default · whitelist · quotas · budgets · halt        │
        └───────┬────────────────┬────────────────┬────────────────────┘
                │                │                │
                v                v                v
   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
   │ TENANT AUTHORITY│  │  USER AUTHORITY │  │ PERSONA AUTHORITY│
   │ tenant binding  │  │ session + own   │  │ persona activation│
   │ policy/brand/   │  │ data + consent  │  │ tone/vocab/ceilings│
   │ quota/kill      │  │ markers         │  │ drift lock/fallback│
   └─────────────────┘  └─────────────────┘  └────────┬─────────┘
                                                      │  (consensus gate)
                                                      v
                              ┌─────────────────────────────────────────┐
                              │          READINESS AUTHORITY            │
                              │ external sweep + launch + internal      │
                              │ self-check → READY/revoke (never self)  │
                              └─────────────────────────────────────────┘

  Governance direction:  runtime ←─ sandbox ←─ tenants/users/personas
  Readiness: receives verdicts from verification tooling + self-check (read-only)
```

Rule: higher authorities bound lower ones; the sandbox never loosens itself;
readiness is the only issuer of READY and its decision cannot be overridden by
any other authority.

---

## 2. Authority Definitions

### 2.1 Maya Runtime Authority
**Mandate:** operate the canonical runtime (math engine, world model, safety
layer, expression engine, rendering loop) for the active session.

**Powers:**
- Execute approved computation deterministically; produce `RenderFrame`,
  `MarketGate`, decision records.
- Consume whitelisted inputs (profiles, `data/<company_id>/**`, brand).
- Maintain in-session world state and pattern alignment.

**Boundaries:** cannot create goals; cannot mutate `identity.json`, registries,
or safety thresholds; cannot exceed `CHANNEL_MAX`; cannot serialize CORED
identity; cannot issue READY.

**Prohibited actions:**
- Creating or editing goals/architecture/limits.
- Arbitrary filesystem writes (outside `metadata/**`).
- Network egress or inbound control.
- Self-evolution / self-modification.
- Ignoring a sandbox deny verdict.

### 2.2 Tenant Authority (per-company)
**Mandate:** configure the company's experience within validated fields.

**Powers:**
- Bind sessions to its `company_id`; supply policy/catalog/schedule feeds;
  set brand constants via `override_slot` (validated writes).
- Choose persona from the approved selection set; consume its own outputs/audits.
- Trigger its own kill switch.

**Boundaries:** cannot read another tenant; cannot raise its quota beyond
allocation; cannot touch shared registries or identity; cannot disable safety.

**Prohibited actions:**
- Cross-tenant reads/aggregation without all-tenant consent.
- Quota override or slot violation.
- Mutating base registries or persona definitions.
- Removing `safety_monitoring`/`world_stability` from allowed behaviors.
- Altering shared math or protocol constants.

### 2.3 User Authority (end-user, per session)
**Mandate:** use the service in one session within tenant policy.

**Powers:**
- Start/end sessions; provide input; request persona/role switches (gated);
  read/write own session data; grant consent markers for aggregation.

**Boundaries:** no visibility into other users; no tenant policy edits; no
capability expansion; no identity/CORED access.

**Prohibited actions:**
- Cross-user reads or session carry-over.
- Escalation beyond role grants.
- Tenant policy edits or brand mutation.
- Accessing CORED identity or raw geometry.

### 2.4 Sandbox Authority
**Mandate:** enforce the security boundary at every action. Deny-by-default,
owner of the whitelist and resources.

**Powers:**
- Allow/deny every action against the surface table; enforce quotas/budgets/
  cadence; clean halt; record violations to the self-check engine.

**Boundaries:** cannot grant beyond the whitelist; cannot weaken itself; not
influenced by persona, user, or tenant preference.

**Prohibited actions:**
- Overriding its own deny-list at runtime.
- Opening network or process escape paths.
- Permitting identity/CORED export.
- Suspending enforcement during a session.

### 2.5 Persona Authority
**Mandate:** govern which persona is active and keep all expression inside its
bands.

**Powers:**
- Activate personas from approved bundles; apply tone/vocabulary/ceilings;
  enforce step caps and monotone transitions; block unsafe switches; drift-lock;
  fail-closed reset to `calm/even`.

**Boundaries:** cannot alter persona definitions or registries; cannot vary by
device; cannot transport channels outside the persona band.

**Prohibited actions:**
- Creating/editing personas or registry enums.
- Runtime band widening.
- Forcing risky registers (e.g., playful during a crisis) — blocked by context
  gates.
- Drift masking (suppressing bounded-drift anomalies).

### 2.6 Readiness Authority
**Mandate:** issue and revoke READY state via consensus of **external
verification** (full sweep + controlled launch parity) and **internal
self-check** (7 subsystems). Maya is never a decision-maker here.

**Powers:**
- Grant READY (external clean ∧ internal stable); revoke on anomaly; record
  verdicts; expose `info/status.json` readiness.

**Boundaries:** cannot be overridden by tenant/user/persona/runtime; an unclean
report can never be READY; no hidden or partial readiness.

**Prohibited actions:**
- Self-certification (a Maya process declaring itself ready).
- Accepting a dirty sweep/launch as clean.
- Per-tenant override of global readiness.
- Issuing readiness in quiet/edge cases without full consensus.

---

## 3. Request Decision Flow (who checks what)

```
 request: user asks to X
  A. Sandbox:   surface allow? quota ok? budget ok?        destroy → DENY+log
  B. User:      session valid? own-scope? consent needed?  → DENY
  C. Tenant:    tenant bound? namespace ok? kill-switch ok?→ DENY
  D. Runtime:   action within approved computation?        → DENY
  E. Persona:   register/ceiling/drift/context-safe?       → DENY + drift lock
  F. Readiness: if X requires verified runtime → READY?    → DENY (blocked)
  all pass ──► ALLOW + audit (redacted, no identity keys)
```

Any single DENY at any authority blocks the request; there is no bypass chain.

## 4. Boundary Matrix (who cannot cross what)

| From \\ Into | Identity/CORED | Math/ceilings | Registries | Other tenant | Other user | Network | READY |
|---|---|---|---|---|---|---|---|
| Runtime | ✗ | ✗ (consume) | ✗ (consume) | ✗ | ✗ | ✗ | ✗ |
| Tenant | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ |
| User | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Sandbox | ✗ export | — read | ✗ mutate | isolates | isolates | ✗ | — |
| Persona | ✗ | ✗ widen | ✗ edit | — | — | ✗ | ✗ |
| Readiness | — | observes | ✗ | — | — | ✗ | issues |

`✗` = prohibited cross; `consumes/observes` = read-only by design.

## 5. Emergency & Override Hierarchy

| Event | Owner | Action | Scope |
|---|---|---|---|
| Tenant abuse | Tenant Authority (kill switch) | deny tenant actions only | one tenant |
| Resource starvation | Sandbox Authority | quotas, budgets, throttle | affected tenants |
| Drift accumulation | Persona Authority | drift lock + reset to calm/even | session |
| Self-check anomaly | Readiness Authority | revoke READY → degraded | runtime-wide |
| Severe sandbox violation | Sandbox Authority | clean halt (no partial state) | global bound |
| Real-time danger signal | SAFETY_MONITOR | neutralize frame + audit | frame/session |

Escalation never loosens a lower gate; emergencies only tighten.

## 6. Verification Contract

New suite `test_runtime_authority_map.py`:

| Label | Asserts |
|---|---|
| `authority_runtime_powers` | runtime compute allowed; goal creation denied |
| `authority_sandbox_verdict` | sandbox verdict binds runtime/user/tenant/persona |
| `authority_tenant_scope` | tenant reads own namespaces only; kill switch self-scoped |
| `authority_user_scope` | user own-session only; no carry-over |
| `authority_persona_gate` | unsafe switch blocked; drift lock engages; fallback calm/even |
| `authority_readiness_consensus` | READY only on external-clean ∧ internal-stable |
| `authority_no_self_declare` | Maya process cannot issue READY to itself |
| `authority_boundary_matrix` | every ✗ in §4 enforced (identity/math/registry/network) |
| `authority_deny_fast` | first authority denial short-circuits (no later allow) |
| `authority_override_hierarchy` | emergencies tighten, never loosen; scope honored |
| `authority_parity` | decisions identical native == headless |
| `authority_suite` | module import + total label parity |

---

## 7. Traceability

| Authority | Backed by |
|---|---|
| Runtime | Blueprint components (§2.1–2.10) |
| Tenant | Isolation Manager `tenant.py` + Company Integration Kit §8 |
| User | Isolation Manager `user.py` |
| Sandbox | Demo Blueprint §2.9 `sandbox.py` + Company Kit §6 |
| Persona | Persona Layer (switching/safety) + Expression L6 |
| Readiness | Stabilization protocol v2.0 + `verification/*` + `readiness.self_check` |