"""Safety locks: surfaces that Maya may never modify without an explicit
architect instruction. A lock read is always allowed; a modification only
when the architect instruction is present and non-empty.
"""
from __future__ import annotations

LOCKED_SURFACES = ("math", "personas", "identity", "world_model")


class SafetyLocks:
    """Read-only verification gate for architect-driven evolution."""

    def verify_modify(self, surface, architect_instruction=None, change=None):
        if surface not in LOCKED_SURFACES:
            raise ValueError("unknown locked surface %r" % surface)
        if architect_instruction is None or \
                str(architect_instruction).strip() == "":
            return {
                "surface": surface,
                "allowed": False,
                "reason": "architect_instruction_required",
                "change": change,
            }
        return {
            "surface": surface,
            "allowed": True,
            "reason": None,
            "change": change,
        }

    def check(self, surface):
        if surface in LOCKED_SURFACES:
            return {"locked": True, "surface": surface}
        return {"locked": False, "surface": surface}


SAFETY_LOCKS = SafetyLocks()