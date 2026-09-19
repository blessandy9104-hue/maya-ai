# Maya Persona Expression Calibration — Calibration Table + Ruleset

- **Status:** Specification (v1.0) — calibration reference for the Expression Engine
- **Scope:** L0–L7 intensity scale, persona-specific ceilings, semantic-weight →
  expression-intensity mapping, rendering constraints.
- **Convention:** the L-scale here is an **intensity level** (0–7) applied at
  Expression L1; personification/expression lane gating happens at L6; the old
  "L0–L7 layers" nomenclature of the Expression spec is retained for pipeline
  stages, while this document defines the **amplitude levels** used inside them.

---

## 1. The L0–L7 Intensity Scale

Level factor over the usable band span:

| Level | Semantics | Factor |
|---|---|---|
| L0 | neutral / resting (band floor) | 0.000 |
| L1 | subtle acknowledgment | 0.14 |
| L2 | gentle interest | 0.29 |
| L3 | engaged / informative | 0.43 |
| L4 | warm emphasis | 0.57 |
| L5 | strong emphasis | 0.71 |
| L6 | high engagement (capped registers) | 0.86 |
| L7 | **maximum for that persona** (never beyond ceiling) | 1.00 |

**Formula (deterministic):**
```
amp(ch, L, persona) = band.lo(persona, ch) + factor(L) * (band.hi(persona, ch) − band.lo(persona, ch))
band ⊆ CHANNEL_MAX          → amp ≤ C[ch] = CHANNEL_MAX[ch]
```

Level selection from a semantic weight `w ∈ [0,1]`:
```
L(w) = clamp(round(7 * w), 0, 7)            # deterministic rounding (round-half-up)
```

### 1.1 Absolute table for a reference persona band (`calm` default:
expr 0.15–0.40 · viseme 0.05–0.22 · micro 0.000–0.006)

| Level | expression | viseme | micro |
|---|---|---|---|
| L0 | 0.150 | 0.050 | 0.0000 |
| L1 | 0.186 | 0.074 | 0.0008 |
| L2 | 0.222 | 0.099 | 0.0017 |
| L3 | 0.257 | 0.123 | 0.0026 |
| L4 | 0.293 | 0.147 | 0.0034 |
| L5 | 0.329 | 0.171 | 0.0043 |
| L6 | 0.364 | 0.196 | 0.0051 |
| L7 | **0.400** | **0.220** | **0.0060** |

All values inside `CHANNEL_MAX`; L7 = the persona's own ceiling, never the
global ceiling unless the persona band reaches it (only companion/playful).

---

## 2. Persona-Specific Ceilings

| Persona | expr hi | viseme hi | micro hi | anat hi | step_cap | Note |
|---|---|---|---|---|---|---|
| `calm` | 0.40 | 0.22 | 0.006 | 0.40 | 0.05 | default; L7 = these |
| `warm` | 0.44 | 0.26 | 0.008 | 0.50 | 0.06 | L6–7 allowed in support |
| `authoritative` | 0.40 | 0.24 | 0.006 | 0.45 | 0.04 | firm, flat |
| `playful` | 0.50 | 0.35 | 0.012 | 0.70 | 0.07 | only persona hitting global micro/hi |
| *(companion)* | 0.50 | 0.35 | 0.012 | 0.70 | 0.07 | training alias of playful |
| *(kiosk)* | 0.30 | 0.18 | 0.004 | 0.25 | 0.04 | lowest ceiling set |

Rules:
- `hi(persona,ch) ≤ CHANNEL_MAX[ch]` always; L7 never exceeds the persona hi.
- Band lo stays ≥ 0; L0 is the persona's neutral (never forced to 0 unless lo=0).

## 3. Semantic-Weight → Expression-Intensity Mapping

Primary mapping is `L(w) = clamp(round(7w),0,7)`; register gating refines it:

| Semantic weight `w` | Level | Register uses |
|---|---|---|
| 0.00–0.14 | L0–L1 | wait, neutral, technical status |
| 0.15–0.29 | L2 | greeting (subtle), clarify |
| 0.30–0.43 | L3 | transfer, options, instruction |
| 0.44–0.57 | L4 | warm emphasis, progress affirm |
| 0.58–0.71 | L5 | celebration, strong encouragement |
| 0.72–0.86 | L6 | performance registers (lively) |
| 0.87–1.00 | L7 | max allowed by persona (rare, gated) |

**Downward override:** urgency/taboo/load forces `L ≤ 1` regardless of `w`;
`soothing` and `even` registers may not exceed L3 (except L4 in warm support).

> Note: earlier nominal anchors "low 0.18 / mid 0.30 / high 0.42" map to this
> scale as L1≈0.19, L4≈0.29, L7→persona ceiling; 0.42 is only valid for persona
> bands with hi ≥ 0.42 (playful), otherwise the ceiling clips it.

## 4. Rendering Constraints

| Constraint | Value | Enforced at |
|---|---|---|
| Cadence | ≤ 30 frames/s | rendering loop |
| Frame step | ≤ 1 level change per frame (≤ step_cap) | L6 gate |
| Monotone | sweeps via `stable_exp_smooth`, no overshoot | L4/L6 |
| L7 gating | only when register+persona explicitly allow | L6 |
| Timestamps | none in `RenderFrame` | L7 |
| Web payload | JSON, bounded frame lanes | WebRenderer |
| Kiosk | fullscreen, frames within band | KioskRenderer |
| Robotics | actuator commands, extra `anat ≤ channel max` | RoboticsRenderer |
| Parity | native == headless identical outputs | verification |

Rendering may **reduce** a level (consume-only) but never raise it past the
calibrated value for the active persona.

## 5. Ruleset (R1–R12)

```
R1  amp computed by formula; L7 = persona hi, never global ceiling
R2  L0 == persona neutral floor
R3  level changes ≤ 1 per frame (prevents teleport)
R4  monotone smoothing, no overshoot
R5  urgency/taboo/load ⟹ L ≤ 1, tone forced even/soothing
R6  soothing/even ≤ L3; warm support may reach L4
R7  calibration deterministic (bit-identical across devices)
R8  persona ceilings gate L6 output
R9  blends keep TASK_BLEND_WEIGHTS = (0.6,0.3,0.1)
R10 RenderFrame carries no timestamps; adapters reduce-only
R11 Fail-closed: any calibration/gate error → L0 calm/even
R12 Calibration table versioned; changes require re-verification
```

## 6. Verification Contract

New suite `test_persona_expression_calibration.py`:

| Label | Asserts |
|---|---|
| `calib_level_scale` | L(w) deterministic; factors 0–1 stepwise |
| `calib_reference_table` | calm-band absolute table reproduced exactly |
| `calib_persona_ceilings` | every hi ≤ CHANNEL_MAX; L7 == persona hi |
| `calib_formula_bound` | amp(ch,L,persona) ∈ [lo,hi] ⊆ ceiling |
| `calib_weight_mapping` | weight windows match §3 |
| `calib_downward_override` | urgency forces L ≤ 1 + even/soothing |
| `calib_level_step` | ≤1 level change per frame |
| `calib_monotone` | sweeps monotone, no overshoot |
| `calib_render_bounds` | web/kiosk/robotics/general payloads in band |
| `calib_fail_closed` | calibration errors → L0 neutral calm frame |
| `calib_parity` | identical native == headless |
| `calib_suite` | module import + total label parity |

## 7. Traceability

| Item | Backed by |
|---|---|
| Band/ceiling definitions | Persona Layer profiles + training sets |
| Weight mapping | Semantic→Persona→Expression pipeline L1 |
| Gates & neutralization | Pure Persona Governance neutralization triggers |
| Smoothing | math_coordinator `stable_exp_smooth` (0.6/0.3/0.1 preserved) |
| RenderFrame bounds | Expression Engine L7 + Demo blueprint |