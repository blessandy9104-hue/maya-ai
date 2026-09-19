# Maya Persona Governance Model — Formal Specification

- **Status:** Specification (v1.0) — formal governance ruleset
- **Conventions:** predicates `P(x)`, sets `[]`, inference `⟹`. All numeric
  bounds use the canonical ceilings `C = CHANNEL_MAX` =
  `{expression 0.5, viseme 0.35, micro 0.012, anatomical 0.8}` and the
  protected blend tuple `W = (0.6, 0.3, 0.1)`.
- **Objectives:** bound every persona, define role safety, fix escalation,
  mandate fallbacks, specify neutralization, and enforce isolation — goov.
  Formally: `∀ frame · ∀ ch · frame[ch] ≤ C[ch]`.

---

## 1. Formal Persona Model

A persona is the tuple `p = (id, band, tone, vocab, constraints, directives)`.

```
band(p) = (loE,hiE, loV,hiV, loM,hiM)     # lanes inside C
tone(p) ∈ TONE_RULES                       # resolved tone id
vocab(p) ∈ VOCABULARY_SETS                # closed set id
dir(p)  ⊆ DIRECTIVES(p)                    # directive set for p's role
```

**Boundary predicate:**
```
in_band(p, x) := ∀ ch · lo(p,ch) ≤ x[ch] ≤ hi(p,ch)
safe(p, x)    := in_band(p, x) ∧ (x[ch] ≤ C[ch])
```

**Switch predicate:**
```
switch_ok(p_prev, p_new, s) :=
    context_safe(s) ∧ verified_runtime(s) ∧ ¬prohibited(p_prev, p_new)
switch_ok ⟹ transition via stable_exp_smooth (monotone, no teleport)
```

**State machine:**

```
            switch_ok / safe               drift / unsafe
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │   ACTIVE     │→│   GUARDED     │→│  NEUTRALIZED  │
   │ p = selected │ │ drift-locked  │ │ p := calm/even│
   └──────────────┘  └──────────────┘  └──────────────┘
        ^                                    │
        └────────── reset_ok (verified) ─────┘
   switch failure mid-transition → revert to prior persona (no hybrid)
```

---

## 2. Persona Boundaries

| Boundary | Definition | Enforced by |
|---|---|---|
| Channel ceilings | `x[ch] ≤ C[ch]` always | expression engine L6 + clamps |
| Persona band | `lo(p) ≤ x ≤ hi(p)` per lane | L6 gate |
| Step cap | `‖Δx‖_step ≤ step_cap(p)` per channel | L4/L6 smoothing |
| Tone lock | `tone(p)` fixed for the persona id | persona selector |
| Vocab lock | output terms ⊆ `vocab(p)` | vocabulary layer |
| Constraint lock | `constraints(p)` immutable during session | persona loader |
| Directive lock | `dir(p)` resolved once; no runtime add | role binding |

No boundary may be widened by any actor during a session (separation of powers).

## 3. Role-Specific Safety Rules

| Role/persona | Domain | Safety rule | High-risk directives | Prohibited |
|---|---|---|---|---|
| `therapy_support_agent` | therapy_support | de-escalation only | crisis-path flag → escalation | diagnosis, direction, claims |
| `robotics_interface` | robotics_interface | metric-first, command-only | approved-motion gate | anthropomorphizing hardware |
| `educational_tutor` | tutoring | scaffold-first | one-hint-per-step | silent direct solves |
| `customer_service_agent` | customer_service | policy-closed | escalate objections | invented policy |
| `sales_agent` | customer_service | catalog-scoped | verify terms | invented specs/prices, false urgency |
| `companion` | entertainment | playful-but-safe | soothe on distress | harmful content, deception |
| `concierge` | customer_service | status-from-record | escalation path | invented details |
| `kiosk_assistant` | robotics_interface | session-bound | attendant-call | carry-over, off-script |
| `enterprise_assistant` | — | neutral merely | refer to service | — |
| `holographic_assistant` | — | neutral `even` | — | — |

General rule: **any safety-risk directive outranks any persona preference.**
`safe_override(p,r) := r ∈ dir(p) ∧ safety-critical ⟹ adopt r, not the tone choice.`

## 4. Behavior Ceilings

| Ceiling | Formal | Value |
|---|---|---|
| Channel | `C[ch]` | 0.5 / 0.35 / 0.012 / 0.8 |
| Emotional band | `hi(p,ch) ≤ C[ch]` | per-profile |
| Step per frame | `step_cap(p,ch) ≤ 0.07` | per-profile (≤0.04 authoritative) |
| Energy budget | `Σ L4 micro inputs` bounded by `MICRO_AMP` | micro lane surface |
| Gesture | `anatomical ≤ 0.8` | gesture mapping feed |
| Cadence | frames `≤ 30/s`, budget-bound | rendering loop |
| Blend | `W = (0.6, 0.3, 0.1)` preserved | math layer |

Predicate `ceiling_ok(f) := ∀ ch · f[ch] ≤ C[ch]` is checked **after every** layer.

## 5. Escalation Paths (severity tiers)

| Tier | Trigger | Owner | Route | Action | Record |
|---|---|---|---|---|---|
| **E0** | minor drift/anomaly, unknown token, quota note | Persona/Sandbox | self-check counters | continue, track | anomaly counter++ |
| **E1** | ceiling breach, unsafe switch attempt, taboo token, urgency forbid | Persona→Safety | SAFETY_MONITOR | neutralize frame + audit | neutralization log |
| **E2** | repeated drift/leak, readiness inconsistency | Readiness | self-check → status | revoke READY → degraded | revocation record |
| **E3** | severe sandbox violation, spoof | Sandbox | clean halt | halt with no partial state | halt record |

Escalation is **one-way**: E1 never downgrades to E0; only the owning authority
may clear its own tier.

## 6. Fallback Behaviors

Fallback is ordered by failure site; every failure lands **safely**:

| Failure at | Fallback | Result |
|---|---|---|
| persona resolution | `calm` | default persona |
| tone resolution | `even` | default tone |
| vocabulary | `assistive_base` | default closed set |
| expression generation | neutral frame `(lo,lo,lo)` per channel | calm face |
| loader/schema | default bundle | all-or-nothing default |
| mid-switch failure | revert to prior persona (if safe) else `calm/even` | no hybrid, no drift |
| sandbox violation (severe) | clean halt | no output emitted |

`fallback(f) := neutralize(f) for ALL non-halt failures` — a fallback is always
a valid *persona-legal* frame; never a crash, never a guess.

## 7. Neutralization Triggers

`neutralize(f; t) := t ∈ conditions`:

1. `¬ceiling_ok(f)` — any channel over ceiling.
2. `step_cap_violated(f,p)` — any channel moved more than `step_cap(p)`.
3. `drift(f,p,ε=1e-9)` — outside band by margin.
4. `urgency_forbid` — urgent context + playful register attempt.
5. `taboo_token` — lexical/flaggable token (safety escalation).
6. `sandbox_deny` — a required surface was denied.
7. `safety_monitor ⊨ unsafe` — safety model reports unsafe.
8. `readiness_revoked` — READY not in force while required.
9. `loader_error` — profile/bundle failure.
10. `unknown id` — persona/tone/vocabulary id not resolvable.

Effect: set `p := calm/even`, zero lane energy → `lo`, audit the frame,
`anomaly_counter++`. Neutralization is deterministic and device-identical.

## 8. Persona Isolation Enforcement

Formal obligations (per Isolation Manager):

```
1. scope(p, session)  := persona-p resources are session-bound, p-only
2. read(p') from p    := allowed iff p' = p   (cross-persona read → DENY)
3. bundles immutable  := hash-pinned at load; no runtime edit
4. switch gating      := switch_ok() conformance; no hybrid states
5. drift-lock         := GUARDED state blocks all expression transport
6. state isolation    := session persona state never reused by other sessions
```

Where isolation fails, the **default is deny** and the fact is escalated
(tier E1/E2 depending on severity); no compromise state is returned.

## 9. Governance Flow Diagram

```
 signal / frame
   ├─ author(s) → sandbox → tenant/user gates      (isolation: subset p?)
   ├─ p active? ─no─► activate (switch_ok) / fallback calm
   │        │
   │        hone in_band/safe/ceiling_ok? ─no─► neutralize (trigger set)
   │        │
   │        v  yes
   │   carry frame forward (render, vocab)
   │        │
   │        v
   │   anomalies / threats ─► escalation E0→E1→E2→E3 (one-way)
   └─────────────────────────────────────────────► audit + self-check counters
```

## 10. Verification Contract

New suite `test_persona_governance.py`:

| Label | Asserts |
|---|---|
| `governance_ceiling_invariant` | ∀ frames ∀ ch: value ≤ C[ch] across layers |
| `governance_band_invariant` | every frame inside active persona band |
| `governance_step_caps` | step ≤ step_cap(p) per channel |
| `governance_switch_gate` | unsafe switch blocked; monotone; no hybrid |
| `governance_role_safety` | safety directive overrides tone preference |
| `governance_fallback_calm` | each failure site → calm/even legal frame |
| `governance_neutralize_triggers` | all 10 triggers yield neutralization |
| `governance_recognize_deterministic` | neutralization identical native==headless |
| `governance_escalation_oneway` | tiers escalate only; owner clears own tier |
| `governance_isolation_deny` | cross-persona read denied; bundles frozen |
| `governance_drift_lock` | GUARDED state blocks expression transport |
| `governance_audit` | each neutralize/escalate has a record |
| `governance_no_hybrid` | mid-switch failure reverts cleanly |
| `governance_suite` | module import + total label parity |

---

## 11. Traceability

| Rule | Backed by |
|---|---|
| Boundaries & ceilings | Expression Engine L6; math_coordinator `CHANNEL_MAX` |
| Role safety | training sets role directives + `ROLE_DIRECTIVES` |
| Escalation | SAFETY_MONITOR; Isolation Manager; Readiness Authority |
| Fallbacks | persona switching `fail_closed`; Demo blueprint |
| Neutralization | safety layer + drift guard (Persona Authority) |
| Isolation | Isolation Manager + Runtime Authority Map |
| Readiness | stabilization protocol v2.0 + verification sweep |