"""shape_math — deterministic projection of a VisualState into a temporary
geometric embodiment.

Batch 8C temporary shape: a clean abstract core (round orb) with an orbit ring
and a gaze pointer. It is visually and architecturally separate from Maya's
canonical face; it exists only to make the semantic pipeline visibly move.

    VisualState -> ProjectedShape(frame) -> renderer primitives

Everything here is a pure function of ``(VisualState, frame)``:

    same state + same frame  =>  same numbers  (exact replay)

No randomness, no wall clock. ``frame`` is an explicit integer input (the UI
tick counter); tests pass explicit frames.

Mapping (every motion has a semantic source, every output is bounded):

- ``attention``      -> attitude roll (orientation) and gaze-travel gain.
- ``focus``          -> stabilization: higher focus shrinks the slow lateral
                        drift amplitude to a floor.
- ``curiosity``      -> bounded lateral sweep + orbit-ring phase offset.
- ``activity``       -> bounded scale lift + gentle bob; drives ring size.
- ``gaze_dx/dy``     -> target position offset (bounded travel); pointer when
                        non-zero gaze.
- ``rest``           -> exactly the resting scale, centered, no pulse, ring
                        contracted, pointer hidden.

All amplitudes are hard bounds: clamp() keeps every output inside its domain.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Bounds (these ARE the contract; tests + oracle mirror them).
# ---------------------------------------------------------------------------

SCALE_MIN = 0.72          # resting / dormant scale (fraction of BASE_RADIUS)
SCALE_MAX = 1.00          # activity ceiling scale
BASE_RADIUS = 0.16        # unit-space radius at scale == 1.0 (of size side)
TRAVEL_MAX = 0.16         # max gaze position travel (unit space)
TRAVEL_Y_GAIN = 0.60      # vertical travel is gentler than horizontal
ATTENTION_TRAVEL_GAIN = 1.0   # attention gates travel: pos = travel * attention
CURIOUS_SWEEP = 0.05      # curiosity lateral sweep amplitude (unit space)
LATERAL_DRIFT = 0.035     # unfocused drift amplitude (unit space)
STABILIZE_FLOOR = 0.25    # drift amplitude floor at full focus
BOB = 0.020               # activity bob amplitude (unit space)
ROLL_MAX_DEG = 24.0       # max attitude roll from attention (degrees)
PULSE_AMP = 0.06          # activity pulse amplitude (fraction of scale lift)
PULSE_RATE = 0.10         # radians per frame at activity pulse
SWEEP_RATE = 0.02         # curiosity sweep radians per frame
DRIFT_RATE = 0.009        # unfocused drift radians per frame
BOB_RATE = 0.030          # activity bob radians per frame
RING_BASE = (0.30, 0.10)  # orbit ring radii at scale  1 (rx, ry)
RING_ACTIVITY_GAIN = 0.4  # how much activity grows the ring
RING_SPIN_RATE = 2.0 * math.pi / 120.0   # orbital revolution per frame
RING_PHASE_CURIOUS = math.pi / 2.0       # curiosity rotates ring phase
POINTER_MAX = 0.10        # max pointer length (unit space)


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _unit(degrees):
    return degrees * math.pi / 180.0


def _round9(value):
    return round(float(value), 9)


@dataclass(frozen=True)
class ProjectedShape:
    """Bounded, deterministic projection for the renderer (unit space)."""

    cx: float
    cy: float
    radius: float          # orb radius (fraction of size)
    roll_deg: float        # attitude roll (degrees)
    ring_rx: float
    ring_ry: float
    ring_phase: float      # orbit phase (radians)
    resting: bool
    pointer_dx: float
    pointer_dy: float
    pointer_len: float

    def signature(self) -> str:
        import hashlib

        payload = "|".join("%.9f" % v for v in (
            self.cx, self.cy, self.radius, self.roll_deg,
            self.ring_rx, self.ring_ry, self.ring_phase,
            self.pointer_dx, self.pointer_dy, self.pointer_len,
        )) + ("|rest" if self.resting else "|live")
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict_safe(self) -> dict:
        return {
            "cx": self.cx, "cy": self.cy, "radius": self.radius,
            "roll_deg": self.roll_deg, "ring_rx": self.ring_rx,
            "ring_ry": self.ring_ry, "ring_phase": self.ring_phase,
            "resting": self.resting, "pointer_dx": self.pointer_dx,
            "pointer_dy": self.pointer_dy, "pointer_len": self.pointer_len,
        }


def _pointer_from_gaze(dx: float, dy: float):
    """Unit direction and magnitude from rig gaze; zero gaze hides it."""
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return 0.0, 0.0, 0.0
    return dx / length, dy / length, min(1.0, length)


def project(vs, frame: int) -> ProjectedShape:
    """Project a VisualState at an explicit frame index into unit-space
    embodiment parameters. Pure, bounded, deterministic."""
    frame = int(frame)
    attention = vs.attention
    focus = vs.focus
    curiosity = vs.curiosity
    activity = vs.activity

    if vs.rest:
        scale = SCALE_MIN
        ring_phase = (frame * RING_SPIN_RATE) % (2.0 * math.pi)
        return ProjectedShape(
            cx=0.5, cy=0.5, radius=BASE_RADIUS * SCALE_MIN, roll_deg=0.0,
            ring_rx=RING_BASE[0], ring_ry=RING_BASE[1],
            ring_phase=ring_phase, resting=True,
            pointer_dx=0.0, pointer_dy=0.0, pointer_len=0.0,
        )

    # --- scale: activity lifts the orb; a deterministic pulse is gated by
    #     activity, so a resting (but non-dormant) state still pulses softly.
    pulse = math.sin(frame * PULSE_RATE) * PULSE_AMP * activity
    scale = SCALE_MIN + (SCALE_MAX - SCALE_MIN) * activity
    scale = _clamp(scale, SCALE_MIN, SCALE_MAX)
    scale = _clamp(scale + pulse, SCALE_MIN, SCALE_MAX)

    # --- position: gaze travel gated by attention; curiosity sweeps; low
    #     focus drifts. focus stabilizes the drift down to a floor.
    drift_amp = LATERAL_DRIFT * (STABILIZE_FLOOR + (1.0 - STABILIZE_FLOOR) * (1.0 - focus))
    target_x = vs.gaze_dx * TRAVEL_MAX * ATTENTION_TRAVEL_GAIN * attention
    target_y = vs.gaze_dy * TRAVEL_MAX * TRAVEL_Y_GAIN * attention
    wander_x = (math.sin(frame * SWEEP_RATE) * CURIOUS_SWEEP * curiosity
                + math.sin(frame * DRIFT_RATE) * drift_amp)
    bob_y = math.cos(frame * BOB_RATE) * BOB * activity
    cx = _clamp(0.5 + target_x + wander_x, 0.25, 0.75)
    cy = _clamp(0.5 + target_y + bob_y, 0.28, 0.72)

    # --- attitude: attention raises the roll.
    roll_deg = attention * ROLL_MAX_DEG

    # --- orbit ring: activity grows it; curiosity shifts the phase.
    ring_gain = RING_ACTIVITY_GAIN
    ring_rx = RING_BASE[0] * (1.0 - ring_gain + ring_gain * activity)
    ring_ry = RING_BASE[1] * (1.0 - ring_gain + ring_gain * activity)
    ring_phase = (frame * RING_SPIN_RATE + curiosity * RING_PHASE_CURIOUS) \
        % (2.0 * math.pi)

    ux, uy, pulled = _pointer_from_gaze(vs.gaze_dx, vs.gaze_dy)
    plen = _clamp(pulled * POINTER_MAX, 0.0, POINTER_MAX)

    return ProjectedShape(
        cx=_round9(cx), cy=_round9(cy),
        radius=_round9(scale * BASE_RADIUS),
        roll_deg=_round9(roll_deg),
        ring_rx=_round9(ring_rx), ring_ry=_round9(ring_ry),
        ring_phase=_round9(ring_phase),
        resting=False,
        pointer_dx=_round9(ux), pointer_dy=_round9(uy),
        pointer_len=_round9(plen),
    )


def motion_signature(vs, frames) -> str:
    """Deterministic signature over a frame window (replay corpus)."""
    import hashlib

    parts = [vs.signature()]
    for frame in frames:
        parts.append(project(vs, frame).signature())
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Headless raster (pure): a deterministic RGB buffer + digest. Used by the
# parity and sabotage drills; the Tk renderer draws the same projection.
# ---------------------------------------------------------------------------

def render_raster(vs, frame: int, size: int = 192):
    """Deterministic RGB bytearray of the orb + ring + pointer.

    Uses only integer arithmetic and the identity distance test, so the bytes
    are identical on every interpreter. Returns (bytes, sha256_hex).
    """
    import hashlib

    size = max(8, int(size))
    p = project(vs, frame)
    cx = p.cx * size
    cy = p.cy * size
    radius = p.radius * size
    buf = bytearray(size * size * 3)
    for y in range(size):
        row = y * size * 3
        for x in range(size):
            # orb fill test (distance <= radius)
            dx = x + 0.5 - cx
            dy = y + 0.5 - cy
            in_orb = dx * dx + dy * dy <= radius * radius
            if in_orb:
                r, g, b = 88, 132, 216   # core blue
            else:
                # orbit ring: near ellipse with radius band, phase-swept
                rx = p.ring_rx * size
                ry = p.ring_ry * size
                ex = (x + 0.5 - cx) / max(1.0, rx)
                ey = (y + 0.5 - cy) / max(1.0, ry)
                d = math.hypot(ex, ey)
                near = abs(d - 1.0) < 0.05
                # pointer segment (unit direction, length pulled)
                if p.pointer_len > 0:
                    tl = p.pointer_len * size
                    tipx = cx + p.pointer_dx * tl
                    tipy = cy + p.pointer_dy * tl
                    px_ = x + 0.5 - tipx
                    py_ = y + 0.5 - tipy
                    along = (px_ * -p.pointer_dx) + (py_ * -p.pointer_dy)
                    perp = abs(px_ * -p.pointer_dy - py_ * p.pointer_dx)
                    on_ptr = 0.0 <= along <= tl and perp <= max(1.0, tl * 0.045)
                else:
                    on_ptr = False
                if near:
                    r, g, b = 216, 180, 108   # ring amber
                elif on_ptr:
                    r, g, b = 190, 220, 160   # pointer mint
                else:
                    r, g, b = 16, 18, 26      # background
            buf[row + x * 3] = r
            buf[row + x * 3 + 1] = g
            buf[row + x * 3 + 2] = b
    return bytes(buf), hashlib.sha256(bytes(buf)).hexdigest()