"""Post-turn state update (Batch 8G)."""
from __future__ import annotations

from .state import ConversationState, MODES

_DOMAIN_MODE = {
    "psychology": "analytical",
    "philosophy": "philosophical",
    "planning": "planning",
    "mathematics": "analytical",
    "evidence": "analytical",
}


def apply_turn(state, interpretation, response_plan=None):
    """Fold one interpreted + planned turn into a *new* state.

    Deterministic. Never mutates the input state. ``response_plan`` may be
    None (callers that did not route still get the interpretation folded).
    """
    state = state if isinstance(state, ConversationState) else \
        ConversationState(session_id=getattr(state, "session_id", "session1")
                          if state is not None else "session1")
    result = state.apply_interpretation(interpretation)
    if response_plan and isinstance(response_plan, dict):
        result = result.set_response_objective(
            response_plan.get("objective", "answer"))
        domains = response_plan.get("domains") or []
        for domain in domains:
            mode = _DOMAIN_MODE.get(domain)
            if mode:
                result = result.set_mode(mode)
                break
    return result