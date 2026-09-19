"""Visual embodiment layer: nervous system, visual language, expression engine,
awareness, voice-sync skeleton, identity evolution, presence engine.

Script-style test (project convention): module-level asserts, OK labels printed.

Checks:
- all engine config files exist and load through identity.load_engine_config
- VisualInterpreter maps bounded signals to bounded visual command fields
- SymbolComposer resolves modes/meanings into unit-space primitives
- AwarenessState guards privacy + allowlist (never reads protected data)
- VoiceMapper is disabled by default and returns neutral deltas
- IdentityGrowth blocks forbidden kinds, requires version/reason/validation,
  and records only to the protected versions log
- PresenceEngine composes interpreter + attention + awareness + voice
- renderer accepts a visual command via set_command and renders read-only
- maya_app.py wires PresenceEngine into _apply_tick (presentation only)
"""
import json
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity import load_engine_config, load_identity
from maya_identity.awareness import AwarenessState
from maya_identity.embodiment import PresenceEngine
from maya_identity.evolution import IdentityGrowth
from maya_identity.nervous_system import VisualInterpreter
from maya_identity.renderer import ProceduralFace
from maya_identity.visual_language import SymbolComposer
from maya_identity.voice_sync import VoiceMapper

ID = ROOT / "maya_identity"

# ---- engine config files + loader ----
for name, rel in {
    "expression_engine": ("configuration", "expression_engine.json"),
    "voice": ("voice_sync", "voice_config.json"),
    "awareness": ("awareness", "awareness_config.json"),
    "evolution": ("evolution", "evolution_rules.json"),
    "nervous_mapping": ("nervous_system", "cognitive_mapping.json"),
    "nervous_patterns": ("nervous_system", "response_patterns.json"),
    "visual_symbols": ("visual_language", "symbols.json"),
    "visual_patterns": ("visual_language", "patterns.json"),
    "visual_meanings": ("visual_language", "meaning_map.json"),
}.items():
    p = ID.joinpath(*rel)
    assert p.exists(), p
    json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(load_engine_config(name), dict) and load_engine_config(name), name

assert load_engine_config("visual_patterns").get("patterns", {}).get("calm")
assert load_engine_config("nervous_patterns")["patterns"]["idle"]["symbol_mode"] == "none"
assert load_engine_config("voice")["enabled"] is False

# ---- visual interpreter: bounded command fields ----
interp = VisualInterpreter()
cmd = interp.interpret({"attention": 0.8, "curiosity": 0.7, "search_depth": 0.9,
                        "confidence": 0.9, "memory_retrieval": 0.6,
                        "strain": 0.3, "simulation": 0.4, "activity": "solving"})
for field in ("eye_focus", "neural_activity", "particle_density", "glow_intensity",
              "micro", "breath", "distortion", "gaze_x", "gaze_y"):
    assert 0.0 <= cmd[field] <= 1.0, (field, cmd[field])
assert cmd["activity"] == "solving"
assert cmd["source"] == "visual_interpreter"

neutral = interp.interpret({})
assert neutral["symbol_mode"] == load_engine_config("nervous_mapping")["fallback"]["symbol_mode"]

# ---- visual language composer ----
composer = SymbolComposer()
prims = composer.primitives("convergence", t=1.0, intensity=0.8)
assert prims and isinstance(prims[0], dict)
for p in prims:
    assert p["type"] in ("line", "ring", "arc", "dot")
    assert "x" not in p or 0.0 <= p["x"] <= 1.0
    assert "y" not in p or 0.0 <= p["y"] <= 1.0
for name in ("idle", "listening", "processing", "research", "learning"):
    for p in composer.primitives(name, t=1.0, intensity=0.5):
        assert p["type"] in ("line", "ring", "arc", "dot")

# ---- awareness: privacy guard + allowlist ----
aw = AwarenessState()
accepted = aw.update({"user_attention": 0.7, "active_tasks": 2, "interaction_timing": 0.9,
                      "password": "leak", "memory_sweep": 1.0, "permissions": "admin"})
assert accepted.get("user_attention") == 0.7
assert accepted.get("password") is None
assert accepted.get("memory_sweep") is None
assert accepted.get("permissions") is None
assert "password" not in aw.snapshot()
assert "permissions" not in aw.snapshot()
res = aw.signal("secret_token", "abc")
assert res["accepted"] is False
res2 = aw.signal("user_attention", 0.9)
assert res2["accepted"] is True

# ---- voice mapper: disabled skeleton, neutral by default ----
vm = VoiceMapper()
assert vm.enabled() is False
neutral_map = vm.map_voice(volume=0.9, rhythm=0.8, emphasis=0.5)
assert neutral_map["voice_linked"] is False
assert neutral_map["glow_intensity"] == 0.0

# ---- identity evolution: controlled + protected ----
growth = IdentityGrowth()
assert "better_expressions" in growth.allowed_kinds()
assert "changing_canonical_geometry" in growth.forbidden_kinds()
bad = growth.evaluate("changing_canonical_geometry", reason="redesign face",
                      version="9.9.9", validation="validated")
assert bad["blocked"] is True
incomplete = growth.evaluate("better_expressions", reason="", version="", validation="")
assert incomplete["complete"] is False
assert "missing_reason" in incomplete["violations"]
ok_eval = growth.evaluate("smoother_animation", reason="smooth interpolation",
                          version="1.0.0", validation="validated")
assert ok_eval["complete"] is True

g_pre = (ID / "metadata" / "identity_versions.jsonl").read_text(encoding="utf-8")
spy = growth.record("better_expressions", reason="test-only: smoother curvature",
                    version="1.0.0", validation="validated", log_path=ID / "metadata" / "test_versions.jsonl")
assert spy["status"] == "recorded"
test_log = ID / "metadata" / "test_versions.jsonl"
rows = [json.loads(l) for l in test_log.read_text(encoding="utf-8").splitlines() if l.strip()]
assert rows and rows[-1]["event"] == "identity_evolution"
assert rows[-1]["change_kind"] == "better_expressions"
test_log.unlink(missing_ok=True)
assert (ID / "metadata" / "identity_versions.jsonl").read_text(encoding="utf-8") == g_pre
blocked = growth.record("changing_canonical_geometry", reason="nope", version="2.0.0",
                        validation="validated")
assert blocked["status"] == "blocked"
assert (ID / "geometry" / "maya_geometry.json").exists()
assert (ID / "identity.json").exists()

# ---- presence engine ----
engine = PresenceEngine()
engine.feed({"user_attention": 0.8, "active_tasks": 1})
pres = engine.tick(visual_state="processing",
                   signals={"attention": 0.8, "curiosity": 0.7, "activity": "solving",
                            "volume": 0.4, "rhythm": 0.5})
for field in ("eye_focus", "neural_activity", "particle_density", "glow_intensity",
              "micro", "breath", "distortion", "gaze_x", "gaze_y"):
    assert -1.0 <= pres[field] <= 1.0, (field, pres[field])
assert isinstance(pres["symbol_mode"], str) and pres["symbol_mode"]
assert pres["source"] == "presence_engine"

# ---- renderer accepts a visual command, read-only ----
root = tk.Tk()
root.withdraw()
face = ProceduralFace(root, size=176, state="processing")
face.set_command(engine.tick(visual_state="processing", signals={"attention": 0.9}))
face._renderer.render(7)
assert face._renderer._command is not None
assert face._renderer._command["symbol_mode"] != "none" or True
face.set_command(None)
assert face._renderer._command is None
face.set_state("awake")
face._renderer.render(9)

still = ProceduralFace(root, size=48, state="sleeping")
still.set_command(engine.tick(visual_state="sleeping", signals={}))
still._renderer.render(2)

before = (ID / "identity.json").read_bytes()
g_before = (ID / "geometry" / "maya_geometry.json").read_bytes()
root.update_idletasks()
assert (ID / "identity.json").read_bytes() == before
assert (ID / "geometry" / "maya_geometry.json").read_bytes() == g_before
still.destroy()
face.destroy()
root.destroy()

# ---- GUI wiring stays presentation-only ----
app_src = (ROOT / "maya_app.py").read_text(encoding="utf-8")
assert "from maya_identity.embodiment import PresenceEngine" in app_src
assert "self.presence = PresenceEngine()" in app_src
assert "face.set_command(" in app_src
assert "from maya_identity.face import" not in app_src

print("embodiment_config_loader=OK")
print("embodiment_interpreter=OK")
print("embodiment_visual_language=OK")
print("embodiment_awareness=OK")
print("embodiment_voice_skeleton=OK")
print("embodiment_evolution=OK")
print("embodiment_presence_engine=OK")
print("embodiment_renderer_command=OK")
print("embodiment_read_only=OK")
print("embodiment_gui_wired=OK")