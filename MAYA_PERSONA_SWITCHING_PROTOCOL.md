# Maya Persona Switching Protocol — Deterministic State Machine

- **Status:** Specification (v2.0) — supersedes the earlier switching subsection;
  retains compatibility with Persona Layer, Isolation, Governance, and
  stabilization specs.
- **Promise:** switching is **atomic, gated, reset-ordered, monotone, and
  fail-closed**: no partial persona, no teleport, no hybrid state, no drift.

---

## 1. Formal Notation

```
p      :: persona id
B(p)   :: emotional band of p         (∀ch: lo(p,ch) ≤ hi(p,ch) ≤ C[ch])
env(p) :: tone envelope (ToneTargets) from tone(p)
W      :: world slice (session-scoped)
s      :: session state

transition: (state, trigger) → guard? → (state', actions)
```

**Invariants:**
```
I1  ∀ frame · ∀ch · frame[ch] ≤ C[ch] = CHANNEL_MAX
I2  ∀ switch · lanes move via stable_exp_smooth (monotone, no overshoot)
I3  no state where two personas contribute (no hybrid)
I4  any failure → revert-to-prior or NEUTRALIZED (calm/even), never partial
I5  identical trigger sequence ⇒ identical state trace (device-identical)
```

---

## 2. States

| State | Meaning | Fields |
|---|---|---|
| `IDLE` | no active session | — |
| `ACTIVE(p)` | persona p driving | `p`, `frame`, `W` |
| `SWITCHING(prev → next)` | transition in progress | `prev, next, trace, snapshot` |
| `SETTLING(next)` | resets applied; verifying post-conditions | `next` |
| `GUARDED` | drift-lock engaged; expression transport blocked | `p` |
| `NEUTRALIZED` | fail-closed calm/even active | `calm, even` |

Transitions only between these seven states; there is no "waiting" ambiguity.

---

## 3. Switch Triggers

| Trigger | Source | Validated against |
|---|---|---|
| `user_request` | user switches persona explicitly | user scope + persona availability |
| `role_change` | role binding changes (tenant policy / domain shift) | tenant policy, role grants |
| `context_signal` | domain/task shift (e.g., distress → support) | `context_safe` predicate |
| `urgency_force` | urgency/taboo forces soothing/even | SAFETY_MONITOR |
| `tenant_policy` | tenant admin changes persona policy | tenant kill-switch/quota state |

Every trigger yields a **switch intent** `(prev, next, reason)`; intents with
`next == prev` are no-ops (no event recorded).

---

## 4. Safety Checks (ordered guards)

All must pass; first failure short-circuits to §8.

```
G1 sandbox  : action "switch" → allow on surface table
G2 tenant   : tenant binding valid; kill-switch false; quota ok
G3 user     : requester owns session; switch within their grants
G4 isolation: no cross-persona/cross-tenant read; bundles hash-pinned
G5 ready    : verified_runtime for constrained targets (kiosk/robotics)
G6 context  : context_safe(s) — not crisis-restricted, not therapy-locked
G7 pairs    : ¬prohibited(prev, next)  (e.g., playful→therapy, lively→robotics)
G8 bands    : ∃ anchor a∈ℝ^4 · a∈B(prev) ∧ a∈B(next)   (monotone path exists)
G9 drift    : no GUARDED lock pending for this session
G10 cooldown: switch count within session budget (no flapping)
```

`anchor` (`G8`) is computed deterministically as the intersection midpoint of
`B(prev) ∩ B(next)` if nonempty (else `G8` fails and the switch is refused, not
loosened).

---

## 5. Transition Table

| From | Event | Guard result | To | Actions |
|---|---|---|---|---|
| `IDLE` | session start | G1–G5 pass | `ACTIVE(p_init)` | load profile, calm default |
| `ACTIVE(p)` | trigger t | pass | `SWITCHING(p,n)` | snapshot frame; anchor; trace start |
| `ACTIVE(p)` | trigger t | fail | `ACTIVE(p)` | record refusal; anomaly counter++ |
| `SWITCHING(p,n)` | smooth done ∧ resets ok | all | `SETTLING(n)` | reset order S1–S4 (§6) |
| `SWITCHING(p,n)` | guard changed mid-way | — | revert to snapshot → `ACTIVE(p)` or `NEUTRALIZED` | undo, log |
| `SETTLING(n)` | post-conditions hold | I1–I2 | `ACTIVE(n)` | commit new persona |
| `SETTLING(n)` | post-check fail | — | `NEUTRALIZED` | calm/even, anomaly |
| `ACTIVE(p)` | drift(i) for i frames | threshold | `GUARDED` | freeze expression transport |
| `GUARDED` | reset_ok (verified) | all | `ACTIVE(p)` | resume from neutral |
| any | `urgency_force` | pass | `NEUTRALIZED`→`ACTIVE(calm/even forced)` | force even/soothing tone |

The trace is append-only; every row is recorded with `(from,to,reason,outcome)`.

---

## 6. Reset Order (S1–S4) — applied in SWITCHING → SETTLING

**S1 · Tone reset**
```
tone(new) = urgency_force? even/soothing : tone_default(p_new)
env(new)  = envelope(tone(new))                     # new band B(p_new)
```
Tone takes effect immediately as a **target**, but paced: pace lerps from
`pace(prev)` to `pace(next)` over `N` frames via `stable_lerp`.

**S2 · Expression reset**
```
per channel ch:
    sequence seq(ch) = stable_exp_smooth(current, anchor[ch], N)
    ∀k: |seq[k+1] - seq[k]| ≤ step_cap(p_new, ch)
    seq ⊆ B(prev) ∪ B(next)  (monotone through anchor; I2)
```
Result: lanes re-center into `B(p_new)` without ever exceeding
`max(hi(prev,ch), hi(next,ch)) ≤ C[ch]`.

**S3 · World-model reset (session slice)**
```
W' = reset_slice(W, domain(p_new))
  recompute stability features deterministically
  re-bind PATTERN_ALIGNMENT to domain(p_new)
  W' seeded from same inputs ⇒ bit-identical on every device
```
Session context persists (no privacy loss at switch); only the *domain slate* is
re-initialized.

**S4 · Post-checks**
```
assert ∀ch frame_settled[ch] ∈ B(p_new)
assert ∑ lanes ≤ energy budget(p_new)
assert tone = expected; world slice = W'
else → revert (G-fail path)
```

Ordering rationale: tone defines the envelope before lanes move (S1→S2); world
re-binds after lanes so the final frame is stable against the new domain (S3);
post-checks close the commit (S4).

---

## 7. Worked Deterministic Trace

Context: `calm → playful` for companion demo (N=24, step_cap=0.07).

```
prev band: expr [0.15,0.40] · next band: expr [0.20,0.50]
anchor = intersection point (expr 0.30, viseme 0.18, micro 0.005)
S1 tone: even → lively (target), pace 0.60 → 0.75 over 24 frames
S2 expression lane: start 0.20 → monotone stable_exp_smooth → 0.32
   sequence: 0.20, 0.21, 0.22, ... 0.32   (max step 0.05 < 0.07 ✓)
S3 world slice re-binds: entertainment domain; patterns recomputed
S4 post-checks pass
commit: ACTIVE(playful)   [trace: calm→playful, reason=context_signal]
```

Same inputs ⇒ same trace on desktop, kiosk, robotics, and headless.

---

## 8. Fail-Closed Fallback Ladder

| Failure | Ladder step | Result |
|---|---|---|
| guard fails pre-transition | 1 | remain `ACTIVE(prev)`; log refusal |
| mid-transition failure | 2 | revert to **snapshot** values (pre-switch frame), then if unsafe → step 3 |
| revert unsafe / post-check fail | 3 | `NEUTRALIZED` → `calm/even` default |
| any exception in protocol | 4 | `NEUTRALIZED` + anomaly; no partial frames emitted |

Fail-closed is always a **valid persona-legal frame** (I4). No case returns
hybrid state or garbage output.

## 9. Integration Contracts

- **Isolation Manager:** switch requires crossing its gates (G4); drift-lock
  blocks transport (GUARDED).
- **Governance model:** neutralization triggers reuse — urgency forbid, drift,
  loader error, unknown id all route through ladder steps.
- **Authority Map:** switch is authorized only by Persona Authority under
  sandbox verdicts; READY gating respected for constrained targets.
- **Stabilization:** switch anomalies feed self-check counters; READY state is
  not affected by persona switches (orthogonal axes).

## 10. Verification Contract

New suite `test_persona_switching_protocol.py`:

| Label | Asserts |
|---|---|
| `switch_state_machine` | only the 7 states; transitions per table |
| `switch_trigger_noop` | prev==next yields no event |
| `switch_guards_all` | each of G1–G10 enforced; first failure short-circuits |
| `switch_prohibited_pairs` | playful→therapy, lively→robotics refused |
| `switch_anchor_monotone` | G8 anchor exists; lanes monotone through it |
| `switch_tone_reset` | S1 target + paced lerp; urgency forces even/soothing |
| `switch_expression_reset` | S2 sequence within B(prev)∪B(next); step caps |
| `switch_world_reset` | S3 slice re-binds domain; same inputs → same slice |
| `switch_post_checks` | S4 asserts new-band membership + energy budget |
| `switch_fail_closed` | ladder steps 1–4 all yield valid frames, no hybrid |
| `switch_deterministic_trace` | identical trace native==headless |
| `switch_suite` | module import + total label parity |