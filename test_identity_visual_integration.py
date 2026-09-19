"""Identity-to-embodiment integration battery (MAYA BATCH 8J-C).

Proves the explicit, controlled pathway:

    Maya identity
        -> verified behavior
        -> semantic state
        -> controlled visual representation
        -> future face-ready architecture

Core principle:
    Embodiment represents identity.
    Embodiment does not create identity.

Requirements covered (Batch 8J-C §10):
  1. Identity consistency    — same identity version produces the same
                               visual rules and identity digests.
  2. Visual determinism      — same VisualState produces the same output
                               (restricted state, projection, raster digest).
  3. Boundary protection     — identity constrains renderer inputs; the
                               renderer cannot modify identity.
  4. Expression limits       — expressions stay within approved bounds and
                               the honest vocabulary.
  5. Version tracking        — visual identity changes are recorded through
                               an explicit activation gate (no silent drift).
"""
import inspect
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_identity import identity as midentity
from maya_identity.embodiment import semantic_interpretation as _seminterp
from maya_identity.embodiment import shape_math
from maya_identity.embodiment import visual_command as _vc
from maya_identity.embodiment.semantic_interpretation import adapt_semantic
from maya_identity.embodiment.visual_command import (
    VisualCommand,
    activate_visual_identity,
    build_visual_command,
    restrict_visual_state,
    to_visual_state,
    validate_visual_identity,
    visual_identity_version,
)
from maya_identity.embodiment.visual_state import VisualState, build_visual_state
from maya_identity.wireframe.face_semantics import (
    SEMANTIC_NAMES,
    semantic_controls,
)
from maya_identity.wireframe.math_coordinator import (
    CHANNEL_MAX,
    CH_EXPRESSION,
    CH_VISEME,
    CONTROL_CHANNELS,
)
from maya_runtime import personality

_ROOT = os.path.dirname(os.path.abspath(__file__))
_IDENTITY_JSON = os.path.join(_ROOT, "maya_identity", "identity.json")
_JOURNAL = os.path.join(_ROOT, "maya_identity", "metadata",
                        "identity_versions.jsonl")
_COMMAND_SRC = os.path.join(_ROOT, "maya_identity", "embodiment",
                           "visual_command.py")
_TEMP_SHAPE_SRC = os.path.join(_ROOT, "maya_identity", "renderer",
                               "temporary_shape.py")
_SEMANTIC_SRC = os.path.join(_ROOT, "maya_identity", "embodiment",
                             "semantic_interpretation.py")
_APP_SRC = os.path.join(_ROOT, "maya_app.py")

_EXPECTED_RULE_CODES = {
    "visual_consistency", "visual_stability", "visual_versioned_change",
    "visual_conservative_presence", "visual_honest_expression",
}

_SEMANTIC_NAMES_EXACT = {
    "neutral", "attentive", "focused", "curious", "warm", "amused",
    "concerned", "speaking", "listening", "dormant", "active",
}


def _ok(label):
    print(label + "=OK")


def _stat(path):
    st = os.stat(path)
    return (st.st_mtime, st.st_size, st.st_ino)


def _pure_vs(semantic="focused", attention=0.4, focus=0.6, activity=0.5,
             curiosity=0.0):
    return VisualState(semantic=semantic, attention=attention, focus=focus,
                       curiosity=curiosity, activity=activity,
                       gaze_dx=0.1, gaze_dy=0.0, rest=False)


# ---- 1. contract module + architecture-backed rules ----------------------

_cmd = build_visual_command()
assert _cmd is not None
assert _cmd.identity_version == midentity.load_identity()["identity_version"]
assert _cmd.visual_identity_version == \
    visual_identity_version(midentity.load_identity())
_ok("visual_command_import_ok")

_rules = {r.code: r for r in (_cmd.active_rules or ())}
assert set(_rules) == _EXPECTED_RULE_CODES, set(_rules)
assert set(SEMANTIC_NAMES) == _SEMANTIC_NAMES_EXACT
assert hasattr(shape_math, "SCALE_MIN") and hasattr(shape_math, "SCALE_MAX")
assert hasattr(shape_math, "TRAVEL_MAX")
assert hasattr(midentity, "VERSIONS_LOG")
assert callable(activate_visual_identity)
assert callable(validate_visual_identity)
assert callable(adapt_semantic)
assert callable(semantic_controls)
# the conservative-presence rule is backed by the existing restricted gate:
# a restricted reading suppresses the semantic activity lift in VisualState.
class _Fs:
    extra = {"semantic": "focused"}

_fs = _Fs()
_vs_free = build_visual_state(
    _fs, semantic=adapt_semantic({"confidence": 0.9, "meaning_scalar": 0.9,
                                  "meaning_ok": True, "stability_ok": True,
                                  "stability": 0.9, "restricted": False}))
_vs_held = build_visual_state(
    _fs, semantic=adapt_semantic({"confidence": 0.9, "meaning_scalar": 0.9,
                                  "meaning_ok": True, "stability_ok": True,
                                  "stability": 0.9, "restricted": True}))
assert _vs_free.activity > _vs_held.activity, (_vs_free.activity,
                                               _vs_held.activity)
_ok("visual_identity_rules_architecture_supported_ok")

# ---- 2. immutability + determinism ---------------------------------------

_payload = dict(midentity.load_identity())
_payload_before = json.loads(json.dumps(_payload, sort_keys=True))
_cmd = build_visual_command(identity_payload=_payload)
assert json.loads(json.dumps(_payload, sort_keys=True)) == _payload_before
try:
    setattr(_cmd, "identity_digest", "tampered")
    raise AssertionError("VisualCommand is not frozen")
except Exception as exc:
    assert type(exc).__name__ == "FrozenInstanceError", repr(exc)
_ok("visual_command_immutable_ok")

_cmd2 = build_visual_command(identity_payload=dict(_payload))
assert _cmd.as_dict() == _cmd2.as_dict()
assert _cmd.identity_digest == _cmd2.identity_digest
assert _cmd.signature() == _cmd2.signature()
_ok("visual_command_deterministic_ok")

# ---- 3. identity consistency (same version -> same visual rules) ---------

_rule_codes_a = {r.code for r in _cmd.active_rules}
_rule_codes_b = {r.code for r in build_visual_command(
    identity_payload=dict(_payload)).active_rules}
assert _rule_codes_a == _rule_codes_b
assert _cmd.identity_digest == \
    build_visual_command(identity_payload=dict(_payload)).identity_digest
_ok("visual_identity_consistency_ok")

_bumped = dict(_payload)
_bumped["identity_version"] = "1.0.1"
_cmd_bumped = build_visual_command(identity_payload=dict(_bumped))
assert _cmd_bumped.visual_identity_version == "1.0.1/1.0.0"
assert _cmd_bumped.identity_digest != _cmd.identity_digest
assert _cmd_bumped.signature() != _cmd.signature()
_ok("visual_identity_version_detectable_ok")

# ---- 4. provenance -------------------------------------------------------

_keys = set(_payload.keys())
for r in _cmd.active_rules:
    assert r.source in _keys, r.source
assert set(_cmd.provenance) == {r.source for r in _cmd.active_rules}
_ok("visual_rule_provenance_ok")

# ---- 5. bounded command --------------------------------------------------

for _field in ("attention", "activity", "focus", "presence"):
    assert 0.0 <= getattr(_cmd, _field) <= 1.0, _field
assert _cmd.semantic_emphasis in SEMANTIC_NAMES
for _control, _value in _cmd.expression_params:
    assert 0.0 <= _value <= 1.0, (_control, _value)
assert len(_cmd.identity_digest) == 64
assert len(_cmd.signature()) == 64
_ok("visual_command_bounded_ok")

# ---- 6. visual determinism (same VisualState -> same output) -------------

_vs = _pure_vs()
_cmdv = build_visual_command(base_state=_vs, identity_payload=_payload)
_restricted = restrict_visual_state(_cmdv, _vs)
assert _restricted == _vs  # identity re-enforces the same hard bounds
_t = to_visual_state(_cmdv)
assert _t.attention == _vs.attention and _t.focus == _vs.focus
assert _t.activity == _vs.activity and _t.semantic == _vs.semantic
assert shape_math.project(_vs, 3).signature() == \
    shape_math.project(_restricted, 3).signature()
assert shape_math.render_raster(_vs, 3)[1] == \
    shape_math.render_raster(_restricted, 3)[1]
_ok("visual_determinism_state_ok")

# ---- 7. boundary protection ----------------------------------------------

_id_before = _stat(_IDENTITY_JSON)
_journal_before = _stat(_JOURNAL)
_vs_hi = _pure_vs(attention=0.9, activity=0.8)
_cmdv_hi = build_visual_command(base_state=_vs_hi, identity_payload=_payload)
assert _cmdv_hi.identity_digest == _cmdv.identity_digest
assert _cmdv_hi.signature() != _cmdv.signature()  # state binds, identity stays
to_visual_state(_cmdv_hi)
restrict_visual_state(_cmdv_hi, _vs_hi)
assert _stat(_IDENTITY_JSON) == _id_before
assert _stat(_JOURNAL) == _journal_before
_ok("identity_constrains_renderer_boundaries_ok")

# ---- 8. renderer purity (identity change never changes the raster) -------

_raster_before = shape_math.render_raster(_vs, 3)[1]
build_visual_command(base_state=_vs, identity_payload=dict(_bumped))
assert shape_math.render_raster(_vs, 3)[1] == _raster_before
assert shape_math.project(_vs, 3).signature() == \
    shape_math.project(_restricted, 3).signature()
_ok("renderer_pure_output_ok")

# ---- 9. honest expression vocabulary -------------------------------------

_low_em = _cmd.semantic_emphasis.lower()
for _word in ("feeling", "feels", "emotion", "emotional", "conscious",
              "consciousness", "private experience", "happy", "sad",
              "angry", "fear", "joy"):
    assert _word not in _low_em, _word
_rule = _rules["visual_honest_expression"]
assert "never real feelings" in _rule.implication
assert set(SEMANTIC_NAMES) == _SEMANTIC_NAMES_EXACT
_ok("visual_honest_expression_vocabulary_ok")

# ---- 10. expression limits within approved bounds ------------------------

for _control, _value in _cmdv.expression_params:
    _ch = CONTROL_CHANNELS.get(_control)
    if _ch in (CH_EXPRESSION, CH_VISEME):
        assert _value <= CHANNEL_MAX[_ch] + 1e-9, (_control, _value, _ch)
assert CHANNEL_MAX["expression"] == 0.5
assert CHANNEL_MAX["viseme"] == 0.35
_ok("expression_limits_within_bounds_ok")

# ---- 11. identity not in the renderer / semantic layer -------------------

_tmp_src = open(_TEMP_SHAPE_SRC, encoding="utf-8").read()
assert "visual_command" not in _tmp_src
assert "maya_identity.behavior" not in _tmp_src
assert "build_visual_command" not in _tmp_src
_sem_src = open(_SEMANTIC_SRC, encoding="utf-8").read()
assert "visual_command" not in _sem_src
for _bad in ("import random", "import time", "datetime", "subprocess"):
    assert _bad not in _sem_src, _bad
assert "maya_conversation" not in _sem_src
_ok("identity_not_in_renderer_ok")
_ok("identity_not_in_semantic_interpretation_ok")

# ---- 12. build path purity (command layer never writes or animates) ------

_build_src = "".join(inspect.getsource(getattr(_vc, name))
                     for name in ("build_visual_command",
                                  "validate_visual_identity",
                                  "restrict_visual_state",
                                  "to_visual_state",
                                  "visual_identity_version",
                                  "_identity_digest"))
for _bad in ("open(", "'w'", '"w"', "import random", "import time",
             "datetime", "subprocess", "conversation", "import renderer",
             "renderer.", "from maya_identity.renderer"):
    assert _bad not in _build_src, _bad
_ok("visual_identity_build_pure_ok")

_id_after_build = _stat(_IDENTITY_JSON)
_journal_after_build = _stat(_JOURNAL)
assert _id_after_build == _id_before and _journal_after_build == _journal_before
_ok("visual_identity_write_free_ok")

# ---- 13. validation -------------------------------------------------------

_okv, _reasons = validate_visual_identity(_cmd)
assert _okv, _reasons
assert not validate_visual_identity(
    build_visual_command(identity_payload={}))[0]
from dataclasses import replace
assert not validate_visual_identity(replace(_cmd, attention=7.0))[0]
assert not validate_visual_identity(
    replace(_cmd, identity_digest="00" * 32))[0]
_ok("versioning_validation_ok")

# ---- 14. activation gate (no silent drift; explicit record only) ---------

_journal_hash_before = open(_JOURNAL, "rb").read()
_tmp_journal = os.path.join(tempfile.mkdtemp(), "identity_versions.jsonl")
_orig_log = midentity.VERSIONS_LOG
try:
    midentity.VERSIONS_LOG = _tmp_journal
    _evt = activate_visual_identity(_cmd)
    assert _evt["event"] == "visual_identity_activated"
    assert _evt["visual_identity_version"] == _cmd.visual_identity_version
    assert _evt["identity_digest"] == _cmd.identity_digest
    assert _evt["validation"] == "validated"
    _rows = [json.loads(r) for r in
             open(_tmp_journal, encoding="utf-8").read().splitlines()
             if r.strip()]
    assert len(_rows) == 1 and _rows[0]["event"] == "visual_identity_activated"
    _size = os.path.getsize(_tmp_journal)
    _failed = activate_visual_identity(replace(_cmd, attention=7.0))
    assert _failed["status"] == "validation_failed"
    assert os.path.getsize(_tmp_journal) == _size  # invalid -> no write
finally:
    midentity.VERSIONS_LOG = _orig_log
assert open(_JOURNAL, "rb").read() == _journal_hash_before
assert _stat(_JOURNAL) == _journal_before
assert _stat(_IDENTITY_JSON) == _id_before
_ok("versioning_activation_gate_ok")

# ---- 15. presentation isolation from visual identity ---------------------

_P = personality.PERSONALITY
_t_cmd = build_visual_command(identity_payload=dict(_payload)).as_dict()
for _persona in _P.available():
    _P.paced_state(_persona, {"expression": 0.2, "viseme": 0.2, "micro": 0.0})
_t_cmd_after = build_visual_command(identity_payload=dict(_payload)).as_dict()
assert _t_cmd == _t_cmd_after
_ok("presentation_isolation_from_visual_identity_ok")

# ---- 16. wired into the real tick pathway --------------------------------

_app_src = open(_APP_SRC, encoding="utf-8").read()
assert "from maya_identity.embodiment.visual_command import" \
    " build_visual_command" in _app_src
assert "_latest_visual_identity = build_visual_command(" in _app_src
assert "_latest_visual_identity = None" in _app_src
_ok("maya_app_visual_identity_wiring_ok")

print("test_identity_visual_integration=PASS")