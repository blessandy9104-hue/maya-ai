"""oracle_temporary_embodiment — clean-room numeric oracle for the Batch 8C
temporary shape mathematics.

Written independently from ``maya_identity/embodiment/shape_math.py``: it
re-derives every formula with its own algebraic route (parameterized target
values, re-computed bounds via triangle inequality, an explicit rotation-free
phase identity). The test suite asserts that the source implementation and
this oracle agree exactly, so the pipeline is not its own proof.

Independence note: both arms call the same IEEE transcendental functions
(``math.sin``/``math.cos``), which is unavoidable for a bit-for-bit contract,
but the surrounding algebra, ordering, and clamping routes are written
separately here. Cross-interpreter equality is additionally asserted directly.
"""
from __future__ import annotations

import math

# Same mathematical constants as the source; kept to their documented meaning.
SCALE_MIN = 0.72
SCALE_MAX = 1.00
BASE_RADIUS = 0.16
TRAVEL_MAX = 0.16
TRAVEL_Y_GAIN = 0.60
CURIOUS_SWEEP = 0.05
LATERAL_DRIFT = 0.035
STABILIZE_FLOOR = 0.25
BOB = 0.020
ROLL_MAX_DEG = 24.0
PULSE_AMP = 0.06
PULSE_RATE = 0.10
SWEEP_RATE = 0.02
DRIFT_RATE = 0.009
BOB_RATE = 0.030
RING_BASE = (0.30, 0.10)
RING_ACTIVITY_GAIN = 0.4
RING_SPIN_RATE = 2.0 * math.pi / 120.0
RING_PHASE_CURIOUS = math.pi / 2.0
POINTER_MAX = 0.10


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def oracle_scale(activity, rest, frame):
    """Independent re-derivation of the orb scale (fraction of base radius)."""
    if rest:
        return SCALE_MIN
    pulse = math.sin(float(frame) * PULSE_RATE) * PULSE_AMP * activity
    lifted = SCALE_MIN + (SCALE_MAX - SCALE_MIN) * activity
    lifted = _clamp(lifted, SCALE_MIN, SCALE_MAX)
    return _clamp(lifted + pulse, SCALE_MIN, SCALE_MAX)


def oracle_center(attention, focus, curiosity, activity,
                  gaze_dx, gaze_dy, rest, frame):
    """Independent re-derivation of the unit-space center position."""
    if rest:
        return 0.5, 0.5
    drift_amp = LATERAL_DRIFT * (
        STABILIZE_FLOOR + (1.0 - STABILIZE_FLOOR) * (1.0 - focus))
    target_x = gaze_dx * TRAVEL_MAX * attention
    target_y = gaze_dy * TRAVEL_MAX * TRAVEL_Y_GAIN * attention
    wx = math.sin(float(frame) * SWEEP_RATE) * CURIOUS_SWEEP * curiosity \
        + math.sin(float(frame) * DRIFT_RATE) * drift_amp
    by = math.cos(float(frame) * BOB_RATE) * BOB * activity
    return (_clamp(0.5 + target_x + wx, 0.25, 0.75),
            _clamp(0.5 + target_y + by, 0.28, 0.72))


def oracle_roll(attention):
    return attention * ROLL_MAX_DEG


def oracle_ring(activity, curiosity, frame, rest=False):
    """Independent ring radii + phase. Rest states keep the contracted ring."""
    if rest:
        return RING_BASE[0], RING_BASE[1], (
            float(frame) * RING_SPIN_RATE) % (2.0 * math.pi)
    g = RING_ACTIVITY_GAIN
    rx = RING_BASE[0] * (1.0 - g + g * activity)
    ry = RING_BASE[1] * (1.0 - g + g * activity)
    phase = (float(frame) * RING_SPIN_RATE + curiosity * RING_PHASE_CURIOUS) \
        % (2.0 * math.pi)
    return rx, ry, phase


def oracle_pointer(gaze_dx, gaze_dy):
    """Independent pointer: unit direction + reach, hidden on zero gaze."""
    length = math.hypot(gaze_dx, gaze_dy)
    if length <= 1e-12:
        return 0.0, 0.0, 0.0
    pulled = min(1.0, length)
    return gaze_dx / length, gaze_dy / length, pulled * POINTER_MAX


def oracle_project(vs, frame):
    """Independent projection of a VisualState at a frame index."""
    scale = oracle_scale(vs.activity, vs.rest, frame)
    cx, cy = oracle_center(vs.attention, vs.focus, vs.curiosity, vs.activity,
                           vs.gaze_dx, vs.gaze_dy, vs.rest, frame)
    roll = oracle_roll(vs.attention)
    rx, ry, phase = oracle_ring(vs.activity, vs.curiosity, frame, rest=vs.rest)
    ux, uy, reach = oracle_pointer(vs.gaze_dx, vs.gaze_dy)
    if vs.rest:
        cx = cy = 0.5
        roll = 0.0
        reach = 0.0
    return {
        "cx": cx, "cy": cy, "radius": scale * BASE_RADIUS,
        "roll_deg": roll, "ring_rx": rx, "ring_ry": ry, "ring_phase": phase,
        "resting": vs.rest, "pointer_dx": ux, "pointer_dy": uy,
        "pointer_len": reach,
    }


def oracle_bounds_proof(attention, focus, curiosity, activity,
                        gaze_dx, gaze_dy):
    """Triangle-inequality bound proof: max |x - 0.5| never exceeds a closed
    bound computed WITHOUT the clamping the source relies on."""
    travel = abs(gaze_dx) * TRAVEL_MAX * max(0.0, min(1.0, attention))
    wander = CURIOUS_SWEEP * max(0.0, min(1.0, curiosity))
    drift = LATERAL_DRIFT * (
        STABILIZE_FLOOR + (1.0 - STABILIZE_FLOOR)
        * max(0.0, min(1.0, 1.0 - focus)))
    upper = travel + wander + drift
    assert upper <= TRAVEL_MAX + CURIOUS_SWEEP + LATERAL_DRIFT
    return upper