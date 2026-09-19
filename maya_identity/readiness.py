"""Maya -- internal verification (self-check) engine.

Maya does not declare readiness. This module provides the internal half of
the stabilization protocol: deterministic, subsystem-scoped diagnostics that
detect anomalies, drift, or instability and log any finding.

Readiness itself is decided only when an external verification report AND this
internal self-check both report stability (see ``maya_identity.stabilization``).
"""
from __future__ import annotations

import json
import pathlib
import re
import time

RUNTIME_REVISION = "1.0.0"

PURPOSE = (
    "To provide expressive, stable, deterministic interaction.",
    "To support the user with clarity, coherence, and emotional consistency.",
    "To act as a safe, math-governed embodied intelligence.",
    "To serve human benefit through predictable, bounded behavior.",
)

_METADATA = pathlib.Path(__file__).resolve().parent / "metadata"
_SELF_CHECK_LOG = _METADATA / "self_check.jsonl"


def _log(entry: dict) -> None:
    _METADATA.mkdir(parents=True, exist_ok=True)
    line = dict(entry)
    line["at"] = time.time()
    with _SELF_CHECK_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")


from . import capability_registry as _caps  # noqa: E402
from . import cognition as _cognition  # noqa: E402
from . import interaction as _interaction  # noqa: E402
from .wireframe import presentation_math as _presentation_math  # noqa: E402
from .wireframe.expression_controller import ALL_CONTROLS, PRESETS  # noqa: E402
from .wireframe.math_coordinator import (  # noqa: E402
    CHANNEL_MAX,
    MATH_AGENT,
    PRECISION_EXPERT,
    PRECISION_STANDARD,
    PRECISION_TOLERANCE,
    WORLD_STATE_PATTERNS,
)
from .wireframe.rig_math import (  # noqa: E402
    NUMERIC_CONTRACTS,
    cosine_similarity,
    lerp,
    stable_exp_smooth,
)


def stabilized():
    """Live internal stabilization flag -- derived from the self-check, never
    an unconditional constant."""
    return bool(self_check()["stable"])


def _check_intelligence_stage_ordering(stages=None):
    canonical = ("sense", "interpret", "stabilize", "decide", "express",
                 "log", "reflect")
    try:
        if stages is None:
            from maya_runtime import intelligence as _intel
            observed = tuple(_intel.STAGES)
        else:
            observed = tuple(stages)
    except Exception as exc:
        return False, f"intelligence import failed: {exc!r}"
    if observed != canonical:
        return False, f"intelligence stage order drifted: {observed}"
    return True, "7-stage ordering intact"


_FORBIDDEN_RUNTIME_IMPORTS = ("random", "time", "datetime", "tkinter",
                              "subprocess", "socket")


def _check_intelligence_no_runtime_imports(sources=None):
    if sources is None:
        try:
            from maya_runtime import intelligence as _intel
            package_dir = pathlib.Path(_intel.__file__).resolve().parent
            sources = sorted(package_dir.glob("*.py"))
        except Exception as exc:
            return False, f"intelligence import failed: {exc!r}"
    for source in sources:
        if hasattr(source, "read_text"):
            try:
                text = source.read_text(encoding="utf-8")
            except OSError as exc:
                return False, f"cannot read {source}: {exc!r}"
        else:
            try:
                with open(source, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except OSError as exc:
                return False, f"cannot read {source}: {exc!r}"
        name = getattr(source, "name", str(source))
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for banned in _FORBIDDEN_RUNTIME_IMPORTS:
                if (re.match(rf"import\s+{banned}([ .]|$)", stripped)
                        or re.match(rf"from\s+{banned}([ .])?\s+import\b",
                                    stripped)):
                    return False, f"{name}:{line_number} imports {banned}"
    return True, "intelligence free of nondeterministic/runtime imports"


def _check_intelligence_deterministic(run_func=None):
    payload = {
        "semantic": {"coherence": 0.8, "salience": 0.6},
        "emotional": {"intensity": 0.4, "arousal": 0.5, "valence": 0.6},
        "contextual": {"urgency": 0.3, "impact": 0.4, "effort": 0.5},
        "historical": {"stability": [0.5, 0.51, 0.5, 0.505, 0.5]},
        "render": {"glow": 0.6, "depth": 0.5, "thickness": 2.0},
        "reference": (0.5, 0.5, 0.5),
        "metrics": {"cpu_percent": 10, "memory_percent": 20,
                    "process_count": 1, "launches": 0},
        "now": "2026-09-09T00:00:00Z",
        "sequence": 1,
        "environment": "local",
    }
    try:
        if run_func is None:
            from maya_runtime import intelligence as _intel
            compute = _intel.run
        else:
            compute = run_func
        first = compute(**dict(payload))
        second = compute(**dict(payload))
    except Exception as exc:
        return False, f"intelligence execution failed: {exc!r}"
    if first != second:
        return False, "intelligence output nondeterministic over fixed payload"
    return True, "deterministic repeated execution over a fixed synthetic payload"


def _check_math_deterministic_centralized():
    if PRECISION_TOLERANCE[PRECISION_EXPERT] > PRECISION_TOLERANCE[PRECISION_STANDARD]:
        return False, "precision expert is not stricter than standard"
    sample = MATH_AGENT.pattern_state(0.0, 1.0, 0.5)
    if not (sample == 0.5 and MATH_AGENT.pattern_state(0.0, 1.0, 0.5) == sample):
        return False, "pattern_state nondeterministic"
    if len(NUMERIC_CONTRACTS) != 22:
        return False, "numeric contract table incomplete"
    return True, "MATH_AGENT centralized; 22 contracts; repeated calls identical"


def _check_world_model_stable():
    eq = WORLD_STATE_PATTERNS["stable_equilibrium"]
    stable = MATH_AGENT.world_stability([1.0, 1.0, 1.0, 1.0], max_std=0.05)
    drift = MATH_AGENT.world_drift([1.0, 1.0, 1.0, 1.0], tolerance=0.35)
    coherence = MATH_AGENT.world_coherence(eq, equilibrium=eq, floor=0.6)
    if stable["std"] != 0.0 or drift["drift"] != 0.0:
        return False, "stable series not drift-free"
    if coherence["coherence"] != 1.0:
        return False, "equilibrium coherence below 1.0"
    return True, "equilibrium stable, drift 0.0, coherence 1.0"


def _check_safety_bounded_predictable_nonblocking():
    if set(CHANNEL_MAX) != {"expression", "viseme", "micro", "anatomical"}:
        return False, "channel ceiling set drifted"
    for _limit in CHANNEL_MAX.values():
        if not (isinstance(_limit, float) and _limit > 0.0):
            return False, "non-finite channel ceiling"
    decision = MATH_AGENT.check_limits(20.0, 30.0, 1, 0)
    if not isinstance(decision, dict) or decision.get("safe") is not True:
        return False, "normal load not reported safe"
    margin = MATH_AGENT.pattern_safety_margin(20.0, 30.0, 1, 0)
    if not (0.0 <= margin <= 1.0):
        return False, "safety margin outside [0, 1]"
    return True, "ceilings finite; normal load safe; margin bounded"


def _check_rendering_loop_smooth_cadence_correct():
    if len(ALL_CONTROLS) != 20:
        return False, "expression control set incomplete"
    if not PRESETS:
        return False, "expression presets missing"
    try:
        from .visual_surface import FRAME_MS_DEFAULT
    except Exception as exc:
        return False, f"cadence constant unavailable on this host: {exc}"
    if not (FRAME_MS_DEFAULT > 0):
        return False, "invalid frame cadence"
    return True, f"20 controls; {len(PRESETS)} presets; cadence {FRAME_MS_DEFAULT} ms"


def _check_agents_normalized_deterministic_vectors():
    if cosine_similarity((1.0, 0.0), (1.0, 0.0)) != 1.0:
        return False, "identical vectors not similarity 1.0"
    if not (0.0 <= cosine_similarity((1.0, 0.0), (0.0, 1.0)) <= 1.0):
        return False, "orthogonal similarity out of [0, 1]"
    pattern = WORLD_STATE_PATTERNS["stable_equilibrium"]
    if MATH_AGENT.pattern_alignment(pattern, pattern) != 1.0:
        return False, "self-alignment not 1.0"
    return True, "cosine + pattern alignment deterministic and normalized"


def _check_presentation_math_consolidated():
    expected = {"boost", "clip", "decay_alpha", "gaze_focus",
                "mix_color", "remap_centered", "scale"}
    public = {n for n in expected if getattr(_presentation_math, n, None) is not None}
    if public != expected:
        return False, f"presentation surface incomplete: {sorted(expected - public)}"
    _a = _presentation_math.scale(2.0, 0.5, hi=1.0)
    _b = _presentation_math.scale(2.0, 0.5, hi=1.0)
    if _a != _b or not isinstance(_a, float) or not (_a <= 1.0):
        return False, "presentation math nondeterministic or unbounded"
    return True, "7 consolidated presentation functions; deterministic"


def _check_internal_transitions_bounded_smooth():
    lo, hi, target = 0.2, 0.9, 0.95
    cursor = lo
    for _ in range(64):
        nxt = stable_exp_smooth(cursor, target, 0.3)
        if not (lo - 1e-12 <= nxt <= target + 1e-12):
            return False, "transition overshot target or left band"
        cursor = nxt
    if lerp(1.0, 2.0, 0.0) != 1.0 or lerp(1.0, 2.0, 1.0) != 2.0:
        return False, "lerp endpoints not exact"
    return True, "64-step no-overshoot climb; lerp endpoints exact"


def _check_emotion_math_governed_channels():
    signal = _interaction.INTERACTION.voice_input(
        {"pitch": 0.5, "rate": 0.3, "energy": 0.4, "pause": 0.1}
    )
    for _value in signal.values():
        if not (0.0 <= _value <= 1.0):
            return False, "voice channel outside [0, 1]"
    return True, "voice targets bounded by math-governed channels"


def _check_interaction_natural_consistent():
    r1 = _cognition.COGNITION.reasoning({"support": 0.9, "oppose": 0.1})
    r2 = _cognition.COGNITION.reasoning({"support": 0.9, "oppose": 0.1})
    if r1 != r2:
        return False, "reasoning not deterministic"
    if not (0.0 <= r1["score"] <= 1.0):
        return False, "reasoning score out of [0, 1]"
    teaching = _interaction.INTERACTION.adaptive_teaching(0.2, 0.9, 1.0)
    level = teaching["recommended_level"]
    if not (0.0 <= level <= 0.9 + 1e-12):
        return False, "teaching target overshot"
    return True, "reasoning deterministic; teaching never overshoots"


def _check_registry_and_invariants_intact():
    if len(_caps.CAPABILITY_REGISTRY) != 11 or len(_caps.MARKET_ROLE_REGISTRY) != 8:
        return False, "registry dimensions drifted"
    if _caps.REGISTRY_VERSION != "1.1":
        return False, "registry version drifted"
    return True, "11 capabilities / 8 roles / v1.1"


_CHECKS = (
    ("math_centralized_deterministic", _check_math_deterministic_centralized,
     "math layer is deterministic, precise, and fully centralized"),
    ("world_model_stable", _check_world_model_stable,
     "world model is stable, drift-controlled, and coherence-checked"),
    ("safety_bounded_predictable_nonblocking", _check_safety_bounded_predictable_nonblocking,
     "safety system is bounded, predictable, and non-blocking"),
    ("rendering_loop_smooth_cadence_correct", _check_rendering_loop_smooth_cadence_correct,
     "rendering loop is smooth, unified, and cadence-correct"),
    ("agents_normalized_deterministic_vectors", _check_agents_normalized_deterministic_vectors,
     "agents communicate through normalized, deterministic vectors"),
    ("presentation_math_consolidated", _check_presentation_math_consolidated,
     "presentation math is consolidated and consistent across all surfaces"),
    ("internal_transitions_bounded_smooth", _check_internal_transitions_bounded_smooth,
     "internal state transitions are bounded, smooth, and context-aligned"),
    ("emotion_math_governed_channels", _check_emotion_math_governed_channels,
     "emotion is expressed through math-governed channels"),
    ("interaction_natural_consistent", _check_interaction_natural_consistent,
     "reaction to user input is natural and consistent"),
    ("registry_and_invariants_intact", _check_registry_and_invariants_intact,
     "capability registry and role registry match the certified surface"),
    ("intelligence_stage_ordering", _check_intelligence_stage_ordering,
     "canonical 7-stage intelligence loop ordering is intact"),
    ("intelligence_no_runtime_imports", _check_intelligence_no_runtime_imports,
     "intelligence is free of nondeterministic/runtime imports"),
    ("intelligence_deterministic", _check_intelligence_deterministic,
     "intelligence is deterministic over a fixed synthetic payload"),
)

SUBSYSTEMS = {
    "math_determinism": ("math_centralized_deterministic",),
    "world_stability": ("world_model_stable", "internal_transitions_bounded_smooth"),
    "safety_boundaries": ("safety_bounded_predictable_nonblocking",),
    "rendering_cadence": (
        "rendering_loop_smooth_cadence_correct",
        "emotion_math_governed_channels",
    ),
    "agent_coherence": (
        "agents_normalized_deterministic_vectors",
        "interaction_natural_consistent",
    ),
    "pattern_alignment": ("agents_normalized_deterministic_vectors",),
    "state_consistency": (
        "internal_transitions_bounded_smooth",
        "presentation_math_consolidated",
        "registry_and_invariants_intact",
    ),
    "intelligence": (
        "intelligence_stage_ordering",
        "intelligence_no_runtime_imports",
        "intelligence_deterministic",
    ),
}


def verify():
    """Run every internal diagnostic against the live modules."""
    results = {}
    for _name, _fn, _description in _CHECKS:
        try:
            _ok, _note = _fn()
        except Exception as _exc:
            _ok, _note = False, f"check raised: {_exc!r}"
        results[_name] = {"ok": bool(_ok), "reason": _note or _description}
    return results


def _anomalies(results):
    return [name for name, entry in results.items() if not entry["ok"]]


def self_check(subsystems=None, log=False):
    """Internal verification across the required subsystems."""
    checks = verify()
    anomalies = _anomalies(checks)
    subsystem_status = {}
    for name, members in SUBSYSTEMS.items():
        subsystem_status[name] = {
            "ok": all(checks[member]["ok"] for member in members),
            "checks": list(members),
        }
    report = {
        "approach": "internal",
        "subsystems": subsystem_status,
        "checks": checks,
        "anomalies": anomalies,
        "stable": not anomalies,
    }
    if log:
        _log({"event": "self_check", "stable": report["stable"],
              "anomalies": anomalies})
    return report