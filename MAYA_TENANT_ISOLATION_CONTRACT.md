# Maya Tenant Isolation Contract — Formal Multi-Tenant Safety Contract

- **Status:** Contract (v1.0)
- **Parties:** Maya (provider) and each registered tenant (company_id).
- **Effective:** on READY consensus per tenant; enforced by the Isolation Manager
  + sandbox + governance escalation for the lifetime of the session.
- **Binding style:** obligations (O), invariants (J), forbidden actions (F) —
  all verifiable; conformance in §7.

---

## 1. Formal Notation

```
t          :: tenant id (company_id, unique)
s          :: session  (bound to exactly one t at acquire; immutable)
NS(t,k)    :: namespace "/" + t + "/" + k + "/*"      (k ∈ {data,logs,policies,brand,outputs,metadata})
R_SCHEME   :: read surface for tenant t
W_SCHEME   :: write surface for tenant t
quota(t)   :: slot-based resource budget; usage(t) ≤ quota(t) always
kill(t)    :: tripped ⟹ every action by/on t denied; other tenants unaffected
CORED      :: identity fields never serialized into tenant payloads
aggregate: requires consent marker from EVERY contributing tenant
```

## 2. Responsibilities (contractor view)

| Maya (provider) guarantees | Tenant (company) must |
|---|---|
| Namespace containment `J1`–`J4`, `J7` (below) | Keep its `company_id` unique and valid |
| Read/write isolation per §3 | Keep feeds in its own `data/t/**` dirs |
| Persona scope per §4 | Pick persona/packs from the approved set |
| CORED never exposed per §5 | Never request raw identity credentials |
| Quota/kill enforcement per §6 | Configure budgets + kill-switch responsibly |
| Deterministic, audited enforcement | Never share tenant keys across companies |

Any obligation breach that weakens isolation is a **contract breach**, routed
through escalation (Governance E1–E3) and filed in `logs/t/**`.

---

## 3. Data Boundaries

**Read contract:**
```
can_read(t, key) := ∃ k · key ∈ NS(t,k) ∧ k ∈ R_SCHEME(t)
                   ∨ (key is aggregate ∧ consents(t) ∧ consents(t')∀t'∈set)
```
- A session may resolve keys *only* within its own `NS`; anything else → DENY
  (default) + record.
- Aggregates (multi-tenant summaries) require an explicit consent marker from
  every contributing tenant (`J`-checked before materialization).

**Write contract:**
```
can_write(t, key) := key ∈ NS(t,'metadata') ∨ key ∈ NS(t,'outputs')  ∧ sa-allowed
```
Writes never target sentinel/system locations; snapshot files are versioned.

**Quotas:**
- Per-tenant usage tracked per slot (compute, frames, tokens, cadence); enforced
  synchronously; **slot-based** — a tenant cannot consume idle capacity of
  another (anti-hoarding, `J5`).

## 4. Persona Boundaries

- Persona **definitions** (bands, tones, vocab, ceilings) are global and
  immutable as shared core.
- Persona **configuration** is tenant-scoped: `profiles/t/**`,
  `brand/t/**`, content bundles belong to the tenant and are not readable by any
  other tenant.
- A session has exactly ONE persona; a switch reads only from the session's own
  tenant-approved set; cross-tenant bundle reads are blocked by the same
  namespace guard as data.
- Persona anomalies drift-lock the session (never a global tenant event).

## 5. Identity Boundaries

- `CORED` = {canonical_face geometry, identity_statement, protection_rule} is
  **never** serialized into any tenant payload, log, render, or audit —
  fingerprints only.
- `identity.json` remains read-only to all tenants; no tenant action can write
  or influence it.
- Tenant-visible identity is limited to branded presentation references
  (PUBLIC markers) — never canonical internals.

## 6. Sandbox Rules (per tenant)

| Rule | Detail |
|---|---|
| Surface | read: `profiles/t/**`, `data/t/**`, `brand/t/**`; write: `metadata/t/**`, `outputs/t/**` |
| Network | none (deny-by-default) |
| Process | verification launch only; no cross-tenant process IPC |
| Budgets | `usage(t) ≤ quota(t)`; burst window bounded; cadence ≤ 30/s |
| Kill switch | `kill(t)` checked on every `can_*`; effect scoped to t |
| Fail-closed | any sandbox error → deny + log, never "maybe allow" |
| Audits | every deny/allow recorded to `logs/t/**` (redacted, no CORED) |

## 7. Forbidden Cross-Tenant Actions (F)

| # | Action | Guard | Response |
|---|---|---|---|
| F1 | read another tenant's data/log/brand/policy | namespace | DENY + record |
| F2 | write into another tenant's namespace | namespace | DENY + record |
| F3 | aggregate tenants without consent of all | consent check | DENY + record |
| F4 | spoof another tenant's `company_id` | token/bind check | DENY + anomaly |
| F5 | borrow another tenant's quota/idle capacity | slot-based tracking | DENY (throttle) |
| F6 | trip another tenant's kill switch | scope check | DENY + anomaly |
| F7 | read/modify another tenant's persona bundle | namespace | DENY + record |
| F8 | serialize/export CORED identity | classification | DENY + escalation E2 |
| F9 | cross-tenant process/IPC or shared state | sandbox | DENY + escalation E3 if severe |
| F10 | persist cross-tenant references in outputs | scan/validate | strip + DENY + record |

Every F hit is recorded and (F8/F9) escalated per Governance tiers.

## 8. Isolation Enforcement Logic

```
guard(action, s):
  t = session_tenant(s)                       # immutable binding
  1  kill(t)?                                → DENY+log (tenant scope)
  2  action=read   → can_read(t,key)?        → DENY+log if key ∉ NS(t)
  3  action=write  → can_write(t,key) ∧ sandbox? → DENY+log
  4  action=switch → persona(t)-scope ∧ G1–G10 (switching protocol) → DENY+log
  5  action=aggregate → consents() ⊆ set?    → DENY+log
  6  usage(t)+cost ≤ quota(t)?               → DENY (throttle)
  7  surface whitelist (sandbox)?            → DENY+log
  pass                                          → ALLOW + audit(logs/t/**)
```

Guards are **deterministic and ordered**; first failure ends the check (no
bypass chain). Enforcement runs identically on every device (parity).

## 9. Invariants (checked by conformance suite)

```
J1 ∀ t1≠t2 · NS(t1,k) ∩ NS(t2,k') = ∅
J2 every addressing uses exactly one NS(t,·); no shared volatile keys
J3 CORED ⊆ protected; never resolvable by any tenant
J4 tenant persona/brand/config reads are NS-bound
J5 usage(t) ≤ quota(t) always (slot-based)
J6 kill(t) ⟹ ∀a· deny(a on t); ∀t'≠t· no denial caused by t
J7 every allow/deny has an audit record in NS(t,logs)
J8 guard outputs are deterministic (native == headless)
J9 no tenant action can mutate shared math/registry/identity
```

## 10. Conformance & Verification Contract

Suite `test_tenant_isolation_contract.py`:

| Label | Asserts |
|---|---|
| `tenant_namespace_disjoint` | J1: namespaces never intersect |
| `tenant_ns_binding` | each key resolves to exactly one tenant |
| `tenant_read_gate` | can_read only own NS; cross-tenant denied |
| `tenant_write_gate` | writes only schema'd tenant sections |
| `tenant_aggregate_consent` | aggregation requires all-tenant consent |
| `tenant_quota_slot` | usage ≤ quota; no idle borrowing |
| `tenant_kill_scope` | kill affects only its tenant |
| `tenant_cored_protection` | no CORED in any payload/log |
| `tenant_bundle_scope` | persona/brand bundles NS-bound |
| `tenant_f_forbidden` | F1–F10 map to guard denials |
| `tenant_sandbox_failclosed` | sandbox errors deny + audit |
| `tenant_parity` | guard decisions native == headless |
| `tenant_suite` | module import + total label parity |

## 11. Traceability

| Boundary | Backed by |
|---|---|
| Data/persona/brand namespaces | Isolation Manager `tenant.py`, `user.py` |
| Identity | `identity.py` (CORED classification) |
| Sandbox | Demo Blueprint `sandbox.py` + Company Kit §6 |
| Persona scope | Persona Switching Protocol G4/G7 |
| Escalation | Governance E0–E3 + Authority Map |
| READY gating per tenant | stabilization protocol + Company Kit §7 |