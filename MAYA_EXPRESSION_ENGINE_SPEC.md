# Maya Expression Engine — Architecture Specification

- **Status:** Specification (v1.0) — layered architecture + flow diagrams
- **Domain:** `maya_identity.wireframe.math_coordinator` (canonical math),
  `maya_identity.interaction` (behavioral entry points),
  `maya_runtime.personality` (persona engine),
  `maya_runtime.rendering` + `maya_runtime/deploy` (integration).
- **Conformance:** every stage is bounded, deterministic, ceiling-clamped,
  device-neutral, and persona-gated. Nothing here adds randomness or motion
  beyond the canonical math timeline.

---

## 1. Position in the Stack

```
  Sense / Context                          Interaction / Cognition / Voice
  (world state, user, partner, task,       (voice_input, emotional_mirroring,
   learning performance, intent)            adaptive_teaching, domain signals)
                     |                                   |
                     v                                   v
   L1 SEMANTIC WEIGHT -------------->  weight ∈ [0,1] per channel
                     |
                     v
   L2 TONE SHAPING ----------------->  tone targets (bounded bands)
                     |
                     v
   L3 EMOTIONAL MODULATION          <-- mirroring / blend alpha
                     |
                     v
   L4 MICRO-EXPRESSION BLENDING ----->  TASK_BLEND_WEIGHTS tree (0.6,0.3,0.1)
                     |
                     v
   L5 GESTURE MAPPING --------------->  gestures, joints, ceilings
                     |
                     v
   L6 PERSONA RULES ------------------>  amplitude caps, step caps, bans
                     |
                     v
   L7 RENDERING INTEGRATION ---------->  RenderFrame -> desktop/web/kiosk/robotics
```

L0 collects inputs; L1–L5 are pure math; L6 gates by persona; L7 is the only
hardware-touching stage. Any layer may clamp, never exceed.

---

## 2. Canonical Vocabulary (existing, reused unmodified)

| Symbol | Value | Role |
|---|---|---|
| `CHANNEL_MAX` | `expression 0.5 · viseme 0.35 · micro 0.012 · anatomical 0.8` | absolute ceilings |
| `CH_EXPRESSION, CH_VISEME, CH_MICRO, CH_ANATOMICAL` | channel keys | addressed lanes |
| `TASK_BLEND_WEIGHTS` | `(0.6, 0.3, 0.1)` | protected blend triple |
| `BLEND_E, BLEND_M, BLEND_V` | weight constants | evidence / modulation / cadence lhs |
| `MICRO_AMP, MICRO_AMP_X` | micro amplitude parameters | micro energy scale |
| `JAW_GAIN`, `jaw_open()` | jaw drive | anatomical coordination |
| `VISEME_ETYPES` | emotion type set | viseme selection universe |
| `stable_exp_smooth, stable_lerp, clamp01, clamp` | canonical smoothing/clamping | transition algebra |
| `blend_pose`, `STATE_CONTROLS, EMOTION_CONTROLS, VISEME_CONTROLS, MICRO_CONTROLS, ANATOMICAL_CONTROLS, SCENE_CONTROLS` | pose algebra | final composition |

`TASK_BLEND_WEIGHTS` is frozen by contract: the expression engine consumes it,
derives its own label mapping, and never reorders or rescales its members.

---

## 3. Layer Definitions

### L0 — Context Input (facade: `interaction`)

Consumes canonical entry points (`voice_input(features)`,
`emotional_mirroring(own, partner, alpha=MIRROR_DEFAULT_ALPHA)`,
`adaptive_teaching(...)`, gesture requests). Outputs a normalized context
`{evidence, semantic, relevance, pace, emotion_ref, gesture?, learning?}`.

Invariants:
- All scalars in `[0,1]` (normalized upstream).
- Context is a pure snapshot; no timestamps enter the expression pipeline.

### L1 — Semantic Weight Layer (semantic-weight → expression-intensity mapping)

Defined as a deterministic piecewise map from semantic weight to per-channel
intensity:

```
semantic_intensity(channel, weight):
    high   -> floor + 0.70 * span
    mid    -> floor + 0.35 * span
    low    -> floor
    where span = CELING[channel] - floor, floor >= 0
```

`bucket_of(weight)` (per canonical bucketing) selects the segment; boundary
values map by strict ordering so identical weights always pick identical
segments. Per channel:

| Channel | low bucket | mid bucket | high bucket |
|---|---|---|---|
| expression | 0.18 | 0.30 | 0.42 |
| viseme | 0.10 | 0.18 | 0.26 |
| micro | 0.001 | 0.004 | 0.008 |

All values inside `CHANNEL_MAX`. Mapping is a pure function: same weight →
bit-identical intensity on every device.

### L2 — Tone Shaping (bind: `persona.tone_targets(tone)`)

Tone rules (`even, warm, lively, authoritative, soothing, technical`) each
declare a channel band + pace. Application:

```
shaped[ch] = clamp01( L1[ch] * tone_scale[ch] + tone_baseline[ch] )
shaped.pace = tone_pace(tone)             # full resolution L1
```

Tone may scale, never raise the input outside the tone band and ceiling.

### L3 — Emotional Modulation (bind: `emotional_mirroring`, world model)

Mirroring folds partner emotion toward Maya's own timeline:

```
modulated[ch] = stable_lerp(own, shaped[ch], alpha * partner[ch])
alpha = MIRROR_DEFAULT_ALPHA unless overridden
```

- `alpha ∈ [0,1]`, deterministic, no oscillation.
- Emotional state is clamped to the persona emotional band (L6) afterwards.
- World-conditioned modulation (load/velocity) is monotic and downward-only:
  stable load raises → emotional amplitude only neutralizes toward `floor`.

```
context load/velocity
        |
        v
[downward modulation] -> amplitude -> band-floor (never upward)
```

### L4 — Micro-Expression Blending (bind: `MICRO_CONTROLS`, `MICRO_AMP`)

Micro lane is a three-input blend governed by the protected weight triple:

```
micro_out = 0.6 * E_micro + 0.3 * M_micro + 0.1 * V_micro
E_micro = evidence-driven emphasis (MICRO_AMP * evidence)
M_micro = modulation/emotion ripple (L3 micro)
V_micro = viseme cadence margin (breathing/timing)
```

- All three terms computed deterministically; micro_out clamped to
  `CHANNEL_MAX[CH_MICRO]` = 0.012.
- No random jitter; micros are *deterministic* signal, never noise.
- Blend weights come from `TASK_BLEND_WEIGHTS`; scale is `MICRO_AMP`/`MICRO_AMP_X`.

### L5 — Gesture Mapping (bind: `gesture_mapping(gesture, ceilings=None)`)

Gesture tokens map to anatomical targets respecting ceilings:

```
gesture_mapping(token, ceilings=None):
    joint_plan = GESTURE_ATLAS[token]          # deterministic
    constrained = clamp(joint_plan, ceil(CEILING_VAL[CH_ANATOMICAL]))
    return joint_plan | constrained
```

- `ceilings` optional override is clamped to the canonical ceiling.
- Gestures coexist with speech: energy budget per frame shared with L4;
  gestures have priority for anatomical lane only and never borrow expression.
- Unknown token → fails closed to idle (never invents motion).

```
token -> atlas lookup -> joint plan -> ceilings -> paced blend -> output joints
```

### L6 — Persona-Specific Expression Rules

Persona gates (from profile → `PERSONAS`/identity profile):

| Persona | amp cap (per ch) | max step/frame | micro energy | gesture set | bans |
|---|---|---|---|---|---|
| `calm` | low | 0.05 | quiet | small | fast/exaggerated gestures |
| `warm` | mid | 0.06 | soft | warm-closed | theatrical motion |
| `authoritative` | firm | 0.04 | flat | hands-down | jovial/playful emote |
| `playful` | high | 0.07 | lively | animated | none within caps |

Rules:
1. Persona caps are ceilings; a persona cannot exceed its band (profile
   `emotional_range`).
2. Switching happens via the persona layer's `stable_exp_smooth` transition —
   the expression engine sees only monotone-moving targets.
3. Fail-closed persona `calm/even` on any switch error.

### L7 — Rendering Integration Points

`RenderFrame` (bounded, no timestamps) is the single handoff:

```
 render_engine(frame<channels, joints, pose, pace>, target):
     desktop -> tk   (RenderFrame -> TkRenderer)
     web     -> JSON payload (WebRenderer canvas)
     kiosk   -> fullscreen RenderFrame (KioskRenderer)
     robotics-> bounded actuator command (RoboticsRenderer, CHANNEL_MAX enforced)
```

- Only L7 sees devices; all math above is device-neutral.
- Cross-process signature parity is asserted (native == headless) per
  verification contract.
- A renderer never modifies frame values; it only consumes + presents.

---

## 4. Frame Pipeline (flow)

```
        ┌───────────┐   ┌──────────────┐   ┌──────────┐
 context│ L0 inputs │ → │ L1 semantic  │ → │ L2 tone  │
        └───────────┘   │  intensity   │   └──────────┘
                        └──────┬───────┘
                               v
   ┌────────────┐    ┌──────────────────┐    ┌────────────┐
   │ L5 gesture │ ←  │ L3 modulation +  │ ←  │ mirroring  │
   │  mapping   │    │ L4 micro blend   │    │ partner    │
   └──────┬─────┘    └────────┬─────────┘    └────────────┘
          │                   v
          │         ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
          └────────►│ L6 persona gate      │  clamps & step-caps
                    └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
                               v
                    ┌──────────────────────┐
                    │ L7 RenderFrame        │  channels + joints + pose
                    │  desktop/web/kiosk/   │
                    │  robotics             │
                    └──────────────────────┘
```

Each stage redacts (clamps) downward to the ceilings; the only branch is the
persona gate which forwards to the render target.

## 5. Integration With Existing Contracts

| Existing system | Connection |
|---|---|
| `interaction.voice_input` | feature → evidence/viseme drive (L1/L2) |
| `interaction.emotional_mirroring` | partner effect at L3 |
| `interaction.gesture_mapping` | gesture token → L5 |
| `math_coordinator.blend_pose` | final pose composition (L7 input) |
| `personality.channel_targets/paced_state` | L6 persona targets/pace |
| `WorldModel` stability features | loads → monotonic band-floor modulation (L3) |
| `PATTERN_ALIGNMENT` domain alignment | gate: expression stays inside aligned domain style |
| stabilization protocol | switching gating; expression anomalies feed `self_check` |
| `CHANNEL_MAX`, `TASK_BLEND_WEIGHTS` | absolute constraints (L3/L4/L6) |

## 6. Determinism & Safety Invariants

1. All L1–L6 functions are pure: no RNG, time, environment, or wall-clock.
2. Transition algebra uses `stable_exp_smooth` only (monotone, no overshoot,
   no teleport).
3. Every frame stays inside `CHANNEL_MAX`; persona step caps ≤ persona rule.
4. `TASK_BLEND_WEIGHTS (0.6,0.3,0.1)` preserved verbatim.
5. RenderFrame carries no timestamps; device identifiers never affect frames.
6. Fail-closed: any gate/handler error returns the calm/even neutral frame.
7. Downward-only context modulation: load can only flatten, not excite.

## 7. Verification Contract

New suite `test_expression_engine.py` (labels; compiled + validated):

| Label | Asserts |
|---|---|
| `expression_semantic_mapping` | `semantic_intensity` is deterministic & bucket-bounded per channel |
| `expression_ceiling_bounds` | all layers produce frames inside `CHANNEL_MAX` |
| `expression_blend_weights_preserved` | `TASK_BLEND_WEIGHTS == (0.6,0.3,0.1)` unchanged |
| `expression_micro_blend` | micro_out equals the documented 0.6/0.3/0.1 combination; ≤ 0.012 |
| `expression_tone_shaping` | tone-raised values stay inside tone band and ceiling |
| `expression_mirror_alpha` | `emotional_mirroring` respects alpha; monotone lerp |
| `expression_gesture_ceiling` | gesture mapping clamps anatomical to ≤ 0.8, unknown → idle |
| `expression_persona_gates` | each persona respects its amp/step caps; switch is monotone |
| `expression_render_frame_bounded` | RenderFrame channels in-band, joints bounded |
| `expression_device_parity` | native == headless frame signature for same inputs |
| `expression_fail_closed` | invalid tone/gesture/persona → calm/even neutral frame |
| `expression_suite` | module imports + total label parity |