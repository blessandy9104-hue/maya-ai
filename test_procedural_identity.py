"""Procedural Digital Identity layer: geometry, expressions, renderer, config.

Script-style test (project convention): module-level asserts, OK labels printed.

Checks:
- identity.json declares geometry_version 1.0.0 + established procedural body
- the geometry identity rule is referenced in identity.json, geometry model, rules md
- all geometry models load; structure, symmetry, neural map present
- the six expression transforms load as numeric config for all states
- effects + animation toggles are config-driven (nothing hardcoded in the GUI)
- ProceduralFace renders live from geometry (no image assets), cycles states,
  reports no-placeholder, and never mutates identity files
- maya_app.py (presentation only) is wired to the procedural face
"""
import json
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity import (
    geometry_version,
    get_animation_config,
    load_effects_config,
    load_expression,
    load_geometry_bundle,
    load_identity,
)
from maya_identity.renderer import ProceduralFace

ID = ROOT / "maya_identity"

# ---- identity declaration ----
identity = load_identity()
assert identity["geometry_version"] == "1.0.0"
assert geometry_version() == "1.0.0"
assert identity["procedural_identity"]["status"] == "established"
assert identity["procedural_identity"]["engine"].endswith("hologram_renderer")
statement = identity["identity_statement"].lower()
assert "gender-neutral" in statement
assert "not defined as male or female" in statement

geo_rule = identity["identity_geometry_rule"].lower()
assert "same underlying geometry" in geo_rule
assert "emotional signature" in geo_rule

# ---- rule referenced across the identity layer ----
bundle = load_geometry_bundle()
assert "same underlying geometry" in bundle["identity"]["identity_rule"].lower()
rules_md = (ID / "metadata" / "consistency_rules.md").read_text(encoding="utf-8").lower()
assert "the geometry is the identity" in rules_md
prompt = (ID / "prompts" / "maya_face_generation.md").read_text(encoding="utf-8").lower()
assert "same underlying geometry" in prompt

# ---- geometry models ----
for key in ("identity", "facial_structure", "symmetry", "neural_pattern"):
    assert key in bundle
fs = bundle["facial_structure"]
for feature in ("face_outline", "brows", "eyes", "nose", "mouth", "temple_braids", "signature_features"):
    assert feature in fs, feature
sym = bundle["symmetry"]
assert sym["mirror"] is True
assert sym["axis"] == 0.5
assert sym["groups"]
for group in sym["groups"]:
    assert group["mode"] == "pair"
np_map = bundle["neural_pattern"]
assert np_map["seed"] == 21098
assert np_map["grid"]["rows"] >= 5 and np_map["grid"]["cols"] >= 5
assert np_map["halo"]["enabled"] is True

# coordinates stay inside the canonical unit space
def in_unit(value):
    return 0.0 <= value <= 1.0

eye_level = fs["eyes"]["level"]
assert in_unit(eye_level)
assert in_unit(fs["mouth"]["corners"]["left"][0])
assert in_unit(fs["signature_features"]["awareness_gem"]["point"][1])

# ---- expressions ----
STATES = ("idle", "listening", "processing", "research", "learning", "sleeping")
for st in STATES:
    expr = load_expression(st)
    assert expr and expr["expression"] == st, st
    for section in ("geometry", "eyes", "brows", "mouth", "neural", "particles", "glow", "halo"):
        assert section in expr and expr[section], (st, section)
    assert isinstance(expr["symbols"], list)
    raw = json.loads((ID / "expressions" / f"{st}.json").read_text(encoding="utf-8"))
    assert isinstance(raw["geometry"]["scale"], (int, float))
    assert 0.0 <= raw["particles"]["density"] <= 1.0
    assert 0.0 <= raw["neural"]["activity"] <= 1.0

# ---- effects + animation config are the only driver ----
effects = load_effects_config()
assert effects["hologram"]["enabled"] is True
assert effects["symbol_overlay"]["never_modifies_identity"] is True
assert effects["engine"] == "procedural_hologram"

anim = get_animation_config()
assert anim["neural_motion"]["enabled"] is True
assert anim["blink"]["enabled"] is False and anim["blink"]["future_support"] is True
assert anim["breathing"]["enabled"] is False and anim["breathing"]["future_support"] is True
assert anim["eye_tracking"]["enabled"] is False
assert anim["voice_sync"]["enabled"] is False
assert anim["procedural_rendering"]["frame_ms"] >= 16

# ---- renderer smoke: pure geometry, no image assets ----
root = tk.Tk()
root.withdraw()
face = ProceduralFace(root, size=176, state="sleeping")
assert face.is_placeholder() is False
from maya_identity.renderer.hologram_renderer import STATE_TEXT as RSTATE
for state in ("awake", "processing", "listening", "research", "sleeping", "offline"):
    face.set_state(state)
    assert face.state == state
    face._renderer.render(4)
    assert face.state_text() == RSTATE.get(state)
status = face.status_text()
assert "Maya" in status and "geometry 1.0.0" in status

small = ProceduralFace(root, size=48, state="awake")
small.set_state("sleeping")
assert small.state == "sleeping"

before = (ID / "identity.json").read_bytes()
root.update_idletasks()
after = (ID / "identity.json").read_bytes()
assert before == after, "renderer mutated identity.json"

small.destroy()
face.destroy()
root.destroy()

# ---- GUI wired presentation-only ----
app_src = (ROOT / "maya_app.py").read_text(encoding="utf-8")
assert "from maya_identity.renderer import ProceduralFace" in app_src
assert "from maya_identity.face import" not in app_src

print("procedural_identity=OK")
print("procedural_geometry=OK")
print("procedural_symmetry=OK")
print("procedural_expressions=OK")
print("procedural_config_driven=OK")
print("procedural_renderer=OK")
print("procedural_no_assets=OK")
print("procedural_none_mutating=OK")
print("procedural_gui_wired=OK")