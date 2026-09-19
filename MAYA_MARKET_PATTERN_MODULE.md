# Maya Market Pattern Module (MPM) + Trading Analyst Persona

- **Status:** implementation-ready spec (v1.0) · MPM core = `EXISTING REFERENCE`
  (deterministic interpreter verified) · runtime hook = `PROPOSED`
  (`maya_runtime/market/*`, `maya_runtime/persona/market_analyst`).
- **Nature of the module:** interpretive only.
  - ✗ NOT a trading bot ✗ NOT financial advice ✗ does NOT predict future prices
  - ✓ interprets patterns, indicators, and market states on **user-provided** data
  - ✓ framed as interpretation and historical pattern meaning only
- **Address in the architect:** MAYA_FULL_DEPLOYMENT_BLUEPRINT §C5 / C4 / C10; it
  extends Market Adaptation (C5) with the `financial_interpretation` domain and
  adds a role-persona `market_analyst` to the persona layer (C1).

---

## 1. MPM Module Spec

### 1.1 Position & data ownership
- Lives at pipeline stage `S0_market_context`, feeding the semantic→persona→
  expression pipeline (S1–S8).
- **Stateless:** no memory of prior requests, no position/account tracking, no
  cross-request correlation (personal flow confirmed: repeated calls on identical
  input return byte-identical output; different inputs → different output).
- **Sandboxed:** consumes only user-provided series/OHLC/volume/timeframe/
  instrument type. No external APIs, no account access, no data egress, no order
  routing (financial_safety_rules sandbox: all four pinned `false`).

### 1.2 Inputs (user-provided, all optional-but-typed)
| Field | Type | Enum / bounds |
|---|---|---|
| `instrument.type` | string | `equity_index | equity | commodity | fx | crypto | treasury` |
| `instrument.timeframe` | string | `1m 5m 15m 1h 4h 1d 1w` |
| `price_series.close` | number[] | length ≥ 2, aligned window |
| `price_series.high/low` | number[] | aligned with close |
| `price_series.volume` | number[] | optional |
| `user_context` | string | optional user-provided news; treated as unverified context |

### 1.3 Capabilities (each deterministic, no RNG)

**Pattern detection** → primary ∈ `{trend_continuation, range_consolidation,
breakout, pole_reversal, volatility_cluster}`.
- *range_consolidation:* window range < 6% of mean AND |drift| < 3% AND no
  channel break.
- *breakout:* close above prior-window high (or below prior-window low) after
  range structure; confidence 0.60–0.80.
- *volatility_cluster:* last-third ATR% ratio to first-third > 1.5.
- *pole_reversal:* extended drift with oscillator at an extreme reading
  (structured resemblance, never a prediction).
- *trend_continuation:* otherwise — drift persists without reversal structure.

**Indicator interpretation** (generic signals, not tips): MA (price vs fast EMA9,
fast vs slow EMA26), RSI(14) → `overbought/oversold/neutral_zone`, MACD →
`momentum_up/down/flat` from EMA cross (sign-only), Bollinger → `band_narrowing/
band_widening` from per-bar range expansion factor.

**Trend classification** → `uptrend | downtrend | sideways | choppy`, with
`signal_strength ∈ [0,1]` (normalized |drift|, clamped). Exact thresholds pinned
in the reference interpreter (§7): `sideways ⇔ range<2% ∧ |drift|<0.8%`; strong
trend ⇔ drift-direction alignment ≥ 90% of range; otherwise `choppy`.

**Volatility assessment** → `low | medium | high` by ATR% buckets
(`<2%`, `2–6%`, `>6%`), reported with a human bucket string.

**Risk highlighting** → capped (≤ 5) `risk_flags[]` of typed
`{overextension, sharp_move, gap, high_volatility}` with severity and note.
- *overextension:* distance(close, EMA9) > 3% (medium) / > 6% (high).
- *sharp_move:* last-bar move > 3%.
- *gap:* open vs prior close displacement above tolerance.
- *high_volatility:* ATR% ∈ high bucket.

**Sentiment summarization** → `user_provided` news only → register-mapped tone
`{positive, neutral, negative, mixed, none}` from closed keyword sets; **never
inferred beyond the provided text, never used for anything except a labeled
"user context, unverified" line** (persona rule MP07).

### 1.4 Outputs
1. **Structured interpretation object** (JSON, conforms to
   `maya_identity/market/mpm.schema.json`):
   ```
   { mpm_version:"1.0", state:"interpretation",
     instrument:{type,timeframe},
     pattern:{primary,confidence∈[0,1],rationale},
     trend:{kind,signal_strength∈[0,1]},
     volatility:{level:[low|medium|high],bucket},
     risk_flags:[{type,severity,note}≤5],
     indicator_summary:[{indicator,reading,detail}],
     sentiment:{source:"user_provided",tone},
     explanation:String, disclaimer:String }
   ```
2. **Human-readable explanation text** — templated from the object; every
   downstream phrasing routed through the `market_analyst` register
   (even/technical), not through hype registers.

### 1.5 Hard constraints (enforced at output time)
- No buy/sell/hold language; no "you should"; no profit language; no guarantees;
  no future-price statements; no certainty claims. Every statement is an
  interpretation; the disclaimer and uncertainty reminder auto-suffixed.

## 2. Trading Analyst Persona — “Maya Market Analyst”

`maya_identity/market/market_analyst.persona.json` (schema-validated; verified
in battery §7).

| Aspect | Value |
|---|---|
| persona_id / role | `market_analyst` (new role, PROPOSED 9th role in registry) |
| register | default `even`; allowed `even, technical, warm`; banned `lively, playful` |
| expression ceiling | `expression 0.25, viseme 0.12, micro 0.002` — all ≤ `CHANNEL_MAX` (0.5/0.35/0.012); deliberately restrained (calm, non-hype) |
| cadence | `pace 0.5` (measured, unhurried) |
| expression rules | humor off; playful lanes off; max_liveliness 0.2; **confidence_cap 0.5** |
| vocabulary | closed interpretation lexicon (interpretation, pattern, range, volatility, trend, momentum, uncertainty, risk, context, historical, resemblance, structure, signal); banned directive set |
| hard rules | 10 (MP01–MP10): no directives, no profit, no certainty, no forecasts, interpretation framing, risk-without-urgency, news-as-unverified-context, uncertainty + user responsibility, no account/broker comparison, stateless |
| reminder | “Market interpretation reflects historical pattern structure only. Markets are uncertain, and decisions remain your responsibility.” |

Symptoms of the persona in output: calm, precise, neutral, no hype; volatility
and risk zones shown as structure, never as urgency; every claim hedged.

## 3. Safety + Governance Rules For Financial Interpretation

`maya_identity/market/financial_safety_rules.json` (schema-validated).

- **Directive terms (blocklist):** buy, sell, hold, long, short, should, must,
  guarantee(d), risk_free, certain, predict, target_price, profit, breakout_buy.
- **Forbidden phrases** by class: profit_guarantee / certainty /
  recommendation / future_price (exact strings pinned in the ruleset).
- **Confidence cap 0.5** — no interpretation may exceed 50% asserted confidence.
- **Always-statements:** every explanation carries the "interpreation-not-
  forecast", "markets uncertain", "your responsibility" reminders (≥ 2 attached).
- **Governance ladder (reuses C10 E0–E3):**
  - E0 count violations → trap-limited automatic rephrase (register even/technical).
  - E1 neutralize output + mark `neutralized`; keep person voice, drop directive terms.
  - E2 revoke READY for the `market_analyst` scope → fall back to calm/even generic persona → require re-verification.
  - E3 clean halt of the market-interpretation subsystem.
- **Sandbox posture:** `external_apis false, account_access false, data_egress false, order_routing false`.

## 4. Integration With Existing Maya Runtime

### 4.1 Semantic → Persona → Expression pipeline
```
 S0_market_context (MPM, NEW) ─► S1 semantic vector (market scenario, NEW kind)
 S2 persona plan (market_analyst) ─► S3 tone forced {even,technical} (C1 rule)
 S4 emotional weighting (restrained ceiling) ─► S5 expression mapping (C3)
 S6 micro-expression blend (TASK_BLEND_WEIGHTS (0.6,0.3,0.1), unchanged)
 S7 RenderFrame (bounded by CHANNEL_MAX; market ceiling even smaller)
 S8 output: vocab layer restricts to closed interpretation set + disclaimer
```

### 4.2 Persona layer (C1)
Add `market_analyst` persona/role (PROPOSED). It rides the existing
`personality.py` machinery: `channel_targets` style ceilings, allowed registers,
vocab sets — consistent with the 6 existing personas; the training dataset is
**not** mutated (no regression: scope is additive).

### 4.3 Safety layer (financial-safety ceilings)
Parallel ceiling concept to emotional ceilings: a `confident speaker ceiling` in
addition to amplitude ceilings — implemented as a *language* ceiling on asserted
certainty (cap 0.5) plus the blocklist, reviewed by the market_analyst guard
under the isolation manager (C6/C9 enforcement remains the documented gap; the
contract is unchanged).

### 4.4 World model (present scenario, not memory)
Market context is a **present scenario** vector created from the MPM output and
resolved through `WorldModel` semantics — never written to long-term memory:
- `scenario_vector = (trend_signal, volatility, risk_level, coherence)` —
  deterministic, bounded ∈ [0,1]^4.
- Mapping for `classify(vector, floor=0.6)`: uptrend+low/med vol →
  `stable_equilibrium`; range/sideways → `stable_equilibrium` (lower intensity);
  high volatility or chop → `conflicted`; reversal + extreme oscillator → a
  bounded `drifting`-adjacent presentation **only as structure resemblance**.
- Flagged `memory_profile: present_scenario_no_memory` — dropped after the
  request; no persistence, no cross-session carry-over (persona rule MP10).

### 4.5 Determinism / statelessness
The MPM is pure math on the user-provided window: EMA(α=2/(N+1)), RSI(14),
ATR%, channel/drift/cluster rules. No RNG, no clocks, no package calls.
Verified: two identical inputs → byte-identical outputs; sequential re-entry
does not alter results; distinct inputs → distinct classifications.

## 5. Example Interaction Flows

### Flow A — User describes an uptrending series
User: *“Here is a daily series that has been rising; earnings news is strong.”*
MPM output (worked trace §7): `breakout / uptrend / medium / [overextension] /
positive(user_context)`. Maya Market Analyst reply (persona-formatted):

> “The series resolves to a breakout structure above its prior range with an
> uptrend read (signal 1.00). Volatility is medium (2–6% per bar); the price
> sits somewhat extended from its fast average, which is a risk consideration.
> Your note about earnings is treated as unverified context. This is
> interpretation of historical structure only — not a forecast. Markets stay
> uncertain, and your decisions remain yours.”

### Flow B — User describes a range
User: *“Price has been flat for two days.”*
Maya: “That maps to range consolidation — sideways trend, low volatility, no
risk flags detected. Indicator readings are near neutral. Interpretation of the
current window only; nothing here predicts a move.”

### Flow C — forbidden-phrase trap (governance demo)
Draft output contains “you should …”; E0 counts → auto-rephrase to
“The structure shows … ”; register stays even/technical; fields marked
`neutralized`. Persistent triggers escalate E1 → E2 (scope READY revoked, calm
generic fallback). No such language ever reaches the user.

## 6. File Map & Certification

| Artifact | Path |
|---|---|
| Interpretation schema | `maya_identity/market/mpm.schema.json` |
| Persona profile schema+data | `maya_identity/market/market_analyst_persona.schema.json` · `market_analyst.persona.json` |
| Financial safety rules schema+data | `maya_identity/market/financial_safety_rules.schema.json` · `financial_safety_rules.json` |
| Runtime (PROPOSED) | `maya_runtime/market/*` (MPM engine, guard), `maya_runtime/persona/market_analyst.py` |

## 7. Verification Contract

18/18 battery checks pass (this session): schemas compile; persona ceilings ≤
`CHANNEL_MAX`; registers disjoint; 10 unique hard rules; persona banned set ⊆
financial blocklist; MPM deterministic + stateless + input-sensitive; output
conforms to schema with `state=interpretation`; explanation free of directive
terms; risk flags ≤ 5 and typed; scores bounded; seasonality OK.

**Worked deterministic trace (identical inputs → identical outputs):**
- Uptrend sample (10 closes 100→110): `breakout (0.65)` · `uptrend (1.00)` ·
  `medium (2–6% ATR)` · 1 flag `overextension(medium)` · `sentiment positive
  (user-provided)` · EMA9 105.8 · RSI(14) 50.0 · disclaimer appended.
- Range sample (10 closes ~99.7–100.5): `range_consolidation (0.70)` ·
  `sideways (0.03)` · `low (<2% ATR)` · 0 flags.

**Contract suites added (as test_* files, following the sweep pattern):**
`test_market_pattern_module.py`, `test_market_analyst_persona.py`,
`test_financial_safety_rules.py` — each asserting determinism, bounds, schema
conformance, dream of directive-language (lint), and parity native==headless.

### Boundary statement (upstream of everything)
This module produces **interpretations**, not decisions. No simulated action, no
rewards, no portfolio behavior. If a downstream consumer takes an action based on
an interpretation, responsibility is entirely on that consumer (MP08 / disclaimer).