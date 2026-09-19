# Maya Persona Isolation Manager — Architecture Specification

- **Status:** Specification (v1.0) — strict isolation architecture + enforcement logic
- **Package (PROPOSED):** `maya_runtime/isolation/`
- **Policy:** **deny-by-default** — everything a request does not explicitly
  authorize is refused, logged, and (where relevant) raised to the
  stabilization/self-check engine as an anomaly.
- **Scope:** enforces *boundaries*, *tenancy*, *drift*, and *leakage* rules
  around personas, roles, companies, users, tone, and identity. It never grants
  capability, never edits identity, never touches math/world/safety algebra.

---

## 1. Threat Model (what isolation prevents)

| # | Threat | Vector | Prevented by |
|---|---|---|---|
| T1 | persona bleed | A persona reads/gains another's band or vocab | persona boundaries |
| T2 | role privilege escalation | session reaches caps unassigned to its role | role isolation |
| T3 | cross-company leakage | tenant A reads tenant B logs/policy/brand | company isolation |
| T4 | cross-user leakage | user A sees user B memory/history/state | user isolation |
| T5 | tone drift | register/amplitude leaves the active persona's band | tone drift prevention |
| T6 | identity leakage | canonical identity/face/tagline exposed cross-tenant | identity leakage prevention |
| T7 | multi-tenant abuse | one tenant starving/altering others | multi-tenant safety rules |

---

## 2. Isolation Domains (boundaries)

| Domain | Boundary = | Boundary ≠ |
|---|---|---|
| **Persona** | active `PersonaPlan` tuple: id, band, tone, vocab, constraints, directives | any other persona's plan at any depth |
| **Role** | session-bound role → capability grant (subset of the 11 caps / 8 roles) | inherited/union grants of other roles |
| **Company (tenant)** | tenant key → company id + policy + brand + namespaced metadata | any other tenant's keys/records |
| **User** | session owner → user-scoped memory, world snapshots, learning history, prefs | other users' sessions, collated views |
| **Tone** | active persona's tone `ToneTargets` inside envelope `[lo,hi]` | any excursion `> ε` from envelope |
| **Identity** | canonical `identity.json` (cored) | all derived/approximate copies, tenant exposure |

Every domain is a *namespace* + *accessor*: isolation means the accessor resolves
only within its namespace; `deny-by-default` means any unresolved key → refusal.

---

## 3. Module Map (all PROPOSED)

| Module | Interface | Enforces |
|---|---|---|
| `isolation/__init__.py` | `guard.can(request)`, `guard.acquire/switch/record` — facade | orchestration, audit |
| `isolation/persona.py` | `bound(persona)`, `in_band(signal, persona)`, `switch_allowed(frm, to, session)` | persona boundaries |
| `isolation/role.py` | `grants(role)`, `can(actor, capability, session)` | role isolation |
| `isolation/tenant.py` | `tenant_ctx(company_id)` → namespaced handle | company isolation |
| `isolation/user.py` | `user_ctx(session)` → scoped memory/world slice | user isolation |
| `isolation/tone.py` | `envelope(persona)`, `drift(signal, env, ε)` | tone drift prevention |
| `isolation/identity.py` | `key_class(key)`, `redact(payload)`, `token_access(key)` | identity leakage prevention |
| `isolation/multi.py` | `limit(tenant)`, `quota_state(tenant)`, `kill_switch(tenant)` | multi-tenant safety |

---

## 4. Enforcement Primitives

### 4.1 Access Control Vector
```
request = (actor, action, resource, tenant_id, session_id)
```
- `actor` = persona session | role | user | system.
- `resource` = persona§band | cap§id | user§memory | tenant§policy | identity§cored | log§span …
- `tenant_id` and `session_id` are mandatory; missing → auto-deny.

### 4.2 Guard predicate (deny-by-default)
```
can(request):
  if not all fields present              -> DENY
  if not in_session(request)              -> DENY
  if not actor_in_tenant(actor, tenant)   -> DENY
  if not resource_in_tenant(resource)     -> DENY
  if not role_grants(action, resource)    -> DENY
  if not tenant_quota_ok(tenant)          -> DENY (throttle)
  if drift_pending(actor)                 -> DENY (drift lock)
  else                                    -> ALLOW + audit(request)
```
Any DENY is written to the tenant's audit span **and** to the self-check
anomaly feed when it repeats (drift / cross-tenant / identity probes).

### 4.3 Audit rule
- Logs carry `(tenant_id, session_id, action, outcome)` with no actor PII
  beyond the session id; identity keys are never written to audit.
- Allow-logs may name the resource; deny-logs always redact contents.

---

## 5. Enforcement Logic per Domain

### 5.1 Persona boundaries (`persona.py`)
- One active persona per session: `SESSION.state.persona == PersonaPlan`.
- Construction copies only the active plan; all lookups are `state-bound`.
- `bound(persona)` asserts: band ⊆ ceilings, vocab id exists, constraints known.
- `switch_allowed(frm, to, session)`:
  - `False` if `street`/`therapy` context prevents (per persona safety rules),
  - `False` if not `verified_runtime` for constrained tenant,
  - else monotone transition via `stable_exp_smooth` (no teleport),
  - on success → audit `switch frm→to (tenant, reason)`.
- A switch error leaves prior persona active and raises an anomaly, never a
  partial hybrid persona.

### 5.2 Role isolation (`role.py`)
- `grants(role)` returns a frozen capability subset; grants compose **never**.
- `can(actor, capability, session)` enforces `capability ∈ grants(session.role)`.
- Elevated actions (identity access, tenant policy write) require system actor;
  no role grant can issue them (`admin`-role does not exist by design).

### 5.3 Company isolation (`tenant.py`)
- Every session binds exactly one `company_id` at acquire; binding is immutable
  for the session's life.
- Data paths are namespaced: `metadata/<company_id>/*`,
  `logs/<company_id>/*`, `brand/<company_id>/*`. Cross-tenant literal leading
  segment is a direct deny.
- Policy and brand hooks are tenant-snapshot copies; edits apply to the
  snapshot, never the registry.

### 5.4 User isolation (`user.py`)
- All memories, world snapshots, learning histories are keyed by
  `session_id`/`user_key` inside the tenant namespace.
- Renders may expose the owning user's own data only; collated/anonymized
  aggregates require the owning user's explicit consent marker.
- Session never inherits a previous session's slices (no carry-over).

### 5.5 Tone drift prevention (`tone.py`)
```
envelope(persona) = persona.band                # frozen [lo,hi] per channel
drift(signal, env, ε):
  if any(signal[ch] < env.lo[ch] - ε or signal[ch] > env.hi[ch] + ε):
      return (True, ch)                          # drift detected
  return (False, None)

response on drift:
  1. suppress the excursion  -> keep frames inside envelope
  2. snap presenters to neutral (calm/even)   [deterministic]
  3. raise anomaly -> stabilization self_check (drift counter++)
  4. lock actor until drift_reset(session) clears
```
- `ε = 1e-9` (matches `POSE_EPSILON` convention). No threshold gymnastics.
- Drift is a *guard*, not a clamp: it blocks, then neutralizes, then records.
- Drift telemetry is deterministic and device-identical.

### 5.6 Identity leakage prevention (`identity.py`)
- `identity.json` fields are classified:
  `CORED` (canonical_face geometry, identity_statement, protection_rule) —
  **never serialized** into any tenant payload, render, or audit;
  `TENANT` (role/tagline-derived register) — readable only through exact-token
  permission inside the owning tenant; `PUBLIC` (name, version marker) — may
  surface, never in full canonical form.
- `redact(payload)` strips/rewrites CORED fields (geometry → hashed fingerprint).
- `token_access(key)` succeeds only for PUBLIC in any tenant; TENANT with
  session token inside owner tenant; CORED → always deny (system bootstrap only).
- Fingerprints are used for drift/consistency checks, never as content.

### 5.7 Multi-tenant safety rules (`multi.py`)
| Rule | Enforcement |
|---|---|
| Tenant namespace | all reads/writes scoped `/tenant_id/`; unmatched → DELETE guard: deny + log |
| Quota / burst | per-tenant budget `budgets[tenant]`; exceeded → throttle (deny-with-retry), recorded |
| Isolation under load | no tenant may exceed its slice even if global idle (slot-based, not opportunistic) |
| Degraded mode | constrained tenants require `verified_runtime` (stabilization) |
| Kill switch | per-tenant flag checked on every `can()`; tripped → all tenant actions deny, log, keep other tenants untouched |
| Cross-tenant hoarding | rename/aggregate denied unless consent markers present for each source tenant |

---

## 6. Flow Diagram

```
 request ──► guard.can()
              ├─ missing fields? ─────────────► DENY+log
              ├─ session/tenant binding? ─────► DENY+log
              ├─ role grants cap? ────────────► DENY+log
              ├─ persona switch ok? ─────────► DENY+anomaly
              ├─ drift pending? ──────────────► DENY (drift lock)
              ├─ tenant quota? ───────────────► DENY (throttle)
              └─ identity cored? ─────────────► DENY
              v ALLOW ──► audit ──► execute within tenant namespace
 drift loop: frame ─► in envelope? ─no─► neutralize + anomaly + lock
 multi-tenant: every can() hits kill_switch + quota first
```

---

## 7. Determinism & Safety Invariants

1. **Deny-by-default:** every non-explicitly-allowed action is denied.
2. **No cross reads:** namespaces never merge; aggregates need per-source consent.
3. **Pure enforcement:** guard functions are deterministic; no RNG, no wall-clock.
4. **Fail-closed:** guard error → deny + calm/even neutral output; isolation
   failure never degrades to "maybe allowed".
5. **Drift is observable:** each drift/leak/tenant event increments a counter
   surfaced by the self-check engine (readiness sees isolation health).
6. **Immutable core:** isolation logic can read identity/registry references but
   enforces their immutability; it cannot mutate them.

---

## 8. Verification Contract

New suite `test_persona_isolation.py`:

| Label | Asserts |
|---|---|
| `isolation_deny_by_default` | empty/partial request denied; no exception path permits |
| `isolation_persona_bound` | cross-band persona lookup denied |
| `isolation_switch_gates` | blocked/forced/uncertain switches denied; monotone transition audit |
| `isolation_role_grants` | unassigned capability denied; grants never compose |
| `isolation_tenant_scope` | cross-tenant literal key denied; namespaced keys resolve inside |
| `isolation_user_scope` | cross-user memory deny; no session carry-over |
| `isolation_tone_drift` | excursion outside envelope+ε blocked, snapped, anomaly counter++ |
| `isolation_identity_redact` | CORED fields absent from payload/fingerprint-only |
| `isolation_identity_token` | PUBLIC accessible; TENANT token-gated; CORED denied |
| `isolation_multi_quota` | quota/burst throttle enforced per tenant; slots honored |
| `isolation_kill_switch` | kill-switch denies only its tenant; others unaffected |
| `isolation_parity` | guard decisions identical native == headless |
| `isolation_suite` | module import + total label parity |

---

## 9. Dependencies

- `SAFETY_MONITOR` (urgency / taboo escalation feeds),
- stabilization `self_check` (drift / anomaly counters),
- capability registry (role grants),
- persona profiles + tone rules (envelopes),
- `identity.json` (key classification),
- verification sweep (parity + regression).