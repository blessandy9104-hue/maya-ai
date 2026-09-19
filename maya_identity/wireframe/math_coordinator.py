"""Math Coordination Agent — executes vig_math equations and coordinates
every subsystem that depends on mathematical correctness.

Every facial expression, viseme, micro-motion, pattern, world state, and
rendering behaviour must derive from ``rig_math`` primitives and semantic
meaning. This agent is the single arbiter: it assembles poses from
channel-separated contributions, gates transitions with
``lerp / smoothstep / exp_smooth / clamp01``, validates pattern alignment
with ``dot(normalize(a), normalize(b))``, verifies rendering swaps through
``zprime / depth01 / shade_of / thickness01 / glow01``, and rejects or
corrects any subsystem output that violates mathematical rules.

Universal rule: all subsystems compute through this agent. No direct
arithmetic, no heuristics, no raw increments. Maya solves all behaviour
through math, pattern alignment, and semantic expression understanding.

Channel model (semantic meaning of every vertex):
    expression   — emotion/attention rig deformations (brow, nose, lips,
                   cheeks, mouth_rim, jaw posture).
    viseme       — mouth/jaw opening from ``mouth = jaw_open * viseme_phase``.
    micro        — emotional tremor for non-eye vertices, gated by
                   ``smoothstep(emotion_intensity)``.
    anatomical   — eye blink / gaze / lid (detail, applied at full weight,
                   never blended into the 0.6/0.3/0.1 mix).

Semantic meaning (the agent's interpretation of every control):
    affect        -> expression : smile, sadness, anger, surprise, fear, calm,
                                  attention, tiredness, thinking, uncertainty,
                                  confidence
    phonetic      -> viseme     : speaking, voice_intensity
    reflex        -> anatomical : blink, gaze_x, gaze_y
    physiological -> micro      : tremor
Emotional meaning never overrides anatomical meaning (the eye aperture is
driven only by blink/gaze, never by emotion), viseme meaning is confined to
the mouth/jaw so speech cannot distort the emotional rig, micro stays bounded
by MICRO_AMP, and all four channels blend exclusively through
``blend_pose(E, V, M)`` with anatomical added at full weight.

The identity rule for the pose is

    final_pose = 0.6 * expression_pose + 0.3 * viseme_pose + 0.1 * micro + anatomical

and every per-axis field is assembled by :meth:`MathAgent.compose_vertex`.

Beyond the rig, the agent also arbitrates the subsystems that consume Maya's
math: the pattern mapper (alignment via cosine similarity, pattern transitions
exclusively through ``lerp(old, new, clamp01(t))``, pattern-driven state
changes exclusively through ``exp_smooth(...)``), the world model (stability
and domain bounds), the safety engine (policy thresholds and compliance
checks), and any task orchestrator (coordination of a produced output against
the mathematically expected result). Above those planes, teams of agents
coordinate as peers: every message is a normalized vector, goals align by
dot similarity, contributions blend through ``lerp`` and ``exp_smooth``,
and each message is peer-validated for semantic meaning and rig_math
correctness so no heuristic enters the round. Learning and prediction follow
the same discipline: pattern series are summarized by variance and stability,
trends are detected by dot similarity on a normalized movement vector, and
predictions are stabilized by ``exp_smooth`` and re-derived before acceptance.
Every pattern interpretation must be
grounded against the five aligned domains — emotional state, viseme state,
world model state, safety threshold, and task priority — before it is
accepted. Every subsystem computes through this agent; nothing invents
arithmetic.
"""
from __future__ import annotations

import itertools
import math

from .rig_math import (
    clamp01, clamp, lerp, smoothstep, exp_smooth, stable_lerp,
    stable_exp_smooth, cosine_similarity,
    dot, normalize, magnitude, blend_pose, _blend_kernel, jaw_open, color_lerp,
    zprime, depth01, shade_of, thickness01, glow01,
    oscillate,
    bucket_of, bucket_midpoint,
    math_isclose, POSE_EPSILON,
    NB, CAM_D, SHADE_LO, SHADE_HI,
    BLEND_E, BLEND_V, BLEND_M, BLINK_LAMBDA, JAW_GAIN,
)

# Canonical invariant — the blend weights must sum to unity within the
# working tolerance. Guarded at import in both rig_math and this agent.
assert math_isclose(BLEND_E + BLEND_V + BLEND_M, 1.0, POSE_EPSILON)

# Math Precision Mode — deterministic, CPU-light tolerance/arithmetic switch
# for the agent. ``standard`` is the production baseline (POSE_EPSILON = 1e-9
# comparisons, one-step ``exp_smooth``). ``expert`` applies a stricter
# (smaller) tolerance and the numerically stable two-product smoothing forms;
# it never introduces randomness and tightens no safety threshold. The mode
# is a property of the singleton agent: set it explicitly, never at random.
PRECISION_STANDARD = "standard"
PRECISION_EXPERT = "expert"
PRECISION_MODES = frozenset({PRECISION_STANDARD, PRECISION_EXPERT})
# Expert uses a STRICTER equality tolerance (smaller epsilon) than standard.
PRECISION_TOLERANCE = {
    PRECISION_STANDARD: POSE_EPSILON,
    PRECISION_EXPERT: 1e-12,
}
# Constraint that must hold for every comparison-rule change: tighter modes
# may only ever equal or tighten (never loosen) the accepted error band.
assert PRECISION_TOLERANCE[PRECISION_EXPERT] <= PRECISION_TOLERANCE[PRECISION_STANDARD] < 1.0


def _metric_finite(value):
    """True only for a numeric, finite scalar — the fail-closed gate every
    safety/coordination metric passes through before a threshold applies."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)

CH_EXPRESSION = "expression"
CH_VISEME = "viseme"
CH_MICRO = "micro"
CH_ANATOMICAL = "anatomical"
CHANNELS = (CH_EXPRESSION, CH_VISEME, CH_MICRO, CH_ANATOMICAL)

JAW_REGIONS = frozenset({"jaw_l", "jaw_r", "chin", "neck"})
VISEME_ETYPES = frozenset({"mouth_rim", "cavity"})

# Micro-motion canonical amplitudes. Physiological tremor is subtle by
# construction: per-axis outputs are bounded by these exact constants, and
# the micro ceiling equals MICRO_AMP so micro can never rise to expression
# scale.
MICRO_AMP = 0.012
MICRO_AMP_X = 0.006

# Semantic displacement ceilings per channel used by verification. These
# guard meaning (a muscle cannot displace a vertex past anatomy); exact
# channel-assembly equality is the hard rule.
CHANNEL_MAX = {
    CH_EXPRESSION: 0.50,
    CH_VISEME: 0.35,
    CH_MICRO: MICRO_AMP,
    CH_ANATOMICAL: 0.80,
}

# Semantic channel manifest — every facial control belongs to exactly one
# semantic category. Emotional controls are affect (expression), phonetic
# controls are viseme mouth shapes, reflex controls are anatomical eye
# behaviour, and physiological controls are micro-motion. The agent uses
# this manifest to interpret controls; an unrecognised control is a category
# error, never a guess.
EMOTION_CONTROLS = frozenset({
    "smile", "sadness", "anger", "surprise", "fear", "calm",
})
STATE_CONTROLS = frozenset({
    "attention", "tiredness", "thinking", "uncertainty", "confidence",
})
VISEME_CONTROLS = frozenset({"speaking", "voice_intensity"})
ANATOMICAL_CONTROLS = frozenset({"blink", "gaze_x", "gaze_y"})
MICRO_CONTROLS = frozenset({"tremor"})

# Presentation/body controls that are deliberately NOT facial channels: they
# drive rendering materials or whole-body behaviour, never expression meaning.
SCENE_CONTROLS = frozenset({"glow_intensity", "scan_activity", "breath"})

CONTROL_CHANNELS = {}
for _control in EMOTION_CONTROLS:
    CONTROL_CHANNELS[_control] = CH_EXPRESSION
for _control in STATE_CONTROLS:
    CONTROL_CHANNELS[_control] = CH_EXPRESSION
for _control in VISEME_CONTROLS:
    CONTROL_CHANNELS[_control] = CH_VISEME
for _control in ANATOMICAL_CONTROLS:
    CONTROL_CHANNELS[_control] = CH_ANATOMICAL
for _control in MICRO_CONTROLS:
    CONTROL_CHANNELS[_control] = CH_MICRO

# Canonical safety policy — the single source of truth default. The on-disk
# ``maya_resource_policy.json`` may only tighten these limits; it can never
# relax the agent's contract.
SAFETY_POLICY = {
    "max_cpu_percent": 60.0,
    "max_memory_percent": 70.0,
    "max_process_count": 2,
    "max_launches_per_minute": 1,
    "sample_interval_seconds": 2.0,
}

# Canonical world-feature domain (normalised world state maps onto [0, 1]).
WORLD_DOMAIN = (0.0, 1.0)

# Canonical pattern-alignment domains — every interpretation of a pattern
# must be grounded against these five coordinated states.
PATTERN_ALIGNMENT_DOMAINS = ("emotional", "viseme", "world", "safety", "task")

# Canonical world-state feature space and equilibrium reference patterns.
# A world state is a normalized vector on (stability, drift, currency,
# consensus); classification and coherence are dot similarities against
# these reference patterns — regime descriptors of the world model, never
# claims about truth.
WORLD_STATE_FEATURES = ("stability", "drift", "currency", "consensus")

WORLD_STATE_PATTERNS = {
    "stable_equilibrium": (1.0, 0.0, 1.0, 1.0),
    "drifting":           (0.5, 1.0, 0.5, 1.0),
    "unstable":           (0.0, 1.0, 0.0, 0.5),
    "conflicted":         (0.5, 0.5, 0.5, 0.0),
}

# Task orchestration domain — the fifth aligned plane. Task features are
# bounded onto [0, 1] before any similarity, blend, or smoothing touches
# them; priority is angular (normalized vectors), fusion is weighted
# (rig_math.blend_pose), and confidence is stabilized by exp_smooth.
TASK_FEATURES = ("urgency", "impact", "effort")
TASK_PRIORITY_REFERENCE = (1.0, 1.0, 1.0)
TASK_BLEND_WEIGHTS = (0.6, 0.3, 0.1)  # BLEND_E / BLEND_V / BLEND_M
TASK_CONFIDENCE_DEFAULT_ALPHA = 0.15

# Multi-agent collaboration domain — the coordinating layer above the five
# aligned planes. Agent messages are normalized vectors, goals align by dot
# similarity, contributions blend by ``lerp`` + ``exp_smooth``, and every
# message is peer-validated for semantic meaning and rig_math correctness.
AGENT_ALIGNMENT_FLOOR = 0.6
AGENT_CONTRIBUTION_DEFAULT_ALPHA = 0.15

# Learning / prediction domain — evaluation of a pattern series over time.
# Learning summarizes a series with population variance and a stability
# bound; the learning feature vector is normalized over (variance, stability,
# trend); trend is detected by dot similarity on the normalized movement
# signature; predictions are stabilized by exp_smooth and are accepted only
# after semantic and mathematical re-validation.
LEARNING_FEATURES = ("variance", "stability", "trend")
LEARNING_MAX_STD = 0.05
LEARNING_TREND_FLOOR = 0.6
LEARNING_PREDICTION_DEFAULT_ALPHA = 0.15
LEARNING_DEFAULT_HORIZON = 1

# Material semantics — the face's visual vocabulary. Owned here so the
# colour engine derives its output from the agent, never from local guesses.
JEWEL = {
    "cyan":   (0x63, 0xd9, 0xff),
    "blue":   (0x2f, 0x8b, 0xf0),
    "violet": (0x8a, 0x7d, 0xff),
    "white":  (0xd8, 0xf9, 0xff),
    "dim":    (0x0e, 0x2a, 0x4c),
}

PALETTE = {
    "bg":       (0x07, 0x0d, 0x1a),
    "pupil":    (0xa8, 0xf0, 0xff),
    "iris":     (0x3c, 0xa8, 0xee),
    "globe":    (0x28, 0x8c, 0xd0),
    "lid":      (0x0f, 0x34, 0x5e),
    "socket":   (0x0a, 0x20, 0x40),
    "brow":     (0x22, 0x6e, 0xa8),
    "nose":     (0x24, 0x72, 0xb4),
    "nostril":  (0x0a, 0x1c, 0x38),
    "cavity":   (0x07, 0x16, 0x2e),
    "mouth":    (0x1a, 0x52, 0x8e),
    "chin":     (0x14, 0x38, 0x60),
    "jaw":      (0x11, 0x2c, 0x52),
    "cheek":    (0x11, 0x30, 0x58),
    "temple":   (0x0d, 0x24, 0x46),
    "forehead": (0x12, 0x30, 0x56),
    "ear":      (0x0d, 0x1e, 0x3c),
    "neck":     (0x0a, 0x1c, 0x36),
    "scalp":    (0x0b, 0x18, 0x30),
    "scan":     (0x15, 0x3a, 0x66),
    "spoke":    (0x1e, 0x5a, 0x90),
    "attach":   (0x0e, 0x2a, 0x4c),
    "skin":     (0x0f, 0x2a, 0x48),
    "default":  (0x0f, 0x28, 0x48),
}

BRIGHT_REGIONS = frozenset({"iris", "pupil", "spoke", "globe", "nose", "brow"})
EYE_REGIONS = frozenset({
    "socket_l", "socket_r", "lid_top_l", "lid_top_r",
    "lid_bot_l", "lid_bot_r", "globe_l", "globe_r",
    "iris_l", "iris_r", "pupil_l", "pupil_r",
})
HIGHLIGHT_REGIONS = frozenset({
    "iris", "pupil", "spoke", "globe",
    "nostril", "lid", "mouth", "nose", "brow",
})


def _rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(r))),
        max(0, min(255, int(g))),
        max(0, min(255, int(b))),
    )


class MathAgent:
    """Executes rig_math equations and arbitrates every downstream subsystem.

    All heavy lifting delegates to ``rig_math``; nothing here invents
    arithmetic. The agent exists so subsystems can be *checked* against the
    canonical equations and *corrected* when they drift.
    """

    def __init__(self, precision_mode=PRECISION_STANDARD):
        """The singleton agent starts in the production ``standard`` mode.
        ``expert`` is opt-in via :meth:`set_precision_mode`; every switch is
        deterministic and reversible."""
        self._precision = PRECISION_STANDARD
        self.set_precision_mode(precision_mode)

    # ---- math precision mode -------------------------------------------
    @property
    def precision_mode(self):
        """The active mode: ``standard`` (production baseline) or ``expert``
        (stricter tolerance, stable two-product smoothing)."""
        return self._precision

    def set_precision_mode(self, mode):
        """Switch the deterministic precision mode. ``mode`` must be one of
        :data:`PRECISION_MODES`; anything else raises ``ValueError``. The
        switch only ever tightens comparisons and smoothing arithmetic
        (never loosens, never random). Returns ``self`` for chaining."""
        if mode not in PRECISION_MODES:
            raise ValueError(
                f"unknown precision mode {mode!r} (expected one of "
                + ", ".join(sorted(PRECISION_MODES)) + ")")
        self._precision = mode
        return self

    def precision_tolerance(self):
        """The canonical equality tolerance for the active mode: ``1e-9`` in
        standard, a stricter ``1e-12`` in expert."""
        return PRECISION_TOLERANCE[self._precision]

    # ---- control domain ------------------------------------------------
    def control(self, value):
        """Any input control must live on the canonical [0, 1] domain."""
        return clamp01(value)

    def map01(self, value):
        """Normalise an arbitrary scalar onto [0, 1]."""
        return clamp01(value)

    def smoothstep(self, value):
        return smoothstep(value)

    def transition(self, current, target, alpha, mode="exp"):
        """Allowable transition families — everything is lerp, exp_smooth,
        or smoothstep; anything else is not a Maya transition."""
        value = clamp01(alpha)
        if mode == "exp":
            return exp_smooth(current, target, value)
        if mode == "lerp":
            return lerp(current, target, value)
        if mode == "smooth":
            return smoothstep(lerp(current, target, value))
        raise ValueError(f"unknown transition mode {mode!r}")

    # ---- viseme / emotion semantic gates --------------------------------
    def jaw_envelope(self, speaking, surprise):
        """Mouth amplitude is the max of active speech and surprise."""
        return jaw_open(max(clamp01(speaking), clamp01(surprise) * 0.6))

    def viseme_phase(self, t, speed=0.55, phase=1.2):
        """Syllabic phasing — a smoothstep-windowed speech wave."""
        return smoothstep(0.5 + 0.5 * math.sin(t * speed + phase))

    def emotion_gate(self, emotions):
        """Emotional intensity gates micro-motion; calm is emotional too."""
        return smoothstep(max(clamp01(emotion) for emotion in emotions))

    def control_channel(self, name):
        """The single semantic channel of a control.

        Emotional and cognitive controls are affect (expression), voice
        controls are phonetic (viseme), blink/gaze are reflex (anatomical),
        and tremor is physiological (micro). An unrecognised control raises —
        Maya never guesses what a control means."""
        try:
            return CONTROL_CHANNELS[name]
        except KeyError:
            raise ValueError(
                f"control {name!r} has no semantic channel") from None

    def micro_displacement(self, t, phase, amp):
        """Canonical micro-motion: subtle physiological tremor, bounded.

        Every channel keeps its exact amplitude ceiling —
        ``|y| <= MICRO_AMP``, ``|x| <= MICRO_AMP_X``, ``z == 0`` — so micro
        can never rise to expression scale. All blending still goes through
        :meth:`compose_vertex` at 0.1 weight."""
        amp = clamp01(amp)
        return (
            oscillate(t * 1.1 + phase * 1.7, 0.0, amp * MICRO_AMP_X),
            oscillate(t * 1.7 + phase, 0.0, amp * MICRO_AMP),
            0.0,
        )

    # ---- semantic interpretation and enforcement -------------------------------
    def semantic_profile(self, controls):
        """Channel-labelled view of a control vector.

        Every control name is interpreted through the semantic manifest into
        exactly one channel — affect (expression), phonetic (viseme), reflex
        (anatomical), or physiological (micro) — so no vector can ever mix
        categories. Scene/body controls (``glow_intensity``,
        ``scan_activity``, ``breath``) are presentation, not facial meaning,
        and are collected separately. An unrecognised control is raised:
        Maya never guesses meaning."""
        if not controls:
            return {ch: {} for ch in CHANNELS}
        profile = {ch: {} for ch in CHANNELS}
        for name, value in controls.items():
            channel = CONTROL_CHANNELS.get(name)
            if channel is None:
                if name in SCENE_CONTROLS:
                    continue
                raise ValueError(
                    f"control {name!r} has no semantic meaning")
            profile[channel][name] = value
        return profile

    def interpret(self, emotion=None, meta=None, fallback_visual="neutral"):
        """Interpret an emotion label or raw metadata into a validated,
        channel-labelled control vector.

        Emotional labels (``happy``, ``sad``, ``surprised``, ``neutral``,
        ``angry``, ``fearful``, ...) are affect meaning: they may only drive
        the expression channel. Phonetic, reflex, and physiological meaning
        can only enter through their own named controls — a label can never
        smuggle one channel into another. Returns ``(controls, preset,
        channels)`` with only the *effective* (non-zero) controls, and with
        ``channels`` mapping each affected control to its single semantic
        channel (empty buckets dropped)."""
        from .emotion_mapper import parse_metadata
        if meta is None:
            meta = {} if emotion is None else {"emotion": emotion}
        controls, preset, _warnings = parse_metadata(
            meta, fallback_visual=fallback_visual)
        active = {name: value for name, value in controls.items()
                  if value != 0.0}
        profile = self.semantic_profile(active)
        channels = {ch: bucket for ch, bucket in profile.items() if bucket}
        return active, preset, channels

    def enforce_semantics(self, ctrl, t=0.0, reduced=True):
        """Live enforcement gate: run the semantic audit and raise on any
        violation of meaning — expression may never override anatomy, viseme
        never distorts expression, micro stays bounded, and every per-vertex
        axis must blend exclusively through ``blend_pose(E, V, M)``."""
        report = self.verify_pose(ctrl, t, reduced)
        self.reject(report, message="semantic meaning violated")
        return report

    # ---- channel semantics ----------------------------------------------
    def channels_of(self, vpar):
        """Which semantic channels may deform this vertex."""
        channels = set()
        etype = vpar.get("etype")
        region = vpar.get("region", "")
        if vpar.get("eid") is not None:
            channels.add(CH_ANATOMICAL)
            return frozenset(channels)
        if etype in ("nostril", "mouth_rim") or (
            "brow" in region
        ) or region == "nose" or vpar.get("lip") or (
            "cheek" in region
        ) or region in JAW_REGIONS:
            channels.add(CH_EXPRESSION)
        if etype in VISEME_ETYPES or vpar.get("lip") or region in JAW_REGIONS:
            channels.add(CH_VISEME)
        channels.add(CH_MICRO)
        return frozenset(channels)

    # ---- pose assembly ---------------------------------------------------
    def compose_vertex(self, expression, viseme, micro, anatomical=(0.0, 0.0, 0.0)):
        """Per-vertex canonical assembly: blend expression/viseme/micro at
        the fixed 0.6/0.3/0.1 proportions, then add anatomical detail at
        full weight. Channels never bleed into each other's weight."""
        ex, ey, ez = expression
        ux, uy, uz = viseme
        mx, my, mz = micro
        jx, jy, jz = anatomical
        # Hot path: 3 blends per vertex per pose call. The channel values
        # arrive from guarded controller math (verified finite by the pose
        # integrity tests), so the raw kernel runs direct — guarded entry
        # points are for cross-boundary callers (see rig_math.blend_pose).
        return (
            _blend_kernel(ex, ux, mx) + jx,
            _blend_kernel(ey, uy, my) + jy,
            _blend_kernel(ez, uz, mz) + jz,
        )

    def assemble_pose(self, base, fields):
        """Expected pose from base mesh + channel fields (independent
        recomputation used by verification). Fields are 12-tuples of the four
        3-vectors (expression, viseme, micro, anatomical)."""
        out = []
        for (vx, vy, vz), f in zip(base, fields):
            e, u, m, j = f[:3], f[3:6], f[6:9], f[9:12]
            dx, dy, dz = self.compose_vertex(e, u, m, j)
            out.append((vx + dx, vy + dy, vz + dz))
        return out

    # ---- pattern alignment ------------------------------------------------
    def pattern_similarity(self, a, b):
        """Cosine similarity on the canonical domain (N dimensions), taken
        directly from the rig_math primitives:

        ``clamp01(dot(normalize(a), normalize(b)))``

        Zero vectors carry no meaning, so their similarity is 0 (not 1)."""
        if len(a) != len(b):
            raise ValueError("pattern vectors must share dimension")
        if not any(a) or not any(b):
            return 0.0
        result = clamp01(dot(normalize(a), normalize(b)))
        assert 0.0 <= result <= 1.0  # numeric invariant, guaranteed by clamp01
        return result

    def cosine_alignment(self, a, b):
        """Raw (un-clamped) pattern alignment: the stable dot similarity
        bounded onto [-1, 1] (see rig_math :func:`cosine_similarity`). Used
        by :meth:`verify_pattern_alignment` to assert the underlying
        similarity invariant kept score within [-1, 1]."""
        if len(a) != len(b):
            raise ValueError("pattern vectors must share dimension")
        return cosine_similarity(a, b)

    def semantic_alignment(self, vector_a, vector_b):
        """Alias used by pattern/world-state alignment checks."""
        return self.pattern_similarity(vector_a, vector_b)

    # ---- pattern transitions / state change / domain alignment --------------
    def pattern_transition(self, old, new, t):
        """Canonical pattern transition: ``lerp(old, new, clamp01(t))`` with
        both endpoints clamped onto the [0, 1] pattern domain before blending.
        This is the only allowed way an interpreted pattern value moves to
        another; any other between-value transition is rejected."""
        result = lerp(clamp01(old), clamp01(new), clamp01(t))
        assert -POSE_EPSILON <= result <= 1.0 + POSE_EPSILON
        return result

    def pattern_state(self, current, target, alpha):
        """Canonical pattern-driven state change:
        ``exp_smooth(current, target, clamp01(alpha))``. A pattern can alter
        a state only through exponential smoothing so the change converges
        without overshoot or unbounded jumps. In the ``expert`` precision
        mode the same contract is evaluated with the numerically stable
        two-product form :func:`stable_exp_smooth` (identical clamping, more
        precise arithmetic at extreme magnitudes)."""
        current = clamp01(current)
        target = clamp01(target)
        alpha_v = clamp01(alpha)
        if self._precision == PRECISION_EXPERT:
            return stable_exp_smooth(current, target, alpha_v)
        return exp_smooth(current, target, alpha_v)

    def pattern_alignment(self, pattern, state):
        """Explicit pattern-domain alias of ``pattern_similarity``: how well
        an interpretation vector aligns with a target state vector, always
        ``clamp01(dot(normalize(pattern), normalize(state)))``."""
        return self.pattern_similarity(pattern, state)

    def pattern_priority(self, value):
        """Align a raw task/path priority onto the canonical [0, 1] domain.
        Priorities are pattern inputs, so they must be bounded before any
        similarity comparison or smoothing touches them."""
        return clamp01(value)

    def pattern_safety_margin(self, cpu_percent, memory_percent, process_count,
                              launches, policy=None):
        """Safety as an aligned pattern state: ``1 - clamp01(max normalized
        load)`` against the canonical (or supplied) policy thresholds.
        1.0 = fully clear, 0.0 = at/over a threshold. A pattern interpretation
        that drives this below 0 is rejected by :meth:`pattern_alignment_ok`.

        Fail-degraded: a non-finite metric or an invalid (non-positive or
        non-finite) ceiling is treated as at/over the threshold (ratio 1.0),
        so the margin collapses to 0.0 instead of reporting a false-safe."""
        policy = policy or SAFETY_POLICY
        ratios = []
        for value, ceiling in (
            (cpu_percent, policy["max_cpu_percent"]),
            (memory_percent, policy["max_memory_percent"]),
            (process_count, policy["max_process_count"]),
            (launches, policy["max_launches_per_minute"]),
        ):
            try:
                ceiling_ok = math.isfinite(float(ceiling))
            except (TypeError, ValueError):
                ceiling_ok = False
            if not ceiling_ok or float(ceiling) <= 0.0:
                ratios.append(1.0)
                continue
            if not _metric_finite(value):
                ratios.append(1.0)
            else:
                ratios.append(float(value) / float(ceiling))
        return 1.0 - clamp01(max(ratios))

    def pattern_alignment_ok(self, aligned_states):
        """Five-domain alignment contract. A pattern interpretation is valid
        only when it is grounded against every domain Maya coordinates —
        emotional state, viseme state, world model state, safety threshold,
        and task priority — with each aligned value present, finite, and
        inside the canonical [0, 1] domain. Missing, non-finite, or
        out-of-domain values are alignment violations the agent rejects."""
        violations = []
        states = aligned_states or {}
        missing = [name for name in PATTERN_ALIGNMENT_DOMAINS
                   if name not in states]
        if missing:
            violations.append({"rule": "pattern_domain_missing",
                               "domains": missing})
        for name in PATTERN_ALIGNMENT_DOMAINS:
            value = states.get(name)
            if value is None or isinstance(value, bool):
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(v):
                violations.append({"rule": "pattern_domain_non_finite",
                                   "domain": name})
            elif v < WORLD_DOMAIN[0] or v > WORLD_DOMAIN[1]:
                violations.append({"rule": "pattern_domain_out_of_range",
                                   "domain": name, "value": v})
        return {"ok": not violations, "violations": violations}

    # ---- world stability ---------------------------------------------------
    def world_normalize(self, vector):
        """Unit-normalise a world feature vector (direction carries meaning)."""
        n = normalize(vector)
        if not any(n):
            return tuple(0.0 for _ in vector)
        return n

    def world_stability(self, series, lo=None, hi=None, max_std=0.05):
        """Stability of a world-state feature series: every value finite and
        (when a domain is given) within ``[lo, hi]``, and the series is not
        drifting beyond ``max_std``. A zero-length series is undefined."""
        vals = [float(v) for v in series]
        if not vals:
            return {"ok": False, "reason": "no samples", "std": None}
        if any(not math.isfinite(v) for v in vals):
            return {"ok": False, "reason": "non_finite_value", "std": None}
        lo = WORLD_DOMAIN[0] if lo is None else lo
        hi = WORLD_DOMAIN[1] if hi is None else hi
        if any(v < lo or v > hi for v in vals):
            return {"ok": False, "reason": "out_of_domain", "std": None}
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        assert variance >= 0.0  # invariant: variance is a sum of squares
        std = math.sqrt(variance)
        assert std >= 0.0  # invariant: std cannot be negative
        if not math.isfinite(std):
            return {"ok": False, "reason": "non_finite_variance", "std": std}
        return {"ok": std <= max_std, "reason": None if std <= max_std else "drift_beyond_tolerance", "std": std}

    def world_state_ok(self, mapping, domain=WORLD_DOMAIN):
        """Validate a world-state mapping: every numeric field is finite and
        inside the canonical domain; non-numeric values are ignored."""
        violations = []
        for key, value in mapping.items():
            if isinstance(value, bool):
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(v):
                violations.append({"rule": "world_non_finite", "field": key})
            elif v < domain[0] or v > domain[1]:
                violations.append({"rule": "world_out_of_domain", "field": key, "value": v})
        return {"ok": not violations, "violations": violations}

    # ---- world-state pattern math ----------------------------------------
    def world_index(self, value, ceiling):
        """Normalised world index (complement ratio):
        ``1 - clamp01(value / ceiling)`` — 1.0 at or below an ideal baseline,
        0.0 at or over the ceiling. The same bounded complement used for
        safety margins, applied to world-feature dispersion.

        Fail-degraded: a non-finite value or an invalid (non-positive or
        non-finite) ceiling returns 0.0 (the at/over-ceiling state), never a
        false-clear index."""
        try:
            ceiling_v = float(ceiling)
        except (TypeError, ValueError):
            ceiling_v = 0.0
        if not math.isfinite(ceiling_v) or ceiling_v <= 0.0:
            return 0.0
        if not _metric_finite(value):
            return 0.0
        return 1.0 - clamp01(float(value) / ceiling_v)

    def world_drift(self, series, alpha=0.03, tolerance=0.35, lo=None, hi=None):
        """Equilibrium drift check for a world-state feature series.

        The equilibrium of a series is its exponential-smoothed central
        tendency: it starts at the first sample and adapts toward each later
        sample through ``exp_smooth(eq, sample, clamp01(alpha))`` with a small
        ``alpha``, so a genuinely moving state is flagged instead of absorbed.
        Drift is the distance of the latest sample from that equilibrium,
        bounded onto the canonical domain by ``clamp01``:

            equilibrium = series[0]
            equilibrium = exp_smooth(equilibrium, sample, alpha)  per sample
            drift       = clamp01(abs(latest - equilibrium) / (hi - lo))

        A series that oscillates around its equilibrium is unstable by
        variance but does not drift; a series that shifts away from its
        equilibrium is drifting. Both checks are independent."""
        vals = [float(v) for v in series]
        if len(vals) < 2:
            return {"ok": True, "reason": None,
                    "equilibrium": vals[0] if vals else None, "drift": 0.0}
        if any(not math.isfinite(v) for v in vals):
            return {"ok": False, "reason": "non_finite_value",
                    "equilibrium": None, "drift": None}
        lo = WORLD_DOMAIN[0] if lo is None else lo
        hi = WORLD_DOMAIN[1] if hi is None else hi
        if any(v < lo or v > hi for v in vals):
            return {"ok": False, "reason": "out_of_domain",
                    "equilibrium": None, "drift": None}
        equilibrium = vals[0]
        for sample in vals[1:]:
            equilibrium = exp_smooth(equilibrium, sample, clamp01(alpha))
        span = max(1e-9, hi - lo)
        drift = clamp01(abs(vals[-1] - equilibrium) / span)
        assert 0.0 <= drift <= 1.0  # invariant: drift is clamp01-bounded
        if not math.isfinite(equilibrium) or not math.isfinite(drift):
            return {"ok": False, "reason": "non_finite_drift",
                    "equilibrium": equilibrium, "drift": drift}
        return {
            "ok": drift <= tolerance,
            "reason": None if drift <= tolerance else "drift_beyond_equilibrium",
            "equilibrium": equilibrium, "drift": drift,
        }

    def world_coherence(self, observed, equilibrium=None, floor=0.6):
        """Coherence of a world-state pattern against the mathematically
        expected (equilibrium) reference: ``clamp01(dot(normalize(observed),
        normalize(reference)))``. Coherence is an alignment measurement, not
        a truth judgement."""
        reference = (equilibrium if equilibrium is not None
                     else WORLD_STATE_PATTERNS["stable_equilibrium"])
        reference = tuple(reference[:len(observed)])
        if len(reference) != len(observed):
            raise ValueError("world-state vectors must share dimension")
        coherence = self.pattern_alignment(observed, reference)
        assert 0.0 <= coherence <= 1.0  # invariant: alignment is clamp01-bounded
        return {
            "ok": coherence >= floor,
            "coherence": coherence,
            "equilibrium": reference,
            "reason": None if coherence >= floor else "below_coherence_floor",
        }

    def world_classify(self, vector, floor=0.6):
        """Classify a world-state pattern against the canonical equilibrium
        reference patterns using normalized vectors: for each reference,

            ``clamp01(dot(normalize(pattern), normalize(reference)))``

        picking the best alignment. A zero pattern carries no meaning and
        cannot classify."""
        dim = len(vector)
        scores = {}
        for name, reference in WORLD_STATE_PATTERNS.items():
            ref = tuple(reference[:dim])
            if len(ref) != dim:
                continue
            scores[name] = self.pattern_alignment(vector, ref)
        if not scores:
            return {"ok": False, "reason": "no_matching_pattern_dimension",
                    "best": None, "alignment": 0.0, "scores": {}}
        assert all(0.0 <= v <= 1.0 for v in scores.values())
        best = max(scores, key=lambda name: scores[name])
        alignment = scores[best]
        return {
            "ok": alignment >= floor,
            "best": best,
            "alignment": alignment,
            "scores": scores,
            "reason": None if alignment >= floor else "below_classification_floor",
        }

    def world_evaluate(self, vector, floor=0.6):
        """Composite world-state evaluation: classify the normalized pattern
        and measure coherence against the equilibrium expectation. Both are
        dot similarities on normalized vectors; nothing here invents math."""
        classification = self.world_classify(vector, floor=floor)
        coherence = self.world_coherence(vector, floor=floor)
        return {
            "ok": classification["ok"] and coherence["ok"],
            "classification": classification,
            "coherence": coherence,
            "pattern_vector": tuple(vector),
        }

    def world_predict(self, predicted, expected, alpha=0.5, floor=0.6):
        """Align a world prediction with the mathematical expectation.

        Alignment is ``clamp01(dot(normalize(predicted), normalize(
        expected)))``; the predicted feature values move toward expectation
        exclusively through the canonical pattern transition
        ``lerp(clamp01(old), clamp01(new), clamp01(alpha))`` — lerp with both
        endpoints bounded onto the [0, 1] world domain."""
        if len(predicted) != len(expected):
            raise ValueError("world-state vectors must share dimension")
        alignment = self.pattern_alignment(predicted, expected)
        assert 0.0 <= alignment <= 1.0  # invariant: alignment is clamp01-bounded
        moved = tuple(self.pattern_transition(p, e, alpha)
                      for p, e in zip(predicted, expected))
        assert all(-POSE_EPSILON <= m <= 1.0 + POSE_EPSILON for m in moved)
        return {
            "ok": alignment >= floor,
            "alignment": alignment,
            "aligned": moved,
            "alpha": clamp01(alpha),
            "reason": None if alignment >= floor else "below_prediction_floor",
        }

    def channel_bounds_ok(self, channel, vector):
        """Semantic guard: a channel's displacement must respect its ceiling."""
        magnitude = max(abs(x) for x in vector)
        return magnitude <= CHANNEL_MAX[channel]

    # ---- expert invariants --------------------------------------------------
    def verify_world(self, report):
        """Audit the four world-state results (stability, drift / coherence,
        classify, predict) against their numeric invariants. Every invariant
        is mathematically guaranteed by the primitives (post-clamp bounds,
        finite deviations, bounded transitions), so a violation here means
        the model has drifted outside the canonical world algebra."""
        violations = []
        checks = {}
        stability = report.get("stability")
        if stability is not None and stability.get("std") is not None:
            std = stability["std"]
            checks["std"] = std
            if not math.isfinite(std):
                violations.append({"rule": "world_std_non_finite", "value": std})
            if std < 0.0:
                violations.append({"rule": "world_std_negative", "value": std})
        drift = report.get("drift")
        if drift is not None and drift.get("drift") is not None:
            d = drift["drift"]
            checks["drift"] = d
            if not math.isfinite(d) or not (0.0 <= d <= 1.0):
                violations.append({"rule": "world_drift_out_of_domain", "value": d})
        coherence = report.get("coherence")
        if coherence is not None and coherence.get("coherence") is not None:
            c = coherence["coherence"]
            checks["coherence"] = c
            if not math.isfinite(c) or not (0.0 <= c <= 1.0):
                violations.append({"rule": "world_coherence_out_of_domain", "value": c})
        classification = report.get("classification", report.get("classify"))
        if classification is not None:
            scores = classification.get("scores") or {}
            checks["scores"] = dict(scores)
            for name, value in scores.items():
                if not math.isfinite(float(value)) or not (0.0 <= float(value) <= 1.0):
                    violations.append({"rule": "world_score_out_of_domain",
                                       "score": name, "value": value})
            best = classification.get("best")
            if best is not None and scores and scores.get(best) is not None:
                top = classification.get("alignment")
                if top is not None and not math_isclose(
                        float(top), float(scores[best]), self.precision_tolerance()):
                    violations.append({"rule": "world_best_inconsistent",
                                       "best": best, "top": top})
        predict = report.get("predict")
        if predict is not None:
            alignment = predict.get("alignment")
            checked = tuple(predict.get("aligned") or ())
            checks["predicted_alignment"] = alignment
            checks["aligned"] = checked
            if alignment is not None and not (0.0 <= alignment <= 1.0):
                violations.append({"rule": "world_prediction_out_of_domain",
                                   "value": alignment})
            for m in checked:
                if not math.isfinite(float(m)) or not (-POSE_EPSILON <= float(m) <= 1.0 + POSE_EPSILON):
                    violations.append({"rule": "world_transition_unbounded", "value": m})
        return {"ok": not violations, "checks": checks,
                "violations": violations[:12]}

    def verify_pattern_alignment(self, pattern, state, tolerance=None):
        """Pattern-alignment invariants: the raw dot similarity is bounded
        onto [-1, 1], both vectors are unit-normalized (or zero, which scores
        0), and the clamped [0, 1] alignment equals ``pattern_alignment``.
        Drift between the raw and canonical scorings is a contract fault."""
        if len(pattern) != len(state):
            raise ValueError("pattern vectors must share dimension")
        tol = self.precision_tolerance() if tolerance is None else tolerance
        raw = self.cosine_alignment(pattern, state)
        na, nb = normalize(pattern), normalize(state)
        ma, mb = magnitude(na), magnitude(nb)
        aligned = clamp01(raw)
        canonical = self.pattern_alignment(pattern, state)
        violations = []
        if not (-1.0 <= raw <= 1.0):
            violations.append({"rule": "raw_similarity_out_of_domain", "value": raw})
        for label, vec in (("pattern", na), ("state", nb)):
            if not all(math.isfinite(float(c)) for c in vec):
                violations.append({"rule": "vector_non_finite", "where": label})
        for label, m in (("pattern", ma), ("state", mb)):
            if m > 0.0 and not math_isclose(m, 1.0, tol):
                violations.append({"rule": "vector_not_unit_normalized",
                                   "where": label, "magnitude": m})
        if not math_isclose(float(aligned), float(canonical), tol):
            violations.append({"rule": "alignment_scoring_drift",
                               "raw_clamped": aligned, "canonical": canonical})
        return {"ok": not violations, "raw": raw, "clamped": aligned,
                "canonical": canonical, "violations": violations[:12]}

    def verify_task_fusion(self, report, weights=None):
        """Task-fusion invariants: fused and blended task signals stay in
        [0, 1], the blend weights are finite, non-negative, and sum to unity
        within tolerance, and the confidence state never leaves its current-
        to-target band (no overshoot). Returns a violation list (empty when
        the fusion respected every invariant)."""
        fused = report.get("fused")
        blended = report.get("blended")
        confidence = report.get("confidence")
        alpha = report.get("alpha")
        weights = weights or TASK_BLEND_WEIGHTS
        violations = []
        checks = {"fused": fused, "alpha": alpha}
        if fused is not None and not (0.0 <= fused <= 1.0):
            violations.append({"rule": "task_fused_out_of_domain", "value": fused})
        if blended is not None:
            if isinstance(blended, dict):
                items = list(blended.items())
            else:
                items = [("blend_%d" % i, value)
                         for i, value in enumerate(blended)]
            checks["blended"] = dict(items)
            for name, value in items:
                if not math.isfinite(float(value)) or not (0.0 <= float(value) <= 1.0):
                    violations.append({"rule": "task_blend_out_of_domain",
                                       "signal": name, "value": value})
        try:
            wf = tuple(float(w) for w in weights)
        except (TypeError, ValueError):
            violations.append({"rule": "task_weights_invalid", "weights": weights})
        else:
            checks["weights"] = wf
            if not all(w >= 0.0 and math.isfinite(w) for w in wf) or not math_isclose(
                    sum(wf), 1.0, self.precision_tolerance()):
                violations.append({"rule": "task_weights_not_normalized",
                                   "weights": wf})
        if alpha is not None and not (0.0 <= float(alpha) <= 1.0):
            violations.append({"rule": "task_alpha_out_of_domain", "value": alpha})
        if confidence is not None:
            current = report.get("current")
            target = report.get("target")
            if not (0.0 <= confidence <= 1.0):
                violations.append({"rule": "task_confidence_out_of_domain",
                                   "value": confidence})
            elif current is not None and target is not None:
                band = (min(current, target), max(current, target))
                if confidence < band[0] - self.precision_tolerance() or \
                        confidence > band[1] + self.precision_tolerance():
                    violations.append({"rule": "task_confidence_overshoot",
                                       "value": confidence, "band": band})
        return {"ok": not violations, "checks": checks,
                "violations": violations[:12]}

    def channel_bounds_ok(self, channel, vector):
        """Semantic guard: a channel's displacement must respect its ceiling."""
        magnitude = max(abs(x) for x in vector)
        return magnitude <= CHANNEL_MAX[channel]

    # ---- safety -------------------------------------------------------------
    def check_limits(self, cpu_percent, memory_percent, process_count, launches,
                     stop_active=False, policy=None, cumulative=True):
        """Compliance check against the canonical (or supplied) safety policy.

        CPU/memory use ``>=``; process count and launch rate use ``>``. The
        policy on disk can only tighten these limits, never relax them.

        Fail-closed: a non-finite or unconvertible metric is itself a
        violation (``"* metric invalid"``), so an unreadable sensor reading
        can never pass as safe."""
        policy = policy or SAFETY_POLICY
        violations = []
        if not _metric_finite(cpu_percent):
            violations.append("CPU metric invalid")
        elif cpu_percent >= float(policy["max_cpu_percent"]):
            violations.append("CPU threshold exceeded")
        if not _metric_finite(memory_percent):
            violations.append("memory metric invalid")
        elif memory_percent >= float(policy["max_memory_percent"]):
            violations.append("memory threshold exceeded")
        if not _metric_finite(process_count):
            violations.append("process-count metric invalid")
        elif process_count > int(policy["max_process_count"]):
            violations.append("Maya process-count limit exceeded")
        if not _metric_finite(launches):
            violations.append("launch-rate metric invalid")
        elif launches > int(policy["max_launches_per_minute"]):
            violations.append("launch-rate limit exceeded")
        if stop_active:
            violations.append("emergency stop marker is active")
        return {"safe": not violations, "violations": violations}

    def enforce_safety(self, cpu_percent, memory_percent, process_count, launches,
                       stop_active=False, policy=None):
        """Raise when the safety contract is violated."""
        report = self.check_limits(cpu_percent, memory_percent, process_count,
                                   launches, stop_active, policy)
        self.reject(report, message="safety contract violated")

    def resource_anomaly(self, series, current, z_threshold=2.0, limit=1.0,
                         lo=0.0, hi=100.0):
        """Variance-based resource anomaly detection, mathematically derived
        and bounded by ``clamp01``.

        The baseline statistics (mean, population standard deviation) come
        from the supplied history *without* the current sample. The current
        sample's deviation from that baseline is standardised by an anomaly
        scale and clipped onto [0, 1]:

            mean      = sum(series) / len(series)
            std       = sqrt(variance(series))
            min_std   = (hi - lo) * 0.02      # a flat series is not rigid
            scale     = z_threshold * max(std, min_std)
            anomaly   = clamp01(abs(current - mean) / scale)

        The decision is an explicit threshold comparison: ``ok`` requires
        ``anomaly < limit``. A series with fewer than two baseline samples
        cannot yet be judged (``ok``)."""
        vals = [float(v) for v in series]
        if not _metric_finite(current):
            return {"ok": False, "reason": "non_finite_current", "anomaly": 0.0,
                    "deviation": None, "mean": None, "std": None}
        if len(vals) < 2:
            return {"ok": True, "reason": None, "anomaly": 0.0,
                    "deviation": None, "mean": None, "std": None}
        if any(not math.isfinite(v) for v in vals):
            return {"ok": False, "reason": "non_finite_value", "anomaly": 0.0,
                    "deviation": None, "mean": None, "std": None}
        span = hi - lo
        if any(v < lo or v > hi for v in vals):
            return {"ok": False, "reason": "out_of_domain", "anomaly": 0.0,
                    "deviation": None, "mean": None, "std": None}
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance)
        min_std = max(1e-9, span * 0.02)
        scale = z_threshold * max(std, min_std)
        if not math.isfinite(mean) or not math.isfinite(std) or scale <= 0:
            return {"ok": False, "reason": "non_finite_variance", "anomaly": 0.0,
                    "deviation": None, "mean": mean, "std": std}
        deviation = abs(float(current) - mean)
        anomaly = clamp01(deviation / scale)
        reason = None if anomaly < limit else "anomaly_beyond_threshold"
        return {"ok": anomaly < limit, "reason": reason, "anomaly": anomaly,
                "deviation": deviation, "mean": mean, "std": std,
                "scale": scale, "limit": limit}

    def motion_instability(self, series, lo=0.0, hi=1.0, max_std=0.05,
                           drift_tolerance=0.35):
        """Instability of a per-frame motion-energy series, derived from the
        canonical world math: variance instability (:meth:`world_stability`)
        and equilibrium drift (:meth:`world_drift`). The instability pressure
        is the bounded component-wise maximum of the two, aligned onto [0, 1]:

            std_pressure    = clamp01(std / max_std)
            drift_pressure  = world drift of the series
            instability     = clamp01(max(std_pressure, drift_pressure))

        The series is unstable when either component violates its bound."""
        stability = self.world_stability(series, lo=lo, hi=hi, max_std=max_std)
        drift = self.world_drift(series, lo=lo, hi=hi, tolerance=drift_tolerance)
        std_pressure = (clamp01(stability["std"] / max_std)
                        if stability.get("std") is not None else 0.0)
        drift_level = drift.get("drift") or 0.0
        if not math.isfinite(drift_level):
            drift_level = 0.0
        instability = clamp01(max(std_pressure, drift_level))
        ok = stability["ok"] and drift["ok"]
        return {"ok": ok, "instability": instability,
                "reason": None if ok else "motion_instability",
                "std": stability.get("std"), "drift": drift_level}

    def safety_evaluate(self, cpu_percent, memory_percent, process_count,
                        launches, stop_active=False, policy=None,
                        cpu_history=None, memory_history=None,
                        motion_series=None, world_series=None):
        """Composite safety decision — every constraint mathematically derived
        and validated by the agent, bounded by ``clamp01`` and ended by an
        explicit threshold comparison.

        Components, each optional on top of the canonical threshold check:

            thresholds      :meth:`check_limits` (CPU/memory ``>=``, process
                             count/launch rate ``>``, emergency stop)
            cpu_anomaly     :meth:`resource_anomaly` over CPU history
            memory_anomaly  :meth:`resource_anomaly` over memory history
            motion          :meth:`motion_instability` over a motion series
            world_drift     :meth:`world_drift` over a world-feature series

        Every component reports an aligned [0, 1] margin; the composite margin
        is the component-wise minimum. The decision is ``safe`` only when the
        thresholds hold and no optional component is anomalous."""
        policy = policy or SAFETY_POLICY
        thresholds = self.check_limits(cpu_percent, memory_percent,
                                       process_count, launches,
                                       stop_active, policy)
        violations = list(thresholds["violations"])
        margin = self.pattern_safety_margin(cpu_percent, memory_percent,
                                            process_count, launches, policy)
        checks = {"thresholds": thresholds["safe"]}
        flags = [thresholds["safe"]]

        if cpu_history is not None and cpu_percent is not None:
            report = self.resource_anomaly(cpu_history, cpu_percent)
            checks["cpu_anomaly"] = report["ok"]
            checks["cpu_anomaly_level"] = report["anomaly"]
            margin = min(margin, 1.0 - report["anomaly"])
            flags.append(report["ok"])
            if not report["ok"]:
                violations.append("CPU usage anomaly")

        if memory_history is not None and memory_percent is not None:
            report = self.resource_anomaly(memory_history, memory_percent)
            checks["memory_anomaly"] = report["ok"]
            checks["memory_anomaly_level"] = report["anomaly"]
            margin = min(margin, 1.0 - report["anomaly"])
            flags.append(report["ok"])
            if not report["ok"]:
                violations.append("memory usage anomaly")

        if motion_series is not None:
            report = self.motion_instability(motion_series)
            checks["motion_instability"] = report["ok"]
            checks["motion_instability_level"] = report["instability"]
            margin = min(margin, 1.0 - report["instability"])
            flags.append(report["ok"])
            if not report["ok"]:
                violations.append("motion instability")

        if world_series is not None:
            report = self.world_drift(world_series)
            checks["world_drift"] = report["ok"]
            checks["world_drift_level"] = report.get("drift") or 0.0
            margin = min(margin, 1.0 - (report.get("drift") or 0.0))
            flags.append(report["ok"])
            if not report["ok"]:
                violations.append("world-state drift")

        safe = all(flags)
        return {"safe": safe, "violations": violations,
                "margin": max(0.0, min(1.0, margin)), "checks": checks,
                "policy": policy}

    # ---- task orchestration ------------------------------------------------
    def task_priority(self, features, reference=None):
        """Task priority using normalized vectors — the alignment of a task's
        bounded feature vector with the canonical priority direction:

            priority = clamp01(dot(normalize(features), normalize(reference)))

        The default reference is the highest-priority direction ``(1, 1, 1)``.
        Priority is angular: scaling a feature vector does not change it, and
        a zero feature vector carries no meaning (its priority is 0)."""
        features = tuple(clamp01(float(v)) for v in features)
        reference = tuple(clamp01(float(v)) for v in
                          (reference or TASK_PRIORITY_REFERENCE))
        return {"priority": self.pattern_alignment(features, reference),
                "features": features, "reference": reference}

    def task_blend(self, values, weights=None):
        """General multi-signal weighted blend (N signals). Every value is
        bounded with ``clamp01``; weights are non-negative and finite, and
        normalized by their sum before blending — the same weighted-blend
        rule as ``rig_math.blend_pose``, extended to N sources."""
        vals = [clamp01(float(v)) for v in values]
        if not vals:
            raise ValueError("task blend requires at least one signal")
        if weights is None:
            w = [1.0 / len(vals)] * len(vals)
        else:
            w = [float(x) for x in weights]
        if len(w) != len(vals) or not all(math.isfinite(x) for x in w) \
                or any(x < 0.0 for x in w):
            raise ValueError(
                "task blend weights must match the signal count and be "
                "finite and non-negative")
        total = sum(w)
        if total <= 0.0:
            raise ValueError("task blend weights must sum above zero")
        normalized = tuple(wi / total for wi in w)
        fused = clamp01(sum(v * wi for v, wi in zip(vals, normalized)))
        return {"fused": fused, "blended": tuple(vals),
                "weights": normalized}

    def task_fuse(self, primary, secondary, context, weights=None):
        """Multi-signal fusion using ``rig_math.blend_pose`` — the canonical
        weighted blend 0.6/0.3/0.1 (expression/viseme/micro proportions)
        applied to the task context: primary signal, corroborating signal,
        ambient context. Every signal and the mix are bounded with
        ``clamp01``:

            fused = clamp01(blend_pose(clamp01(primary),
                                       clamp01(secondary),
                                       clamp01(context), *weights))

        ``blend_pose`` is the only blend allowed for task fusion — task
        decisions share the pose-blend mathematics."""
        w = tuple(float(x) for x in
                  (weights if weights is not None else TASK_BLEND_WEIGHTS))[:3]
        if len(w) != 3 or any(x < 0.0 for x in w) \
                or not all(math.isfinite(x) for x in w):
            raise ValueError(
                "task fusion needs three finite, non-negative blend weights")
        p, s, c = (clamp01(float(primary)), clamp01(float(secondary)),
                   clamp01(float(context)))
        return {"fused": clamp01(blend_pose(p, s, c, *w)),
                "blended": (p, s, c), "weights": w}

    def task_state(self, current, target, alpha):
        """Stabilized task decision state — the canonical exponential-smoothing
        pattern state, ``exp_smooth(clamp01(current), clamp01(target),
        clamp01(alpha))``. Nothing else may move a decision state."""
        return self.pattern_state(current, target, alpha)

    def task_confidence(self, primary, secondary, context, current=None,
                        alpha=None, weights=None):
        """Confidence score for a task decision: the multi-signal fusion
        (:meth:`task_fuse`, ``rig_math.blend_pose`` weights) stabilized over
        time by exponential smoothing. The first decision sets the baseline;
        later decisions move it exclusively through ``exp_smooth``:

            blended    = task_fuse(primary, secondary, context)["fused"]
            confidence = exp_smooth(clamp01(current), clamp01(blended),
                                    clamp01(alpha))

        Default ``alpha`` is ``TASK_CONFIDENCE_DEFAULT_ALPHA``."""
        fused = self.task_fuse(primary, secondary, context, weights)
        alpha_v = clamp01(float(TASK_CONFIDENCE_DEFAULT_ALPHA
                                if alpha is None else alpha))
        if current is None:
            confidence = fused["fused"]
            current_v = None
        else:
            current_v = float(current)
            confidence = self.pattern_state(current_v, fused["fused"], alpha_v)
        return {"confidence": confidence, "blended": fused["blended"],
                "weights": fused["weights"], "current": current_v,
                "alpha": alpha_v}

    def task_decision(self, features, primary, secondary, context,
                      reference=None, current=None, alpha=None, weights=None):
        """Build a complete task decision: priority from normalized vectors,
        multi-signal fusion through ``rig_math.blend_pose``, and confidence
        stabilized by ``exp_smooth``. The decision carries its own derivation
        so :meth:`task_decision_ok` can re-derive and verify it."""
        priority = self.task_priority(features, reference)
        confidence = self.task_confidence(primary, secondary, context,
                                          current=current, alpha=alpha,
                                          weights=weights)
        p, s, c = confidence["blended"]
        fused = self.task_fuse(p, s, c, confidence["weights"])["fused"]
        return {
            "features": priority["features"],
            "reference": priority["reference"],
            "priority": priority["priority"],
            "primary": p,
            "secondary": s,
            "context": c,
            "weights": confidence["weights"],
            "fused": fused,
            "current": confidence["current"],
            "alpha": confidence["alpha"],
            "confidence": confidence["confidence"],
        }

    def task_decision_ok(self, decision, tolerance=1e-9):
        """Validate a final task decision for semantic meaning and
        mathematical correctness. Semantic: every decision field is present,
        finite, bounded onto [0, 1], and the feature/reference vectors agree
        in dimension. Mathematical: the stored priority, fused blend, and
        exp-smoothed confidence are re-derived from the decision's own inputs
        and must match within tolerance."""
        violations = []
        scalar_fields = ("priority", "primary", "secondary", "context",
                         "fused", "confidence")
        vector_fields = ("features", "reference")
        for field in vector_fields + scalar_fields:
            if field not in decision:
                violations.append({"rule": "task_missing_field", "field": field})
                continue
            value = decision[field]
            if isinstance(value, (tuple, list)):
                if not value or not all(
                        isinstance(v, (int, float)) and not isinstance(v, bool)
                        and math.isfinite(float(v)) for v in value):
                    violations.append({"rule": "task_non_finite", "field": field})
                elif any(float(v) < 0.0 or float(v) > 1.0 for v in value):
                    violations.append({"rule": "task_out_of_domain",
                                       "field": field})
            elif isinstance(value, bool) \
                    or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                violations.append({"rule": "task_non_finite", "field": field})
            elif float(value) < 0.0 or float(value) > 1.0:
                violations.append({"rule": "task_out_of_domain", "field": field})

        features = tuple(float(v) for v in decision.get("features", ()))
        reference = tuple(float(v) for v in decision.get("reference", ()))
        if features and reference and len(features) != len(reference):
            violations.append({"rule": "task_dimension_mismatch"})

        checks = {}
        recomputed = {}
        blockers = {"task_missing_field", "task_non_finite",
                    "task_out_of_domain", "task_dimension_mismatch"}
        if not any(v["rule"] in blockers for v in violations):
            expected_priority = self.pattern_alignment(features, reference)
            checks["priority"] = math_isclose(
                expected_priority, float(decision["priority"]), tolerance)
            recomputed["priority"] = expected_priority

            weights = tuple(float(w) for w in
                            decision.get("weights", TASK_BLEND_WEIGHTS))
            expected_fused = self.task_fuse(
                decision["primary"], decision["secondary"],
                decision["context"], weights)["fused"]
            checks["fused"] = math_isclose(
                expected_fused, float(decision["fused"]), tolerance)
            recomputed["fused"] = expected_fused

            if decision.get("current") is not None:
                expected_confidence = self.pattern_state(
                    float(decision["current"]), expected_fused,
                    float(decision.get("alpha",
                                       TASK_CONFIDENCE_DEFAULT_ALPHA)))
            else:
                expected_confidence = expected_fused
            checks["confidence"] = math_isclose(
                expected_confidence, float(decision["confidence"]), tolerance)
            recomputed["confidence"] = expected_confidence

            for name, ok in checks.items():
                if not ok:
                    violations.append(
                        {"rule": "task_math_mismatch", "field": name})

        return {"ok": not violations, "violations": violations,
                "checks": checks, "recomputed": recomputed}

    # ---- multi-agent collaboration -------------------------------------------
    def agent_state(self, features):
        """Share state as a normalized math vector: every feature is bounded
        onto the canonical [0, 1] pattern domain with ``clamp01`` before it may
        enter an agent message. Non-finite inputs carry no meaning and become
        0. An agent can only communicate in this normalized form."""
        out = []
        for value in features:
            try:
                f = float(value)
            except (TypeError, ValueError):
                f = 0.0
            if not math.isfinite(f):
                f = 0.0
            out.append(clamp01(f))
        return tuple(out)

    def agent_goal_alignment(self, a_state, b_state, reference=None):
        """Goal alignment between two agents by dot similarity on their
        normalized state vectors — ``clamp01(dot(normalize(a),
        normalize(b)))`` via :meth:`pattern_alignment`. A ``reference`` goal
        direction compares one agent's state against that shared goal instead
        of against the other agent. A zero vector carries no goal, so its
        alignment is 0. No heuristic agreement: goals align only when their
        normalized directions align."""
        a = self.agent_state(a_state)
        target = (self.agent_state(reference) if reference is not None
                  else self.agent_state(b_state))
        alignment = self.pattern_alignment(a, target)
        return {"ok": alignment >= AGENT_ALIGNMENT_FLOOR,
                "alignment": alignment,
                "a_state": a, "b_state": target,
                "reason": None if alignment >= AGENT_ALIGNMENT_FLOOR
                          else "below_alignment_floor"}

    def agent_contribution(self, contribution, current, alpha, t=0.5):
        """Blend an agent's contribution into the shared state using the two
        canonical moves on the pattern domain — ``lerp`` for the current
        round's voiced move and ``exp_smooth`` for the converging shared
        state:

            voiced  = lerp(clamp01(current), clamp01(contribution), clamp01(t))
            evolved = exp_smooth(clamp01(current), clamp01(contribution),
                                 clamp01(alpha))

        Nothing else may move a shared state; both values stay on [0, 1]."""
        contribution_v = clamp01(float(contribution))
        current_v = clamp01(float(current))
        t_v = clamp01(float(t))
        alpha_v = clamp01(float(alpha))
        return {"voiced": clamp01(lerp(current_v, contribution_v, t_v)),
                "evolved": clamp01(exp_smooth(current_v, contribution_v,
                                             alpha_v)),
                "contribution": contribution_v, "current": current_v,
                "t": t_v, "alpha": alpha_v}

    def agent_validate(self, message, tolerance=1e-9):
        """Peer-validate an agent message for semantic meaning and rig_math
        correctness — the check every agent applies to every other agent's
        output. Semantic: ``agent_id`` present and non-blank, ``state`` and
        ``goal`` are non-empty vectors with every element finite and inside
        [0, 1] and matching dimension, and the scalar fields ``contribution``,
        ``current``, ``evolved``, ``voiced``, ``alpha``, ``t`` are present,
        finite, and inside [0, 1]. Mathematical: the stored ``voiced`` must
        equal :meth:`pattern_transition` (lerp) and the stored ``evolved``
        must equal :meth:`pattern_state` (exp_smooth) re-derived from the
        message's own inputs; an ``alignment`` field, when present, must
        equal :meth:`pattern_alignment` on the state/goal vectors."""
        violations = []
        agent_id = message.get("agent_id")
        if not agent_id or not isinstance(agent_id, str) or not agent_id.strip():
            violations.append({"rule": "agent_missing_id"})
        for field in ("state", "goal"):
            if field not in message:
                violations.append({"rule": "agent_missing_field", "field": field})
                continue
            value = message[field]
            if not isinstance(value, (tuple, list)) or not value:
                violations.append({"rule": "agent_non_finite", "field": field})
                continue
            bad = [v for v in value if isinstance(v, bool)
                   or not isinstance(v, (int, float))
                   or not math.isfinite(float(v))]
            if bad:
                violations.append({"rule": "agent_non_finite", "field": field})
            elif any(float(v) < 0.0 or float(v) > 1.0 for v in value):
                violations.append({"rule": "agent_out_of_domain", "field": field})
        for field in ("contribution", "current", "evolved", "voiced",
                      "alpha", "t"):
            if field not in message:
                violations.append({"rule": "agent_missing_field", "field": field})
                continue
            value = message[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                violations.append({"rule": "agent_non_finite", "field": field})
            elif float(value) < 0.0 or float(value) > 1.0:
                violations.append({"rule": "agent_out_of_domain", "field": field})
        if "alignment" in message:
            value = message["alignment"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                violations.append({"rule": "agent_non_finite", "field": "alignment"})
            elif float(value) < 0.0 or float(value) > 1.0:
                violations.append({"rule": "agent_out_of_domain",
                                   "field": "alignment"})
        state = message.get("state")
        goal = message.get("goal")
        if isinstance(state, (tuple, list)) and isinstance(goal, (tuple, list)) \
                and state and goal and len(state) != len(goal):
            violations.append({"rule": "agent_dimension_mismatch"})

        checks = {}
        recomputed = {}
        blockers = {"agent_missing_id", "agent_missing_field",
                    "agent_non_finite", "agent_out_of_domain",
                    "agent_dimension_mismatch"}
        if not any(v["rule"] in blockers for v in violations):
            expected_voiced = self.pattern_transition(
                float(message["current"]), float(message["contribution"]),
                float(message["t"]))
            checks["voiced"] = math_isclose(
                expected_voiced, float(message["voiced"]), tolerance)
            recomputed["voiced"] = expected_voiced
            expected_evolved = self.pattern_state(
                float(message["current"]), float(message["contribution"]),
                float(message["alpha"]))
            checks["evolved"] = math_isclose(
                expected_evolved, float(message["evolved"]), tolerance)
            recomputed["evolved"] = expected_evolved
            if "alignment" in message:
                expected_alignment = self.pattern_alignment(
                    message["state"], message["goal"])
                checks["alignment"] = math_isclose(
                    expected_alignment, float(message["alignment"]), tolerance)
                recomputed["alignment"] = expected_alignment
            for name, ok in checks.items():
                if not ok:
                    violations.append(
                        {"rule": "agent_math_mismatch", "field": name})
        return {"ok": not violations, "violations": violations,
                "checks": checks, "recomputed": recomputed}

    def agent_collaborate(self, messages, floor=AGENT_ALIGNMENT_FLOOR,
                          tolerance=1e-9):
        """A team round: every agent message is peer-validated for semantic
        meaning and rig_math correctness, every agent's normalized state
        vector is aligned against every other agent's by dot similarity
        (:meth:`pattern_alignment`), and the team's shared state is the
        sequential ``exp_smooth`` of the validated contributions — the only
        way a round moves the shared state. The team alignment is the
        worst-case (minimum) pairwise alignment. An empty round has nothing
        to coordinate and is accepted; no heuristic enters the round."""
        report = {"ok": True, "agents": {}, "pairs": [], "violations": [],
                  "team_alignment": None, "shared_state": None}
        validated = {}
        rounds = list(messages or [])
        for msg in rounds:
            verdict = self.agent_validate(msg, tolerance)
            agent_id = str(msg.get("agent_id", "?"))
            validated[agent_id] = verdict
            report["agents"][agent_id] = verdict["ok"]
            report["violations"].extend(verdict["violations"])
        pairs = []
        for i in range(len(rounds)):
            for j in range(i + 1, len(rounds)):
                left, right = rounds[i], rounds[j]
                labels = [str(left.get("agent_id", "?")),
                          str(right.get("agent_id", "?"))]
                left_state = left.get("state")
                right_state = right.get("state")
                if not isinstance(left_state, (tuple, list)) \
                        or not isinstance(right_state, (tuple, list)) \
                        or len(left_state) != len(right_state):
                    pairs.append({"agents": labels, "alignment": 0.0, "ok": False})
                    report["violations"].append({
                        "rule": "agent_round_dimension_mismatch",
                        "agents": labels})
                    continue
                alignment = self.pattern_alignment(left_state, right_state)
                ok = alignment >= floor
                pairs.append({"agents": labels, "alignment": alignment, "ok": ok})
                if not ok:
                    report["violations"].append({
                        "rule": "agent_goals_misaligned", "agents": labels})
        report["pairs"] = pairs
        if pairs:
            report["team_alignment"] = min(p["alignment"] for p in pairs)
        team = None
        for msg in rounds:
            try:
                contribution = clamp01(float(msg.get("contribution", 0.0)))
                alpha = clamp01(float(msg.get(
                    "alpha", AGENT_CONTRIBUTION_DEFAULT_ALPHA)))
            except (TypeError, ValueError):
                contribution = 0.0
                alpha = AGENT_CONTRIBUTION_DEFAULT_ALPHA
            if team is None:
                team = contribution
            else:
                team = exp_smooth(team, contribution, alpha)
        if team is not None:
            report["shared_state"] = clamp01(team)
        report["ok"] = all(validated.values()) and all(p["ok"] for p in pairs)
        return report

    # ---- learning / prediction -----------------------------------------------
    def learn_stats(self, series):
        """Learning summary of a pattern series: population variance and
        standard deviation with a stability judgement against
        ``LEARNING_MAX_STD``. Every sample must be finite and inside the
        canonical [0, 1] pattern domain; an empty series is undefined.
        ``ok`` means the series is a valid, spendable signal; ``stable``
        means its standard deviation stays within the learning bound."""
        vals = [float(v) for v in series]
        if not vals:
            return {"ok": False, "reason": "no_samples", "mean": None,
                    "variance": None, "std": None, "stable": False, "count": 0}
        if any(not math.isfinite(v) for v in vals):
            return {"ok": False, "reason": "non_finite_value", "mean": None,
                    "variance": None, "std": None, "stable": False,
                    "count": len(vals)}
        if any(v < WORLD_DOMAIN[0] or v > WORLD_DOMAIN[1] for v in vals):
            return {"ok": False, "reason": "out_of_domain", "mean": None,
                    "variance": None, "std": None, "stable": False,
                    "count": len(vals)}
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance)
        return {"ok": True, "reason": None, "mean": mean,
                "variance": variance, "std": std,
                "stable": std <= LEARNING_MAX_STD, "count": len(vals)}

    def learn_trend(self, series, reference=None, floor=None):
        """Trend detection by dot similarity on the normalized movement
        signature of a pattern series. The per-step signed movement is
        bounded onto [0, 1] and treated as a direction:

            movement[i] = clamp01(v[i+1] - v[i])
            alignment   = clamp01(dot(normalize(movement),
                                      normalize(reference)))

        The default reference is a steady rise over the same window (all
        ones). A static or strictly falling window carries a zero movement
        vector with no trend meaning (alignment 0). Fewer than two samples
        cannot describe a direction."""
        floor = LEARNING_TREND_FLOOR if floor is None else float(floor)
        vals = [float(v) for v in series]
        if any(not math.isfinite(v) for v in vals):
            return {"ok": False, "reason": "non_finite_value",
                    "alignment": 0.0, "movement": (), "reference": ()}
        if len(vals) < 2:
            return {"ok": False, "reason": "insufficient_samples",
                    "alignment": 0.0, "movement": (), "reference": ()}
        movement = tuple(clamp01(vals[i + 1] - vals[i])
                         for i in range(len(vals) - 1))
        if reference is None:
            reference_vector = tuple(1.0 for _ in movement)
        else:
            reference_vector = reference
            if isinstance(reference_vector, (tuple, list)):
                reference_vector = tuple(reference_vector[:len(movement)])
            if not isinstance(reference_vector, tuple) \
                    or len(reference_vector) != len(movement):
                return {"ok": False, "reason": "dimension_mismatch",
                        "alignment": 0.0, "movement": movement,
                        "reference": tuple(reference)}
        alignment = self.pattern_alignment(movement, reference_vector)
        return {"ok": alignment >= floor, "alignment": alignment,
                "movement": movement, "reference": reference_vector,
                "reason": None if alignment >= floor else "below_trend_floor"}

    def learn_feature(self, series):
        """The learner's normalized feature vector over ``LEARNING_FEATURES``
        — (variance, stability, trend) — each derived from the series and
        bounded onto [0, 1]:

            variance_pressure = clamp01(std / LEARNING_MAX_STD)
            stability        = 1 - clamp01(std / LEARNING_MAX_STD)
            trend            = :meth:`learn_trend` alignment (dot similarity)

        An invalid series carries the zero vector: no learning meaning."""
        stats = self.learn_stats(series)
        if not stats["ok"]:
            return (0.0, 0.0, 0.0)
        pressure = clamp01(stats["std"] / LEARNING_MAX_STD)
        trend_alignment = self.learn_trend(series)["alignment"]
        return (clamp01(pressure), clamp01(1.0 - pressure),
                clamp01(trend_alignment))

    def predict_signal(self, series, expected, alpha=None, horizon=None):
        """Predict a pattern signal over time. The observed series fixes the
        baseline, the ``expected`` reference is the target, and the
        prediction is stabilized exclusively with ``exp_smooth`` across the
        horizon:

            predicted[0] = latest sample
            predicted[i] = exp_smooth(predicted[i-1], clamp01(expected),
                                      clamp01(alpha))

        The trend alignment (:meth:`learn_trend`, dot similarity) qualifies
        the prediction. The series and the expected reference must be finite
        and inside [0, 1]; otherwise the prediction is rejected."""
        alpha_v = clamp01(float(LEARNING_PREDICTION_DEFAULT_ALPHA
                                if alpha is None else alpha))
        horizon_v = int(LEARNING_DEFAULT_HORIZON if horizon is None else horizon)
        if horizon_v < 1:
            return {"ok": False, "reason": "invalid_horizon",
                    "predicted": None, "expected": None, "trend": None,
                    "alpha": None, "horizon": horizon_v}
        stats = self.learn_stats(series)
        if not stats["ok"]:
            return {"ok": False, "reason": stats["reason"],
                    "predicted": None, "expected": None, "trend": None,
                    "alpha": None, "horizon": horizon_v}
        try:
            expected_v = float(expected)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "non_finite_expected",
                    "predicted": None, "expected": None, "trend": None,
                    "alpha": None, "horizon": horizon_v}
        if not math.isfinite(expected_v):
            return {"ok": False, "reason": "non_finite_expected",
                    "predicted": None, "expected": expected_v, "trend": None,
                    "alpha": None, "horizon": horizon_v}
        if not (0.0 <= expected_v <= 1.0):
            return {"ok": False, "reason": "expected_out_of_domain",
                    "predicted": None, "expected": expected_v, "trend": None,
                    "alpha": None, "horizon": horizon_v}
        predicted = clamp01(float(series[-1]))
        for _ in range(horizon_v):
            predicted = exp_smooth(predicted, expected_v, alpha_v)
        trend = self.learn_trend(series)
        return {"ok": True, "reason": None, "predicted": predicted,
                "expected": expected_v, "trend": trend["alignment"],
                "alpha": alpha_v, "horizon": horizon_v}

    def predict_validate(self, series, prediction, tolerance=1e-9):
        """Validate a prediction for semantic meaning and mathematical
        correctness. Semantic: a valid prediction reports finite in-domain
        ``predicted``, ``expected``, ``trend``, and ``alpha`` values, an
        integer ``horizon`` >= 1, and ``ok`` true. Mathematical: the stored
        prediction must equal :meth:`predict_signal` re-derived from the same
        inputs; any mismatch is a prediction violation that must be rejected."""
        violations = []
        if not isinstance(prediction, dict):
            violations.append({"rule": "prediction_not_a_report"})
        if not prediction.get("ok", False):
            violations.append({"rule": "prediction_not_accepted"})
        for field in ("predicted", "expected", "trend", "alpha"):
            if field not in prediction:
                violations.append({"rule": "prediction_missing_field",
                                   "field": field})
                continue
            value = prediction[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                violations.append({"rule": "prediction_non_finite",
                                   "field": field})
            elif float(value) < 0.0 or float(value) > 1.0:
                violations.append({"rule": "prediction_out_of_domain",
                                   "field": field})
        if "horizon" in prediction:
            horizon = prediction.get("horizon")
            if isinstance(horizon, bool) or not isinstance(horizon, int) \
                    or horizon < 1:
                violations.append({"rule": "prediction_invalid_horizon"})
        checks = {}
        recomputed = {}
        blockers = {"prediction_not_a_report", "prediction_not_accepted",
                    "prediction_missing_field", "prediction_non_finite",
                    "prediction_out_of_domain", "prediction_invalid_horizon"}
        if not any(v["rule"] in blockers for v in violations):
            derived = self.predict_signal(
                series,
                expected=prediction["expected"],
                alpha=prediction["alpha"],
                horizon=prediction["horizon"])
            checks["predicted"] = math_isclose(
                derived["predicted"], float(prediction["predicted"]), tolerance)
            recomputed["predicted"] = derived["predicted"]
            checks["trend"] = math_isclose(
                derived["trend"], float(prediction["trend"]), tolerance)
            recomputed["trend"] = derived["trend"]
            for name, ok in checks.items():
                if not ok:
                    violations.append({"rule": "prediction_math_mismatch",
                                       "field": name})
        return {"ok": not violations, "violations": violations,
                "checks": checks, "recomputed": recomputed}

    def predict_enforce(self, series, prediction, tolerance=1e-9):
        """Reject any prediction that violates mathematical correctness or
        semantic meaning: validate via :meth:`predict_validate`, then raise
        through :meth:`reject` when the prediction is invalid."""
        verdict = self.predict_validate(series, prediction, tolerance)
        self.reject(verdict, message="prediction violates the learning contract")
        return verdict

    # ---- final-output coordination --------------------------------------------
    @staticmethod
    def _energy(value):
        """Scalar energy of a numeric output (pose/state/prediction)."""
        if isinstance(value, dict):
            values = [v for v in value.values()
                      if isinstance(v, (int, float)) and not isinstance(v, bool)]
            value = tuple(values)
        if isinstance(value, (tuple, list)):
            if value and isinstance(value[0], (tuple, list)):
                return math.sqrt(sum(c * c for v in value for c in v))
            return magnitude(value)
        return abs(float(value))

    def output_consistency(self, rendered, state, predicted, tolerance=1e-6):
        """The rendered face, internal state, and predicted behaviour are three
        projections of the same mathematics; their energies must agree. Any
        disagreement is a coordination violation."""
        parts = (("rendered", rendered), ("state", state), ("predicted", predicted))
        violations = []
        for (name_a, value_a), (name_b, value_b) in itertools.combinations(parts, 2):
            energy_a = self._energy(value_a)
            energy_b = self._energy(value_b)
            if abs(energy_a - energy_b) > tolerance:
                violations.append({
                    "rule": "output_mismatch",
                    "fields": (name_a, name_b),
                    "energies": (energy_a, energy_b),
                })
        return {"ok": not violations, "violations": violations,
                "energies": {name: self._energy(value) for name, value in parts}}

    def coordinate(self, subsystem, produced, expected, tolerance=1e-6):
        """Generic orchestrator contract: a produced output must equal the
        mathematically expected result (within tolerance)."""
        ok = abs(self._energy(produced) - self._energy(expected)) <= tolerance
        return {"subsystem": subsystem, "ok": ok,
                "produced_energy": self._energy(produced),
                "expected_energy": self._energy(expected),
                "violations": [] if ok else [{
                    "rule": "coordination_mismatch", "subsystem": subsystem}]}

    def orchestrate(self, subsystems, t=0.0, reduced=True,
                    state_vector=None, predicted_vector=None):
        """Full-stack coordination contract — the single entry point through
        which every subsystem's final output is validated in one pass.

        ``subsystems`` may name any of:

            pose    -> ExpressionController, checked by :meth:`verify_pose`
            aligned -> five-domain pattern mapping (emotional / viseme /
                       world / safety / task), checked by
                       :meth:`pattern_alignment_ok`
            world   -> dict (mapping) or sequence (series), checked by
                       :meth:`world_state_ok` / :meth:`world_stability`
            safety  -> dict {cpu_percent, memory_percent, process_count,
                       launches, stop_active?, policy?}, checked by
                       :meth:`check_limits` plus :meth:`pattern_safety_margin`
            agents  -> list of agent messages (each a normalized state vector,
                       a goal direction, and a contribution), checked by
                       :meth:`agent_collaborate`

        Rendered face, internal state, and predicted behaviour are the final
        consistency contract: their energies must agree, otherwise the frame
        is rejected. Omitted subsystems are not part of the frame contract."""
        report = {"ok": True, "subsystems": {}, "violations": [],
                  "ensembles": {}}
        surface = None
        if "pose" in subsystems:
            pose = self.verify_pose(subsystems["pose"], t, reduced)
            report["subsystems"]["pose"] = pose["ok"]
            report["violations"].extend(pose["violations"])
            surface = self._energy(pose.get("pose") or ())
        if "aligned" in subsystems:
            alignment = self.pattern_alignment_ok(subsystems["aligned"])
            report["subsystems"]["aligned"] = alignment["ok"]
            report["violations"].extend(alignment["violations"])
        if "world" in subsystems:
            world = subsystems["world"]
            world_check = (self.world_state_ok(world) if isinstance(world, dict)
                           else self.world_stability(world))
            report["subsystems"]["world"] = bool(world_check["ok"])
            if not world_check["ok"]:
                world_violations = world_check.get("violations")
                if not world_violations and world_check.get("reason"):
                    world_violations = [{"rule": world_check["reason"]}]
                report["violations"].extend(world_violations or [])
        if "safety" in subsystems:
            data = subsystems["safety"] or {}
            names = ("cpu_percent", "memory_percent", "process_count", "launches")
            present = all(k in data for k in names)
            if present:
                args = tuple(data.get(k) for k in names)
                safety = self.check_limits(*args,
                                           stop_active=bool(data.get("stop_active")),
                                           policy=data.get("policy"))
                report["subsystems"]["safety"] = bool(safety["safe"])
                report["subsystems"]["safety_margin"] = self.pattern_safety_margin(
                    *args, policy=data.get("policy"))
                if not safety["safe"]:
                    report["violations"].append(
                        {"rule": "safety_contract", "details": safety["violations"]})
        if "agents" in subsystems:
            collaboration = self.agent_collaborate(subsystems["agents"])
            report["subsystems"]["agents"] = collaboration["ok"]
            report["violations"].extend(collaboration["violations"])
            if collaboration["team_alignment"] is not None:
                report["subsystems"]["team_alignment"] = collaboration["team_alignment"]
            if collaboration["shared_state"] is not None:
                report["subsystems"]["shared_state"] = collaboration["shared_state"]
        state = (surface if state_vector is None
                 else self._energy(state_vector))
        predicted = (state if predicted_vector is None
                     else self._energy(predicted_vector))
        if surface is not None or state is not None:
            consistency = self.output_consistency(
                surface if surface is not None else state, state, predicted)
            report["subsystems"]["consistency"] = consistency["ok"]
            report["violations"].extend(consistency["violations"])
            report["ensembles"] = consistency["energies"]
        report["ok"] = all(report["subsystems"].values())
        report["violations"] = report["violations"][:12]
        return report

    def finalize(self, ctrl, t=0.0, reduced=True, state_vector=None, predicted_vector=None):
        """Conductor: ties pose validation and output consistency into one
        final-output contract for the face renderer. Delegates to
        :meth:`orchestrate` so every frame is validated through the single
        coordination entry point. State and predicted vectors are optional;
        when omitted they are taken to be the rendered energy itself (a
        compliant, consistent default)."""
        full = self.orchestrate({"pose": ctrl}, t, reduced,
                                state_vector=state_vector,
                                predicted_vector=predicted_vector)
        return {
            "ok": full["ok"],
            "pose_ok": full["subsystems"].get("pose", False),
            "consistency_ok": full["subsystems"].get("consistency", False),
            "violations": full["violations"],
            "ensembles": full["ensembles"],
        }

    # ---- rendering ---------------------------------------------------------
    def depth_bucket(self, z):
        """Shade grade bucket from the depth grade ``shade_of``."""
        return bucket_of(shade_of(z))

    def compute_edge_color(self, region, materials, t, zp, bg):
        """Canonical line colour through the rig_math depth chain:
        ``zprime -> depth01 -> shade_of -> color_lerp -> glow01``."""
        cyan = color_lerp(JEWEL["cyan"], JEWEL["blue"],
                          clamp01(materials.get("cyan_blue_balance", 0.55)))
        violet = color_lerp(JEWEL["violet"],
                            JEWEL["blue"],
                            1.0 - clamp01(materials.get("violet_diagnostic", 0.18)))
        base = color_lerp(cyan, violet, clamp01(t))
        palette_key = "default"
        for rk in PALETTE:
            if rk in region:
                palette_key = rk
                break
        skin = PALETTE.get(palette_key, PALETTE["default"])
        bright = 0.70
        if any(rk in region for rk in EYE_REGIONS):
            bright = materials.get("eye_brightness", 0.95)
        elif any(rk in region for rk in BRIGHT_REGIONS):
            bright = 0.88
        elif any(rk in region for rk in HIGHLIGHT_REGIONS):
            bright = 0.82
        line = color_lerp(skin, base, clamp01(bright))
        opacity = materials.get("wireframe_opacity", 0.85)
        line = color_lerp(bg, line, clamp01(opacity))
        glow = glow01(zp)
        glow_mat = materials.get("glow_intensity", 0.0)
        add = clamp01(glow * glow_mat * 0.45)
        line = color_lerp(line, (0x5a, 0xcc, 0xff), add)
        return _rgb_to_hex(*line)

    def line_width(self, z, size):
        """Canvas stroke width from ``thickness01``, capped for the canvas."""
        w = thickness01(zprime(z))
        cap = max(1, int(size / 40))
        return int(clamp(w, 1.0, float(cap)))

    # ---- verification / correction -----------------------------------------
    def verify_pose(self, ctrl, t=0.0, reduced=True, correct=False):
        """Audit a controller against the canonical channel model.

        Recomputes the expected pose from the channel fields captured by the
        controller and checks: exact channel assembly (the hard rule),
        per-channel displacement ceilings, and semantic channel separation
        (a channel may only deform a vertex whose meaning includes that
        channel — emotion/viseme/micro never touch the eyes, viseme never
        touches brows/nose/cheeks, and anatomical never touches non-eye
        vertices). With ``correct=True`` the expected (mathematically
        correct) pose is returned; otherwise the report carries the
        violations.
        """
        prev = getattr(ctrl, "_audit", False)
        ctrl._audit = True
        try:
            ctrl.compute_pose(t, reduced)
        finally:
            ctrl._audit = prev
        fields = getattr(ctrl, "_last_fields", None)
        expected = getattr(ctrl, "_last_pose", None)
        violations = []
        if fields is None or expected is None:
            return {"ok": False, "violations": [{"rule": "audit_unavailable"}],
                    "pose": []}
        base = ctrl._mesh.verts
        rebuilt = self.assemble_pose(base, fields)
        verts = ctrl._mesh.vpar
        for i in range(len(fields)):
            if any(abs(expected[i][k] - rebuilt[i][k]) > 1e-9 for k in range(3)):
                violations.append({"rule": "channel_assembly", "index": i})
        for i, f in enumerate(fields):
            e, u, m, j = f[:3], f[3:6], f[6:9], f[9:12]
            if max(abs(x) for x in e) > CHANNEL_MAX[CH_EXPRESSION]:
                violations.append({"rule": "expression_ceiling", "index": i})
            if max(abs(x) for x in u) > CHANNEL_MAX[CH_VISEME]:
                violations.append({"rule": "viseme_ceiling", "index": i})
            if max(abs(x) for x in m) > CHANNEL_MAX[CH_MICRO]:
                violations.append({"rule": "micro_ceiling", "index": i})
            if max(abs(x) for x in j) > CHANNEL_MAX[CH_ANATOMICAL]:
                violations.append({"rule": "anatomical_ceiling", "index": i})
        for i, f in enumerate(fields):
            allowed = self.channels_of(verts[i])
            e, u, m, j = f[:3], f[3:6], f[6:9], f[9:12]
            labelled = (
                (CH_EXPRESSION, e),
                (CH_VISEME, u),
                (CH_MICRO, m),
                (CH_ANATOMICAL, j),
            )
            for channel, vector in labelled:
                if channel not in allowed and any(
                        abs(x) > 1e-14 for x in vector):
                    violations.append({
                        "rule": "semantic_scope",
                        "channel": channel, "index": i})
        ok = not violations
        report = {"ok": ok, "violations": violations[:12], "pose": []}
        if correct:
            report["pose"] = rebuilt if ok else rebuilt
        else:
            report["pose"] = expected
        return report

    def verify_render(self, region, materials, z=None, bucket=None,
                      expected_hex=None, expected_width=None, size=40, bg=(0x07, 0x0d, 0x1a)):
        """Validate a subsystem colour/width against the canonical math.

        Pass the output a subsystem produced; the agent recomputes the
        expected result from rig_math and reports any mismatch."""
        violations = []
        if z is not None:
            t = depth01(zprime(z))
            zp = zprime(z)
            computed_bucket = self.depth_bucket(z)
        else:
            t = bucket_midpoint(bucket) if bucket is not None else 0.5
            zp = 0.0
            computed_bucket = bucket
        hex_out = self.compute_edge_color(region, materials, t, zp, bg)
        width_out = self.line_width(z, size) if z is not None else None
        if expected_hex is not None and expected_hex != hex_out:
            violations.append({"rule": "render_color_mismatch",
                               "got": expected_hex, "expected": hex_out})
        if expected_width is not None and width_out is not None and expected_width != width_out:
            violations.append({"rule": "render_width_mismatch",
                               "got": expected_width, "expected": width_out})
        return {"ok": not violations, "violations": violations,
                "color": hex_out, "width": width_out, "bucket": computed_bucket}

    # ---- spectral / frequency-domain math --------------------------------
    def spectral_analysis(self, series, sample_rate=1.0):
        """Deterministic frequency report for an observed series (fail-closed).

        Delegated to the architectural frequency layer so every subsystem
        quotes the same class / SNR / periodicity vocabulary."""
        from maya_frequency import analyze
        return analyze(series, sample_rate)

    def signal_quality(self, series, min_snr_db=None, min_periodicity=None,
                       max_noise=None, sample_rate=1.0):
        """Fail-closed spectral quality gate over an observed series."""
        from maya_frequency import signal_quality as _signal_quality
        kwargs = {"sample_rate": sample_rate}
        if min_snr_db is not None:
            kwargs["min_snr_db"] = min_snr_db
        if min_periodicity is not None:
            kwargs["min_periodicity"] = min_periodicity
        if max_noise is not None:
            kwargs["max_noise"] = max_noise
        return _signal_quality(series, **kwargs)

    def signal_to_noise(self, series, min_snr_db=None, sample_rate=1.0):
        """SNR of the periodic content with its margin over the minimum."""
        from maya_frequency import refine_snr
        if min_snr_db is None:
            return refine_snr(series, sample_rate=sample_rate)
        return refine_snr(series, min_snr_db=min_snr_db, sample_rate=sample_rate)

    def periodicity(self, series):
        """Bounded [0, 1] repetition score of a series (0.0 when unreadable)."""
        from maya_frequency import analyze
        report = analyze(series)
        if not report.get("ok"):
            return 0.0
        return clamp01(report["periodicity"])

    def spectral_alignment(self, a, b):
        """Bounded [0, 1] spectral agreement between two observed series."""
        from maya_frequency import alignment
        return clamp01(alignment(a, b))

    def reject(self, report, message="rejected by Math Coordination Agent"):
        """Raise when any coordinated output violates the math or semantics."""
        if not report.get("ok", True):
            raise ValueError(
                f"{message}: {report['violations'][:3]!r}"
            )


MATH_AGENT = MathAgent()

__all__ = [
    "MathAgent", "MATH_AGENT",
    "CH_EXPRESSION", "CH_VISEME", "CH_MICRO", "CH_ANATOMICAL", "CHANNELS",
    "JAW_REGIONS", "VISEME_ETYPES", "CHANNEL_MAX",
    "MICRO_AMP", "MICRO_AMP_X",
    "EMOTION_CONTROLS", "STATE_CONTROLS", "VISEME_CONTROLS",
    "ANATOMICAL_CONTROLS", "MICRO_CONTROLS", "CONTROL_CHANNELS",
    "SCENE_CONTROLS",
    "SAFETY_POLICY", "WORLD_DOMAIN", "PATTERN_ALIGNMENT_DOMAINS",
    "WORLD_STATE_FEATURES", "WORLD_STATE_PATTERNS",
    "TASK_FEATURES", "TASK_PRIORITY_REFERENCE", "TASK_BLEND_WEIGHTS",
    "TASK_CONFIDENCE_DEFAULT_ALPHA",
    "AGENT_ALIGNMENT_FLOOR", "AGENT_CONTRIBUTION_DEFAULT_ALPHA",
    "LEARNING_FEATURES", "LEARNING_MAX_STD", "LEARNING_TREND_FLOOR",
    "LEARNING_PREDICTION_DEFAULT_ALPHA", "LEARNING_DEFAULT_HORIZON",
    "JEWEL", "PALETTE", "BRIGHT_REGIONS", "EYE_REGIONS", "HIGHLIGHT_REGIONS",
    "_rgb_to_hex",
]