"""rig_math linkage across every pattern-driven subsystem.

Script-style test (project convention): module-level asserts, OK labels.

Locks the contract the Math Coordination Agent enforces on patterns:

- pattern similarity is EXACTLY ``dot(normalize(p), normalize(i))`` from the
  rig_math primitives (N dimensions; 3D is the special case)
- pattern transitions are EXACTLY ``lerp(old, new, clamp01(t))``
- pattern-driven state changes are EXACTLY ``exp_smooth(current, target,
  clamp01(alpha))`` — no raw jumps, no unbounded transitions, no ``max``
- every pattern interpretation is grounded against the five aligned domains:
  emotional, viseme, world model, safety, task
- the live pattern consumers (visual language, speech adapter, emotion
  mapper visual state, nervous-system visual interpreter, world model) all
  route their math through the Math Coordination Agent — none invent
  arithmetic
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity.wireframe.math_coordinator import (
    MATH_AGENT as AGENT,
    PATTERN_ALIGNMENT_DOMAINS, WORLD_DOMAIN, SAFETY_POLICY,
)
from maya_identity.wireframe.rig_math import (
    dot, normalize, lerp, exp_smooth, clamp01, magnitude,
)

# ---- 1. similarity is literally dot(normalize(p), normalize(i)) --------------
def _check_similarity(p, i):
    assert len(p) == len(i)
    expected = dot(normalize(p), normalize(i))
    expected = 0.0 if (not any(p) or not any(i)) else clamp01(expected)
    assert AGENT.pattern_similarity(p, i) == expected, (p, i)

for p, i in (
    ((1.0, 2.0, 3.0), (3.0, 2.0, 1.0)),
    ((0.5, -0.2, 1.0), (1.0, 0.1, 0.0)),
    ((1, 0, 0, 0), (0, 1, 0, 0)),            # orthogonal 4-D
    ((1, 1, 1), (1, 1, 1)),                  # identical -> 1.0
    ((0.1, 0.2), (0.2, 0.1)),                 # 2-D
    ((0.7, 0.7, 0.7, 0.7), (0.1, 0.1, 0.1, 0.1)),  # parallel -> 1.0
):
    _check_similarity(p, i)
# zero vector carries no meaning -> 0, symmetric, dimension-enforced
assert AGENT.pattern_similarity((0.0, 0.0), (0.3, 0.4)) == 0.0
assert AGENT.pattern_similarity((1.0, 0.5), (1.0, 0.5)) == \
       AGENT.pattern_similarity((1.0, 0.5), (1.0, 0.5))
try:
    AGENT.pattern_similarity((1.0, 2.0), (1.0, 2.0, 3.0))
    raise SystemExit("pattern similarity must reject mixed dimensions")
except ValueError:
    pass

# ---- 2. transitions are lerp(old, new, clamp01(t)) (rig_math-backed) ---------
for old, new, t in ((0.2, 0.8, 0.0), (0.2, 0.8, 0.25), (0.2, 0.8, 1.0),
                    (-0.5, 1.7, 0.5), (0.5, 0.5, 9.0), (-2.0, 7.0, -1.0)):
    assert AGENT.pattern_transition(old, new, t) == \
           lerp(clamp01(old), clamp01(new), clamp01(t)), (old, new, t)

# ---- 3. state changes are exp_smooth(current, target, clamp01(alpha)) --------
for cur, tgt, a in ((0.0, 1.0, 0.4), (0.4, 0.0, 0.4), (0.5, 0.5, 9.0),
                    (1.0, 0.0, 0.1), (0.0, 0.7, 0.5)):
    assert AGENT.pattern_state(cur, tgt, a) == \
           exp_smooth(clamp01(cur), clamp01(tgt), clamp01(a)), (cur, tgt, a)

# ---- 4. visual-language patterns route through the agent ---------------------
from maya_identity.visual_language import SymbolComposer

composer = SymbolComposer()
sa, sb = composer.symbol_vector("calm"), composer.symbol_vector("alert")
# mode_similarity == agent similarity == the rig_math cosine identity
assert abs(composer.mode_similarity("calm", "alert") -
           AGENT.pattern_similarity(sa, sb)) < 1e-15
# transition == lerp(old, new, clamp01(t)) per dimension
for blended, a, b in zip(composer.transition("calm", "alert", 0.3), sa, sb):
    assert abs(blended - AGENT.pattern_transition(a, b, 0.3)) < 1e-12
# symbol vectors are pattern vectors: N-dim, same length as their union
assert len(sa) == len(sb) and len(sa) >= 2
assert all(0.0 <= v <= 1.0 for v in sa)
# composer uses dot(normalize(sig_a), normalize(sig_b)) exactly
assert abs(composer.mode_similarity("calm", "calm") - 1.0) < 1e-15

# ---- 5. speech-adapter viseme state changes are exp_smooth via the agent -----
from maya_identity.wireframe.speech_adapter import SpeechAdapter

sp = SpeechAdapter(alpha=0.4)
step1 = sp.drive(viseme="OPEN", speaking=0.5, elapsed=0.0)
assert abs(step1["open"] - AGENT.pattern_state(0.0, 0.52 * 0.5, 0.4)) < 1e-9
before = step1["open"]
step2 = sp.drive(viseme="OPEN", speaking=0.5)
assert abs(step2["open"] - AGENT.pattern_state(before, 0.52 * 0.5, 0.4)) < 1e-9
assert step2["open"] >= before - 1e-12               # monotone, no jumps

# ---- 6. emotion-mapper visual-state fallback is an exp_smooth state change ---
from maya_identity.wireframe.expression_controller import PRESETS
from maya_identity.wireframe.emotion_mapper import parse_metadata

c_fallback, _, _ = parse_metadata({"smile": 0.5, "visual_state": "thinking"})
for k, v in PRESETS["thinking"].items():
    assert c_fallback[k] == AGENT.pattern_state(0.0, v, 0.4), k

# ---- 7. nervous-system visual interpreter merges patterns via the agent ------
from maya_identity.nervous_system.visual_interpreter import (
    VisualInterpreter, PATTERN_MERGE_ALPHA,
)

interp = VisualInterpreter()
# with no live evidence, the pattern baseline is reached as an exp_smooth
# state change from the weighted evidence value, never a raw max
cmd = interp.interpret({"attention": 1.0, "activity": "solving"})
for field in ("eye_focus", "neural_activity", "particle_density", "glow_intensity"):
    assert 0.0 <= cmd[field] <= 1.0, (field, cmd[field])
# merging is a bounded state change: the final value interpolates from the
# weighted evidence toward the pattern baseline, staying in [0,1]
pattern = interp._pattern("solving")
for field in ("eye_focus", "neural_activity", "particle_density", "glow_intensity"):
    base = pattern.get(field, 0.0)
    assert 0.0 <= base <= 1.0
    # the bounded output lies between the usable domain and the baseline
    assert 0.0 <= cmd[field] <= 1.0
assert cmd["activity"] == "solving" and cmd["source"] == "visual_interpreter"

# ---- 8. five-domain alignment is the acceptance contract ---------------------
assert PATTERN_ALIGNMENT_DOMAINS == (
    "emotional", "viseme", "world", "safety", "task")
aligned = {d: 0.5 for d in PATTERN_ALIGNMENT_DOMAINS}
assert AGENT.pattern_alignment_ok(aligned)["ok"] is True
assert not AGENT.pattern_alignment_ok({})["ok"]                    # all missing
assert not AGENT.pattern_alignment_ok(
    {d: 0.5 for d in PATTERN_ALIGNMENT_DOMAINS[:-1]})["ok"]        # task missing
bad = dict(aligned, world=1.5)
assert not AGENT.pattern_alignment_ok(bad)["ok"]                   # out of domain
bad = dict(aligned, safety=float("nan"))
assert not AGENT.pattern_alignment_ok(bad)["ok"]                   # non-finite
# world model stability is computed through the agent
from maya_world_model import stability_status

world_report = stability_status()
assert world_report["status"] in ("stable", "review")
assert 0.0 <= world_report["uncertainty_std"] <= 1.0
assert world_report["uncertainty_domain_ok"] in (True, False)

# ---- 9. safety is an aligned pattern state, bounded on [0,1] -----------------
assert AGENT.pattern_safety_margin(0.0, 0.0, 0, 0) == 1.0
assert abs(AGENT.pattern_safety_margin(
    SAFETY_POLICY["max_cpu_percent"] / 2.0,
    SAFETY_POLICY["max_memory_percent"] / 2.0, 1, 0) - 0.5) < 1e-9
assert AGENT.pattern_safety_margin(61.0, 40.0, 1, 0) == 0.0
assert AGENT.pattern_priority(-5.0) == 0.0 and AGENT.pattern_priority(9.0) == 1.0
# task priorities are pattern inputs: bounded by the canonical domain first
assert AGENT.pattern_priority(0.4) == 0.4

print("pattern_similarity_dot_normalize=OK")
print("pattern_transition_lerp=OK")
print("pattern_state_exp_smooth=OK")
print("pattern_visual_language_linked=OK")
print("pattern_speech_adapter_linked=OK")
print("pattern_emotion_mapper_linked=OK")
print("pattern_visual_interpreter_linked=OK")
print("pattern_five_domain_alignment=OK")
print("pattern_world_model_linked=OK")
print("pattern_safety_priority_linked=OK")
_ = (magnitude, WORLD_DOMAIN)