"""Semantic meaning of every expression channel.

Script-style test (project convention): module-level asserts, OK labels.

Locks the interpretation contract the Math Coordination Agent enforces:

- emotional channels are AFFECT (happy, sad, surprised, neutral, angry,
  fearful ...): they may only drive the expression channel, never the eyes,
  never the mouth/jaw phonetics, never tremor
- viseme channels are PHONETIC mouth shapes: confined to the mouth/jaw,
  they never distort the emotional rig (brows/nose/cheeks) or the eyes
- anatomical channels are REFLEX behaviour (blink, gaze, eye motion):
  emotional meaning must never override them — the eye aperture is pure
  reflex, identical whether emotions are neutral or at maximum
- micro-motion channels are subtle physiological adjustments: bounded by
  the exact MICRO_AMP ceilings
- every blend goes exclusively through rig_math.blend_pose(E, V, M) with
  anatomical detail added at full weight — no other blend exists
- affect labels are interpreted through semantic meaning, never guessed:
  "angry" is anger, "fearful" is fear, "sad" is sadness (regressions on the
  old angry->uncertain / fearful->concerned confusion)
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity.wireframe.math_coordinator import (
    MATH_AGENT as AGENT,
    CONTROL_CHANNELS, CHANNELS,
    CH_EXPRESSION, CH_VISEME, CH_MICRO, CH_ANATOMICAL,
    SCENE_CONTROLS, MICRO_AMP, MICRO_AMP_X, CHANNEL_MAX,
    EMOTION_CONTROLS, STATE_CONTROLS, VISEME_CONTROLS,
    ANATOMICAL_CONTROLS, MICRO_CONTROLS,
)
from maya_identity.wireframe.rig_math import (
    blend_pose, BLEND_E, BLEND_V, BLEND_M,
)
from maya_identity.wireframe.expression_controller import (
    ExpressionController,
)
from maya_identity.wireframe.mesh_model import get_mesh
from maya_identity.wireframe.emotion_mapper import parse_metadata

mesh = get_mesh()

# ---- 1. every control carries exactly one semantic channel ------------------
assert all(CONTROL_CHANNELS[n] == CH_EXPRESSION
           for n in EMOTION_CONTROLS | frozenset(STATE_CONTROLS))
assert all(CONTROL_CHANNELS[n] == CH_VISEME for n in VISEME_CONTROLS)
assert all(CONTROL_CHANNELS[n] == CH_ANATOMICAL for n in ANATOMICAL_CONTROLS)
assert all(CONTROL_CHANNELS[n] == CH_MICRO for n in MICRO_CONTROLS)
# the four channels are disjoint and cover real meaning, never scene controls
assert SCENE_CONTROLS.isdisjoint(CONTROL_CHANNELS)
assert set(CONTROL_CHANNELS) == (set(EMOTION_CONTROLS) | set(STATE_CONTROLS)
                                 | set(VISEME_CONTROLS) | set(ANATOMICAL_CONTROLS)
                                 | set(MICRO_CONTROLS))

# ---- 2. semantic_profile never mixes categories -------------------------------
prof = AGENT.semantic_profile({"smile": 0.7, "speaking": 0.5, "blink": 1.0,
                               "tremor": 0.3, "gaze_x": 0.5})
assert prof[CH_EXPRESSION] == {"smile": 0.7}
assert prof[CH_VISEME] == {"speaking": 0.5}
assert prof[CH_ANATOMICAL] == {"blink": 1.0, "gaze_x": 0.5}
assert prof[CH_MICRO] == {"tremor": 0.3}
assert set(prof.keys()) == {CH_EXPRESSION, CH_VISEME, CH_ANATOMICAL, CH_MICRO}
# scene controls are presentation, not meaning — ignored, not guessed
p2 = AGENT.semantic_profile({"smile": 0.1, "glow_intensity": 0.9,
                             "scan_activity": 0.4, "breath": 1.0})
assert list(p2[CH_EXPRESSION].keys()) == ["smile"]
assert all(not p2[ch] for ch in (CH_VISEME, CH_MICRO, CH_ANATOMICAL))
try:
    AGENT.semantic_profile({"tremor": 0.5, "invented_muscle": 0.2})
    raise SystemExit("unknown controls have no meaning and must be rejected")
except ValueError:
    pass

# ---- 3. affect labels interpret to the EXPRESSION channel only ---------------
_AFFECT = {
    "happy": "happy", "sad": "sad", "surprised": "surprised",
    "neutral": "neutral", "angry": "angry", "fearful": "fear",
    "joy": "happy", "happiness": "happy", "afraid": "fear",
    "scared": "fear", "annoyed": "angry", "gloomy": "sad",
    "unhappy": "sad", "furious": "angry",
}
for label, expected_preset in _AFFECT.items():
    controls, preset, channels = AGENT.interpret(label)
    assert preset == expected_preset, (label, preset)
    # every *effective* control is affect meaning — expression channel only
    assert set(channels) == {CH_EXPRESSION}, (label, channels)
    assert "blink" not in controls and "gaze_x" not in controls
    assert "speaking" not in controls and "voice_intensity" not in controls

# ---- 4. regressions: the old label confusions are gone -----------------------
c_angry, p_angry, ch_angry = AGENT.interpret("angry")
assert p_angry == "angry"
assert c_angry.get("anger", 0.0) > 0.4                       # really angry
assert c_angry.get("uncertainty", 0.0) == 0.0                # NOT uncertain
assert c_angry.get("sadness", 0.0) == 0.0                    # not sadness either
c_fear, p_fear, _ = AGENT.interpret("fearful")
assert p_fear == "fear"
assert c_fear.get("fear", 0.0) > 0.4                         # really fearful
assert c_fear.get("sadness", 0.0) == 0.0                     # not concerned-sad
c_sad, p_sad, _ = AGENT.interpret("sad")
assert p_sad == "sad" and c_sad.get("sadness", 0.0) > 0.4
c_concerned, p_concerned, _ = AGENT.interpret("concerned")
assert p_concerned == "concerned"                            # still its own feeling
# raw metadata with an emotion key follows the same interpretation
cm, pm, chm = AGENT.interpret(meta={"emotion": "angry", "smile": 0.9})
assert pm == "angry" and chm[CH_EXPRESSION]["anger"] > 0.4
# explicit affect controls stay in the expression channel even when large
assert chm[CH_EXPRESSION]["smile"] == 0.9

# ---- 5. neutral is the calm baseline: no channel is borrowed ------------------
c_neutral, p_neutral, ch_neutral = AGENT.interpret("neutral")
assert p_neutral == "neutral"
for name in c_neutral:
    assert CONTROL_CHANNELS[name] == CH_EXPRESSION
assert c_neutral.get("calm", 0.0) > 0.0
assert "blink" not in c_neutral and "gaze_x" not in c_neutral

# ---- 6. live controller: emotional meaning never overrides anatomy ------------
ctrl = ExpressionController(mesh)
ctrl._blink_phase = 0.0
ctrl._blink_next = 10 ** 9
neutral_ctrl = {name: 0.0 for name in ctrl.controls.names()}
neutral_ctrl.update({"gaze_x": 0.5, "gaze_y": 0.5})
ctrl.controls.set_all(neutral_ctrl, immediate=True)
calm_pose = [tuple(v) for v in ctrl.compute_pose(0.5, reduced=True)]
full_emo = dict(neutral_ctrl)
full_emo.update({k: 1.0 for k in EMOTION_CONTROLS})
ctrl.controls.set_all(full_emo, immediate=True)
emo_pose = ctrl.compute_pose(0.5, reduced=True)
for i, dv in enumerate(mesh.vpar):
    if dv.get("eid") is not None:
        # the eye aperture is pure reflex — emotions leave it byte-identical
        assert all(abs(calm_pose[i][k] - emo_pose[i][k]) < 1e-12
                   for k in range(3)), (i, dv.get("region"))
report = AGENT.enforce_semantics(ctrl, 0.5, reduced=True)
assert report["ok"]

# ---- 7. viseme meaning is phonetic mouth shape: never the emotional rig ------
vset = {name: 0.0 for name in ctrl.controls.names()}
vset.update({"speaking": 1.0, "voice_intensity": 1.0})
ctrl.controls.set_all(vset, immediate=True)
vres = AGENT.enforce_semantics(ctrl, 0.5, reduced=True)
assert vres["ok"], vres["violations"][:3]
vfields = ctrl._last_fields
for i, dv in enumerate(mesh.vpar):
    if CH_VISEME not in AGENT.channels_of(dv):
        assert max(abs(x) for x in vfields[i][3:6]) < 1e-14, (i, dv.get("region"))
# phonetic meaning must not shift the brows/nose/cheeks relative to neutral
vsad = {name: 0.0 for name in ctrl.controls.names()}
ctrl.controls.set_all(vsad, immediate=True)
assert all(c == 0.0 for c in vfields[0][3:6])  # no residual viseme field

# ---- 8. micro-motion is subtle and mathematically bounded ----------------------
mset = {name: 0.0 for name in ctrl.controls.names()}
mset.update({"surprise": 1.0})
ctrl.controls.set_all(mset, immediate=True)
mres = AGENT.enforce_semantics(ctrl, 0.5, reduced=True)
assert mres["ok"], mres["violations"][:3]
mfields = ctrl._last_fields
for f in mfields:
    mx_, my_, mz = f[6:9]
    assert abs(mx_) <= MICRO_AMP_X + 1e-12
    assert abs(my_) <= MICRO_AMP + 1e-12
    assert mz == 0.0
for t in (0.0, 0.3, 1.7, 4.0):
    dx, dy, dz = AGENT.micro_displacement(t, 1.0, 1.0)
    assert abs(dx) <= MICRO_AMP_X and abs(dy) <= MICRO_AMP and dz == 0.0

# ---- 9. the ONLY blend is blend_pose(E, V, M) + anatomical at full weight -----
vectors = {
    "e": (0.050, 0.120, -0.020),
    "v": (0.0, 0.040, 0.0),
    "m": (0.002, -0.003, 0.0),
    "j": (0.0, -0.25, 0.0),
}
bx, by, bz = AGENT.compose_vertex(vectors["e"], vectors["v"],
                                  vectors["m"], vectors["j"])
eb_, vy_, mb_ = vectors["e"], vectors["v"], vectors["m"]
assert abs(bx - (blend_pose(eb_[0], vy_[0], mb_[0]) + vectors["j"][0])) < 1e-14
assert abs(by - (blend_pose(eb_[1], vy_[1], mb_[1]) + vectors["j"][1])) < 1e-14
assert abs(bz - (blend_pose(eb_[2], vy_[2], mb_[2]) + vectors["j"][2])) < 1e-14
assert abs(BLEND_E + BLEND_V + BLEND_M - 1.0) < 1e-15      # weights are exact
# channel weights never bleed into each other
assert blend_pose(1.0, 0.0, 0.0) == BLEND_E
assert blend_pose(0.0, 1.0, 0.0) == BLEND_V
assert blend_pose(0.0, 0.0, 1.0) == BLEND_M

print("sem_channels_exclusive=OK")
print("sem_profile_no_mixing=OK")
print("sem_interpret_affect=OK")
print("sem_angry_not_uncertain=OK")
print("sem_fear_not_concerned=OK")
print("sem_neutral_baseline=OK")
print("sem_anatomy_not_overridden=OK")
print("sem_viseme_mouth_only=OK")
print("sem_micro_bounded=OK")
print("sem_blend_pose_only=OK")
_ = (prof, p2, ch_angry, ch_neutral)