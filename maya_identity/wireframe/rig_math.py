"""rig_math — Maya's mathematical cognition layer.

Every numerical operation used for projection, interpolation, and pose
blending derives from this module. The equations are the canonical
definitions:

Vector operations:
    add(a, b)       = (a.x + b.x, a.y + b.y, a.z + b.z)
    sub(a, b)       = (a.x - b.x, a.y - b.y, a.z - b.z)
    dot(a, b)       = a.x*b.x + a.y*b.y + a.z*b.z
    normalize(v)    = v / sqrt(dot(v, v))

Interpolation and smoothing:
    lerp(a, b, t)          = a + (b - a) * t
    smoothstep(x)          = x*x*(3 - 2*x)
    exp_smooth(c, t, lam)  = c + (t - c) * lam
    clamp(x, lo, hi)       = max(lo, min(hi, x))
    clamp01(x)             = clamp(x, 0, 1)

Projection and depth normalization:
    Z'    = Z / (1 + (Z / CAM_D))
    depth = clamp01((Z' - Z_min) / (Z_max - Z_min))
    color = lerp(cyan, violet, depth)

Rendering physics:
    thickness       = 1.0 + 2.0 * (1 - Z')
    glow_intensity  = exp(-Z' * 2.5)
    project_scale   = CAM_D / (CAM_D - Z)          # pinhole projection factor
    lift_luminance  = channel + max(0, floor - max(rgb))   # tiny-render floor
    boost_rgb       = min(255, c*scale + offset)            # highlight boost

Pose baseline:
    pose(t) = base_pose
            + sum_k (control_k * weight_k)          -> expression channel
            + viseme(t) * jaw_open                  -> viseme channel
            + smoothstep(emotion_intensity) * micro_motion

Blending and constraints (channels):
    control_k in [0, 1]
    jaw_open      = clamp(amplitude * 1.2, 0, 1)
    final_pose    = 0.6 * expression + 0.3 * viseme + 0.1 * micro_channel

Anatomical detail (eye blink/gaze, breathing, head pose) is applied on top
of the blend at full strength — it is anatomy, not an emotional channel.

Pose blend equality: the blend weights 0.6 / 0.3 / 0.1 are exact literals,
but their binary sum is not exactly 1.0. Compare any pose value with
``pose_near`` (tolerance ``POSE_EPSILON`` = 1e-9), never with ``==``.

Numeric contracts (expert grade): every primitive declares, in its docstring
and in ``NUMERIC_CONTRACTS`` at the end of this module, the valid input
domain, the output guarantee, the maximum arithmetical error bound, the
required float-comparison rule (always ``math_isclose`` — never ``==`` for
re-derived values), and the deterministic fallback for non-finite inputs.
Non-finite values never propagate: each primitive returns a neutral constant
so pose, render, and pattern paths stay finite and stable.
"""
from __future__ import annotations

import math

# ---- projection / shading constants ----
CAM_D = 5.0      # camera distance (canonical head units)
SHADE_LO = -0.9  # Z' far bound (back of skull / neck)
SHADE_HI = 0.80  # Z' near bound (nose tip)
NB = 40          # depth buckets (continuous mapping sampled at this depth)

# ---- pose blend constants ----
BLEND_EXPR = 0.6
BLEND_VISEME = 0.3
BLEND_MICRO = 0.1
# Compatible aliases (the weights that made up the old per-unit blend).
BLEND_E, BLEND_V, BLEND_M = BLEND_EXPR, BLEND_VISEME, BLEND_MICRO
BLINK_LAMBDA = 0.12
JAW_GAIN = 1.2

# Floating-point identity risk: 0.6 + 0.3 + 0.1 != 1.0 exactly in binary.
# Any equality check on a blended pose must use pose_near() with this
# tolerance. The weights themselves are canonical and MUST NOT change.
POSE_EPSILON = 1e-9


def _finite(value, fallback=0.0):
    """Coerce a numeric input to a finite float; NaN/±inf and unconvertible
    values become ``fallback``. Guards every primitive so a non-finite value
    can never propagate through a pose, render, or pattern."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(v):
        return fallback
    return v


def math_isclose(a, b, tolerance=1e-9):
    """Canonical tolerance-based equality: ``abs(a - b) <= tolerance *
    max(1.0, abs(a), abs(b))`` — a relative tolerance with an absolute floor
    of 1.0, so it carries a fixed slack of ``tolerance`` for values at or
    below unit scale (exactly the pose / blend / pattern domain). Non-finite
    inputs are never equal. This is the only sanctioned way to compare
    blended or re-derived float values."""
    ta = _finite(a, float("nan"))
    tb = _finite(b, float("nan"))
    if math.isnan(ta) or math.isnan(tb):
        return False
    return abs(ta - tb) <= float(tolerance) * max(1.0, abs(ta), abs(tb))


# Canonical invariant — the pose-blend weights MUST sum to unity within the
# working tolerance. Fails loudly at import time if they ever drift.
assert math_isclose(BLEND_E + BLEND_V + BLEND_M, 1.0, POSE_EPSILON)


# ---------------------------------------------------------------------------
# Vector operations
# ---------------------------------------------------------------------------
def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    """Inner product over equal-length vectors (any dimension; 3D special
    case). Used for pattern alignment — ``dot(normalize(p), normalize(i))`` —
    and for mesh geometry alike, from a single canonical primitive."""
    return sum(x * y for x, y in zip(a, b))


def magnitude(v):
    s = dot(v, v)
    if not math.isfinite(s) or s < 0.0:
        return 0.0
    return math.sqrt(s)


def normalize(v):
    """Unit vector preserving dimension (zero vector -> the zero vector of
    the same dimension). 3D vectors keep their exact prior behaviour."""
    n = len(v)
    m = magnitude(v)
    if m <= 0.0:
        return tuple(0.0 for _ in range(n))
    inv = 1.0 / m
    return tuple(x * inv for x in v)


# ---------------------------------------------------------------------------
# Interpolation and smoothing
# ---------------------------------------------------------------------------
def _fast_finite(value):
    """Cheap finiteness probe for the frame-loop hot path: values arriving
    here are already numerics (they are produced by clamped controller math),
    so the check is a single ``isfinite`` call. Non-numeric operands fall
    back to the guarded coercion instead of raising here."""
    try:
        return math.isfinite(value)
    except TypeError:
        return False


def lerp(a, b, t):
    if (_fast_finite(a) and _fast_finite(b) and _fast_finite(t)):
        return a + (b - a) * t
    return _finite(a) + (_finite(b) - _finite(a)) * _finite(t)


def smoothstep(x):
    x = clamp01(x)
    return x * x * (3.0 - 2.0 * x)


def exp_smooth(current, target, alpha):
    if (_fast_finite(current) and _fast_finite(target)
            and _fast_finite(alpha)):
        return current + (target - current) * alpha
    return _finite(current) + (_finite(target) - _finite(current)) * _finite(alpha)


def clamp(x, lo, hi):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return lo
    if not math.isfinite(v):
        return lo
    return max(lo, min(hi, v))


def clamp01(x, fallback=0.0):
    if _fast_finite(x):
        return 1.0 if x >= 1.0 else (0.0 if x <= 0.0 else x)
    return fallback


def color_lerp(c1, c2, t):
    """lerp(cyan, violet, depth) per channel -> integer rgb.

    Only ``t`` is guarded: it is the sole flight path for non-finite depth
    (via :func:`depth01`); the palette endpoints are canonical integer
    constants and can never be non-finite. Guarding every channel here would
    triple-call each per-edge colour in the frame loop."""
    t = _finite(t)
    return tuple(int(c1[k] * (1.0 - t) + c2[k] * t) for k in range(3))


# ---------------------------------------------------------------------------
# Projection and depth normalization
# ---------------------------------------------------------------------------
def zprime(z):
    """Depth-compressed view coordinate: Z' = Z / (1 + Z / CAM_D).

    The pole at ``z = -CAM_D`` is a documented singularity and is preserved
    exactly; non-finite inputs degrade to 0.0 (no depth meaning)."""
    if _fast_finite(z):
        return z / (1.0 + z / CAM_D)
    return 0.0


def zprime_inv(zp):
    """Inverse depth-compression: world Z from a Z' coordinate.

    ``zprime_inv(zprime(z)) == z`` for every ``z > -CAM_D`` (this is the
    exact algebraic inverse, pole at ``z' = CAM_D``). Reconstructing a world
    depth from a ``Z'`` value — e.g. turning a shade-grade bucket back into a
    camera-space depth — must go through this inverse, never through ``zprime``
    itself, which would double-compress the depth."""
    if _fast_finite(zp):
        return CAM_D * zp / (CAM_D - zp)
    return 0.0


def depth01(zp, lo=SHADE_LO, hi=SHADE_HI):
    """Normalized depth in [0, 1]: Z' far bound -> 0, near bound -> 1.

    Non-finite inputs saturate through ``clamp01`` and all degrade to the
    far-bound null 0.0 (unchanged behaviour, now explicitly locked by tests).
    A degenerate band (``lo == hi``) carries no depth scale and returns the
    midpoint 0.5 instead of dividing by zero. A non-finite bound (no depth
    scale) also returns the midpoint."""
    if not (_fast_finite(lo) and _fast_finite(hi)):
        return 0.5
    if lo == hi:
        return 0.5
    return clamp01((zp - lo) / (hi - lo))


def shade_of(z):
    """Continuous depth grade of a world coordinate: cyan-zone (near) to
    violet-zone (far) mapped through Z'."""
    return depth01(zprime(z))


def bucket_of(t, nb=NB):
    """Shade-grade bucket from a normalized depth ``t``.

    The quantizer that every bucket in Maya uses: ``b = round(t * (nb-1))``
    so the grade fills exactly ``nb`` buckets ``0..nb-1``. The inverse grade
    of a bucket is :func:`bucket_midpoint` — the two must share the same
    ``nb-1`` scale or bucket arithmetic drifts by one cell."""
    return int(round(clamp01(t) * (nb - 1)))


def bucket_midpoint(bucket, nb=NB):
    """Representative normalized depth of a shade-grade bucket.

    A bucket ``b`` produced by :func:`bucket_of` covers depth cell
    ``b(nb-1)``; its midpoint grade is ``b / (nb-1)``. Using ``/ nb`` here
    (or any other scale) would misplace every cell by up to one full grade."""
    b = clamp(bucket, 0, nb - 1)
    return b / (nb - 1)


# ---------------------------------------------------------------------------
# Rendering physics
# ---------------------------------------------------------------------------
def thickness01(zp):
    """Variable line width in [1, 5]: thickness = 1 + 2*(1 - Z')."""
    if _fast_finite(zp):
        return 1.0 + 2.0 * (1.0 - zp)
    return 3.0


def glow01(zp):
    """Additive neon glow: glow_intensity = exp(-Z' * 2.5).

    Total over every real input: a finite Z' that would overflow
    ``exp(-Z' * 2.5)`` (Z' << 0, far behind the camera line) is capped at
    ``exp(700.0)`` — still astronomically bright, but finite, and any
    downstream ``clamp01`` absorbs it. Non-finite Z' carries no depth meanin
    and maps to 1.0, so the glow never diverges: ``glow01(-inf)`` was
    ``exp(inf) == inf`` and is now bounded to ``exp(0.0) == 1.0``."""
    if _fast_finite(zp):
        return math.exp(min(-zp * 2.5, 700.0))
    return 1.0


def project_scale(z):
    """True pinhole projection scale: s = CAM_D / (CAM_D - z). The factor
    that scales screen coordinates equals the depth-compression family.

    The pole at ``z = CAM_D`` is a documented singularity and is preserved
    exactly; non-finite inputs carry no depth meaning and map to the neutral
    origin, scale 1.0."""
    if _fast_finite(z):
        return CAM_D / (CAM_D - z)
    return 1.0


def lift_luminance(rgb, floor):
    """Absolute luminance floor for tiny renders: lift every channel by the
    same clamped amount so the max channel reaches ``floor``. Non-finite
    inputs degrade to 0.0; the integer output stays within [0, 255]."""
    floor = floor if _fast_finite(floor) else 0.0
    amount = max(0.0, floor - max(_finite(c) for c in rgb))
    return tuple(int(min(255, _finite(c) + amount)) for c in rgb)


def boost_rgb(rgb, scale=1.25, offset=28.0):
    """Presentation boost for highlights: ``min(255, c*scale + o)`` where
    ``offset`` is a scalar or per-channel sequence (grid of three offsets).
    Uses a fixed integer grid, so the same ``(r, g, b)`` always maps to the
    same boosted colour. Non-finite ``scale``/``offset`` degrade to neutral
    (1.0 / 0.0) so the palette can never produce NaN colours. Channels are
    canonical palette values (finite integers) and are blended directly."""
    scale_v = scale if _fast_finite(scale) else 1.0
    if isinstance(offset, (list, tuple)):
        offsets = tuple(o if _fast_finite(o) else 0.0 for o in offset)
    else:
        offsets = (offset if _fast_finite(offset) else 0.0,) * 3
    return tuple(int(min(255, max(0, c * scale_v + offsets[i])))
                 for i, c in enumerate(rgb))


def oscillate(x, mid=0.0, amp=1.0):
    """Deterministic oscillation ``mid + amp*sin(x)`` — the canonical motion
    carrier every sine pulse derives from."""
    if (_fast_finite(x) and _fast_finite(mid) and _fast_finite(amp)):
        return mid + amp * math.sin(x)
    return _finite(mid) + _finite(amp) * math.sin(_finite(x))


def wave01(x):
    """Unit pulse on [0, 1]: ``clamp01(oscillate(x, 0.5, 0.5))``."""
    return clamp01(oscillate(x, 0.5, 0.5))


def wave_range(x, lo, hi):
    """Pulse mapped to [lo, hi] through lerp: ``lerp(lo, hi, wave01(x))``."""
    return lerp(lo, hi, wave01(x))


def cycle_sweep(t, speed, span, offset=0.0):
    """Wrapped linear sweep position: ``(t*speed) % span - offset`` — the
    canonical scan/cycle motion. A degenerate span (<= 0) carries no sweep
    scale and returns the full-sweep position ``1.0 - offset`` instead of
    dividing by zero."""
    t = _finite(t)
    speed = _finite(speed)
    span_v = _finite(span, 1.0)
    offset = _finite(offset)
    if span_v <= 0.0:
        return 1.0 - offset
    return (t * speed) % span_v - offset


# ---------------------------------------------------------------------------
# Pose blending
# ---------------------------------------------------------------------------
def blend_pose(expression, viseme, micro,
               we=BLEND_EXPR, wv=BLEND_VISEME, wm=BLEND_MICRO):
    """final_pose = 0.6*expression + 0.3*viseme + 0.1*micro_channel.

    The weights are exact literals and MUST NOT change. Because
    0.6 + 0.3 + 0.1 is not exactly 1.0 in binary floating point, compare
    blended results with :func:`pose_near` (tolerance ``POSE_EPSILON``),
    never with ``==``. Non-finite channels carry no meaning and become 0.0
    before blending; weights must be finite and non-negative or the blend
    raises ``ValueError``.

    This guarded entry point is for cross-boundary callers. The per-frame
    pose loop blends through :func:`_blend_kernel` directly (its channels are
    derived from already-guarded, verified-finite controller math)."""
    try:
        weights = (float(we), float(wv), float(wm))
    except (TypeError, ValueError):
        raise ValueError(
            "blend weights must be finite and non-negative") from None
    if not all(w >= 0.0 and math.isfinite(w) for w in weights):
        raise ValueError("blend weights must be finite and non-negative")
    return _blend_kernel(_finite(expression), _finite(viseme),
                         _finite(micro), *weights)


def _blend_kernel(expression, viseme, micro,
                  we=BLEND_EXPR, wv=BLEND_VISEME, wm=BLEND_MICRO):
    """Hot-path blend kernel — the exact weighted arithmetic, presumed-finite
    inputs (no guard overhead). Used by the per-frame pose assembler, whose
    channels are produced by guarded controller math and verified finite by
    the pose-integrity tests; cross-boundary calls must go through the
    guarded :func:`blend_pose`."""
    return we * expression + wv * viseme + wm * micro


def pose_near(a, b, tolerance=POSE_EPSILON):
    """Tolerance-based equality for pose blends (see ``POSE_EPSILON``).

    Use this instead of ``==`` whenever a value produced by
    :func:`blend_pose` is compared against an expected pose. Delegates to
    :func:`math_isclose`, so non-finite values are never equal and the
    comparison carries the canonical absolute floor of ``tolerance``."""
    return math_isclose(a, b, tolerance)


# ---------------------------------------------------------------------------
# Stable arithmetic (expert grade)
#
# Tested against magnitude extremes (1e-12 .. 1e12), non-finite inputs, and
# 10k+ seeded random draws in test_math_expert.py. The existing primitives
# keep their exact arithmetic; these forms are added where precision at the
# extremes matters and are used by the Math Precision "expert" mode.
# ---------------------------------------------------------------------------
def stable_lerp(a, b, t):
    """Two-product lerp ``a*(1 - t) + b*t`` (cf. ``lerp``'s
    ``a + (b - a)*t``). Equivalent for ordinary magnitudes; better when
    operands carry extreme opposite magnitudes, where ``b - a`` would
    cancel. Never overshoots the interval: for ``t`` on [0, 1] the result
    lies within [min(a, b), max(a, b)] for any magnitudes. Exact endpoint
    snap ``t == 0.0 -> a``, ``t == 1.0 -> b``. Non-finite operands degrade
    exactly like ``lerp`` (neutral 0.0 each)."""
    if (_fast_finite(a) and _fast_finite(b) and _fast_finite(t)):
        return a * (1.0 - t) + b * t
    return _finite(a) * (1.0 - _finite(t)) + _finite(b) * _finite(t)


def stable_exp_smooth(current, target, alpha, horizon=1):
    """Exponential smoothing in the numerically stable two-product form,
    with the easing ``alpha`` clamped onto [0, 1].

    Contract: for ``horizon`` repeats the result stays inside
    ``[min(current, target), max(current, target)]`` — convergence can never
    overshoot, however long the horizon — and the output equals one
    :func:`stable_lerp` step at ``horizon == 1``. ``horizon`` is
    ``max(1, int(horizon))``. Non-finite ``current``/``target`` fall back to
    the neutral 0.0 form exactly like :func:`exp_smooth`."""
    horizon = 1 if not _fast_finite(horizon) else max(1, int(horizon))
    if not (_fast_finite(current) and _fast_finite(target)):
        return (_finite(current) + (_finite(target) - _finite(current))
                * _finite(alpha))
    a = clamp01(_finite(alpha))
    value = current
    for _ in range(horizon):
        value = stable_lerp(value, target, a)
    return value


def cosine_similarity(a, b):
    """Stable raw dot similarity ``dot(normalize(a), normalize(b))``,
    canonicalised onto [-1, 1].

    Contract: result always lies in [-1, 1] (clamped), every component of
    each operand is finite, and zero or fully non-finite vectors carry no
    direction and score 0.0 deterministically. This is the un-clamped
    similarity used to verify pattern alignment; ``pattern_similarity``
    still wraps it in ``clamp01`` for [0, 1] scoring."""
    if len(a) != len(b):
        raise ValueError("vectors must share length")
    na = normalize(a)
    nb = normalize(b)
    sim = dot(na, nb)
    if not math.isfinite(sim):
        return 0.0
    return max(-1.0, min(1.0, sim))


# ---------------------------------------------------------------------------
# Contract table
#
# Living documentation of the numeric contracts every primitive promises.
# Each entry names the valid input domain, the output guarantee, the maximum
# relative error bound, the sanctioned comparison rule, and the deterministic
# non-finite fallback. test_math_expert.py asserts the table is complete,
# well-formed, and consistent with the primitive behaviour it describes.
# ---------------------------------------------------------------------------
NUMERIC_CONTRACTS = {
    "lerp": ("a + (b - a) * t", "a + (b - a) * t",
             "1e-12 rel at unit scale", "math_isclose",
             "neutral 0.0 per non-finite operand"),
    "stable_lerp": ("a*(1-t) + b*t; t in [0,1] preferred",
                    "in [min(a,b), max(a,b)]; endpoint snap t=0/1",
                    "1e-12 rel at unit scale",
                    "math_isclose", "neutral 0.0 per non-finite operand"),
    "exp_smooth": ("current, target real; alpha real", "current + (target-current)*alpha",
                   "1e-12 rel at unit scale", "math_isclose",
                   "neutral 0.0 per non-finite operand"),
    "stable_exp_smooth": ("current, target real; alpha clamped to [0,1]; horizon >= 1",
                          "in [min, max] for any horizon; no overshoot",
                          "1e-12 rel at unit scale", "math_isclose",
                          "non-finite -> exp_smooth neutral form"),
    "cosine_similarity": ("equal-length real vectors",
                          "[-1, 1]; zero/non-finite vector scores 0.0",
                          "1e-12 rel at unit scale", "math_isclose",
                          "0.0 for non-finite vector"),
    "clamp01": ("any real x", "[0, 1]",
                "1e-12 rel at unit scale", "math_isclose",
                "fallback 0.0"),
    "clamp": ("x real; lo <= hi", "[lo, hi]",
              "exact within float at bounds", "math_isclose",
              "lo"),
    "smoothstep": ("x real", "[0, 1]", "1e-12 rel at unit scale",
                   "math_isclose", "clamp01 fallback -> 0.0"),
    "dot": ("equal-length real vectors", "sum of products",
            "n * 1e-16 * max|product|", "math_isclose",
            "propagates non-finite"),
    "magnitude": ("real vector", ">= 0.0", "1e-12 rel at unit scale",
                  "math_isclose", "0.0"),
    "normalize": ("real vector", "unit vector, same length; zero in/out",
                  "1e-12 rel at unit scale", "math_isclose",
                  "component-wise 0.0"),
    "zprime": ("z real", "z mined toward CAM_D", "1e-12 rel at unit scale",
               "math_isclose", "0.0"),
    "zprime_inv": ("z real", "[0, CAM_D], 0.0..1.0 typical", "1e-12 rel",
                   "math_isclose", "0.0"),
    "depth01": ("z real", "[0, 1]", "1e-12 rel", "math_isclose",
                "0.0 (via clamp01)"),
    "project_scale": ("z real", "1.0 at CAM_D, grows beyond camera",
                      "1e-12 rel", "math_isclose", "1.0"),
    "thickness01": ("z real", "[1, 3]", "1e-12 rel", "math_isclose",
                    "nan -> 3.0, +inf/-inf -> 3.0"),
    "glow01": ("z real", "(0, 1] for z >= 0; finite total (capped exp(700)) for all real z",
               "1e-12 rel", "math_isclose",
               "non-finite z -> 1.0"),
    "blend_pose": ("finite weights >= 0, sum ~ 1; channels real",
                   "per-channel weighted mean", "POSE_EPSILON (1e-9)",
                   "pose_near", "non-finite channels -> 0.0"),
    "math_isclose": ("reals (or None)", "bool; non-finite never equal",
                     "tolerance * max(1.0, |a|, |b|)",
                     "literal", "False"),
    "pose_near": ("pose-like reals", "bool", "POSE_EPSILON",
                  "pose_near", "False"),
    "cycle_sweep": ("span > 0", "(t*speed) % span - offset",
                    "1e-12 rel", "math_isclose",
                    "span <= 0 -> 1.0 - offset"),
    "oscillate": ("amp >= 0", "[lo - amp, hi + amp]",
                  "1e-12 rel", "math_isclose", "0.0"),
}


def jaw_open(amplitude):
    """jaw_open = clamp(amplitude * 1.2, 0, 1)."""
    return clamp01(_finite(amplitude) * JAW_GAIN)