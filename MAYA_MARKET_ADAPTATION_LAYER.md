# Maya Market Adaptation Layer — Architecture Specification

- **Status:** Specification (v1.0) — modular subsystem with clear interfaces
- **Package (PROPOSED):** `maya_runtime/market/`
- **Input-side:** normalizes and classifies what humans send to Maya.
  **Output-side:** shapes Maya's register inside persona + vocabulary bounds.
- **Principles:** deterministic, table-driven (no runtime model invocations,
  CPU-light), closed-vocabulary, fail-closed, and persona-consistent — the layer
  adapts *presentation*, never identity, math, safety, or architecture.

---

## 1. Position in the Stack

```
 human input ──► M1 Slang Normalization
                  M2 Dialect Detection
                  M3 Language Routing           input-side gate
                  M4 Tone Inference
                  M5 Cultural Cue Interpretation
                  M6 Urgency Detection
                          │
                          v
          normalized / classified context
                          │
     Semantic → Persona → Expression pipeline  (S1 uses normalized text;
                          │                     S3 tone can be overridden
                          v                     by M4/M6; S8 uses M7)
          M7 Persona-Consistent Output Shaping
                          │
                  shaped phrase ──► text / voice / UI
```

M1–M6 run on the **input**; M7 runs on the **output**. The layer never invents
meaning, never guesses culture, and never lets register exceed the persona's
bounds.

---

## 2. Module Map (all PROPOSED)

| Module | Responsibility | Key interfaces | Depends on |
|---|---|---|---|
| `market/__init__.py` | facade `process(in_text, persona, context) -> MarketGate`; orchestrates M1–M7 | `process()` | all modules |
| `market/slang.py` | slang → canonical lexicon; unknown → flagged ellipsis | `normalize(text, vocabulary_set)` | vocab sets |
| `market/dialect.py` | region/dialect probe (rule-based feature match) | `detect(text) -> DialectProbe` | — |
| `market/language_router.py` | BCP-47 pack registry, incl. mixed-language routing | `route(text, probe) -> LanguageRoute` | dialect |
| `market/tone_inference.py` | input tone → candidate tone id | `infer(text, persona, route) -> ToneInference` | personas, tones |
| `market/culture.py` | cultural cue interpretation (bounded, non-guessing) | `interpret(text, route, tone) -> CulturalCues` | route |
| `market/urgency.py` | bounded urgency scalar + class | `detect(text, route) -> Urgency` | SAFETY_MONITOR |
| `market/shaping.py` | register shaping inside persona bounds | `shape(phrase, persona, tone, route, urgency) -> ShapedOutput` | vocab sets, tone |

---

## 3. Data Contracts

| Contract | Fields | Producer | Consumer |
|---|---|---|---|
| `NormalizedText` | `canonical_text`, `replacements[]`, `unknown_tokens[]`, `gaps_flag` | M1 | M2–M5, pipeline S1 |
| `DialectProbe` | `dialect_id`, `register`, `confidence` (identity-format, ∈[0,1]), `features[]` | M2 | M3, M4 |
| `LanguageRoute` | `route_id`, `pack_id` (BCP-47), `secondary_pack?`, `mix_flag` | M3 | M4, M5, M6, M7 |
| `ToneInference` | `tone_id`, `cues[]`, `priority` (`forced`, `suggested`) | M4 | S3 |
| `CulturalCues` | `flags[]`, `honorific_hint?`, `formality_band`, `taboo_flags[]` | M5 | M7, safety |
| `Urgency` | `u` (∈[0,1]), `class` (`calm`/`attentive`/`urgent`) | M6 | S3, safety_monitor |
| `ShapedOutput` | `phrase`, `terms[]` (⊆ vocab set), `register`, `exclaim` (bool) | M7 | pipeline S8 / voice |
| `MarketGate` | union of all above + `accepted`/`blocked` | facade | pipeline |

Numeric fields are clamped; every classification carries a confidence; no field
is derived from wall-clock time or RNG.

---

## 4. Interfaces (modular subsystem)

### M1 · slang.normalize
```
normalize(text: str, vocabulary_set: str) -> NormalizedText
```
- Lexicon-driven, frozen table: `gonna→going to`, `idk→I don't know`,
  `u→you`, `k/kk→okay`, `brb→be right back`, … canonical forms must belong to
  the active vocabulary set's scope.
- Unknown slang/typo → `unknown_tokens[]` appended, `gaps_flag=True`; output
  text keeps the canonical form and flags — **never invented**.
- Pure function; identical output on every device.

### M2 · dialect.detect
```
detect(text: str) -> DialectProbe
```
- Rule-based featural matching (spellings, contractions, particles): e.g.,
  `en-US`, `en-GB`, `en-IN` register variants.
- `confidence` = signed feature match; lowest observed → `dialect_id='neutral'`.
- No model calls; CPU-light; deterministic.

### M3 · language_router.route
```
route(text: str, probe: DialectProbe) -> LanguageRoute
```
- Pack registry keyed by BCP-47 (`en`, `en-GB`, `hi`, `es`, `ar`, …) —
  packs may reuse an existing translation/pack registry if present.
- **Mixed-language routing:** dominant segment → primary pack; secondary packs
  recorded; output uses primary pack and may echo bounded secondary terms only
  from a registered pack.
- Unsupported language → `route_id = pack:en-fallback` + `mix_flag=True` (flag,
  never guess).

### M4 · tone_inference.infer
```
infer(text: str, persona: PersonaPlan, route: LanguageRoute) -> ToneInference
```
- Input cues (politeness, frustration, formality) map to candidate tone id
  within `TONE_RULES`; priority `suggested` unless urgency overrides → `forced`.
- Confidence-gated: at or below floor → persona default tone.

### M5 · culture.interpret
```
interpret(text: str, route: LanguageRoute, tone: ToneInference) -> CulturalCues
```
- Bounded cue recognition: greeting/honorific patterns, formality bands, date
  order, punctuation clusters, taboo terms (→ `taboo_flags[]` and **never
  echoed**; escalated to `safety_monitor`).
- Interpretation only — never asserts culture, never adapts meaning, no
  fabrication. All cues within route's region table.

### M6 · urgency.detect
```
detect(text: str, route: LanguageRoute) -> Urgency
```
- Lexical + structural signed signals → `u` scalar.
- Bands: `calm u<0.33` · `attentive 0.33≤u<0.66` · `urgent u≥0.66`.
- `urgent` → forced tone `even`/`soothing` (respecting persona de-escalation
  constraint), `exclaim=False`, and synchronous escalation record to
  `safety_monitor` — urgent speech is never voiced with playful register.

### M7 · shaping.shape
```
shape(phrase: str, persona: PersonaPlan, tone: ToneInference,
      route: LanguageRoute, urgency: Urgency) -> ShapedOutput
```
- Re-frame output strictly from the active vocabulary set (`expand` terms only).
- Register band = persona + tone + formality band from M5; punctuation caps per
  tone (e.g., lively ≤3, soothing ≤1, even ≤1, technical 0).
- Urgent band → shortest canonical phrasing, no exclamation, no slang.
- Guarantee: output never exceeds persona's bounds; `terms[] ⊆ vocabulary_set`; fail-closed returns the neutral `calm/even` phrasing.

---

## 5. Flow Diagram (M1–M7)

```
  in_text ─────────► M1 normalize ──► M2 detect ──► M3 route
                              │                     │
                              ▼                     ▼
                        M4 tone inference ──► M6 urgency (→ SAFETY_MONITOR)
                              │                     │
                              ▼                     ▼
                        M5 cultural cues      forcing (even/soothing)
                              │                     │
                              └────────┬────────────┘
                                       v
                              M7 shape ──► ShapedOutput ──► S1/S3/S8 pipeline
```

Every arrow is interface-pure; M7 is the only writer to output.

---

## 6. Safety & Determinism Invariants

1. All mappings frozen at import; no RNG, no model inference, no wall-clock.
2. Unknown input token, dialect, language, or cultural marker → explicit flag
   + canonical fallback; nothing guessed, nothing invented.
3. `taboo_flags` and `urgent` escalate to `safety_monitor` verbatim; they are
   never voiced or echoed.
4. Output register is capped by persona; urgency can only flatten register
   (never raise it above persona bounds).
5. `MarketGate` feeds only presentation/S1 context — it cannot mutate persona,
   capabilities, world model, stabilization, math, or safety thresholds.
6. Cross-device parity: `process(in_text, persona, context)` returns an
   identical `MarketGate` on every platform (asserted in tests).

---

## 7. Verification Contract

New suite `test_market_adaptation.py`:

| Label | Asserts |
|---|---|
| `market_slang_normalization` | canonical replacements; unknown token flagged; deterministic |
| `market_dialect_detection` | probe ids + confidence bounded; neutral fallback |
| `market_language_routing` | primary/secondary pack resolution; fallback flag on unsupported |
| `market_mixed_language` | dominant segment routes primary; bounded secondaries |
| `market_tone_inference` | candidate tone within TONE_RULES; persona default on low confidence |
| `market_cultural_cues` | cues bounded; taboo flagged and never echoed |
| `market_urgency_bands` | u in [0,1]; class thresholds exact; escalation recorded |
| `market_urgency_tone_force` | urgent → even/soothing forced, exclaim=False |
| `market_shaping_closed_set` | output terms ⊆ vocabulary set |
| `market_autho_force` | urgency cannot raise register above persona bounds |
| `market_parity` | native == headless MarketGate for same input |
| `market_suite` | module import + label parity |

---

## 8. Module Boundary / Dependencies

```
input text
   └─ M1 slang.py      (vocab sets)
       └─ M2 dialect.py
           └─ M3 language_router.py (pack registry)
               ├─ M4 tone_inference.py (personas, TONE_RULES)
               ├─ M5 culture.py       (route table)
               └─ M6 urgency.py       (safety_monitor, tones)
   └─ M7 shaping.py    (vocab sets, tone, urgency, persona)
   └─ market/__init__.py :: process → MarketGate
```

The layer is downstream-agnostic: `MarketGate` is consumed by the Semantic →
Persona → Expression pipeline (S1 normalized text, S3 tone override, S8 output
shaping) and by safety monitoring, with no reverse dependency.