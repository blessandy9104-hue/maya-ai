"""Identity-to-behavior integration battery (MAYA BATCH 8J-B).

Proves the explicit, controlled pathway:

    Maya identity
        -> controlled behavioral constraints
        -> verified response behavior
        -> presentation expression

Requirements covered (Batch 8J-B §8, §9):
  1. Identity influence   — changing an approved identity constraint changes
     the derived behavioral constraints.
  2. Identity isolation   — presentation personality never alters identity or
     reasoning.
  3. Verification priority— identity cannot bypass validation gates.
  4. Determinism          — same input + same identity version -> identical
     behavior.
  5. Provenance           — every behavioral constraint has an identity source.
  6. Versioning           — identity version changes are detectable.
  7. Memory safety        — user memory != Maya identity.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_identity.behavior import (
    IdentityBehavior,
    build_identity_behavior,
)
from maya_identity import identity as midentity
from maya_identity import rollback
from maya_runtime import personality
from maya_runtime.intelligence import bus
from maya_runtime.intelligence import feature_map
from maya_runtime.intelligence.bridge import (
    _extract_cognitive,
    expression_directive,
    run_conversation_for_expression,
)
from maya_runtime.intelligence.detector import detect

_ROOT = os.path.dirname(os.path.abspath(__file__))
_IDENTITY_JSON = os.path.join(_ROOT, "maya_identity", "identity.json")
_JOURNAL = os.path.join(_ROOT, "maya_identity", "metadata",
                        "identity_versions.jsonl")
_BEHAVIOR_SRC = os.path.join(_ROOT, "maya_identity", "behavior.py")
_DETECTOR_SRC = os.path.join(_ROOT, "maya_runtime", "intelligence",
                             "detector.py")

_EXPECTED_CODES = {"supervision_local", "identity_consistency",
                   "identity_stability", "versioned_change", "calibrated_self"}


def _ok(label):
    print(label + "=OK")


def _stat(path):
    st = os.stat(path)
    return (st.st_mtime, st.st_size, st.st_ino)


def _behavior_src():
    return open(_BEHAVIOR_SRC, encoding="utf-8").read()


# ---- 1. contract module ------------------------------------------------

_base = build_identity_behavior()
assert _base is not None
assert _base.identity_version == midentity.load_identity()["identity_version"]
_ok("identity_behavior_import_ok")

# every active principle is backed by a verification surface that exists
_principle_codes = {p[0] for p in _base.active_principles}
assert _principle_codes == {"epistemic_honesty", "verification_first",
                            "transparency", "controlled_evolution",
                            "user_sovereignty"}
assert feature_map.ALIGNMENT_FLOOR == 0.6
assert callable(midentity.finalize_canonical_face)
assert rollback.ROLLBACK_PROTOCOL == "maya.identity_rollback.plan.v1"
import maya_conversation_store as _store
assert "never promotes" in (_store.__doc__ or "")
_unsafe = _extract_cognitive({
    "meaning": {"meaning_scalar": 0.6, "meaning_vector": (0.6,), "ok": True},
    "language": {"register": "compact", "tone": "measured", "meaning_sha": "x"},
    "state": {"stability": 0.2, "drift": 0.8, "std": 0.3, "alignment": 0.4,
              "ok": False, "stability_ok": False},
    "safety": {"ok": False, "violations": ["boundary"]},
    "confidence": {"confidence": 0.3, "restricted": True, "output_budget": 24},
    "fusion": {"dominant": "maya"}})
_hold = expression_directive(_unsafe)
assert _hold["budget"] == 16 and "safety_boundary" in _hold["holds"]
_ok("identity_principles_architecture_supported_ok")

# ---- 2. immutability + determinism -------------------------------------

_payload = dict(midentity.load_identity())
_payload_before = json.loads(json.dumps(_payload, sort_keys=True))
_ctx = build_identity_behavior(_payload)
assert json.loads(json.dumps(_payload, sort_keys=True)) == _payload_before
try:
    setattr(_ctx, "digest", "tampered")
    raise AssertionError("IdentityBehavior is not frozen")
except Exception as exc:
    assert type(exc).__name__ == "FrozenInstanceError", repr(exc)
_ok("identity_context_immutable_ok")

_ctx2 = build_identity_behavior(dict(_payload))
assert _ctx.to_plain() == _ctx2.to_plain()
assert _ctx.digest == _ctx2.digest
_ok("identity_context_deterministic_ok")

# ---- 3. identity influence + provenance + versioning -------------------

_codes = {c.code for c in _ctx.behavioral_constraints}
assert _codes == _EXPECTED_CODES, _codes
_stripped = {k: v for k, v in _payload.items() if k != "protection_rule"}
_ctx_less = build_identity_behavior(_stripped)
_codes_less = {c.code for c in _ctx_less.behavioral_constraints}
assert "versioned_change" not in _codes_less
assert _ctx_less.text != _ctx.text
_ok("identity_influence_constraint_change_ok")

_bumped = dict(_payload)
_bumped["identity_version"] = "1.0.1"
_ctx_bumped = build_identity_behavior(_bumped)
assert _ctx_bumped.digest != _ctx.digest
assert _ctx_bumped.identity_version == "1.0.1"
_ok("identity_version_detectable_ok")

_keys = set(_payload.keys())
for c in _ctx.behavioral_constraints:
    assert c.source in _keys, c.source
assert set(_ctx.provenance) == {c.source for c in _ctx.behavioral_constraints}
_ok("identity_provenance_ok")

assert len(_ctx.text) < 512
assert len(_ctx.text.splitlines()) <= 8
assert _ctx.text.count("- ") == len(_ctx.behavioral_constraints)
_ok("identity_constraints_bounded_ok")

# ---- 4. verification priority (identity cannot bypass gates) ------------

_held = expression_directive(None)
_merged = dict(_held)
_merged["text"] = _held["text"] + "\n\n" + _ctx.text
assert _merged["budget"] == 16 and _merged["register"] == "reserved"
assert _merged["holds"] == ["intelligence_unavailable"]
_gate_env = run_conversation_for_expression("hello, how are you?")
_gate = dict(_gate_env["directive"])
_gate["text"] = ""
_ref = expression_directive(_gate_env["cognitive"])
_ref["text"] = ""
assert _gate == _ref, (_gate, _ref)
_ok("identity_cannot_override_verification_ok")

assert feature_map.ALIGNMENT_FLOOR == 0.6
_plain = _ctx.to_plain()
assert "confidence" not in _plain and "budget" not in _plain \
    and "holds" not in _plain
_low = _ctx.text.lower()
for _word in ("confident", "certain", "guarantee", "assured"):
    assert _word not in _low, _word
_ok("identity_no_false_confidence_ok")

# ---- 5. presentation isolation -----------------------------------------

_P = personality.PERSONALITY
_targets = {p: _P.channel_targets(p, blend=1.0) for p in _P.available()}
assert _targets["calm"] != _targets["warm"]
_profiles = {p: _P.profile(p) for p in _P.available()}
assert _profiles["calm"] != _profiles["warm"]
assert build_identity_behavior(dict(_payload)).to_plain() == _ctx.to_plain()
_ok("presentation_isolation_from_identity_ok")

def _frame_digest():
    return run_conversation_for_expression("hello, how are you?")["cognitive"]

_cog_before = _frame_digest()
for _p in _P.available():
    _P.paced_state(_p, {"expression": 0.1, "viseme": 0.1, "micro": 0.0})
_cog_after = _frame_digest()
assert _cog_before == _cog_after
_ok("presentation_isolation_from_reasoning_ok")

# ---- 6. identity placed at the correct stage ---------------------------

_text = "temperature 25 degrees"
_det_a = detect(_text)
build_identity_behavior(dict(_payload))
_det_b = detect(_text)
assert _det_a == _det_b
_detector_src = open(_DETECTOR_SRC, encoding="utf-8").read()
assert "maya_identity" not in _detector_src
assert "identity_behavior" not in _detector_src
assert "build_identity_behavior" not in _detector_src
_ok("identity_not_in_interpretation_ok")

_env = run_conversation_for_expression("hello, how are you?")
assert _env["identity"] is not None
assert "Identity behavior" in _env["directive"]["text"]
assert _env["directive"]["text"].endswith(_env["identity"]["text"])
assert len(_env["identity"]["digest"]) == 64
_ok("identity_before_generation_not_decoration_ok")

# ---- 7. bridge pathway + determinism -----------------------------------

_env2 = run_conversation_for_expression("hello, how are you?")
assert _env["identity"] == _env2["identity"]
assert _env["directive"]["text"] == _env2["directive"]["text"]
assert _env["directive"]["budget"] == _env2["directive"]["budget"]
assert _env["identity"]["identity_version"] == \
    midentity.load_identity()["identity_version"]
_ok("bridge_deterministic_pathway_ok")

# ---- 8. memory safety ---------------------------------------------------

assert bus.AUTHORITATIVE_SOURCES["identity"] == "maya_identity/identity.json"
_ok("bus_identity_source_unmodified_ok")

_body = _behavior_src()
for _bad in ("import random", "import time", "datetime",
             "maya_conversation_store", "andy_profile", "subprocess"):
    assert _bad not in _body, _bad
assert "'w'" not in _body and '"w"' not in _body
_ok("identity_guide_not_reasoning_engine_ok")

_id_before = _stat(_IDENTITY_JSON)
_journal_before = _stat(_JOURNAL)
build_identity_behavior()
run_conversation_for_expression("memory safety probe")
_ctx_after = build_identity_behavior()
assert _stat(_IDENTITY_JSON) == _id_before
assert _stat(_JOURNAL) == _journal_before
assert _ctx_after.digest == _ctx.digest
_ok("identity_write_free_ok")

_events = _store.append_exchange("identity vs memory probe",
                                 "User memory stays separate from Maya identity.")
assert _events is not None
assert _stat(_IDENTITY_JSON) == _id_before
assert _stat(_JOURNAL) == _journal_before
assert build_identity_behavior().digest == _ctx.digest
_ok("conversation_memory_never_identity_ok")

print("test_identity_behavior_integration=PASS")