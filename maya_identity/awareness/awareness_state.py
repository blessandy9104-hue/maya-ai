"""Environment awareness interface.

Receives only safe read-only signals (user attention, app state, active tasks,
interaction timing). It never reads private files, passwords, permissions,
security state, or memory, and it never writes anywhere.
"""
from __future__ import annotations

from ..identity import load_engine_config
from ..wireframe import presentation_math as PresentationMath

_SENSITIVE_MARKERS = (
    "password", "passwd", "secret", "token", "key", "credential",
    "permission", "permissions", "security", "priv", "private", "memory",
)


class AwarenessState:
    def __init__(self, cfg=None):
        self.cfg = cfg if cfg is not None else load_engine_config("awareness")
        self._state = {}

    def _allowlist(self):
        return set(self.cfg.get("signal_allowlist", []) or [])

    def guard(self, name: str):
        """Return (allowed, reason). Rejects sensitive or non-allowlisted names."""
        text = str(name).lower()
        if any(marker in text for marker in _SENSITIVE_MARKERS):
            return False, "sensitive: refused (privacy guard)"
        if text in self._allowlist():
            return True, "ok"
        return False, "not in signal allowlist"

    def update(self, fields: dict) -> dict:
        accepted = {}
        for name, value in (fields or {}).items():
            allowed, reason = self.guard(name)
            if allowed:
                bounded = PresentationMath.clip(value, on_error=None)
                if bounded is not None:
                    accepted[name] = bounded
                    self._state[name] = bounded
            else:
                accepted[name] = None
        return accepted

    def signal(self, name: str, value) -> dict:
        allowed, reason = self.guard(name)
        if not allowed:
            return {"accepted": False, "name": str(name), "reason": reason}
        bounded = PresentationMath.clip(value, on_error=None)
        if bounded is None:
            return {"accepted": False, "name": str(name), "reason": "non-numeric"}
        self._state[str(name)] = bounded
        return {"accepted": True, "name": str(name), "reason": "ok"}

    def snapshot(self) -> dict:
        return dict(self._state)

    def contribution(self) -> dict:
        """Read-only environmental contribution to presence (bounded)."""
        state = self._state
        att = state.get("user_attention")
        timing = state.get("interaction_timing")
        return {
            "attention": PresentationMath.clip(att, on_error=None) if att is not None else None,
            "interaction_timing": PresentationMath.clip(timing, on_error=None) if timing is not None else None,
        }


if __name__ == "__main__":
    aw = AwarenessState()
    print(aw.update({"user_attention": 0.7, "active_tasks": 2, "password": "x"}))
    print(aw.snapshot())