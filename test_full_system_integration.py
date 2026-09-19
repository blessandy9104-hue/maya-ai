"""Full-system architectural integration verification suite.

Traces the whole Maya architecture as one thread and proves the layers stay in
harmony and fail closed: raw samples -> math/spectral (frequency) -> pattern
recognition -> trust/alignment -> visual state model, plus the provisioning
recovery and revocation/grant lifecycles.

Scope and what each label proves:

1. Long thread: the frequency layer (substrate -> ``maya_frequency`` ->
   ``MathAgent``/``PatternAlignment``) agrees on class/SNR/periodicity; a
   coherent periodic observation validates to ``available`` and the trust gate
   allows it, while broadband noise validates to ``untrusted`` and is refused;
   the real authorization decision drives the visual state model to
   ``complete``/``unavailable`` and a failure paints no active indicator/node.

2. Provisioning + recovery: an installed dependency is removed (simulated
   outage), its dependent capability drops to ``unavailable`` and every action
   is refused, then OpenCode Active Provisioning installs it through the gated
   sandbox runner and the capability recovers to ``available`` with monotonic
   recovery timestamps; an explicit revocation -> grant round trip is also
   exercised. The visual state model follows the transition
   ``complete -> unavailable -> approval -> complete`` with no invalid state,
   no ``error`` and no flicker (identical inputs give byte-identical views).

3. Fail-closed rigor: malformed spectral evidence is refused at every door and
   poisons trust to ``untrusted``; contradictory trust signals (absent
   provider, raised/timed-out probe, revoked, malformed, unknown verdict) all
   resolve to a failure state with zero active indicators/nodes - no ghost
   authority is ever granted.

4. Performance/latency: the frequency layer's per-window cost, the one-time
   spectral validation added to the trust gate, and the frequency/trust-aware
   core projection added to the UI tick are all measured against documented
   budgets; a spy proves spectral analysis is never invoked inside a UI tick.

5. Final integrity: the real registry and action log are byte-untouched, the
   spectral invariants hold for every test signal, and all nine visual states
   are reachable and deterministic.

Everything runs against temporary registries and a sandbox directory; the real
``trusted_capabilities.jsonl`` / ``maya_trust_actions.jsonl`` are never written.
"""
from __future__ import annotations

import importlib
import json
import math
import sys
import tempfile
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import maya_frequency as frequency  # noqa: E402
import maya_intelligence_core as core  # noqa: E402
import maya_math.spectral as spectral  # noqa: E402
import maya_provisioning as provisioning  # noqa: E402
import maya_trust as trust  # noqa: E402
from maya_identity.visual_surface import FRAME_MS_DEFAULT  # noqa: E402
from maya_identity.wireframe.math_coordinator import MATH_AGENT  # noqa: E402
from maya_runtime.pattern_alignment import PATTERN_ALIGNMENT  # noqa: E402
from maya_runtime.ui.qt import bridge as ui_bridge  # noqa: E402


def _ok(label: str) -> None:
    print(label + " =OK")


# ---- documented latency budgets (milliseconds) ----------------------------

FREQ_BUDGET_MS = 25.0            # one 128-sample spectral analysis window
TRUST_BUDGET_MS = 30.0           # one authorization decision
TRUST_VALIDATE_BUDGET_MS = float(FRAME_MS_DEFAULT)   # one full validation
CORE_VIEW_BUDGET_MS = 16.0       # visual-state projection added per tick

# ---- shared deterministic inputs ------------------------------------------

SINE_P8 = [math.sin(2 * math.pi * k / 8) for k in range(16)]
SINE_WINDOW = [math.sin(2 * math.pi * k / 8) for k in range(128)]


def _lcg(seed: int, n: int):
    x = seed
    out = []
    for _ in range(n):
        x = (1103515245 * x + 12345) % (2 ** 31)
        out.append(x / 2 ** 31)
    return out


NOISE = _lcg(7, 128)

MALFORMED = (None, [], ["a"], [float("nan")], [float("inf")], [True],
             "text", b"bytes", [1, None], [object()])

# ---- isolated runtime state -----------------------------------------------

_TMP = Path(tempfile.mkdtemp())
REGISTRY = _TMP / "trust.jsonl"
ACTIONS = _TMP / "actions.jsonl"
SANDBOX = _TMP / "sandbox"
SANDBOX.mkdir()

_clock = [1000.0]


def _tick_clock() -> float:
    _clock[0] += 1.0
    return _clock[0]


trust.set_clock(_tick_clock)

DEP = "maya_demo_frequency_index"
TOKEN = provisioning.confirmation_token(DEP)

REAL_FILES = (trust.TRUST_FILE, trust.ACTION_LOG)


def _real_state():
    return {str(p): (p.read_bytes() if p.exists() else None)
            for p in REAL_FILES}


_REAL_BEFORE = _real_state()
_TIMELINE: list[tuple[str, float]] = []


def _read(path: Path):
    return path.read_bytes() if path.exists() else None


def _record(capability: str, extra: dict | None = None) -> dict:
    record = {
        "capability": capability,
        "provider": capability + "_provider",
        "context": "personal",
        "permissions": {"read_status": True},
        "actions": ("read_status",),
        "trust_basis": ["integration test dependency"],
        "identity": {"provider": capability + "_provider", "version": "1",
                     "source_digest": None},
        "auth": {"method": "local", "state": "valid"},
        "boundaries": {"input": "project", "output": "project",
                       "cross_context_denied": True},
        "result_confirmation": {"supported": True, "method": "digest"},
        "failure": {"fail_closed": True},
    }
    if extra:
        record.update(extra)
    return record


def _install(descriptor: dict):
    module = descriptor["module"]
    (SANDBOX / (module + ".py")).write_text("VALUE = 1\n", encoding="utf-8")
    if str(SANDBOX) not in sys.path:
        sys.path.insert(0, str(SANDBOX))
    importlib.invalidate_caches()
    return {"installed": module}


def _remove(module: str) -> None:
    sys.modules.pop(module, None)
    path = SANDBOX / (module + ".py")
    if path.exists():
        path.unlink()
    if str(SANDBOX) in sys.path:
        sys.path.remove(str(SANDBOX))
    importlib.invalidate_caches()


def _overview() -> dict:
    return trust.registry_overview(path=REGISTRY)


def _last_authority():
    raw = _read(ACTIONS)
    if not raw:
        return None
    for line in reversed(raw.decode("utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("verdict"):
            return row
    return None


def _view(**over) -> dict:
    args = {"activity": "idle", "resources": "safe", "trust": _overview(),
            "authority": None}
    args.update(over)
    return core.build_core_view(**args)


def _median_ms(fn, runs: int = 9) -> float:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    return samples[len(samples) // 2]


def _min_ms(fn, runs: int = 15) -> float:
    """Best-case time: the stable estimate of compute cost for a fixed workload
    when a surrounding renderer introduces large scheduling jitter."""
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return min(samples)


# ===========================================================================
# 1. End-to-end long thread: samples -> spectral -> pattern -> trust -> core
# ===========================================================================

_math = MATH_AGENT.spectral_analysis(SINE_P8)
_pattern = PATTERN_ALIGNMENT.spectral(SINE_P8)
_layer = frequency.analyze(SINE_P8)
_snr = MATH_AGENT.signal_to_noise(SINE_P8)

assert _math["ok"] and _layer["ok"] and _pattern["ok"]
assert _math["class"] == _pattern["class"] == _layer["class"] == "periodic"
assert _math["dominant_frequency"] == _layer["dominant_frequency"]
assert MATH_AGENT.periodicity(SINE_P8) == PATTERN_ALIGNMENT.periodicity(SINE_P8)
assert _snr["ok"] is True and _snr["margin_db"] > 0.0
assert abs(PATTERN_ALIGNMENT.spectral_alignment(SINE_P8, SINE_P8) - 1.0) < 1e-9
assert PATTERN_ALIGNMENT.spectral_alignment(SINE_P8, NOISE) < 1.0
assert spectral.spectral_invariants(SINE_P8)["ok"] is True
_ok("integration_long_thread_frequency_layer_ok")

# The refined SNR feeds the trust gate: coherent periodic evidence validates,
# broadband noise poisons the record and is refused.
_clean = trust.refresh(_record("spectral_probe", {"signal": SINE_P8}),
                       probe={"available": True}, path=REGISTRY,
                       action_log=ACTIONS)
assert _clean["status"] == trust.AVAILABLE
_allowed = trust.authorize("spectral_probe", "read_status", "personal",
                           path=REGISTRY, action_log=ACTIONS)
assert _allowed["verdict"] == "allowed", _allowed
assert _allowed["verification_supported"] is True

_noisy = trust.refresh(_record("noisy_probe", {"signal": NOISE}),
                       probe={"available": True}, path=REGISTRY,
                       action_log=ACTIONS)
assert _noisy["status"] == trust.UNTRUSTED
_signal_check = [c for c in _noisy["verification"]["checks"]
                 if c["name"] == "signal_integrity"]
assert _signal_check and _signal_check[0]["ok"] is False
_denied = trust.authorize("noisy_probe", "read_status", "personal",
                          path=REGISTRY, action_log=ACTIONS)
assert _denied["verdict"] == "refused", _denied
_ok("integration_frequency_refines_trust_gate_ok")

# The trust gate's decision drives the visual state model.
_clean_view = core.build_core_view(activity="idle", resources="safe",
                                   trust=_overview(), authority=_allowed)
assert _clean_view["state"] == "complete", (_clean_view["state"],
                                            _clean_view["reason"])
assert _clean_view["implies_success"] is True
assert _clean_view["fail_closed"] is False
assert _clean_view["authority"]["verification_supported"] is True

_denied_view = core.build_core_view(activity="idle", resources="safe",
                                    trust=_overview(), authority=_denied)
assert _denied_view["state"] == "unavailable", (_denied_view["state"],
                                                _denied_view["reason"])
assert _denied_view["implies_failure"] is True
assert _denied_view["fail_closed"] is True
assert _denied_view["implies_success"] is False
assert all(not indicator["active"] for indicator in _denied_view["indicators"])
assert all(not node["active"] for node in _denied_view["geometry"]["nodes"])
assert _clean_view["digest"] != _denied_view["digest"]
_ok("integration_trust_gate_drives_visual_state_ok")

# ===========================================================================
# 2. Provisioning + recovery stress test
# ===========================================================================

provisioning.register_provisioning_provider(registry_path=REGISTRY,
                                            action_log=ACTIONS)

assert provisioning.import_available(DEP) is False
_dependent = _record("frequency_service", {"signal": SINE_WINDOW})

# Initial availability: the dependency is provisioned, the service is trusted.
_first = provisioning.provision(DEP, confirmation=TOKEN, execute=True,
                                runner=_install, registry_path=REGISTRY,
                                action_log=ACTIONS, dependent_record=_dependent)
assert _first["status"] == provisioning.STATUS_INSTALLED, _first
assert _first["dependent"]["status"] == trust.AVAILABLE
_t_available = trust.lookup("frequency_service", path=REGISTRY)["last_checked"]

# Simulated outage: remove the required dependency and re-validate.
_remove(DEP)
assert provisioning.import_available(DEP) is False
_outage = provisioning.revalidate_dependent(_dependent, available=False,
                                            registry_path=REGISTRY,
                                            action_log=ACTIONS)
assert _outage["status"] == trust.UNAVAILABLE
_outage_decision = trust.authorize("frequency_service", "read_status",
                                   "personal", path=REGISTRY,
                                   action_log=ACTIONS)
assert _outage_decision["verdict"] == "refused", _outage_decision
_outage_view = core.build_core_view(activity="idle", resources="safe",
                                    trust=_overview(),
                                    authority=_outage_decision)
assert _outage_view["state"] == "unavailable"
assert _outage_view["fail_closed"] is True
assert all(not node["active"] for node in _outage_view["geometry"]["nodes"])
_ok("integration_provisioning_unavailable_state_ok")

# Recovery: gated provisioning installs the dependency and the service recovers.
_recovery = provisioning.provision(DEP, confirmation=TOKEN, execute=True,
                                   runner=_install, registry_path=REGISTRY,
                                   action_log=ACTIONS,
                                   dependent_record=_dependent)
assert _recovery["status"] == provisioning.STATUS_INSTALLED, _recovery
assert _recovery["dependent"]["status"] == trust.AVAILABLE
assert _recovery["dependent"]["supported"] is True
_restored = trust.authorize("frequency_service", "read_status", "personal",
                            path=REGISTRY, action_log=ACTIONS)
assert _restored["verdict"] == "allowed", _restored

_t_outage = float(_outage["last_checked"])
_t_recovery = float(trust.lookup("frequency_service",
                                 path=REGISTRY)["last_checked"])
assert _t_available < _t_outage < _t_recovery, (
    _t_available, _t_outage, _t_recovery)
_TIMELINE.append(("available", float(_t_available)))
_TIMELINE.append(("outage", _t_outage))
_TIMELINE.append(("recovery", _t_recovery))
_ok("integration_provisioning_recovery_transition_ok")

# Explicit revocation -> grant round trip (the tombstone can never self-heal).
trust.revoke("frequency_service", "frequency_service_provider",
             "integration drill", path=REGISTRY, action_log=ACTIONS)
_tomb = trust.lookup("frequency_service", path=REGISTRY)
assert _tomb["status"] == trust.UNTRUSTED and _tomb.get("revoked") is True
_t_revoked = float(_tomb["last_checked"])
_revoked_decision = trust.authorize("frequency_service", "read_status",
                                    "personal", path=REGISTRY,
                                    action_log=ACTIONS)
assert _revoked_decision["verdict"] == "refused"
_revoked_view = core.build_core_view(activity="idle", resources="safe",
                                     trust=_overview(),
                                     authority=_revoked_decision)
assert _revoked_view["state"] == "unavailable"
_granted = trust.grant(_dependent, probe={"available": True},
                       path=REGISTRY, action_log=ACTIONS)
assert _granted["status"] == trust.AVAILABLE
_t_granted = float(_granted["last_checked"])
assert _t_recovery < _t_revoked < _t_granted, (
    _t_recovery, _t_revoked, _t_granted)
_TIMELINE.append(("revoked", _t_revoked))
_TIMELINE.append(("granted", _t_granted))
_regranted = trust.authorize("frequency_service", "read_status", "personal",
                             path=REGISTRY, action_log=ACTIONS)
assert _regranted["verdict"] == "allowed", _regranted
_ok("integration_revocation_grant_roundtrip_ok")

# The visual state model follows the transition without flicker or invalid
# states. Build one more outage -> approval -> recovery cycle and compare.
_v_available = core.build_core_view(activity="idle", resources="safe",
                                    trust=_overview(), authority=_regranted)
_remove(DEP)
_outage2 = provisioning.revalidate_dependent(_dependent, available=False,
                                             registry_path=REGISTRY,
                                             action_log=ACTIONS)
_denied2 = trust.authorize("frequency_service", "read_status", "personal",
                           path=REGISTRY, action_log=ACTIONS)
_v_outage = core.build_core_view(activity="idle", resources="safe",
                                 trust=_overview(), authority=_denied2)
_approval = trust.authorize(provisioning.CAPABILITY, provisioning.ACTION,
                            provisioning.CONTEXT, owner_approval=False,
                            provider=provisioning.PROVIDER, path=REGISTRY,
                            action_log=ACTIONS)
assert _approval["verdict"] == "requires_approval", _approval
_v_approval = core.build_core_view(activity="idle", resources="safe",
                                   trust=_overview(), authority=_approval)
_recovered = provisioning.provision(DEP, confirmation=TOKEN, execute=True,
                                    runner=_install, registry_path=REGISTRY,
                                    action_log=ACTIONS,
                                    dependent_record=_dependent)
_allowed3 = trust.authorize("frequency_service", "read_status", "personal",
                            path=REGISTRY, action_log=ACTIONS)
_v_recovered = core.build_core_view(activity="idle", resources="safe",
                                    trust=_overview(), authority=_allowed3)

_sequence = [_v_available["state"], _v_outage["state"],
             _v_approval["state"], _v_recovered["state"]]
assert _sequence == ["complete", "unavailable", "approval", "complete"], \
    _sequence
assert all(state in core.STATES for state in _sequence)
assert "error" not in _sequence
assert _v_approval["implies_authority_waiting"] is True
assert all(not node["active"] for node in _v_outage["geometry"]["nodes"])
assert all(not indicator["active"] for indicator in _v_outage["indicators"])
# No flicker: identical authoritative inputs give byte-identical views, and the
# recovered state is stable across repeated ticks.
for _ in range(3):
    _again = core.build_core_view(activity="idle", resources="safe",
                                  trust=_overview(), authority=_allowed3)
    assert _again["digest"] == _v_recovered["digest"]
    assert ([n["active"] for n in _again["geometry"]["nodes"]]
            == [n["active"] for n in _v_recovered["geometry"]["nodes"]])
assert _v_recovered["state"] == "complete"
_ok("integration_provisioning_visual_timeline_ok")

# ===========================================================================
# 3. Fail-closed rigor
# ===========================================================================

for _bad in MALFORMED:
    assert frequency.analyze(_bad)["ok"] is False
    assert frequency.analyze(_bad)["class"] == "invalid"
    assert frequency.signal_quality(_bad)["ok"] is False
    assert frequency.signal_quality(_bad)["reason"] == frequency.REASON_INVALID
    assert spectral.classify_spectrum(_bad)["class"] == "invalid"
    assert spectral.spectral_invariants(_bad)["ok"] is False
    assert MATH_AGENT.spectral_analysis(_bad)["ok"] is False
    assert PATTERN_ALIGNMENT.spectral(_bad)["ok"] is False
    assert MATH_AGENT.periodicity(_bad) == 0.0
    assert PATTERN_ALIGNMENT.spectral_alignment(_bad, SINE_P8) == 0.0

_poison = trust.refresh(_record("poisoned_probe",
                                {"signal": [float("nan")]}),
                        probe={"available": True}, path=REGISTRY,
                        action_log=ACTIONS)
assert _poison["status"] == trust.UNTRUSTED
_poison_decision = trust.authorize("poisoned_probe", "read_status",
                                   "personal", path=REGISTRY,
                                   action_log=ACTIONS)
assert _poison_decision["verdict"] == "refused"
_poison_view = core.build_core_view(activity="idle", resources="safe",
                                    trust=_overview(),
                                    authority=_poison_decision)
assert _poison_view["state"] == "unavailable"
assert _poison_view["fail_closed"] is True
_ok("integration_failclosed_malformed_spectral_ok")

_contradictions = [
    trust.refresh(_record("contra_probe"), probe={"available": False},
                  path=REGISTRY, action_log=ACTIONS),
    trust.refresh(_record("contra_raised"),
                  probe={"available": True, "raised": "probe failure"},
                  path=REGISTRY, action_log=ACTIONS),
    trust.refresh(_record("contra_timeout"),
                  probe={"available": True, "timed_out": True},
                  path=REGISTRY, action_log=ACTIONS),
    trust.refresh(_record("contra_revoked", {"revoked": True}),
                  probe={"available": True}, path=REGISTRY,
                  action_log=ACTIONS),
    trust.refresh({"capability": "contra_malformed", "provider": "broken"},
                  probe={"available": True}, path=REGISTRY,
                  action_log=ACTIONS),
]
assert _contradictions[0]["status"] == trust.UNAVAILABLE
for _recorded in _contradictions[1:]:
    assert _recorded["status"] == trust.UNTRUSTED
for _recorded in _contradictions:
    _decision = trust.authorize(_recorded["capability"], "read_status",
                                "personal", path=REGISTRY,
                                action_log=ACTIONS)
    assert _decision["verdict"] == "refused", _decision
    _built = core.build_core_view(activity="idle", resources="safe",
                                  trust=_overview(), authority=_decision)
    assert _built["state"] == "unavailable"
    assert _built["implies_failure"] is True and _built["fail_closed"] is True

# Contradictory authority data can never be painted as success.
assert _view(authority={"verdict": "allowed",
                        "verification_supported": False})["state"] == "verifying"
assert _view(authority={"verdict": "allowed",
                        "verification_supported": False})["implies_success"] \
    is False
assert _view(authority={"verdict": "unknown-verdict"})["state"] == "unavailable"
assert _view(authority="not-a-record")["state"] == "unavailable"
assert _view(trust="not-a-mapping")["state"] == "unavailable"
assert _view(trust={"capabilities": {}})["state"] == "unavailable"
_ok("integration_failclosed_contradictory_trust_ok")

_failure_views = [
    _view(resources="unsafe"),
    _view(trust=None),
    _view(trust={}),
    _view(trust={"schema": "trusted_capability.v1", "capabilities": {}}),
    _view(trust={"capabilities": {"x": "not-a-status"}}),
    _view(authority={"verdict": "unknown-verdict"}),
]
for _failure in _failure_views:
    assert _failure["state"] in core.FAILURE_STATES, _failure["state"]
    assert _failure["fail_closed"] is True
    assert _failure["implies_success"] is False
    assert _failure["implies_authority_waiting"] is False
    assert all(not i["active"] for i in _failure["indicators"])
    assert all(not n["active"] for n in _failure["geometry"]["nodes"])

# Synthetic overlay gating: availability is the only path to an active
# indicator, and a failure state forces even an available one inactive.
_overlay = {"schema": "trusted_capability.v1",
            "capabilities": {"avail": "available", "bad": "untrusted",
                             "gone": "unavailable",
                             "waiting": "pending_validation"}}
_overlay_view = core.build_core_view(activity="idle", resources="safe",
                                     trust=_overlay, authority=None)
assert _overlay_view["state"] == "idle"
_by_name = {i["name"]: i for i in _overlay_view["indicators"]}
assert _by_name["avail"]["active"] is True
assert _by_name["bad"]["active"] is False
assert _by_name["gone"]["active"] is False
assert _by_name["waiting"]["active"] is False
for _forced in (core.build_core_view(activity="idle", resources="unsafe",
                                     trust=_overlay, authority=None),
                core.build_core_view(activity="idle", resources="safe",
                                     trust=_overlay,
                                     authority={"verdict": "unknown"})):
    assert all(not i["active"] for i in _forced["indicators"])
    assert all(not n["active"] for n in _forced["geometry"]["nodes"])
_ok("integration_failclosed_no_ghost_authority_ok")

# ===========================================================================
# 4. Performance and latency audit
# ===========================================================================

_freq_ms = _median_ms(lambda: MATH_AGENT.spectral_analysis(SINE_WINDOW, 8.0))
_gate_ms = _median_ms(lambda: frequency.signal_quality(SINE_WINDOW))
_fft_ms = _median_ms(lambda: spectral.fft_magnitudes(SINE_WINDOW))
assert _freq_ms < FREQ_BUDGET_MS, (_freq_ms, FREQ_BUDGET_MS)
assert _gate_ms < FREQ_BUDGET_MS, (_gate_ms, FREQ_BUDGET_MS)
assert _fft_ms < FREQ_BUDGET_MS, (_fft_ms, FREQ_BUDGET_MS)
_freq_latency = {"analyze": _freq_ms, "quality": _gate_ms, "fft": _fft_ms}
_ok("integration_latency_frequency_within_budget_ok")

_LATREG = _TMP / "latency.jsonl"
_LATLOG = _TMP / "latency_actions.jsonl"
trust.refresh(_record("latency_probe", {"signal": SINE_WINDOW}),
              probe={"available": True}, path=_LATREG, action_log=_LATLOG)
_auth_ms = _median_ms(lambda: trust.authorize("latency_probe", "read_status",
                                              "personal", path=_LATREG,
                                              action_log=_LATLOG))
_plain_ms = _median_ms(lambda: trust.validate_record(
    _record("plain_probe"), probe={"available": True}))
_signal_ms = _median_ms(lambda: trust.validate_record(
    _record("signal_probe", {"signal": SINE_WINDOW}),
    probe={"available": True}))
assert _auth_ms < TRUST_BUDGET_MS, (_auth_ms, TRUST_BUDGET_MS)
assert _plain_ms < TRUST_VALIDATE_BUDGET_MS, (_plain_ms, TRUST_VALIDATE_BUDGET_MS)
assert _signal_ms < TRUST_VALIDATE_BUDGET_MS, (_signal_ms,
                                               TRUST_VALIDATE_BUDGET_MS)
_signal_overhead_ms = _signal_ms - _plain_ms
assert _signal_overhead_ms < FREQ_BUDGET_MS, (_signal_overhead_ms,
                                              FREQ_BUDGET_MS)
_trust_latency = {"authorize": _auth_ms, "validate_plain": _plain_ms,
                  "validate_signal": _signal_ms,
                  "spectral_overhead": _signal_overhead_ms}
_ok("integration_latency_trust_gate_within_budget_ok")

_ticker = ui_bridge.UiTicker()
_payload = _ticker.make_tick_payload("idle")
_ticker.apply_tick_snapshot(_payload)

# Prove spectral analysis never runs inside a UI tick.
_spy_calls = {"n": 0}
_orig_analyze = frequency.analyze
_orig_quality = frequency.signal_quality


def _spy_analyze(*args, **kwargs):
    _spy_calls["n"] += 1
    return _orig_analyze(*args, **kwargs)


def _spy_quality(*args, **kwargs):
    _spy_calls["n"] += 1
    return _orig_quality(*args, **kwargs)


frequency.analyze = _spy_analyze
frequency.signal_quality = _spy_quality
try:
    for _ in range(3):
        _ticker.apply_tick_snapshot(_payload)
finally:
    frequency.analyze = _orig_analyze
    frequency.signal_quality = _orig_quality
assert _spy_calls["n"] == 0

_tick_ms = _min_ms(lambda: _ticker.apply_tick_snapshot(_payload))
# The frequency/trust-aware core projection is the only work the frequency
# layer adds to a tick; measure it directly (the face renderer dominates the
# rest and is pre-existing, so it is excluded from the marginal budget).
_core_ms = _min_ms(lambda: core.runtime_core_view(activity="idle",
                                                  resources="safe"))
assert _core_ms < CORE_VIEW_BUDGET_MS, (_core_ms, CORE_VIEW_BUDGET_MS)
assert _spy_calls["n"] == 0
assert _tick_ms < FRAME_MS_DEFAULT * 3, (_tick_ms, FRAME_MS_DEFAULT)
_tick_latency = {"tick_with_core": _tick_ms, "core_view": _core_ms,
                 "spectral_calls_per_tick": float(_spy_calls["n"]),
                 "frame_budget": FRAME_MS_DEFAULT}
_ok("integration_latency_ui_tick_within_budget_ok")

# ===========================================================================
# 5. Final integrity
# ===========================================================================

assert _real_state() == _REAL_BEFORE
assert _read(trust.TRUST_FILE) is None
assert _read(trust.ACTION_LOG) is None
_ok("integration_real_state_untouched_ok")

for _series in (SINE_P8, SINE_WINDOW, NOISE):
    assert spectral.spectral_invariants(_series)["ok"] is True
_ok("integration_spectral_invariants_hold_ok")

_state_cases = {
    "idle": {"activity": "idle"},
    "observing": {"activity": "listening"},
    "reasoning": {"activity": "processing"},
    "acting": {"activity": "research"},
    "approval": {"authority": {"verdict": "requires_approval"}},
    "verifying": {"authority": {"verdict": "allowed",
                                "verification_supported": False}},
    "complete": {"authority": {"verdict": "allowed",
                               "verification_supported": True}},
    "error": {"resources": "unsafe"},
    "unavailable": {"trust": None},
}
_seen = set()
for _expected, _over in _state_cases.items():
    _built = _view(**_over)
    assert _built["state"] == _expected, (_expected, _built["state"])
    assert _built["state"] in core.STATES
    assert _built["digest"] == _view(**_over)["digest"]
    _seen.add(_built["state"])
assert _seen == set(core.STATES)
_ok("integration_visual_state_model_complete_ok")

print("integration_timeline=" + ";".join(
    f"{phase}@{stamp:.0f}" for phase, stamp in _TIMELINE))
print("integration_latency_frequency_ms=" + ",".join(
    f"{k}:{v:.3f}" for k, v in _freq_latency.items()))
print("integration_latency_trust_ms=" + ",".join(
    f"{k}:{v:.3f}" for k, v in _trust_latency.items()))
print("integration_latency_tick_ms=" + ",".join(
    f"{k}:{v:.3f}" for k, v in _tick_latency.items()))

print("test_full_system_integration=PASS")
