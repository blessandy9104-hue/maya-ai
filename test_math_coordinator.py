"""Math Coordination Agent — canonical arbiter of every Maya subsystem.

Script-style test (project convention): module-level asserts, OK labels.

The agent executes/walks the rig_math equations and coordinates the face
renderer, expression controller, pattern mapper, world model, safety engine,
and orchestrator contract. Universal rule: no direct arithmetic, no
heuristics, no raw increments — behaviour is mathematically derived,
semantically correct, pattern-aligned, and agent-validated.

Checks:
- channel semantics: expression/viseme/anatomical/micro never confused
- canonical pose assembly and transition families (lerp/smooth/exp + clamp01)
- pattern alignment: clamp01(dot(normalize(a), normalize(b)))
- pattern transitions: lerp(old, new, clamp01(t)); state changes via exp_smooth
- five-domain alignment: emotional / viseme / world / safety / task
- rendering delegation: MaterialEngine == agent; verify_render flags drift
- verify_pose on the live controller; reject() raises on violations
- world stability: normalize, domain bounds, drift detection
- safety: check_limits at canonical thresholds; monitor wired to the agent
- final-output coordination: consistency of rendered/state/predicted energies
- full-stack orchestration: pose/alignment/world/safety/consistency in one pass
"""
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity.wireframe.math_coordinator import (
    MathAgent, MATH_AGENT,
    SAFETY_POLICY, WORLD_DOMAIN, CHANNEL_MAX,
    CH_EXPRESSION, CH_VISEME, CH_MICRO, CH_ANATOMICAL,
)

AGENT = MathAgent()

# ---- channel semantics ----------------------------------------------------
from maya_identity.wireframe.mesh_model import get_mesh

mesh = get_mesh()
vpar = mesh.vpar

corner = vpar[mesh.landmarks["mouth_corner_l"]]
iris = vpar[mesh.landmarks["iris_l"]]

assert CH_ANATOMICAL in AGENT.channels_of(iris)
assert CH_EXPRESSION not in AGENT.channels_of(iris)
assert CH_VISEME not in AGENT.channels_of(iris)
assert CH_MICRO not in AGENT.channels_of(iris)
assert CH_EXPRESSION in AGENT.channels_of(corner)
assert CH_VISEME in AGENT.channels_of(corner)
assert CH_MICRO in AGENT.channels_of(corner)

# temple/scalp-like static vertex: only micro tremor
static = {"region": "scalp", "etype": "scalp", "jaw_w": 1.0}
assert AGENT.channels_of(static) == frozenset({CH_MICRO})

# ---- canonical pose assembly ----------------------------------------------
# dy for a mouth corner: expression = (dx, dy, dz) = (0, smile*0.150, smile*0.020)
ax, ay, az = AGENT.compose_vertex((0.0, 0.150, 0.020), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
assert abs(ax - 0.0) < 1e-12
assert abs(ay - 0.6 * 0.150) < 1e-12
assert abs(az - 0.6 * 0.020) < 1e-12

# anatomical detail is added at FULL strength, never blended into 0.6/0.3/0.1
dx, dy, dz = AGENT.compose_vertex((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, -0.25, 0.0))
assert abs(dy - (-0.25)) < 1e-12

# eye vertices carry only anatomical channel weight (zero e/u/m fields)
j = AGENT.channels_of(iris)
assert AGENT.channel_bounds_ok(CH_ANATOMICAL, (0.1, -0.25, 0.0))

# ---- transitions -----------------------------------------------------------
assert AGENT.control(1.4) == 1.0 and AGENT.control(-2.0) == 0.0
assert AGENT.control(0.37) == 0.37
assert abs(AGENT.transition(0.0, 1.0, 0.5, "lerp") - 0.5) < 1e-12
assert abs(AGENT.transition(0.0, 1.0, 0.5, "exp") - 0.5) < 1e-12
assert abs(AGENT.transition(0.0, 1.0, 0.5, "smooth") - 0.5) < 1e-12
assert AGENT.smoothstep(-3.0) == 0.0 and AGENT.smoothstep(4.0) == 1.0
try:
    AGENT.transition(0.0, 1.0, 0.5, "raw_increment")
    raise SystemExit("unrecognized transition mode must be rejected")
except ValueError:
    pass

# semantic gates
assert abs(AGENT.jaw_envelope(0.5, 0.0) - 0.6) < 1e-12
assert abs(AGENT.jaw_envelope(0.0, 1.0) - 0.72) < 1e-12  # surprise 1.0 -> amp 0.6 -> 0.6*1.2
assert abs(AGENT.emotion_gate((0.0, 0.0, 0.0, 1.0, 0.0, 0.0)) - 1.0) < 1e-12
assert AGENT.viseme_phase(0.0) == AGENT.smoothstep(0.5 + 0.5 * math.sin(1.2))

# ---- pattern alignment -----------------------------------------------------
assert AGENT.pattern_similarity((1.0, 0.0), (1.0, 0.0)) == 1.0
assert AGENT.pattern_similarity((2.0, 0.0), (4.0, 0.0)) == 1.0
assert AGENT.pattern_similarity((1.0, 0.0), (0.0, 1.0)) == 0.0
assert AGENT.pattern_similarity((1.0, 0.0), (-1.0, 0.0)) == 0.0
assert AGENT.pattern_similarity((0.0, 0.0), (1.0, 0.0)) == 0.0
assert AGENT.semantic_alignment((0.3, 0.4), (0.6, 0.8)) == 1.0

# ---- pattern transition / state / domain alignment ---------------------------
from maya_identity.wireframe.math_coordinator import PATTERN_ALIGNMENT_DOMAINS
from maya_identity.wireframe.rig_math import (
    dot as _gdot, normalize as _gnormalize, clamp01 as _gclamp01,
)

assert PATTERN_ALIGNMENT_DOMAINS == ("emotional", "viseme", "world", "safety", "task")
# pattern transitions are lerp(old, new, clamp01(t)); endpoints bounded
assert AGENT.pattern_transition(0.2, 0.8, 0.0) == 0.2
assert AGENT.pattern_transition(0.2, 0.8, 1.0) == 0.8
assert abs(AGENT.pattern_transition(0.2, 0.8, 0.25) - 0.35) < 1e-12
assert AGENT.pattern_transition(-0.5, 1.7, 0.5) == 0.5  # clamped domain
# pattern-driven state changes are exp_smooth(current, target, clamp01(alpha))
assert AGENT.pattern_state(0.0, 1.0, 0.4) == 0.4
assert abs(AGENT.pattern_state(0.4, 0.0, 0.4) - 0.24) < 1e-12
assert AGENT.pattern_state(0.5, 0.5, 9.0) == 0.5  # alpha clamped
# similarity is exactly clamp01(dot(normalize(p), normalize(i))) via rig_math
_pa, _pi = (1.0, 2.0, 3.0), (3.0, 2.0, 1.0)
assert abs(AGENT.pattern_similarity(_pa, _pi) -
           _gclamp01(_gdot(_gnormalize(_pa), _gnormalize(_pi)))) < 1e-12
# pattern_alignment is the similarity domain alias
assert AGENT.pattern_alignment((1.0, 0.0), (0.5, 0.0)) == 1.0
# task priority aligns onto the canonical [0, 1] domain
assert AGENT.pattern_priority(1.4) == 1.0 and AGENT.pattern_priority(-1.0) == 0.0
assert AGENT.pattern_priority(0.6) == 0.6
# safety maps thresholds to an aligned margin in [0, 1]
assert AGENT.pattern_safety_margin(0.0, 0.0, 0, 0) == 1.0
assert abs(AGENT.pattern_safety_margin(30.0, 35.0, 1, 0) - 0.5) < 1e-12
assert AGENT.pattern_safety_margin(61.0, 40.0, 1, 0) == 0.0
# five-domain alignment validator: missing/non-finite/out-of-domain rejected
_aligned = {"emotional": 0.4, "viseme": 0.2, "world": 0.3,
            "safety": 0.9, "task": 0.7}
assert AGENT.pattern_alignment_ok(_aligned)["ok"] is True
assert not AGENT.pattern_alignment_ok(dict(_aligned, world=1.7))["ok"]
assert not AGENT.pattern_alignment_ok({"emotional": 0.4, "viseme": 0.2})["ok"]
assert not AGENT.pattern_alignment_ok(
    dict(_aligned, emotional=float("nan")))["ok"]
assert not AGENT.pattern_alignment_ok(dict(_aligned, safety=-0.1))["ok"]

# ---- rendering delegation --------------------------------------------------
from maya_identity.wireframe.render3d import MaterialEngine, edge_thickness
from maya_identity.wireframe.math_coordinator import _rgb_to_hex
from maya_identity.wireframe.rig_math import zprime, depth01, NB, SHADE_LO, SHADE_HI

engine = MaterialEngine()
materials = {"glow_intensity": 0.6, "eye_brightness": 0.95}
for z in (-0.4, 0.0, 0.42, 0.9, 1.6):
    zp = zprime(z)
    expected = AGENT.compute_edge_color("mouth_rim_l", materials, depth01(zp), zp, engine.bg)
    assert engine.edge_color("mouth_rim_l", materials, z=z) == expected
    assert engine.bucket(z) == AGENT.depth_bucket(z)
    assert edge_thickness(z, 176) == AGENT.line_width(z, 176)

# verify_render rejects drift
good = engine.edge_color("mouth_rim_l", materials, z=0.42)
assert AGENT.verify_render("mouth_rim_l", materials, z=0.42, expected_hex=good)["ok"]
bad_report = AGENT.verify_render("mouth_rim_l", materials, z=0.42, expected_hex="#ff0000")
assert not bad_report["ok"]
try:
    AGENT.reject(bad_report, message="render drifted")
    raise SystemExit("reject must raise on drift")
except ValueError:
    pass

# ---- verify_pose / correction on the live controller -----------------------
from maya_identity.wireframe.expression_controller import ExpressionController

ctrl = ExpressionController(mesh)
preset = {name: 0.0 for name in ctrl.controls.names()}
preset.update({"smile": 1.0, "calm": 0.0})
ctrl.controls.set_all(preset, immediate=True)

report = AGENT.verify_pose(ctrl, 0.5, reduced=True)
assert report["ok"], report["violations"][:3]

# corrected pose matches the canonical re-assembly
corrected = AGENT.verify_pose(ctrl, 0.5, reduced=True, correct=True)
expected = AGENT.assemble_pose(mesh.verts, ctrl._last_fields)
assert all(abs(corrected["pose"][i][k] - expected[i][k]) < 1e-9 for i in range(len(expected)) for k in range(3))

# channel confusion is impossible in a compliant controller (eyes carry only
# anatomical weight, assembled at full strength)
fields = ctrl._last_fields
eye_index = mesh.landmarks["iris_l"]
assert max(abs(v) for v in fields[eye_index][:9]) < 1e-14

# ---- semantic meaning enforcement ------------------------------------------
from maya_identity.wireframe.math_coordinator import (
    CONTROL_CHANNELS, CHANNELS, EMOTION_CONTROLS, VISEME_CONTROLS,
    ANATOMICAL_CONTROLS, MICRO_CONTROLS, MICRO_AMP, MICRO_AMP_X, CHANNEL_MAX,
)
from maya_identity.wireframe.rig_math import (
    blend_pose, BLEND_E, BLEND_V, BLEND_M,
)

# every control belongs to exactly one channel, and the agent knows it by name
assert AGENT.control_channel("smile") == CH_EXPRESSION
assert AGENT.control_channel("sadness") == CH_EXPRESSION
assert AGENT.control_channel("attention") == CH_EXPRESSION
assert AGENT.control_channel("speaking") == CH_VISEME
assert AGENT.control_channel("voice_intensity") == CH_VISEME
assert AGENT.control_channel("blink") == CH_ANATOMICAL
assert AGENT.control_channel("gaze_x") == CH_ANATOMICAL
assert AGENT.control_channel("tremor") == CH_MICRO
STATE_SET = frozenset(
    {"attention", "tiredness", "thinking", "uncertainty", "confidence"})
assert all(CONTROL_CHANNELS[n] == CH_EXPRESSION
           for n in EMOTION_CONTROLS | STATE_SET)
assert all(CONTROL_CHANNELS[n] == CH_VISEME for n in VISEME_CONTROLS)
assert all(CONTROL_CHANNELS[n] == CH_ANATOMICAL for n in ANATOMICAL_CONTROLS)
assert all(CONTROL_CHANNELS[n] == CH_MICRO for n in MICRO_CONTROLS)
# the live controller's controls are all interpreted by the manifest (none
# are guessed); the only unmapped ones are scene/body controls, not channels
from maya_identity.wireframe.expression_controller import ALL_CONTROLS
assert not [c for c in ALL_CONTROLS if c not in CONTROL_CHANNELS and
            c not in ("glow_intensity", "scan_activity", "breath")]
try:
    AGENT.control_channel("mystery_muscle")
    raise SystemExit("unknown controls must be rejected, never guessed")
except ValueError:
    pass

# emotional meaning must NOT override anatomical meaning: the eye aperture is
# pure reflex, identical whether emotions are neutral or at maximum
ctrl._blink_phase = 0.0
ctrl._blink_next = 10 ** 9
neutral = {name: 0.0 for name in ctrl.controls.names()}
neutral.update({"gaze_x": 0.5, "gaze_y": 0.5})
ctrl.controls.set_all(neutral, immediate=True)
calm_pose = [tuple(v) for v in ctrl.compute_pose(0.5, reduced=True)]
emotional = dict(neutral)
emotional.update({
    "surprise": 1.0, "sadness": 1.0, "anger": 1.0, "fear": 1.0,
    "attention": 1.0, "tiredness": 1.0,
})
ctrl.controls.set_all(emotional, immediate=True)
emo_pose = ctrl.compute_pose(0.5, reduced=True)
for i, dv in enumerate(mesh.vpar):
    if dv.get("eid") is not None:
        assert all(abs(calm_pose[i][k] - emo_pose[i][k]) < 1e-12
                   for k in range(3)), (i, dv.get("region"))
    else:
        assert any(abs(calm_pose[i][k] - emo_pose[i][k]) > 1e-6
                   for k in range(3)), "emotions must move the expression rig"

# viseme meaning is phonetic mouth shape: it must never touch the emotional
# rig (brows/nose/cheeks) or the eyes
vset = {name: 0.0 for name in ctrl.controls.names()}
vset.update({"speaking": 1.0})
ctrl.controls.set_all(vset, immediate=True)
vreport = AGENT.verify_pose(ctrl, 0.5, reduced=True)
assert vreport["ok"], vreport["violations"][:3]
vfields = ctrl._last_fields
for i, dv in enumerate(mesh.vpar):
    if CH_VISEME not in AGENT.channels_of(dv):
        assert max(abs(x) for x in vfields[i][3:6]) < 1e-14, (
            i, dv.get("region"))

# micro-motion is subtle and mathematically bounded
mset = {name: 0.0 for name in ctrl.controls.names()}
mset.update({"smile": 1.0})
ctrl.controls.set_all(mset, immediate=True)
mreport = AGENT.verify_pose(ctrl, 0.5, reduced=True)
assert mreport["ok"], mreport["violations"][:3]
mfields = ctrl._last_fields
max_micro = max(max(abs(x) for x in f[6:9]) for f in mfields)
assert max_micro <= CHANNEL_MAX[CH_MICRO]
assert max_micro <= MICRO_AMP
dmx, dmy, dmz = AGENT.micro_displacement(0.25, 1.1, 1.0)
assert abs(dmx) <= MICRO_AMP_X and abs(dmy) <= MICRO_AMP and dmz == 0.0

# all channel blending goes exclusively through rig_math.blend_pose(E, V, M)
ee, uu, mm = (0.050, 0.080, -0.020), (0.0, 0.030, 0.0), (0.001, 0.002, 0.0)
jj = (0.0, -0.25, 0.0)
bx, by, bz = AGENT.compose_vertex(ee, uu, mm, jj)
assert bx == blend_pose(ee[0], uu[0], mm[0]) + jj[0]
assert by == blend_pose(ee[1], uu[1], mm[1]) + jj[1]
assert bz == blend_pose(ee[2], uu[2], mm[2]) + jj[2]
assert abs(bx - (BLEND_E * ee[0] + BLEND_V * uu[0] + BLEND_M * mm[0]) - jj[0]) < 1e-12
assert abs(by - (BLEND_E * ee[1] + BLEND_V * uu[1] + BLEND_M * mm[1]) - jj[1]) < 1e-12

# ---- world stability -------------------------------------------------------
n = AGENT.world_normalize((3.0, 4.0, 0.0))
assert abs(math.sqrt(sum(x * x for x in n)) - 1.0) < 1e-12
assert AGENT.world_normalize((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)

stable = AGENT.world_stability([0.3, 0.31, 0.3, 0.29, 0.31], max_std=0.05)
assert stable["ok"] is True
assert AGENT.world_stability([0.3, 0.9, 0.31, 0.3], max_std=0.05)["ok"] is False  # drift
assert AGENT.world_stability([0.3, float("nan"), 0.3])["ok"] is False  # non-finite
assert AGENT.world_stability([0.3, 1.6, 0.3])["ok"] is False  # out of domain
assert AGENT.world_stability([])["ok"] is False  # undefined

state_check = AGENT.world_state_ok({"attention": 0.4, "spark": 0.2, "label": "x"})
assert state_check["ok"] is True
assert AGENT.world_state_ok({"attention": 1.7})["ok"] is False

# ---- safety engine wired to the agent --------------------------------------
assert SAFETY_POLICY["max_cpu_percent"] == 60.0
assert SAFETY_POLICY["max_memory_percent"] == 70.0
assert SAFETY_POLICY["max_process_count"] == 2
assert SAFETY_POLICY["max_launches_per_minute"] == 1
assert WORLD_DOMAIN == (0.0, 1.0)

safe = AGENT.check_limits(20.0, 40.0, 1, 0)
assert safe["safe"] is True and safe["violations"] == []
assert AGENT.check_limits(61.0, 40.0, 1, 0)["safe"] is False
assert AGENT.check_limits(20.0, 70.0, 1, 0)["safe"] is False  # memory >= 70
assert AGENT.check_limits(20.0, 40.0, 3, 0)["safe"] is False  # procs > 2
assert AGENT.check_limits(20.0, 40.0, 1, 2)["safe"] is False  # launches > 1
assert AGENT.check_limits(20.0, 40.0, 1, 0, stop_active=True)["safe"] is False

import maya_safety_monitor as monitor

with tempfile.TemporaryDirectory() as directory:
    monitor.STOP_PATH = Path(directory) / "PRESENCE_STOP"
    safe = monitor.evaluate(monitor.ResourceSnapshot(cpu_percent=10.0, memory_percent=30.0, maya_process_count=1, launches_last_minute=0))
    assert safe["safe"] is True
    unsafe = monitor.evaluate(monitor.ResourceSnapshot(cpu_percent=61.0, memory_percent=30.0, maya_process_count=1, launches_last_minute=0))
    assert unsafe["safe"] is False
    assert unsafe["reasons"] == ["CPU threshold exceeded"]
# on-disk policy cannot relax the agent's ceilings
policy = monitor.load_policy()
assert policy["max_cpu_percent"] <= SAFETY_POLICY["max_cpu_percent"]
assert policy["max_process_count"] <= SAFETY_POLICY["max_process_count"]

# ---- pattern mapper / emotion mapper through the agent ---------------------
from maya_identity.wireframe.emotion_mapper import parse_metadata

controls, preset_used, warnings = parse_metadata({"preset": "happy", "smile": 1.3})
assert controls["smile"] == 1.0  # agent.control clamps the domain
assert preset_used == "happy"

from maya_identity.visual_language import SymbolComposer

composer = SymbolComposer()
assert composer.mode_similarity("calm", "calm") == 1.0
mode_sim = composer.mode_similarity("calm", "alert")
assert 0.0 <= mode_sim <= 1.0
prims = composer.primitives("calm", t=0.5, intensity=5.0)  # domain-clamped
assert isinstance(prims, list)
# visual-language pattern transitions are lerp(old, new, clamp01(t)) through
# the agent, per dimension of the mode signatures
sig_a, sig_b = composer.symbol_vector("calm"), composer.symbol_vector("alert")
for i, blended in enumerate(composer.transition("calm", "alert", 0.3)):
    assert abs(blended - AGENT.pattern_transition(sig_a[i], sig_b[i], 0.3)) < 1e-12
assert all(0.0 <= v <= 1.0 for v in composer.transition("calm", "alert", 2.0))

# viseme state changes in the speech adapter are exp_smooth via the agent
from maya_identity.wireframe.speech_adapter import SpeechAdapter

sp = SpeechAdapter(alpha=0.4)
step1 = sp.drive(viseme="OPEN", speaking=0.5, elapsed=0.0)
assert abs(step1["open"] - AGENT.pattern_state(0.0, 0.52 * 0.5, 0.4)) < 1e-9
step2 = sp.drive(viseme="OPEN", speaking=0.5)
assert abs(step2["open"] - AGENT.pattern_state(step1["open"], 0.52 * 0.5, 0.4)) < 1e-9

# emotion mapper grounds visual-state fallback as a pattern-driven state change
from maya_identity.wireframe.expression_controller import PRESETS

c_fallback, _, _ = parse_metadata({"smile": 0.5, "visual_state": "thinking"})
for k, v in PRESETS["thinking"].items():
    assert abs(c_fallback[k] - AGENT.pattern_state(0.0, v, 0.4)) < 1e-12

# ---- world model exposes agent-backed stability report ---------------------
from maya_world_model import stability_status

world_report = stability_status()
assert world_report["status"] in ("stable", "review")
assert world_report["evidence_count"] >= 0
assert "uncertainty_std" in world_report

# ---- final-output coordination ---------------------------------------------
consist = AGENT.output_consistency(0.5, 0.5, 0.5)
assert consist["ok"] is True and consist["energies"]["rendered"] == 0.5
mismatch = AGENT.output_consistency(0.5, 0.9, 0.5)
assert not mismatch["ok"]

coord_ok = AGENT.coordinate("face_renderer", 0.42, 0.42)
assert coord_ok["ok"] is True and coord_ok["subsystem"] == "face_renderer"
assert AGENT.coordinate("expression_controller", 0.42, 0.10)["ok"] is False

final = AGENT.finalize(ctrl, 0.5, reduced=True)
assert final["pose_ok"] is True and final["consistency_ok"] is True
assert final["ok"] is True

# ---- full-stack orchestration -----------------------------------------------
# every subsystem's final output is validated through one coordination pass
full = AGENT.orchestrate({
    "pose": ctrl,
    "aligned": {"emotional": 0.4, "viseme": 0.2, "world": 0.3,
                "safety": 0.9, "task": 0.7},
    "world": {"attention": 0.3, "spark": 0.2},
    "safety": {"cpu_percent": 0.0, "memory_percent": 0.0,
               "process_count": 0, "launches": 0},
}, 0.5, reduced=True)
assert full["ok"] is True
for name in ("pose", "aligned", "world", "safety", "consistency"):
    assert full["subsystems"][name] is True
assert set(full["ensembles"]) == {"rendered", "state", "predicted"}
assert full["subsystems"]["safety_margin"] == 1.0

# out-of-domain world feature fails the frame contract
bad_world = AGENT.orchestrate({
    "pose": ctrl, "world": {"attention": 1.7},
    "aligned": {"emotional": 0.4, "viseme": 0.2, "world": 0.3,
                "safety": 0.9, "task": 0.7},
    "safety": {"cpu_percent": 0.0, "memory_percent": 0.0,
               "process_count": 0, "launches": 0},
}, 0.5, reduced=True)
assert bad_world["ok"] is False and bad_world["subsystems"]["world"] is False

# threshold breach fails the safety contract
bad_safety = AGENT.orchestrate({
    "pose": ctrl, "world": {"attention": 0.3},
    "aligned": {"emotional": 0.4, "viseme": 0.2, "world": 0.3,
                "safety": 0.9, "task": 0.7},
    "safety": {"cpu_percent": 61.0, "memory_percent": 40.0,
               "process_count": 1, "launches": 0},
}, 0.5, reduced=True)
assert bad_safety["ok"] is False and bad_safety["subsystems"]["safety"] is False
assert bad_safety["subsystems"]["safety_margin"] == 0.0

# an undefined alignment domain fails the pattern contract
bad_aligned = AGENT.orchestrate({
    "pose": ctrl, "world": {"attention": 0.3},
    "aligned": {"emotional": 0.4},
    "safety": {"cpu_percent": 0.0, "memory_percent": 0.0,
               "process_count": 0, "launches": 0},
}, 0.5, reduced=True)
assert bad_aligned["ok"] is False and bad_aligned["subsystems"]["aligned"] is False

# internal state that disagrees with the rendered face fails consistency
drifted = AGENT.orchestrate({
    "pose": ctrl, "world": {"attention": 0.3},
    "aligned": {"emotional": 0.4, "viseme": 0.2, "world": 0.3,
                "safety": 0.9, "task": 0.7},
    "safety": {"cpu_percent": 0.0, "memory_percent": 0.0,
               "process_count": 0, "launches": 0},
}, 0.5, reduced=True, state_vector=0.999)
assert drifted["ok"] is False and drifted["subsystems"]["consistency"] is False

print("math_agent_channels=OK")
print("math_agent_assemble=OK")
print("math_agent_control_meaning=OK")
print("math_agent_anatomy_priority=OK")
print("math_agent_viseme_scope=OK")
print("math_agent_micro_bounds=OK")
print("math_agent_semantic_blend=OK")
print("math_agent_transitions=OK")
print("math_agent_pattern_transition=OK")
print("math_agent_pattern_state=OK")
print("math_agent_pattern_alignment=OK")
print("math_agent_patterns=OK")
print("math_agent_render=OK")
print("math_agent_pose_verify=OK")
print("math_agent_world=OK")
print("math_agent_safety=OK")
print("math_agent_emotion_mapper=OK")
print("math_agent_visual_language=OK")
print("math_agent_world_model=OK")
print("math_agent_orchestrate=OK")
print("math_agent_final_coordination=OK")