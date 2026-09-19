"""Visual bridge: FusedPersonaState -> face signals -> expression controls.

Pure, deterministic, offline. Maps the consensus priority lens onto the canonical
expression-control vocabulary (``expression_controller``) that the face rig
understands, and onto the interpreter input keys the presence engine consumes.

Contract:
- ``NO_ACTIVE_PERSONA`` -> inactive bridge, empty signals (no silent default).
- ``UNRESOLVED_CONFLICT`` / ``INCOMPATIBLE`` -> inactive bridge (do not
  anonymously reinterpret a contested consensus).
- Otherwise each recognised consensus dimension maps to ONE control, clamped
  to ``[0, 1]`` and capped at the control's canonical channel ceiling
  (``math_coordinator.CONTROL_CHANNELS`` / ``CHANNEL_MAX``).

The bridge does not invent dimensions: unknown priority keys are skipped.
"""
from __future__ import annotations

from maya_identity.wireframe.math_coordinator import CHANNEL_MAX, CONTROL_CHANNELS

# Consensus priority dimensions -> single deterministic face control.
PRIORITY_TO_CONTROL = {
    "precision": "confidence",
    "clarity": "confidence",
    "conservatism": "calm",
    "composure": "calm",
    "interpretation": "thinking",
    "elaboration": "thinking",
    "inquisitiveness": "thinking",
    "curiosity": "attention",
    "alertness": "attention",
    "vigilance": "attention",
    "empathy": "smile",
    "warmth": "smile",
    "uncertainty": "uncertainty",
}

# Dimensions that may appear in the consensus for provenance only.
_KNOWN_UNMAPPED = {"fairness", "honesty", "formality", "creativity", "deliberation"}

_BLOCKING_CONFLICTS = frozenset({"UNRESOLVED_CONFLICT", "INCOMPATIBLE"})


def bridge_gate(fused: dict) -> dict:
    """Active only for a FUSED, non-blocking consensus."""
    status = fused.get("status")
    if status != "FUSED":
        return {"active": False, "reason": "NO_ACTIVE_PERSONA", "status": status}
    conflict_status = fused.get("conflict_status") or "NO_CONFLICT"
    if conflict_status in _BLOCKING_CONFLICTS:
        return {"active": False, "reason": conflict_status, "status": status}
    return {"active": True, "reason": conflict_status, "status": status}


def _cap_for_control(control: str) -> float:
    channel = CONTROL_CHANNELS.get(control, "expression")
    return CHANNEL_MAX.get(channel, 0.5)


def persona_signals(fused: dict) -> dict:
    """Face-control signals from the consensus (empty when inactive)."""
    gate = bridge_gate(fused)
    signals: dict = {}
    mapped: dict = {}
    if gate["active"]:
        consensus = fused.get("consensus") or {}
        for dimension in sorted(consensus):
            control = PRIORITY_TO_CONTROL.get(dimension)
            if control is None:
                continue
            raw = float(consensus[dimension])
            value = max(0.0, min(1.0, raw))
            cap = _cap_for_control(control)
            signals[control] = round(min(value, cap), 9)
            mapped[dimension] = signals[control]
    return {
        "source": "visual_bridge",
        "active": gate["active"],
        "reason": gate["reason"],
        "status": gate["status"],
        "signals": signals,
        "mapped_dimensions": mapped,
        "unmapped_dimensions": sorted(
            set((fused.get("consensus") or {}).keys()) - set(mapped) - _KNOWN_UNMAPPED
        ),
    }


def fused_to_controls(fused: dict) -> dict:
    """Direct ExpressionController-ready control overrides for the face rig."""
    bridged = persona_signals(fused)
    meta = {
        "source": bridged["source"],
        "active": bridged["active"],
        "reason": bridged["reason"],
        "persona_ids": list(fused.get("active_personas") or []),
    }
    if not bridged["active"]:
        meta["controls"] = {}
        meta["engagement_note"] = (
            "identity-locked neutral expression; persona not audited"
        )
    return meta


INTERPRETER_KEYS = frozenset(
    {
        "attention",
        "focus",
        "curiosity",
        "cognitive_load",
        "activity_pressure",
        "search_depth",
        "novelty",
        "engagement",
        "confidence",
        "memory_retrieval",
        "strain",
        "stimulation",
    }
)


def merged_interpreter_inputs(base_inputs: dict, fused: dict) -> dict:
    """Overlay mapped consensus signals onto the interpreter input keys.

    Only keys the VisualInterpreter recognises are surfaced; the caller owns the
    base input dict (blended, never mutated in place).
    """
    out = dict(base_inputs or {})
    bridged = persona_signals(fused)
    if not bridged["active"]:
        return out
    for control, value in bridged["signals"].items():
        if control in INTERPRETER_KEYS:
            precedent = float(out.get(control, 0.0))
            out[control] = round(min(max(precedent, value), 1.0), 9)
    return out