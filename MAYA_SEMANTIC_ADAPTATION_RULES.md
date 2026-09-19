# Maya Semantic Adaptation Rules — Modular Ruleset

- **Status:** Specification (v1.0) + machine-readable rule registry
- **Artifacts:**
  - Schema: `maya_identity/adaptation/semantic_adaptation_rules.schema.json`
  - Registry: `maya_identity/adaptation/semantic_adaptation_rules.json` (26 rules, validated)
- **Alignment:** the six modules mirror the Market Adaptation Layer (M1–M6
  input, M7 output shaping); this document is the **executable rule layer**
  with precedence and fail-closed semantics.

---

## 1. Modular Grouping & Priorities

| Module | Id prefix | Scope | Default priority |
|---|---|---|---|
| Slang normalization | `SA.SL` | input text | 1–3 |
| Dialect detection | `SA.DL` | input text | 1–3 |
| Tone inference | `SA.TN` | intent → tone | 2–5 |
| Language routing | `SA.LG` | packs / mixed-language | 1–3 |
| Cultural cue interpretation | `SA.CU` | region cues / taboo | 2–5 |
| Output shaping | `SA.SH` | output phrasing | 1–5 |

Rule fields: `id`, `rule`, `condition`, `action`, `fallback`, `deterministic`,
`priority`. `deterministic` is pinned `true` for every rule (schema-enforced).

## 2. Ruleset Summary per Module

### 2.1 Slang (SA.SL.1–5)
Known slang → canonical terms within the active vocabulary set; **unknown slang
is flagged, never guessed**; numbers/dates/names/IDs pass through unchanged;
normalization applied once in fixed table order; question intent preserved.

### 2.2 Dialect (SA.DL.1–4)
Signed featural score → best `dialect_id` with bounded confidence; low
confidence → `neutral`; single-feature evidence kept conservative; register hint
forwarded to tone inference.

### 2.3 Tone (SA.TN.1–4)
Tone from **explicit surface cues only** (no sarcasm/speculation); urgency
forces even/soothing + `exclaim=false` (priority 5); low-confidence candidates
fall back to the persona default tone.

### 2.4 Language (SA.LG.1–4)
BCP-47 primary pack by dominant segment; secondary-language terms bounded to
registered packs only; unsupported → `en-fallback` + `mix_flag` (never guess);
numbers/dates localized per pack from a fixed table.

### 2.5 Culture (SA.CU.1–4)
Region-table greetings/honorifics → cue + formality band; **taboo terms flagged
and never echoed, escalated to safety_monitor** (priority 5); cues recorded
without asserting cultural meaning; formality band caps output register.

### 2.6 Shaping (SA.SH.1–5)
Output terms ⊆ active vocabulary set (priority 1); register capped by
persona+tone punctuation rules; urgency flattens register downward only;
**no humor in urgent/taboo contexts**; any failure → calm/even phrase with
anomaly record.

## 3. Precedence & Conflict Resolution

1. Higher `priority` wins; ties resolve in table order (documented, deterministic).
2. Module ordering is fixed: `slang → dialect → tone → language → culture`, with
   `shaping` applied last on the output side.
3. **Overrides (priority 5) always win:** `SA.TN.3`, `SA.CU.2`, `SA.SH.3`,
   `SA.SH.4`, `SA.SH.5` — urgency, taboo, and fail-closed can flatten or replace
   any other rule's result.
4. No rule may raise register/amplitude beyond persona bounds (downward-only).

## 4. Determinism & Fail-Closed Guarantees

- All 26 rules are pinned `deterministic: true`; the registry is frozen at load.
- Same input + same active persona + same context ⇒ same rule trace on every
  device (native == headless parity).
- Every rule has an explicit `fallback`; the degenerate path converges to
  neutral canonical phrasing (calm/even) rather than an exception.
- Rule violations surface as anomalies through the stabilization self-check.

## 5. Verification Contract

New suite `test_semantic_adaptation_rules.py`:

| Label | Asserts |
|---|---|
| `adaptation_schema_compile` | schema compiles (draft-07) |
| `adaptation_registry_valid` | registry validates; modules exactly 6 |
| `adaptation_deterministic` | all rules deterministic; ids unique |
| `adaptation_slang` | SL.1–SL.5 behaviors verified |
| `adaptation_dialect` | DL.1–DL.4 behaviors verified |
| `adaptation_tone_force` | TN.3 urgency forces even/soothing, exclaim=false |
| `adaptation_language_route` | LG.1–LG.4 routing + en-fallback |
| `adaptation_culture_taboo` | CU.2 flags and never echoes; escalates |
| `adaptation_shaping_closed` | SH.1 output terms within vocab set |
| `adaptation_priority` | priority-5 rules override lower tiers |
| `adaptation_fail_closed` | any error → calm/even phrase |
| `adaptation_parity` | identical rule trace native == headless |
| `adaptation_suite` | module import + total label parity |

## 6. Traceability

- Market Adaptation Layer (interfaces) → this ruleset (executable rule layer).
- TONE_RULES, VOCABULARY_SETS, persona bounds (Persona Layer / calibration) →
  SA.TN, SA.SH guardrails.
- SAFETY_MONITOR → SA.CU.2 escalation; governance neutralization → SA.SH.5.