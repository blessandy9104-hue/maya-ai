from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maya_runtime as rt  # noqa: E402
from maya_runtime import core, determinism, expression_controller  # noqa: E402
from maya_runtime.pattern_alignment import PATTERN_ALIGNMENT  # noqa: E402
from maya_runtime.personality import PERSONALITY  # noqa: E402
from maya_runtime.rendering import RenderFrame, get_renderer, render_engine, sample_frame  # noqa: E402
from maya_runtime.safety_monitor import SAFETY_MONITOR  # noqa: E402
from maya_runtime.world_model import WORLD_MODEL  # noqa: E402

# --- core math determinism -----------------------------------------------

assert core.lerp(1.0, 2.0, 0.5) == 1.5
assert core.clamp01(-1.0) == 0.0 and core.clamp01(2.0) == 1.0
assert core.stable_lerp(1.0, 2.0, 0.0) == 1.0
assert core.stable_lerp(1.0, 2.0, 1.0) == 2.0
assert len(core.NUMERIC_CONTRACTS) == 22
assert core.MATH_AGENT.pattern_state(0.0, 1.0, 0.5) == 0.5
assert len(core.CHANNEL_MAX) == 4
assert core.glow01(0.0) == 1.0
assert core.cosine_similarity((1.0, 0.0), (1.0, 0.0)) == 1.0
assert core.cosine_similarity((0.0, 0.0), (1.0, 0.0)) == 0.0
for _ in range(3):
    _s = core.MATH_AGENT.world_stability([1.0, 1.0, 1.0, 1.0], max_std=0.05)
    assert _s == {"ok": True, "reason": None, "std": 0.0}, _s  # bit-identical across repeats
print("runtime_core_math=OK")

# --- cross-process determinism via headless fallback ---------------------

_ROOT = os.path.dirname(os.path.abspath(__file__))
_CODE = (
    "import sys\n"
    "sys.path.insert(0, %r)\n"
    "import maya_runtime as rt\n"
    "assert 'tkinter' not in sys.modules\n"
    "for mod_name in ('maya_runtime.core', 'maya_identity.wireframe.rig_math',\n"
    "                 'maya_identity.wireframe.math_coordinator'):\n"
    "    mod = sys.modules.get(mod_name); assert mod is not None, mod_name\n"
    "    for bad in ('random', 'time', 'tkinter', 'datetime'):\n"
    "        assert not hasattr(mod, bad), (mod_name, bad)\n"
    "p = rt.runtime_profile(); assert p['headless_loader'] is True, p\n"
    "print('{0:.15f}'.format(rt.MATH_AGENT.pattern_state(0.0, 1.0, 0.5)))\n"
    "print(len(rt.capability_registry.CAPABILITY_REGISTRY))\n"
    "print(len(rt.capability_registry.MARKET_ROLE_REGISTRY))\n"
) % _ROOT
_env = dict(os.environ)
_env["MAYA_RUNTIME_HEADLESS"] = "1"
_headless = subprocess.run(
    [sys.executable, "-c", _CODE], capture_output=True, text=True, env=_env, cwd=_ROOT,
)
assert _headless.returncode == 0, _headless.stderr
_lines = _headless.stdout.strip().splitlines()
assert float(_lines[0]) == core.MATH_AGENT.pattern_state(0.0, 1.0, 0.5)
assert int(_lines[1]) == 11
assert int(_lines[2]) == 8
print("runtime_core_headless=OK")

# --- no device-coupled modules in the runtime graph ----------------------

for _mod in (core, rt.world_model, rt.safety_monitor, rt.pattern_alignment,
             rt.personality, rt.rendering):
    determinism.assert_deterministic(_mod)
_report = determinism.report()
assert all(_report.values()), _report
print("runtime_core_no_device_deps=OK")

# --- world model facade ---------------------------------------------------

_stab = WORLD_MODEL.stability([1.0, 1.0, 1.0, 1.0], max_std=0.05)
assert _stab["ok"] is True and _stab["std"] == 0.0
_drift = WORLD_MODEL.drift([1.0, 1.0, 1.0, 1.0], tolerance=0.35)
assert _drift["ok"] is True and _drift["drift"] == 0.0
eq = core.WORLD_STATE_PATTERNS["stable_equilibrium"]
_coh = WORLD_MODEL.coherence(eq, equilibrium=eq, floor=0.6)
assert _coh["ok"] is True and _coh["coherence"] == 1.0
_cls = WORLD_MODEL.classify(eq, floor=0.6)
assert _cls["ok"] is True and _cls["best"] == "stable_equilibrium"
assert WORLD_MODEL.evaluate(eq, floor=0.6)["ok"] is True
_pred = WORLD_MODEL.predict((0.9, 0.1, 0.9, 1.0), eq, alpha=0.5, floor=0.6)
assert 0.0 <= _pred["alignment"] <= 1.0
assert WORLD_MODEL.state_ok({"expression": 0.5, "viseme": 0.3, "micro": 0.01,
                             "anatomical": 0.5})["ok"] is True
_n = WORLD_MODEL.normalize((2.0, 2.0))
assert abs(_n[0] ** 2 + _n[1] ** 2 - 1.0) < 1e-9 and _n[0] == _n[1]
print("runtime_world_model=OK")

# --- safety monitor facade ------------------------------------------------

margin = SAFETY_MONITOR.margin(30.0, 40.0, 5, 0)
assert 0.0 <= margin <= 1.0
decision = SAFETY_MONITOR.check(20.0, 30.0, 1, 0)
assert isinstance(decision, dict)
assert decision.get("safe") is True
anomaly = SAFETY_MONITOR.resource_anomaly([10.0, 12.0, 11.0], 90.0, z_threshold=2.0, limit=1.0)
assert anomaly["ok"] is False and anomaly["anomaly"] >= 1.0  # excursion beyond limit
bounded = SAFETY_MONITOR.check(99.0, 99.0, 50, 5)
assert bounded.get("safe") is not True  # fail-closed on overload
print("runtime_safety_monitor=OK")

# --- pattern alignment facade ----------------------------------------------

assert 0.0 <= PATTERN_ALIGNMENT.similarity((1.0, 0.0, 1.0), (1.0, 0.0, 1.0)) <= 1.0
assert PATTERN_ALIGNMENT.state(0.0, 1.0, 0.0) == 0.0
assert PATTERN_ALIGNMENT.state(0.0, 1.0, 1.0) == 1.0
assert PATTERN_ALIGNMENT.alignment((1.0, 0.0, 1.0, 1.0), (1.0, 0.0, 1.0, 1.0)) == 1.0
assert 0.99 <= PATTERN_ALIGNMENT.alignment((1.0, 0.0, 1.0, 1.0), (0.9, 0.05, 1.0, 1.0)) <= 1.0
assert PATTERN_ALIGNMENT.priority(42.0) == 1.0
aligned = {"emotional": "stable_equilibrium", "viseme": "stable_equilibrium",
           "world": "stable_equilibrium", "safety": "stable_equilibrium",
           "task": "stable_equilibrium"}
assert PATTERN_ALIGNMENT.ok(aligned)["ok"] is True
print("runtime_pattern_alignment=OK")

# --- expression controller surface -----------------------------------------

assert len(expression_controller.ALL_CONTROLS) == 20
assert expression_controller.PRESETS
assert callable(expression_controller.ExpressionController)
print("runtime_expression_controls=OK")

# --- personality layer ------------------------------------------------------

assert PERSONALITY.available() == ("authoritative", "calm", "playful", "warm")
for persona in ("calm", "warm", "authoritative", "playful"):
    targets = PERSONALITY.channel_targets(persona, blend=0.5)
    for ch, value in targets.items():
        limit = core.CHANNEL_MAX.get(ch)
        if limit is not None:
            assert value <= limit + 1e-12, (persona, ch, value, limit)
    assert PERSONALITY.channel_targets(persona) == PERSONALITY.channel_targets(persona)
    paced = PERSONALITY.paced_state(persona, {"expression": 0.1, "viseme": 0.1, "micro": 0.0})
    assert 0.0 <= paced["expression"] <= core.CHANNEL_MAX["expression"]
assert PERSONALITY.paced_state("calm", {"expression": 0.5, "viseme": 0.2, "micro": 0.0})[
    "expression"] <= 0.5
print("runtime_personality=OK")

# --- rendering adapters ------------------------------------------------------

sample = sample_frame()
assert render_engine.available() == ("desktop", "kiosk", "robotics", "web")
for kind in ("web", "kiosk", "robotics"):
    adapter = get_renderer(kind)
    p1 = adapter.render(sample)
    p2 = adapter.render(sample)
    assert p1 == p2, (kind, "nondeterministic render")
    assert p1["context"] == kind
    assert p1["state"] == "ready"
robot = get_renderer("robotics").render(sample)
for cmd in robot["actuators"]:
    limit = core.CHANNEL_MAX.get(cmd["channel"])
    if limit is not None:
        assert cmd["command"] <= limit, cmd
assert robot["bounded"] is True
assert sample.bounded() is True
assert RenderFrame.from_channel_state({"expression": 0.2, "viseme": 0.1, "micro": 0.0}).bounded()
print("runtime_rendering_adapters=OK")

# --- capability registry surface ---------------------------------------------

assert len(rt.capability_registry.CAPABILITY_REGISTRY) == 11
assert len(rt.capability_registry.MARKET_ROLE_REGISTRY) == 8
assert rt.capability_registry.REGISTRY_VERSION == "1.1"
for cap in rt.capability_registry.CAPABILITY_REGISTRY.values():
    assert cap["layer"] in ("core", "cognitive", "interaction", "domain")
print("runtime_capability_registry=OK")

# --- deployment targets ------------------------------------------------------------------

assert set(rt.DEPLOYMENT_TARGETS) == {"desktop", "web", "kiosk", "robotics"}
plans = {p["name"]: p for p in rt.manifest()}
assert len(plans) == 4
for name, plan in plans.items():
    assert plan["renderer_kind"] in render_engine.available()
    assert isinstance(plan["platforms"], tuple)
    assert isinstance(plan["requires_display"], bool)
    assert isinstance(plan["headless_ok"], bool)
from maya_runtime.deploy import desktop, kiosk, robotics, web  # noqa: E402

assert desktop.run()["status"] == "ready"
web_report = web.run()
assert web_report["payload"]["context"] == "web"
kiosk_report = kiosk.run()
assert kiosk_report["payload"]["context"] == "kiosk"
robotics_report = robotics.run()
assert robotics_report["payload"]["context"] == "robotics"
assert desktop.run() == desktop.run()
print("runtime_deployment_targets=OK")

# --- final summary --------------------------------------------------------------

profile = rt.runtime_profile()
assert profile["headless_loader"] is False or os.environ.get("MAYA_RUNTIME_HEADLESS") == "1"
print("runtime_profile=%s" % (profile,))
print("runtime_portability_suite=OK")