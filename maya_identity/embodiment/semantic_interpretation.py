"""SemanticCue — bounded, deterministic projection of Maya's cognitive frame.

Batch 8D: the pathway that carries Maya's genuine semantic / intelligence state
(the intelligence-bridge cognitive frame produced each conversational turn) into
the existing bounded ``VisualState``:

    Maya understanding
        -> semantic/internal state (bridge cognitive frame)
        -> adapt_semantic()             (this module; pure)
        -> SemanticCue                  (bounded, deterministic)
        -> build_visual_state(..., semantic=SemanticCue)
        -> VisualState
        -> shape_math.project(...)      (Batch 8C, unchanged)
        -> TemporaryShapeRenderer       (Batch 8C, unchanged)

Principles (Batch 8D):

- Real signal only: every field maps from the bridge's cognitive frame or the
  intent classifier. No invented cognition, no wall clock, no random source, no
  hidden mutable state. The adapter output is a pure function of its two dict
  inputs: identical (cognitive, intent) always produce an identical SemanticCue.
- Bounded: numeric fields live in ``DOMAIN``; anything out of range clamps to the
  nearest bound (a misconfigured upstream can push a value to the ceiling, never
  past it).
- Explicit invalid-input behavior: ``None`` / unknown / malformed fields reduce
  to the documented neutral defaults (ok flags ``False``, flags ``False``), so
  the safe behavior for an absent or garbled reading is *no cognitive lift* —
  byte-identical to the pre-Batch-8D VisualState.
- Rendering independent: nothing here imports a renderer; channel meaning is
  decided by ``VisualState`` consumers downstream.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Authoritative bounds (these ARE the contract; tests mirror them).
# ---------------------------------------------------------------------------

DOMAIN = {
    "confidence": (0.0, 1.0),
    "stability": (0.0, 1.0),
    "meaning": (0.0, 1.0),
}

# Gain constants of the semantic-to-visual mapping (clean-room oracle mirrors
# these formulas independently from the constants alone).
FOCUS_SEMANTIC_GAIN = 0.25   # focus lift bounded per unit confidence
FOCUS_CEILING = 0.95         # hard cap on focus when cognitive lift is active
ACTIVITY_SEMANTIC_GAIN = 0.30  # activity lift bounded per unit meaning

# Machine line used by the GUI channel (single-line JSON, digest-verified).
LINE_PREFIX = "[semantic] "
TAG = "semantic_visual_v1"

DEFAULT_REGISTER = "measured"


def _float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _round12(value):
    return round(float(value), 12)


def _flag(value, default=False):
    """Boolean fields accept only real bools; anything else is the safe 'off'."""
    return value if isinstance(value, bool) else default


def _text(value, default=DEFAULT_REGISTER):
    if isinstance(value, str) and value:
        return value
    return default


@dataclass(frozen=True)
class SemanticCue:
    """Bounded projection of one cognitive frame (immutable, digest-stable).

    Provenance (semantic state -> source -> transformation -> visual channel):

    ``confidence``
      bridge cognitive["confidence"] ([0,1], fused alignment + stability +
      evidence). -> ``VisualState.focus``. Lift =
      confidence * FOCUS_SEMANTIC_GAIN, suppressed when the intent classifier
      flags the turn ambiguous.
    ``meaning``
      bridge cognitive["meaning_scalar"] ([0,1], fused meaning). ->
      ``VisualState.activity`` (engaged work). Lift =
      meaning * ACTIVITY_SEMANTIC_GAIN, gated by meaning_ok and stability_ok,
      and suppressed when restricted is true (reserved/held reading).
    ``restricted``
      bridge cognitive["restricted"] (bool). Gates the ACTIVITY lift off.
    ``ambiguous``
      intent["ambiguous"] (bool, intent classifier). Gates the FOCUS lift off.
    ``meaning_ok`` / ``stability_ok``
      bridge cognitive["meaning_ok"] / ["stability_ok"] (bools). Gate the
      ACTIVITY lift.
    ``stability``
      bridge cognitive["stability"]. Carried for provenance and digest; NOT
      mapped to a visual channel (documented unmapped).
    ``register``
      bridge cognitive["register"]. Carried for provenance and digest; NOT
      mapped to a visual channel (documented unmapped).

    The mapping deliberately never touches attention / curiosity / gaze_dx /
    gaze_dy / rest: those channels keep their Batch 8C provenance (semantic
    control, the validated ``curious`` anchor, rig gaze, rest anchors).
    """

    confidence: float = 0.0
    stability: float = 0.0
    meaning: float = 0.0
    restricted: bool = False
    ambiguous: bool = False
    meaning_ok: bool = False
    stability_ok: bool = False
    register: str = DEFAULT_REGISTER

    def signature(self) -> str:
        """Cross-interpreter stable sha256 over the bounded fields."""
        payload = "|".join([
            "%.12f" % float(self.confidence),
            "%.12f" % float(self.stability),
            "%.12f" % float(self.meaning),
            "1" if self.restricted else "0",
            "1" if self.ambiguous else "0",
            "1" if self.meaning_ok else "0",
            "1" if self.stability_ok else "0",
            str(self.register),
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict:
        return {
            "adapt": TAG,
            "confidence": self.confidence,
            "stability": self.stability,
            "meaning": self.meaning,
            "restricted": self.restricted,
            "ambiguous": self.ambiguous,
            "meaning_ok": self.meaning_ok,
            "stability_ok": self.stability_ok,
            "register": self.register,
            "digest": self.signature(),
        }


def adapt_semantic(cognitive, intent=None) -> SemanticCue:
    """Project the bridge cognitive frame (optionally with intent cues).

    Pure. ``cognitive=None`` or any non-dict reduces to a fully neutral cue
    (encoded as ``SemanticCue()``) — the documented safe behavior for an absent
    reading. Missing / malformed individual fields also default to neutral
    values, so no malformed input can elevate a visual channel.
    """
    if not isinstance(cognitive, dict):
        return SemanticCue()

    confidence = _round12(_clamp(
        _float(cognitive.get("confidence")), *DOMAIN["confidence"]))
    stability = _round12(_clamp(
        _float(cognitive.get("stability")), *DOMAIN["stability"]))
    meaning = _round12(_clamp(
        _float(cognitive.get("meaning_scalar")), *DOMAIN["meaning"]))

    restricted = _flag(cognitive.get("restricted"))
    meaning_ok = _flag(cognitive.get("meaning_ok"))
    stability_ok = _flag(cognitive.get("stability_ok"))
    register = _text(cognitive.get("register"))

    ambiguous = False
    if isinstance(intent, dict):
        ambiguous = _flag(intent.get("ambiguous"))

    return SemanticCue(
        confidence=confidence,
        stability=stability,
        meaning=meaning,
        restricted=restricted,
        ambiguous=ambiguous,
        meaning_ok=meaning_ok,
        stability_ok=stability_ok,
        register=register[:64],
    )


def to_line(cue: SemanticCue) -> str:
    """One deterministic, digest-carrying machine line (for the GUI channel)."""
    return LINE_PREFIX + json.dumps(
        cue.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def from_line(text: str):
    """Parse + digest-verify a machine line back into a SemanticCue.

    Returns ``None`` when the line is not ours, malformed, or fails the digest
    check (the GUI must never trust an unverified payload).
    """
    if not isinstance(text, str) or not text.startswith(LINE_PREFIX):
        return None
    try:
        data = json.loads(text[len(LINE_PREFIX):].strip())
    except (ValueError, TypeError):
        return None
    return from_dict(data)


def from_dict(data) -> SemanticCue | None:
    """Digest-verified decode of a cue dict (safe for the GUI channel)."""
    if not isinstance(data, dict) or data.get("adapt") != TAG:
        return None
    cue = SemanticCue(
        confidence=_round12(_clamp(
            _float(data.get("confidence")), *DOMAIN["confidence"])),
        stability=_round12(_clamp(
            _float(data.get("stability")), *DOMAIN["stability"])),
        meaning=_round12(_clamp(
            _float(data.get("meaning")), *DOMAIN["meaning"])),
        restricted=bool(data.get("restricted", False)),
        ambiguous=bool(data.get("ambiguous", False)),
        meaning_ok=bool(data.get("meaning_ok", False)),
        stability_ok=bool(data.get("stability_ok", False)),
        register=str(data.get("register") or DEFAULT_REGISTER)[:64],
    )
    if cue.signature() != str(data.get("digest") or ""):
        return None
    return cue