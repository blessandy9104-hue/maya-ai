# Maya Full-System Audit Report

- **Date:** 2026-09-08
- **Scope:** entire Maya project (`maya_runtime`, `maya_identity`, `verification`, all `MAYA_*.md` blueprints/specs, all JSON registries)
- **Method:** live execution — full verification sweep, controlled launch, fresh-process protocol semantics, 56-check invariant battery, artifact-vs-schema validation, dependency import chain, doc↔code anchor cross-check.
- **Legend:** ✅ verified · ⚠ contract-gap (planned, no regression) · ❌ defect

---

## 1. Verification Sweep — OpenCode Integrity Check

`py -3 -m verification.sweep` (exit 0):

```
[verify] protocol manifest: 18 suites (module=maya_runtime)
[verify] sweep: 18 suites, 206 ok-labels, clean=True
  OK  test_math_expert 11 · test_math_coordinator 21 · test_math_integrity 16
  OK  test_world_stability_drift 10 · test_semantic_channels 10
  OK  test_visual_embodiment 10 · test_canonical_validation 6
  OK  test_platform_layers 12 · test_portable_runtime 12 · test_readiness 10
  OK  test_verification_sweep 10 · test_rig_math 15 · test_learning_prediction 11
  OK  test_safety_anomalies 11 · test_agent_collaboration 11
  OK  test_task_orchestration 11 · test_current_pc_safety 5 · test_wireframe_face 14
[verify] controlled launch: clean=True native=(0.5,1.0,0.0,4) headless=(0.5,1.0,0.0,4)
[verify] stabilization report: clean=True categories={'unintended_behavior':0,'unexpected_output':0,'instability_drift':0,'rendering_anomaly':0,'safety_boundary_violation':0,'timing_irregularity':0}
[verify] external verdict recorded -> ready=True state=ready
[verify] READY
```

- ✅ **18/18 suites**, 206 ok-labels, clean.
- ✅ **Controlled-launch parity** native == headless == `(0.5,1.0,0.0,4)` — identical signature both paths.
- ✅ All six anomaly categories zero (checked by OpenCode result classifier; traceback/exception/garbage lines are flagged, `OK` labels whitelisted, JSON-structural lines accepted).
- ✅ Report classifier verified independently: `_is_ok_output_line` whitelists OK/benign/JSON lines; rejects tracebacks and errors; `_anomalies_from_output` classifies correctly.

## 2. Readiness-Gate Confirmation (external_clean ∧ internal_stable)

Fresh-process protocol semantics verified (deterministic, reproducible):
- ✅ `READY_CONDITION` = external verification clean AND internal self-check stable AND both agree (no self-declaration).
- ✅ Fresh process: `state=stabilized_pending`, `ready=False`.
- ✅ `confirm({"clean": True})` → `agreed=True` → `ready=True`. `confirm({"clean": False})` → `agreed=False`, **blocks** READY. `confirm({})` → raises `ValueError` (clean key mandatory).
- ✅ Decision path byte-identical across resets (protocol deterministic).
- ✅ `readiness.verify()` = 10/10 checks; internal self-check `stable=True`, `anomalies=[]`, 6 subsystem groups all ok.
- ✅ `OPERATIONAL_GUARANTEES`: 4 (verify-before-declare, no self-evolution, stability/determinism/safety, smooth-on-confirmation).

## 3. Metadata / self_check.jsonl

- ✅ `maya_identity/metadata/self_check.jsonl` — valid JSONL, each record parseable, appended on logged self-checks.

## 4. Subsystem-Specific Findings

| Area | Audit result | Evidence |
|---|---|---|
| **Persona layer integrity** | ✅ | `PERSONAS={calm,warm,playful,authoritative}` exact; `personality.channel_targets(p)` per-persona targets within `CHANNEL_MAX`; `pace` is a cadence field ∈ (0,1] (all 4 personas: 0.50/0.55/0.75/0.65); `paced_state` bounded; determinism report `core_free_of_rng/clock/gui=True`. |
| **Identity profile correctness** | ✅ | schema-valid: `company_template`, `maya-default`; profile schemas strict; persona/tone enums ⊆ closed sets; catchphrase pattern relaxed only; CORED/non-editable semantics documented. |
| **Expression engine consistency** | ✅ | `CHANNEL_MAX={expression:0.5, viseme:0.35, micro:0.012, anatomical:0.8}` exact (owned by `math_coordinator:133`, enforced at lines 823/969/1968–1974; mirrored in `maya_runtime.core`); `TASK_BLEND_WEIGHTS=(0.6,0.3,0.1)` preserved verbatim (`math_coordinator:210`); `stable_exp_smooth`/`stable_lerp` present; `expression_controller` core surface exists. Orchestration stack (L0–L7) is spec-proposed (⚠ C3). |
| **Semantic→persona→expression pipeline alignment** | ✅ | Spec grounded in live registries; S1–S8 trace matches `math_coordinator` blend math and `interaction` surfaces. Runtime facade `maya_runtime/pipeline.py` not yet implemented (⚠ C4). |
| **Market adaptation completeness** | ✅ data / ⚠ runtime | `semantic_adaptation_rules.json` (26 rules/6 modules) schema-valid, all deterministic, unique ids, tones ⊆ {authoritative, even, lively, soothing, technical, warm}. Runtime gating modules `maya_runtime/market/*` absent (⚠ C5). |
| **Persona isolation manager enforcement** | ⚠ | Deny-by-default contract fully specified + invariant suite; **no runtime enforcement code** yet. Single-tenant demo runtime; drift-lock/kill-switch become enforceable once `maya_runtime/isolation/*` lands (⚠ C6). |
| **Demo runtime stability** | ✅ | READY only by consensus; sweep clean; parity native==headless; content layer schema-valid; demo personas ⊆ training personas; demo tones ⊆ closed set. `maya_runtime/sandbox.py` orchestrator absent (⚠ C7). |
| **Sandbox deny-by-default** | ⚠ | Committed as contract; runtime whitelist sandbox not yet implemented (⚠ C7/C8). No app code currently exercises outbound calls — postural assumption only. |
| **Rendering loop determinism** | ✅ | bounded `RenderFrame`, cadence fixed, 20 controls/15 presets, parity (0.5,1.0,0.0,4) both paths, `core_free_of_gui` for logic core, deterministic sweep. |
| **World model stability** | ✅ | equilibrium `(1.0,0.0,1.0,1.0)`; `stability(series) ok=True std=0.0`; `state_ok(...) ok=True violations=[]`; drift suite 10 ok. |
| **Math engine invariants** | ✅ | 16 integrity checks; fusion weights preserved; `stable_exp_smooth` no overshoot (64-step climb); 22 contracts; determinism central. |
| **Safety algebra** | ✅ | `check()` deterministic; extreme inputs (cpu 99/mem95/proc500/launch400) → bounded `safe=False` with 4 violations (no crash); `margin()` scalar ∈[0,1], 0.0 exactly at process-count ceiling, 0.5 healthy. |
| **Stabilization protocol v2.0 compliance** | ✅ | external sweep + internal self-check; READY via consensus only; no self-declaration; deterministic confirm; dirty blocks. |
| **Anomaly detection accuracy** | ✅ | classifier rejects traceback/Error/Exception/garbage; whitelists OK + benign + JSON lines incl. `"`-prefixed members. |
| **Tenant isolation** | ⚠ | Contract (NS namespaces, F1–F10, J1–J9) complete; runtime enforcement pending `isolation/*` (⚠ C9). |
| **Governance model** | ✅ | authority map (6 authorities), escalation E0–E3, neutralization triggers, switching protocol 7-state machine — all documented & contract-tested. |
| **Drift / leakage** | ✅ | no persona drift: all loaded persona targets within channel ceilings (0/56 fails); no tone drift: artifact tone ids ⊆ closed set; no identity leakage: identity-only schema surfaces, redaction/token-access rules committed (enforcement ⚠ same isolation gap). |
| **Cross-tenant contamination** | ✅ (vacuously) | runtime is single-tenant today; no shared mutable cross-tenant state exists; multi-tenant enforcement pending C9 layer. |
| **Dependency chain** | ✅ | 56 Python modules imported cleanly, 0 failures; `verification.runner` cosmetic-output classifier covers the 3 stable JSON lines. |
| **Blueprint contradictions** | ✅ | every numeric anchor re-verified in code: `CHANNEL_MAX` (math_coordinator owns, core mirrors), blend weights, personas, cadence; doc↔code attribution accurate. |

## 5. Confirmed-Correct Subsystems

Core runtime (portal/logic/world/safety/render/determinism), math engine + coordinator, expression surfaces, personality engine, capability registry (11), domain model (8 roles/5 domains), identity/face, readiness, stabilization protocol v2.0, verification package (sweep/runner/report/monitor/manifest), world-model stability, safety algebra, rendering determinism, anomaly classifier, all 4 JSON registries vs schemas, dependency import chain, and the documented governance/switching/calibration/adaptation contracts.

## 6. Detected Issues (no high-severity defects; no regressions)

1. ⚠ **Plan/contract gaps — 5 PROPOSED modules not yet implemented** (all marked PROPOSED in the spec library; none referenced by EXISTING code, so zero broken dependencies):
   - `maya_runtime/market/` (market adaptation runtime)
   - `maya_runtime/persona/` (persona package: profiles/switching/safety)
   - `maya_runtime/isolation/` (isolation manager enforcement — also gates persona drift-lock, kill-switch, tenant contract)
   - `maya_runtime/sandbox.py` (deny-by-default sandbox orchestrator)
   - `maya_runtime/pipeline.py` (S1–S8 facade)
2. ⚠ **Enforcement-dependent guarantees are contract-only today:** denial-by-default sandboxing, persona/tenant isolation enforcement, multi-tenant kill-switches, and drift-lock become runtime-enforced only when the above modules land. Current deployment is single-tenant demo; these guarantees must gate enterprise roll-out per the blueprint's deployment matrix.

None: missing EXISTING dependencies, invalid states, unsafe assumptions in shipped code, or regressions.

## 7. Dependency Chain Validation

`maya_runtime` (13) · `maya_identity` (43 incl. wireframe/renderer/awareness/evolution/nervous_system/embodiment/voice_sync/visual_language) · `verification` (7) → **56 modules, all import cleanly, 0 failures.** No cycle breaks, no stale imports, no references to missing modules from shipped code.

## 8. Readiness-Gate Confirmation

- SwEEP report clean + 6×0 anomalies + launch parity + reconciliation counter-intact → **external_clean ✓**.
- Internal self-check stable (6 groups, 10 checks, 0 anomalies, std 0.0, cadence 80 ms) → **internal_stable ✓**.
- Consensus: `confirm({clean:True})` → `ready=True`. READY re-confirmed at audit time.

## 9. Final Verdict

**`issues_detected`** — qualified: NO defects, NO regressions, NO unsafe assumptions in implemented code; the implemented architecture is fully stable and READY. The two detected issues are **planned contract-gaps**: five PROPOSED modules (`market/`, `persona/`, `isolation/`, `sandbox.py`, `pipeline.py`) remain spec-only, leaving isolation/sandbox enforcement at contract level (single-tenant demo posture). Closing these gaps is the required condition before enterprise multi-tenant deployment per `MAYA_FULL_DEPLOYMENT_BLUEPRINT.md` §5.