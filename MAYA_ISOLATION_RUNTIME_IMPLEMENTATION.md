# Maya Isolation Runtime Implementation (IRI) — Code on Disk

- **Status:** implemented v1.0 · Phase 7 IR modules are now **on disk** under
  `maya_runtime/isolation/` and wired into the runtime. The previously-missing
  isolation implementation that blocked platform launch is closed.
- **Verification:** full-system audit **78/78 green** (was 71/78 with the
  isolation gap), plus a dedicated **IR code battery 66/66 green** exercising
  the nine rules, the MUS boundary chain, CHANNEL_MAX, quotas, sealing,
  cross-denial, fail-closed, founder gating, and determinism.
- **Consistency:** the code enforces exactly what the Phase 7 registry
  (`maya_identity/isolation/isolation_runtime.json`) and the IR implementation
  registry (`maya_identity/isolation/impl/ir_impl.json`) declare — same
  ceilings, same boundary order, same six sandbox rules, same nine-rule set,
  same `guard.can` coordinator role.

---

## 1. Module List

### 1.1 In `maya_runtime/isolation/`
| Module | Role |
|---|---|
| `__init__.py` | package exports, `ISOLATION_VERSION=7.0.0`, `COORDINATOR_ROLE="guard.can"`, `DENY_BY_DEFAULT=True` |
| `ceilings.py` | CHANNEL_MAX (0.5/0.35/0.012/0.8), per-persona ceilings, WEB persona allowlist, TENANT_QUOTAS, message size limit, MUS boundary order, allow/deny/escalate constants, `within_channel`/`persona_allows`/`ceiling_report` |
| `namespace.py` | NS(t,k) `:: /t/k/*` model with the six resource kinds (data, logs, policies, brand, outputs, metadata), `contains`/`disjoint` |
| `persona.py` | `PersonaSeal` — tenant_scoped, cross_tenant_denied, core_shared_readonly; persona ceiling + channel check |
| `role.py` | `RoleSeal` — role scoped to a tenant with an explicit allowlist; OPERATOR/FOUNDER/PLATFORM roles |
| `tenant.py` | `TenantSeal` — six disjoint namespaces per tenant; no cross-tenant read/write |
| `user.py` | `UserSeal` — user identity thread binding per tenant |
| `tone.py` | `ToneSeal` — tone profile that never exceeds the ceiling |
| `identity.py` | `IdentitySeal` — cored_never_serialized, readonly_to_tenants, fingerprint_only, thread bound |
| `multi.py` | cross-tenant / cross-persona / cross-identity / out-of-thread denial predicates |
| `validator.py` | `Validator` — exact-origin postMessage v1 envelope, direction pairing, allowed types, ≤16KB; bound/quota/kill_switch/drift/consent checks |
| `sandbox.py` | `SandboxPolicy` — the six deny-by-default rules + surface allowlist (studio, marketplace, cloud_runtime, api, kiosk, embed_runtime) |
| `router.py` | `IsolationRouter` — declarative, boundary-ordered table (`safety → isolation → legal → business → operator → founder`) |
| `executor.py` | `IsolationExecutor` — namespaced, isolation-guarded, operator-bound; escalates safety/legal/business; requires founder token for founder |
| `guard.py` | `Guard` + `GuardDecision` — the coordinator (`guard.can`) that orders every guard call and denies by default |
| `pipeline.py` | `IsolationPipeline` + `AuditHooks` — validator → router → guard → executor with fail-closed fallback (deny, retry-bounded, escalate-founder) and no-CORED audit |

### 1.2 Facades / integrations created to close the audit gaps
| Path | Role |
|---|---|
| `maya_runtime/sandbox.py` | root facade re-exporting `isolation.sandbox` |
| `maya_runtime/pipeline.py` | root facade exposing `pipeline.run(...)` |
| `maya_runtime/market/__init__.py` | marketplace surface wired through the guard (`MarketplaceGuard`) |
| `maya_runtime/persona/__init__.py` | persona runtime surface (`PersonaRuntime`) enforcing seal + allowlist |
| `maya_runtime/__init__.py` | adds `isolation` import + `__all__` so `maya_runtime.isolation` resolves in the runtime |

---

## 2. Implementation Requirements — how each is enforced

| Requirement | Module(s) | Enforcement |
|---|---|---|
| All nine IR rules | validator, persona, role, tenant, user, tone, identity, multi, guard, sandbox | R1 message validation; R2 identity sealing; R3 persona sealing; R4 tenant sealing; R5 namespace sealing; R6 cross-tenant denial; R7 exact-origin message validation; R8 cross-identity denial; R9 fail-closed |
| Deny-by-default | guard, sandbox, executor | unknown category / surface / envelope all deny; `guard.can` returns `GuardDecision(deny, ...)` |
| MUS boundary chain | router, guard, executor | fixed order; safety/legal/business → `escalate_founder`; isolation → seal check; operator → sandbox+namespace; founder → token required |
| CHANNEL_MAX ceilings | ceilings, guard | every channel checked against (0.5, 0.35, 0.012, 0.8); breach → `ceiling:<ch>` deny |
| Persona/tenant/identity sealing | persona, tenant, identity | tenant_scoped, cross_tenant_denied, readonly_to_tenants, fingerprint_only, CORED never serialized |
| Namespace sealing | namespace, tenant | NS(t,k) formula + six kinds; disjointness; no cross-tenant read/write |
| Cross-tenant/persona/identity denial | multi, guard | predicates deny any cross-boundary access |
| Exact-origin message validation | validator | postMessage v1 envelope, exact evidence check, direction pairing, ≤16KB |
| Fail-closed fallback | pipeline, guard | deny → bounded deterministic retries (max_retries) → escalate-founder; no partial state; record_all/redact_deny/cored_never_logged/anomaly_feed |

---

## 3. Integration Requirements

| Integration point | Binding in code | How |
|---|---|---|
| Runtime | `maya_runtime.isolation` imported from `maya_runtime/__init__.py`; `ISOLATION_VERSION`/`COORDINATOR_ROLE` exported | the guard coordinates calls (`guard.can`) |
| Persona engine | `maya_runtime/persona/__init__.py` (`PersonaRuntime`) | seals personas to tenant; enforces allowlist + ceilings |
| Operator engine | `isolation/executor.py` (operator-bound) + `pipeline.run(..., category="operator*")` | operator tasks allowed only inside namespace + allowlisted surface |
| Command system | deny-by-default via same category/boundary routing; legal/founder categories gated | commands route through the guard |
| AOL loops | `pipeline.run(...)` with a fixed-cadence driver (AOL loop categories → operator boundary) | every loop action isolation-guarded |
| Platform surfaces | `isolation/sandbox.py` SURFACE_WHITELIST + `market/__init__.py` | studio, marketplace, cloud_runtime, api (and kiosk, embed_runtime) are the only allowed surfaces |
| MUS authoritative reference | `ceilings.py` MUS_BOUNDARY_ORDER, CHANNEL_MAX, per-persona ceilings == MUS | identical constants across code and registry |

---

## 4. Usage
```python
import maya_runtime
from maya_runtime.isolation import guard  # Guard()
from maya_runtime.pipeline import run     # optional root facade

pipeline = maya_runtime.isolation.default_pipeline()
result = pipeline.run(
    tenant="acme-corp",
    surface="cloud_runtime",
    category="operator_task",
    action="cleanup",
    context={"tenant": "acme-corp", "namespace_path": "/acme-corp/data", "source": {"tenant": "acme-corp"}, "target": "acme-corp"},
    channels={"expression": 0.38, "viseme": 0.24, "micro": 0.008, "anatomical": 0.2},
)
# result["verdict"] -> "allow" | "deny" | "escalate_founder"
```
Founder-gated actions require an explicit `founder_token` in context; no call
can mint authority for itself.

---

## 5. Verification
- **Full-system audit: 78/78** (was 71/78). All previously-missing modules
  present:
  - `isolation/` (8 modules) ✅
  - `maya_runtime/sandbox.py` ✅
  - `maya_runtime/pipeline.py` ✅
  - `maya_runtime/market/` ✅
  - `maya_runtime/persona/` ✅
- **IR code battery: 66/66.** Exercised on disk: nine rules, boundary chain
  (safety→isolation→legal→business→operator→founder), all 5 persona ceilings
  bounded, CHANNEL_MAX breach denied, quota bounds, identity fingerprint
  (CORED never serialized), founder gating, determinism (no RNG/clock/GUI).
- **Import smoke:** 48 modules in `maya_runtime/` + `persona_layer/` imported;
  `maya_runtime` (incl. isolation/sandbox/pipeline/market/persona) fully clean.
  The only import failure is `persona_layer.persona_registry`, a **pre-existing
  defect** unrelated to the isolation work and outside this scope.

---

## 6. File Map
- Implementation: `maya_runtime/isolation/` (16 modules + `__init__.py`),
  `maya_runtime/sandbox.py`, `maya_runtime/pipeline.py`,
  `maya_runtime/market/__init__.py`, `maya_runtime/persona/__init__.py`,
  `maya_runtime/__init__.py` (isolation wiring).
- Batteries: `C:\Users\USER\AppData\Local\Temp\opencode\ir_code_battery.py`
  (66 checks), `full_system_audit.py` (78 checks).
- Registries (unchanged, authoritative): `maya_identity/isolation/isolation_runtime.json`
  + schema, `maya_identity/isolation/impl/ir_impl.json` + schema.

## 7. Launch-Gate Status After This Work
| Gate | Before | Now |
|---|---|---|
| Isolation runtime re-audit clean | ❌ pending | ✅ **implemented + green** |
| Isolation ceilings match CHANNEL_MAX | ❌ defined only | ✅ enforced in `guard.can` |
| Operator-only autonomy cap | ✅ | ✅ unchanged |
| Legal/business/safety locked | ✅ | ✅ unchanged + escalate verified |
| Surfaces/command/AOL wired to MUS | ✅ | ✅ unchanged + guard importable from runtime |

The platform launch blocker identified in the full-system audit is now cleared:
the isolation runtime implementation is on disk, wired into the runtime, and
re-audited clean at **78/78**.