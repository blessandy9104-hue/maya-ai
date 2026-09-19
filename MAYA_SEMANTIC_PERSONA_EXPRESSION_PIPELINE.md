# Maya Semantic → Persona → Expression Pipeline — Architecture Specification

- **Status:** Specification (v1.0)
- **Scope:** end-to-end pipeline from raw context to rendered frames + persona vocabulary.
- **Composes:** Persona Layer spec, Identity Profile format, Expression Engine spec.
- **Module boundaries:** marked `EXISTING` (built & verified) vs `PROPOSED` (module path defined by this spec, not yet built).

---

## 1. Pipeline Overview

```
 [context snapshot] ──► S1 Semantic → SemanticVector ──► S2 Persona interpretation ──► PersonaPlan
                                                                                              │
                    S8 Vocabulary ──────────► VocabOut                      S3 ──► ToneTargets
                                                                                              │
{render, voice, interaction}                                        S4 Emotional weights ──► weights
                                                                                              │
                                                                                 S5 Expression map ──► frame
                                                                                              │
                                                                                 S6 Math blending ──► BlendPose
                                                                                              │
                                                                                 S7 Rendering ──► RenderFrame
```

Single entry: `maya_runtime.pipeline.run(context)` (PROPOSED facade over all
signals). Every step is deterministic; only S7 touches hardware.

---

## 2. Step-by-Step Pipeline

### S1 — Semantic Vector Extraction
**Module boundary:** `interaction` (EXISTING: `voice_input`, `adaptive_teaching`,
`emotional_mirroring`) → `maya_runtime/pipeline.py::extract_semantic` (PROPOSED).

| In | Out |
|---|---|
| voice features, learner/target/performance, partner emotion, world-load, intent, gesture request | `SemanticVector` (:data contract) |

Algorithm:
1. `evidence = normalize(0.4*performance + 0.6*semantic_match)` — bounded [0,1].
2. `semantic = clamp01(domain_score)` (from domain-specific behaviors / `PATTERN_ALIGNMENT`).
3. `relevance = clamp01(task_priority)` (canonical task features).
4. `emotion_ref = partner emotion vector` (via mirroring) or neutral.
5. `world_load` from `WORLD_MODEL` stability features; `gesture` token or `null`.
6. Return immutable vector. Invariants: all ∈ [0,1]; no timestamps; no RNG.

### S2 — Persona Interpretation
**Module boundary:** `maya_runtime/personality.py` (EXISTING: `PERSONAS`,
`channel_targets`, `paced_state`) + `maya_runtime/persona/profiles.py` (PROPOSED:
`PERSONA_PROFILES`).

Resolves active persona from profile (or fail-closed `calm/even`): picks
`PERSONAS[persona]`, yields `PersonaPlan = (persona_id, tone_id profile,
vocabulary_set, emotional_band, constraint_ids, role_directives)`.

Order: schema-validated profile → registry resolution → disjointness + band
checks → locked immutable plan.

### S3 — Tone Selection
**Module boundary:** `maya_runtime/persona/tone.py::tone_targets` (PROPOSED).

Deterministic selector: tone chosen by persona + context role + intent.

| Context signal | Tone |
|---|---|
| tutoring, low performance curve | `warm` |
| high-stakes / robotics / policy | `technical` (or `authoritative`) |
| therapy / de-escalation | `soothing` |
| customer service / neutral default | `even` |
| entertainment / vtuber | `lively` |

`tone_targets(tone)` returns bounded `{expression, viseme, micro, pace}` inside
`CHANNEL_MAX` and the persona band (never wider).

### S4 — Emotional Weighting
**Module boundary:** `interaction.emotional_mirroring` (EXISTING) +
`persona/emotion.py::clamp_to_range` (PROPOSED).

```
modulated[ch] = stable_lerp(own[ch], target[ch], alpha * partner[ch])
alpha = MIRROR_DEFAULT_ALPHA (or TEACH_DEFAULT_ALPHA for teaching contexts)
then: modulated = clamp_to_range(modulated, persona_band[ch])
```

Invariants: monotone; downward-only under world load; stays inside
`CHANNEL_MAX` and persona emotional band.

### S5 — Expression Mapping
**Module boundary:** Expression Engine L1/L2/L4 (PROPOSED per Expression spec).

Semantic-weight → intensity (piecewise, `bucket_of`):

| channel | low | mid | high |
|---|---|---|---|
| expression | 0.18 | 0.30 | 0.42 |
| viseme | 0.10 | 0.18 | 0.26 |
| micro | 0.001 | 0.004 | 0.008 |

Tone shaping + micro blend tree (0.6/0.3/0.1) applied → bounded frame lanes.

### S6 — Math-Layer Blending
**Module boundary:** `math_coordinator` (EXISTING: `TASK_BLEND_WEIGHTS (0.6,0.3,0.1)`,
`stable_exp_smooth`, `stable_lerp`, `clamp01`, `blend_pose`, `MICRO_AMP`,
`JAW_GAIN`).

1. Smooth all lane targets with `stable_exp_smooth` (monotone, no overshoot).
2. Micro blend exactly `0.6·E + 0.3·M + 0.1·V` (E evidence, M modulation, V viseme cadence), scale `MICRO_AMP`.
3. Compose via `blend_pose(STATE_CONTROLS, EMOTION_CONTROLS, VISEME_CONTROLS, MICRO_CONTROLS, ...)`.
4. Clamp every value to `CHANNEL_MAX`; step caps from persona apply last.
5. Emit `BlendPose` (bounded, no timestamps).

### S7 — Rendering Output
**Module boundary:** `maya_runtime/rendering.py` (EXISTING: `RenderFrame`,
`RendererRegistry::render_engine/get_renderer/sample_frame`) +
`maya_runtime/deploy/` (EXISTING targets).

`render_engine(frame, target)` maps BlendPose → device payload:
desktop→Tk, web→JSON canvas, kiosk→fullscreen, robotics→bounded actuator
commands. Renderers consume only; they never mutate values. Cross-process
native == headless parity asserted by the verification contract.

### S8 — Persona Vocabulary Selection
**Module boundary:** `maya_runtime/persona/vocabulary.py::expand` (PROPOSED,
closed sets).

`expand(profile.vocabulary_set, semantic topic)` → ordered terms from the set
(respecting tone punctuation caps; tone `soothing` may not exclaim). Applied
to the final delivered phrase alongside the rendered frame — deterministic,
set-closed, never invented words.

---

## 3. Cross-Stage Data Contract

| Contract | Fields | Producer | Consumer |
|---|---|---|---|
| `SemanticVector` | intent, evidence∈[0,1], semantic∈[0,1], relevance∈[0,1], emotion_ref, gesture?, learning, world_load, partner | S1 | S2, S3, S4, S5, S8 |
| `PersonaPlan` | persona_id, tone_id, vocabulary_set, emotional_band, constraints, directives | S2 | S3–S8 |
| `ToneTargets` | expression, viseme, micro, pace (all within ceilings) | S3 | S4, S5, S8 |
| `EmotionWeights` | per-channel alpha + target lane | S4 | S5 |
| `FrameLanes` | expression, viseme, micro, anatomical (bounded) | S5 | S6 |
| `BlendPose` | smooth lanes + joints (bounded, no timestamps) | S6 | S7 |
| `RenderFrame` | channels, joints, pose, pace (device-agnostic) | S7 | render adapters |
| `VocabOut` | ordered term list + phrase | S8 | output text/voice |

All numeric fields clamped; no field may exceed `CHANNEL_MAX` per channel.

---

## 4. Worked Example (deterministic trace)

Context: **tutoring**; learner performance `0.68` vs target `0.80`; partner calm;
world-load `0.30`; gesture `null`; persona `calm`.

```
S1  evidence = clamp01(0.4*0.68 + 0.6*0.55) = 0.602
    semantic = 0.55   relevance = 0.80   emotion_ref = (0.15,0.10,0.002)
    -> SemanticVector(evidence=0.602, semantic=0.55, relevance=0.80, ...)

S2  persona=calm  -> band expr[0.15,0.40], step<=0.05, vocab assistive_base

S3  tutoring/low-curve  -> tone=warm -> baseline expr 0.30, viseme 0.18,
    micro 0.004, pace 0.65   (lane∩persona band -> expr target 0.32)

S4  alpha=0.35 (mirror)
    expr  = stable_lerp(0.20, 0.32, 0.35*0.15) = 0.206
    viseme= stable_lerp(0.12, 0.18, 0.35*0.10) = 0.122
    micro = stable_lerp(0.002,0.004,0.35*0.002)=0.002
    -> clamped inside calm band (expr<=0.40) -> keep

S5  semantic=0.55 -> mid bucket: expr 0.30, viseme 0.18, micro 0.004 (targets)
    E=0.006, M=0.003, V=0.002
    micro_out = 0.6*0.006 + 0.3*0.003 + 0.1*0.002 = 0.0047  (<=0.012 ✓)

S6  stable_exp_smooth per lane (monotone, no overshoot), step<=0.05,
    blend_pose compose, clamp -> BlendPose(expr=0.208, viseme=0.124,
    micro=0.0047, anatomical idle)

S7  RenderFrame(expression=0.208, viseme=0.124, micro=0.0047, pose=idle, pace=0.65)
    desktop payload written; native==headless signature asserted

S8  expand("assistive_base","encouragement") -> ["steady","try","next"]
    phrase: "Your progress is steady. Try the next example."
```

Same inputs → same frame + phrase on every device and every call.

---

## 5. Verification Contract

New suite `test_semantic_persona_expression.py`:

| Label | Asserts |
|---|---|
| `pipeline_semantic_vector` | extraction outputs all ∈[0,1], deterministic |
| `pipeline_persona_plan` | plan valid vs persona registry; fail-closed calm on unknown persona |
| `pipeline_tone_targets` | tone in band + ceiling, valid id only |
| `pipeline_emotional_weighting` | mirroring alpha respected, band-clamped, monotone |
| `pipeline_expression_mapping` | semantic→intensity bucket-bounded |
| `pipeline_math_blend_weights` | `TASK_BLEND_WEIGHTS == (0.6,0.3,0.1)`; micro blend exact |
| `pipeline_ceiling_bounds` | RenderFrame channels ≤ CHANNEL_MAX |
| `pipeline_step_caps` | persona step caps honored through S6 |
| `pipeline_device_parity` | native == headless frame signature |
| `pipeline_vocab_closed_set` | output terms ⊆ set; deterministic |
| `pipeline_end_to_end` | worked-example numbers reproduced exactly |
| `pipeline_suite` | module import + total parity |

---

## 6. Module Boundary Map

```
interaction (EXISTING) ── S1,S4 ──► pipeline.py (PROPOSED)
personality.py (EXISTING) ────────► S2 (persona plan source)
persona/{profiles,tone,emotion,vocabulary}.py (PROPOSED) ── S2,S3,S4,S8
Expression Engine L1/L2/L4 (PROPOSED) ────────────── S5
math_coordinator (EXISTING: blend_pose, TASK_BLEND_WEIGHTS) ── S6
rendering.py + deploy/ (EXISTING: RenderFrame, targets) ── S7
```

Dependencies run strictly downstream: no stage reads a later stage; `pipeline`
never mutates registries, world, or safety; ties into stabilization gating for
constrained deployments.