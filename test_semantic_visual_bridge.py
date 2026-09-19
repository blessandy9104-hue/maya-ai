"""Semantic-state integration suite (Batch 8D).

The genuine semantic pathway: Maya's intelligence-bridge cognitive frame ->
``SemanticCue`` (bounded, deterministic) -> existing ``VisualState`` ->
``shape_math.project`` -> embodiment renderer.

The suite is fully deterministic and GUI-free (no tkinter): the semantic
adapter, the visual mapping, and the projector are pure functions. The
end-to-end drill invokes the real intelligence bridge with ``bus_enabled=False``
(no file writes, no network) to prove the chain accepts Maya's actual
semantic output.

Registered in verification/manifest.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from maya_identity.embodiment.semantic_interpretation import (
    ACTIVITY_SEMANTIC_GAIN,
    FOCUS_CEILING,
    FOCUS_SEMANTIC_GAIN,
    DOMAIN as CUE_DOMAIN,
    LINE_PREFIX,
    SemanticCue,
    adapt_semantic,
    from_dict,
    from_line,
    to_line,
)
from maya_identity.embodiment.visual_state import (
    DOMAIN, VisualState, build_visual_state,
)
from maya_identity.embodiment.shape_math import (
    motion_signature, project, render_raster,
)
from maya_identity.wireframe.face_semantics import (
    SEMANTIC_NAMES, build_semantic_face_state,
)
from maya_runtime.face_drive import runtime_face_state
from maya_runtime.intelligence.bridge import run_conversation_for_expression
import verification.oracle_semantic_visual as oracle

# 8C parity pins (prove "semantic=None" never changes the 8C contract).
_8C_PINS = {
    "neutral": "fd371200e5630dce3e8b8887133707d96f198d4f8d5be547830a19c7cde2fff6",
    "attentive": "46eac21a48a581cc4edd716da8ae1776faa6d4e1adcd6bbf4a0e7a79633eb9be",
    "focused": "74ef200a7295a5ffa7aa711688b3cbd6a73a05e2b5c9d3393b61c35c5a71c225",
    "curious": "d7cd21e8203bf0b61c62f2bda07a21a842033bd3348c5bee56081d64c20333d8",
    "warm": "c32190b6aa7cd79f15ee5496715b7d1d7208542fd7495b5bb49fb33f05738eda",
    "amused": "bf9df7bdff7bff2358f3c4150d60bf8acd9c06bab4f2690485c0d4b7ceaca0a7",
    "concerned": "9e2c2e7551be7222a10e905d42b4d18794ebe3756d8ce31b01245592d2e50868",
    "speaking": "6a99e0ec6b689d32864f4012563cc8ebab2b486a212f3539696c734da75f25fa",
    "listening": "acfb6462edbed115639eb2cd8e595155661425784950c804fa3f83ec562c2a75",
    "dormant": "e9d13f605c2ed3868974d15dbff9c47d943c142d6614df1a5707bf275c300e6e",
    "active": "256841688a8331bd80e76c6b86f709e4d77cb2f96111bfcbf38a22f1bea74535",
}

KEEP = ("semantic", "attention", "curiosity", "gaze_dx", "gaze_dy", "rest")


def _chk(name):
    print("=" + name + "=OK")


def _cue(confidence=0.0, meaning=0.0, restricted=False, ambiguous=False,
         meaning_ok=True, stability_ok=True, stability=0.0, register="measured"):
    return SemanticCue(
        confidence=confidence, meaning=meaning, restricted=restricted,
        ambiguous=ambiguous, meaning_ok=meaning_ok, stability_ok=stability_ok,
        stability=stability, register=register)


def _vs(anchor, cue=None, meta=None, commands=None, visual=None, fs=None):
    if fs is None:
        fs = runtime_face_state(
            visual=(visual or _visual_of(anchor)), meta=meta or {},
            commands=commands or {})
    return build_visual_state(fs, meta, commands, semantic=cue)


def _vs_anchor(anchor, cue=None):
    """VS from the exact semantic anchor (bypasses the runtime visual mapping,
    which cannot reach curios/warm/amused/active anchors)."""
    fs = build_semantic_face_state(anchor)
    return build_visual_state(fs, {}, {}, semantic=cue)


def _visual_of(anchor):
    return {
        "neutral": "idle", "attentive": "awake", "focused": "processing",
        "curious": "research", "warm": "awake", "amused": "awake",
        "concerned": "error", "speaking": "awake", "listening": "listening",
        "dormant": "sleeping", "active": "processing",
    }[anchor]


def _fields(vs: VisualState):
    d = vs.as_dict()
    d.pop("signature", None)
    return d


def _same_except(a: VisualState, b: VisualState, only_changed=frozenset()):
    da, db = _fields(a), _fields(b)
    diff = {k for k in da if da[k] != db[k]}
    return diff <= set(only_changed)


# ---------------------------------------------------------------------------
# 1. provenance: every channel change traces to a documented upstream source
# ---------------------------------------------------------------------------

assert FOCUS_CEILING >= 0.0 and ACTIVITY_SEMANTIC_GAIN > 0.0
# Single-sourcing: visual_state consumes the adapter's gain constants, so the
# mapping cannot drift between the two modules.
import maya_identity.embodiment.visual_state as _vs_mod
import maya_identity.embodiment.semantic_interpretation as _si_mod
assert _vs_mod.FOCUS_SEMANTIC_GAIN is _si_mod.FOCUS_SEMANTIC_GAIN
assert _vs_mod.ACTIVITY_SEMANTIC_GAIN is _si_mod.ACTIVITY_SEMANTIC_GAIN
assert _vs_mod.FOCUS_CEILING is _si_mod.FOCUS_CEILING
# Renderer-free adapter (channel meaning lives upstream of any renderer).
assert "renderer" not in _si_mod.__file__.replace("\\", "/").split("/")
_chk("semantic_provenance_ok")


# ---------------------------------------------------------------------------
# 2. determinism: same input -> identical cue and VisualState
# ---------------------------------------------------------------------------

_cog1 = {"confidence": 0.87, "meaning_scalar": 0.72, "stability": 0.9,
         "restricted": False, "meaning_ok": True, "stability_ok": True,
         "register": "measured"}
_int1 = {"ambiguous": False, "confidence": 0.62, "primary_intent": "inquiry"}
_c1a = adapt_semantic(_cog1, _int1)
_c1b = adapt_semantic(dict(_cog1), dict(_int1))
assert _c1a == _c1b
assert _c1a.signature() == _c1b.signature()
_v1a = _vs("attentive", _c1a)
_v1b = _vs("attentive", _c1b)
assert _v1a == _v1b and _v1a.signature() == _v1b.signature()
# JSON machine-line round trip is identity-preserving.
assert from_line(to_line(_c1a)) == _c1a
assert from_dict(_c1a.as_dict()) == _c1a
_chk("semantic_determinism_ok")


# ---------------------------------------------------------------------------
# 3. bounds: all cue fields and all visual channels remain within domains
# ---------------------------------------------------------------------------

_cog3 = {"confidence": 1.7, "meaning_scalar": -0.4, "stability": 3.0,
         "restricted": True, "meaning_ok": True, "stability_ok": True}
_c3 = adapt_semantic(_cog3, {"ambiguous": True})
for k, (lo, hi) in CUE_DOMAIN.items():
    v = getattr(_c3, k)
    assert lo <= float(v) <= hi, k
assert _c3.confidence == 1.0 and _c3.meaning == 0.0
for anchor in SEMANTIC_NAMES:
    for conf in (0.0, 0.4, 0.7, 1.0):
        vs = _vs_anchor(anchor, _cue(confidence=conf, ambiguous=False))
        for k, (lo, hi) in DOMAIN.items():
            if k == "gaze":
                continue
            assert lo <= getattr(vs, k) <= hi, (anchor, k)
        assert vs.focus <= FOCUS_CEILING + 1e-12
    for mean in (0.0, 0.5, 1.0):
        vs = _vs_anchor(anchor, _cue(meaning=mean))
        assert 0.0 <= vs.activity <= 1.0
        assert -1.0 <= vs.gaze_dx <= 1.0 and -1.0 <= vs.gaze_dy <= 1.0
_chk("semantic_bounds_ok")


# ---------------------------------------------------------------------------
# 4. invalid input: malformed / missing / unknown inputs reduce to safe default
# ---------------------------------------------------------------------------

_c4 = adapt_semantic(None, None)
assert _c4 == SemanticCue()
assert _c4.signature() == SemanticCue().signature()
assert adapt_semantic({"confidence": "not-a-number", "meaning_ok": "zz"},
                      ["not-a-dict"]) == SemanticCue()
_c4b = adapt_semantic({"confidence": None, "meaning_scalar": None,
                       "restricted": None, "ambiguous": None, "meaning_ok": None},
                      {"unrelated": 1})
assert _c4b == SemanticCue()  # None/unknown reduce to the neutral default
# A neutral cue (any flavor) must be visually identical to no cue: this is the
# documented "safe behavior = no cognitive lift".
for anchor in SEMANTIC_NAMES:
    assert _vs_anchor(anchor, SemanticCue()).signature() == \
        _vs_anchor(anchor).signature()
    assert _vs_anchor(anchor, adapt_semantic({"bogus": 1})).signature() == \
        _vs_anchor(anchor).signature()
# Garbage semantic argument values never raise and stay neutral.
assert _vs("attentive", object()).signature() == \
    _vs("attentive").signature()
assert _vs("attentive", "nonsense").signature() == \
    _vs("attentive").signature()
# Machine line: rejects garbage, wrong tag, and digest tampering.
assert from_line("not our line") is None
assert from_line(LINE_PREFIX + "{broken") is None
_bad = _c1a.as_dict()
_bad["confidence"] = 0.99
assert from_dict(_bad) is None
_chk("semantic_invalid_input_ok")


# ---------------------------------------------------------------------------
# 5. state separation: a cue change touches only its mapped channels
# ---------------------------------------------------------------------------

_v_base = _vs("attentive", _cue(confidence=0.5, meaning=0.5))
# confidence -> focus only
_v_conf = _vs("attentive", _cue(confidence=1.0, meaning=0.5))
assert _same_except(_v_base, _v_conf, only_changed={"focus"})
assert _v_conf.focus > _v_base.focus
# meaning -> activity only
_v_mean = _vs("attentive", _cue(confidence=0.5, meaning=1.0))
assert _same_except(_v_base, _v_mean, only_changed={"activity"})
assert _v_mean.activity > _v_base.activity
# ambiguous gates focus lift only
_v_amb = _vs("attentive", _cue(confidence=1.0, meaning=0.5, ambiguous=True))
assert _same_except(_v_base, _v_amb, only_changed={"focus"})
assert _v_amb.focus == 0.60  # attentive tier: ambiguity suppresses the lift
assert _v_amb.focus < _v_conf.focus

# restricted gates activity lift only (vs the focused lift control variable)
_v_res = _vs("attentive", _cue(confidence=1.0, meaning=1.0, restricted=True))
assert _same_except(_v_conf, _v_res, only_changed={"activity"})
assert _v_res.activity < _v_conf.activity
assert _v_res.activity == _vs("attentive").activity  # held back to the tier
# unmapped fields (stability / register) change the cue digest but no channel
_v_stb = _vs("attentive", _cue(confidence=0.5, meaning=0.5, stability=0.3))
assert _same_except(_v_base, _v_stb)
assert _v_stb.signature() == _v_base.signature()
_v_reg = _vs("attentive", _cue(confidence=0.5, meaning=0.5, register="reserved"))
assert _same_except(_v_base, _v_reg)
# cue immunity of the kept channels over a grid
for anchor in SEMANTIC_NAMES:
    base = _vs_anchor(anchor, _cue(confidence=0.0, meaning=0.0))
    lifted = _vs_anchor(anchor, _cue(confidence=1.0, meaning=1.0))
    assert _same_except(base, lifted, only_changed={"focus", "activity"})
    for k in KEEP:
        assert getattr(base, k) == getattr(lifted, k)
_chk("semantic_state_separation_ok")


# ---------------------------------------------------------------------------
# 6. renderer separation: the adapter cannot influence rendering back upstream
# ---------------------------------------------------------------------------

_cog6 = dict(_cog1)
_int6 = dict(_int1)
_cue6 = adapt_semantic(_cog6, _int6)
assert _cog6 == _cog1 and _int6 == _int1  # inputs never mutated
_v6 = _vs("focused", _cue6)
assert _v6.semantic == "focused"
# Adapter + build share the same deterministic signature machine; a rerun with
# the same inputs yields identical bytes without any renderer involvement.
_c6b = adapt_semantic(_cog1, _int1)
assert _v6.signature() == _vs("focused", _c6b).signature()
# The adapter never imports anything under maya_identity.renderer.
assert "renderer" not in _si_mod.__file__
_src_text = Path(_si_mod.__file__).read_text(encoding="utf-8")
for forbidden in ("import tkinter", "import random", "import time",
                  "import datetime"):
    assert forbidden not in _src_text, forbidden
_chk("semantic_renderer_separation_ok")


# ---------------------------------------------------------------------------
# 7. replay: the same semantic sequence produces the same cue & VS sequence
# ---------------------------------------------------------------------------

_script = [
    (_cog1, _int1),
    ({"confidence": 0.3, "meaning_scalar": 0.1, "meaning_ok": False,
      "stability_ok": True, "restricted": True}, {"ambiguous": True}),
    ({"confidence": 0.95, "meaning_scalar": 0.9, "meaning_ok": True,
      "stability_ok": True, "restricted": False}, {"ambiguous": False}),
    ({}, {}),
    (None, None),
]
_cues_a = [adapt_semantic(c, i) for c, i in _script]
_cues_b = [adapt_semantic(c, i) for c, i in _script]
assert [c.signature() for c in _cues_a] == [c.signature() for c in _cues_b]
assert [to_line(c) for c in _cues_a] == [to_line(c) for c in _cues_b]
_vs_seq_a = [_vs("attentive", c) for c in _cues_a]
_vs_seq_b = [_vs("attentive", c) for c in _cues_b]
assert [v.signature() for v in _vs_seq_a] == [v.signature() for v in _vs_seq_b]
_chk("semantic_replay_ok")


# ---------------------------------------------------------------------------
# 8. end-to-end: real bridge cognitive frame -> cue -> VS -> projected shape
# ---------------------------------------------------------------------------

_TEXTS = [
    "Explain in detail how uncertainty propagates through an extended Kalman "
    "filter and what the covariance update means.",
    "ok.",
    "Should I take the north route through the mountains or the coastal road "
    "for a faster delivery tomorrow?",
]


def _real_turn(text):
    env = run_conversation_for_expression(text, [], 0, bus_enabled=False)
    cognitive = env.get("cognitive")
    assert cognitive is not None, env.get("failure")
    return adapt_semantic(cognitive)


_e2e_cues = [_real_turn(t) for t in _TEXTS]
_e2e_cues_again = [_real_turn(t) for t in _TEXTS]
assert [c.signature() for c in _e2e_cues] == \
    [c.signature() for c in _e2e_cues_again]
assert any(c.meaning > 0.0 or c.confidence > 0.0 for c in _e2e_cues)
# The driven face state (processing) with vs. without a real cue.
_e2e_fs = runtime_face_state(visual="processing", meta={}, commands={})
_vs_plain = build_visual_state(_e2e_fs)
_vs_cued = build_visual_state(_e2e_fs, semantic=_e2e_cues[0])
assert _vs_plain.semantic == "focused"
assert _vs_cued.semantic == "focused"
# The chain is observable: a real semantic condition changes the visual state.
assert _vs_cued.signature() != _vs_plain.signature()
# ...and it projects deterministically through the Batch 8C embodiment.
_m1 = motion_signature(_vs_cued, range(0, 60, 7))
_m2 = motion_signature(_vs_cued, range(0, 60, 7))
assert _m1 == _m2
_r1 = render_raster(_vs_cued, 12, size=64)[1]
_r2 = render_raster(_vs_cued, 12, size=64)[1]
assert _r1 == _r2
for anchor in ("focused", "attentive"):
    p = project(build_visual_state(runtime_face_state(visual="awake")),
                12) if anchor == "attentive" else project(_vs_cued, 12)
    assert 0.0 <= p.cx <= 1.0 and 0.0 <= p.cy <= 1.0
    assert 0.0 <= p.radius <= 0.2 and 0.0 <= p.roll_deg <= 360.0
_chk("semantic_end_to_end_ok")


# ---------------------------------------------------------------------------
# 9. backward compatibility: semantic=None is byte-identical to the 8C pins
# ---------------------------------------------------------------------------

for anchor, pin in _8C_PINS.items():
    fs = build_semantic_face_state(anchor)
    assert build_visual_state(fs).signature() == pin, anchor
_chk("semantic_backward_compat_ok")


# ---------------------------------------------------------------------------
# 10. clean-room oracle: source matches an independent re-derivation
# ---------------------------------------------------------------------------

for anchor in SEMANTIC_NAMES:
    for conf in (0.0, 0.25, 0.5, 0.75, 1.0):
        for amend, flags in ((False, dict(meaning_ok=True, stability_ok=True,
                                          restricted=False)),
                             (True, dict(meaning_ok=True, stability_ok=True,
                                         restricted=False)),
                             (False, dict(meaning_ok=False, stability_ok=True,
                                          restricted=False)),
                             (False, dict(meaning_ok=True, stability_ok=True,
                                          restricted=True))):
            src_cue = _cue(confidence=conf, meaning=0.7, ambiguous=amend,
                           **flags)
            ora_cue = {"confidence": conf, "meaning": 0.7, "ambiguous": amend,
                       "restricted": flags["restricted"],
                       "meaning_ok": flags["meaning_ok"],
                       "stability_ok": flags["stability_ok"]}
            assert _vs_anchor(anchor, src_cue).focus == \
                oracle.oracle_focus(anchor, ora_cue), (anchor, conf, amend)
            assert _vs_anchor(anchor, src_cue).activity == \
                oracle.oracle_activity(anchor, 0.0, ora_cue), \
                (anchor, conf, flags)
    # backward-compat identities from the oracle
    assert oracle.oracle_focus(anchor, None) == oracle.FOCUS_TIER[anchor]
    assert oracle.oracle_activity(anchor, 0.0, None) == \
        oracle.ACTIVITY_TIER[anchor]
    # bounds proof
    cue100 = {"confidence": 1.0, "meaning": 1.0, "ambiguous": False,
              "meaning_ok": True, "stability_ok": True, "restricted": False}
    assert oracle.oracle_focus(anchor, cue100) <= FOCUS_CEILING + 1e-12
    assert oracle.oracle_bounds_proof(anchor, cue100, 0.0, 1.0) <= 1.0
    assert oracle.oracle_activity(anchor, 0.0, cue100) <= 1.0 + 1e-12
# Separation identity: the oracle's immune set matches the 8D spec (the five
# channels a cue may never touch; the anchor ``semantic`` label is not a
# cue-driven channel).
assert oracle.oracle_separation(None) == \
    {"attention", "curiosity", "gaze_dx", "gaze_dy", "rest"}
_chk("semantic_oracle_ok")


# ---------------------------------------------------------------------------
# 11. machine-line channel: digest-verified and tamper-proof
# ---------------------------------------------------------------------------

_line = to_line(_c1a)
assert _line.startswith(LINE_PREFIX)
_parsed = from_line(_line)
assert _parsed == _c1a and _parsed.signature() == _c1a.signature()
# Tamper: same fields with a different confidence but the stale digest -> reject.
_data = json.loads(_line[len(LINE_PREFIX):])
_evil = dict(_data)
_evil["confidence"] = 0.99
assert from_line(LINE_PREFIX + json.dumps(
    _evil, sort_keys=True, separators=(",", ":"))) is None
# A host re-mints an honest digest for the (bounded) tampered fields -> accept.
_honest = dict(_evil)
_honest["digest"] = SemanticCue(
    confidence=0.99, stability=_c1a.stability, meaning=_c1a.meaning,
    restricted=_c1a.restricted, ambiguous=_c1a.ambiguous,
    meaning_ok=_c1a.meaning_ok, stability_ok=_c1a.stability_ok,
    register=_c1a.register).signature()
assert from_line(LINE_PREFIX + json.dumps(
    _honest, sort_keys=True, separators=(",", ":"))).confidence == 0.99
assert from_dict({"adapt": "other", "digest": "x"}) is None
_chk("semantic_line_channel_ok")


# ---------------------------------------------------------------------------
# 12. cross-interpreter pins (established on 3.13.15; must match on 3.14.7)
# ---------------------------------------------------------------------------

PINNED_CUE = {
    "C_NONE": "7167cec5ecc12967ef7c4e97e2ddc7a7e9b3e6337547b745ad85d310b77c6ee0",
    "C_FULL": "c5a019dfc6ce3e704d4213d7e9adef2be6de868e62b78e99e68264f5e9d8565f",
    "C_AMB_REST": "cc930ee9fb58f95975b52c15a4b6fe4024295a5ebd7711710a541ecc97436df9",
}
PINNED_VS = {
    "VS_C_NONE": "46eac21a48a581cc4edd716da8ae1776faa6d4e1adcd6bbf4a0e7a79633eb9be",
    "VS_C_FULL": "1a8af1f266fb96a28db9acc992d10141e7891aa93533e18e830ffa206636c999",
    "VS_C_AMB_REST": "46eac21a48a581cc4edd716da8ae1776faa6d4e1adcd6bbf4a0e7a79633eb9be",
}
PINNED_E2E = {
    "cue": "76f03ff53a24645038017c8301a55bc11ced030ec4f0a07cc528cb8e9945ea23",
    "vs": "4cefab2deb21c6ff71b00bfea3fccd11aaab4c60e1241e368a28d3cd2e325f40",
    "motion": "108a8e4182536d6e5a84ee0259c019a2aedc61cd1a457e9bd8e102a07e98a3cd",
    "raster": "aba3e321d545723ee1969803adc862b919f577eee370a655397348b51b8d0769",
}

assert SemanticCue().signature() == PINNED_CUE["C_NONE"]
assert SemanticCue(
    confidence=1.0, meaning=1.0, meaning_ok=True, stability_ok=True,
    restricted=False).signature() == PINNED_CUE["C_FULL"]
assert SemanticCue(
    confidence=0.3, meaning=0.5, ambiguous=True, restricted=True,
    meaning_ok=True, stability_ok=True).signature() == PINNED_CUE["C_AMB_REST"]

_awake_fs = runtime_face_state(visual="awake", meta={}, commands={})
assert build_visual_state(_awake_fs, None, None,
                          semantic=SemanticCue()).signature() == \
    PINNED_VS["VS_C_NONE"]
assert build_visual_state(_awake_fs, None, None, semantic=SemanticCue(
    confidence=1.0, meaning=1.0, meaning_ok=True, stability_ok=True,
    restricted=False)).signature() == PINNED_VS["VS_C_FULL"]
assert build_visual_state(_awake_fs, None, None, semantic=SemanticCue(
    confidence=0.3, meaning=0.5, ambiguous=True, restricted=True,
    meaning_ok=True, stability_ok=True)).signature() == \
    PINNED_VS["VS_C_AMB_REST"]

_e2e_pin_cue = _real_turn(_TEXTS[0])
assert _e2e_pin_cue.signature() == PINNED_E2E["cue"]
_e2e_pin_fs = runtime_face_state(visual="processing", meta={}, commands={})
_e2e_pin_vs = build_visual_state(_e2e_pin_fs, None, None,
                                 semantic=_e2e_pin_cue)
assert _e2e_pin_vs.signature() == PINNED_E2E["vs"]
assert motion_signature(_e2e_pin_vs, range(0, 60, 7)) == \
    PINNED_E2E["motion"]
assert render_raster(_e2e_pin_vs, 12, size=64)[1] == PINNED_E2E["raster"]
_chk("semantic_pins_ok")


print("semantic_visual_bridge_clean=OK")