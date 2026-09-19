"""Persona boundary battery (MAYA BATCH 8J-A).

Establishes and verifies the identity-layer naming contract:

- COGNITIVE persona   -- maya_runtime/intelligence/persona.py
                         (protocol maya.persona_fusion.v1). Authoritative for
                         ``context.persona_fusion``; consumed via the
                         intelligence bridge and the unified state bus.
- PRESENTATION        -- maya_runtime/personality.py (channel profiles) and
                         the deployment profile deck. Style only: never a
                         cognitive or identity surface.
- LEGACY persona_layer -- retired to a defined ``deprecated`` state.

Checks: authority, separation (presentation cannot modify cognition),
imports, stale-reference absence, defined legacy state, and memory/identity
write-isolation of the boundary exercise.
"""
import importlib
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime import personality
from maya_runtime.intelligence import bus
from maya_runtime.intelligence import persona as cognitive_persona

import persona_layer
import maya_identity.identity as identity

_ROOT = os.path.dirname(os.path.abspath(__file__))

_COGNITIVE_ONLY_KEYS = {
    "meaning_scalar", "meaning_vector", "meaning_ok", "stability", "drift",
    "alignment", "state_ok", "safety_ok", "register", "tone",
}


def _ok(label):
    print(label + "=OK")


def _file_text(rel):
    return open(os.path.join(_ROOT, rel), encoding="utf-8").read()


def _rel_stat(rel):
    path = os.path.join(_ROOT, rel)
    st = os.stat(path)
    return (st.st_mtime, st.st_size, st.st_ino)


# ---- authority ------------------------------------------------------------

assert cognitive_persona.PERSONA_PROTOCOL == "maya.persona_fusion.v1"
assert cognitive_persona.FUSION_METHOD == "weighted_multi_persona_fusion"
assert callable(cognitive_persona.compute)
_ok("cognitive_authority_protocol_ok")

assert bus.AUTHORITATIVE_SOURCES["persona_fusion"] == \
    "maya_runtime.intelligence.persona"
_ok("persona_fusion_source_ok")

assert importlib.util.find_spec("maya_runtime.intelligence.persona") is not None
_ok("cognitive_authority_module_exists_ok")

# ---- imported surfaces load cleanly --------------------------------------

assert importlib.import_module(
    bus.AUTHORITATIVE_SOURCES["persona_fusion"]).PERSONA_PROTOCOL == \
    "maya.persona_fusion.v1"
_ok("authority_reference_resolves_ok")

# ---- separation: presentation personality cannot modify cognition ---------

_profile = personality.PERSONALITY.profile("calm")
assert set(_profile).issubset({"expression", "viseme", "micro", "pace"})
_ok("presentation_profile_shape_ok")

_CH = getattr(personality, "CHANNEL_MAX", None)
if _CH is None:
    from maya_runtime.core import CHANNEL_MAX as _CH
for _ch in ("expression", "viseme", "micro"):
    assert _profile[_ch] <= _CH[_ch] + 1e-9
targets = personality.PERSONALITY.channel_targets("calm", blend=1.0)
for _ch in ("expression", "viseme", "micro"):
    assert 0.0 <= targets[_ch] <= _CH[_ch] + 1e-9
_ok("presentation_channels_bounded_ok")

assert not set(targets).intersection(_COGNITIVE_ONLY_KEYS)
assert "persona_id" not in targets
_ok("presentation_no_cognition_keys_ok")

_mapping = {
    "kind": "geometric_point",
    "provenance": {"source": "boundary.battery",
                   "retrieved_at": "2026-09-10T12:00:00Z"},
}
_before = cognitive_persona.compute(world_mapping=_mapping,
                                    detected_type="geometric_point")
_appr = personality.PERSONALITY.paced_state("warm", {"expression": 0.1,
                                                     "viseme": 0.1, "micro": 0.0})
_after = cognitive_persona.compute(world_mapping=_mapping,
                                   detected_type="geometric_point")
assert _before == _after
_ok("presentation_no_cognition_side_effect_ok")

# ---- identity / memory write isolation during the boundary exercise -------

_before_identity = _rel_stat(os.path.join("maya_identity", "identity.json"))
_before_journal = _rel_stat(
    os.path.join("maya_identity", "metadata", "identity_versions.jsonl"))
for _pid in ("analytical.geometry", "core.evidence"):
    personality.PERSONALITY.paced_state("calm", {"expression": 0.1,
                                                 "viseme": 0.1, "micro": 0.0})
# repeated fusion exercise
cognitive_persona.compute(world_mapping=_mapping, detected_type="geometric_point")
assert _rel_stat(os.path.join("maya_identity", "identity.json")) == \
    _before_identity
assert _rel_stat(
    os.path.join("maya_identity", "metadata", "identity_versions.jsonl")) == \
    _before_journal
_ok("identity_memory_no_write_ok")

# presentation + cognitive modules carry no memory/identity/conv-store deps
assert "maya_conversation_store" not in _file_text(
    os.path.join("maya_runtime", "personality.py"))
assert "andy_profile" not in _file_text(
    os.path.join("maya_runtime", "personality.py"))
assert "maya_conversation_store" not in _file_text(
    os.path.join("maya_runtime", "intelligence", "persona.py"))
assert "andy_profile" not in _file_text(
    os.path.join("maya_runtime", "intelligence", "persona.py"))
_ok("persona_surface_no_memory_identity_deps_ok")

# # ---- stale reference removed ---------------------------------------------

assert "personality.profiles" not in _file_text(
    os.path.join("maya_runtime", "intelligence", "bus.py"))
_ok("stale_reference_absent_ok")

# ---- no duplicate cognitive authority -------------------------------------

assert not hasattr(personality, "PERSONA_PROTOCOL")
assert not hasattr(personality, "FUSION_METHOD")
assert not hasattr(personality, "compute")
_ok("no_duplicate_cognitive_authority_ok")

# ---- legacy persona_layer: defined state, no ambiguous state ---------------

assert persona_layer.PERSONA_LAYER_STATE in {"active", "adapter",
                                             "deprecated", "removed"}
assert persona_layer.PERSONA_LAYER_STATE == "deprecated"
assert not hasattr(persona_layer, "PersonaLayer")
assert not hasattr(persona_layer, "PERSONA_PROFILES")
_layer_init = _file_text(os.path.join("persona_layer", "__init__.py"))
assert "from .persona_registry" not in _layer_init
assert "from .persona_loader" not in _layer_init
assert ".persona_registry import" not in _layer_init
assert ".persona_loader import" not in _layer_init
_ok("legacy_layer_state_defined_ok")

assert identity.load_identity()["canonical_name"] == "Maya"
_ok("core_identity_intact_ok")