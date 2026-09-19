"""Deterministic conversational-state model (Batch 8G).

A ``ConversationState`` is a pure in-memory representation of the current
conversation: session identity, turn boundary, topic stack, mode, the last
user intent, unresolved questions, corrections already applied, user-provided
constraints, modality, and the response objective of the previous turn.

Design rules:

- No wall clock, no randomness. Temporal fields are set by the caller (or
  ``None``); the state module itself never reads a clock.
- Transitions are deterministic functions of their arguments.
- Inference is never promoted here: the state records what was interpreted,
  not what is true.
- Single source of truth for the verb-noun turn object: everything is a dict
  of primitives so it can be diffed, logged, and cross-interpreter identical.

The state is intentionally small and typed. It does NOT duplicate the
``maya_runtime`` intelligence bus; it is the *conversational* layer that the
bus and the intelligence core do not provide.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Canonical conversational modes (Batch 8G directive section 5).
MODES = {
    "informational",
    "exploratory",
    "analytical",
    "philosophical",
    "reflective",
    "planning",
    "debugging",
    "instructional",
    "argumentative",
    "creative",
    "correction_clarification",
}

DEFAULT_MODE = "informational"

# Canonical response objectives (Batch 8G directive section 19).
RESPONSE_OBJECTIVES = {
    "answer",
    "explain",
    "compare",
    "clarify",
    "correct",
    "reason",
    "challenge",
    "summarize",
    "plan",
    "refuse",
    "acknowledge_uncertainty",
    "ask_missing_information",
}

UNRESOLVED_QUESTION = "unresolved_questions"
TOPIC_STACK = "topic_stack"
MAX_TOPIC_STACK = 6
MAX_UNRESOLVED = 6

_CORRECTION_RE = re.compile(
    r"^\s*(no|wait|that.s? not|that.sn.t|actually|i meant|i mean|"
    r"correction|not what i|wrong)\b", re.IGNORECASE)


def _clean(text):
    return str(text or "").strip()


def _normalized_utterance(text):
    return re.sub(r"\s+", " ", _clean(text).lower())


def _value_of(container, key, default=""):
    """Read one field from a dict or an object (defensive, deterministic)."""
    if isinstance(container, dict):
        return container.get(key, default)
    return getattr(container, key, default)


def _is_correction(text):
    return bool(_CORRECTION_RE.match(_clean(text)))


@dataclass
class ConversationState:
    """Deterministic conversational state for one session.

    Fields are primitives only. ``created_at``/``updated_at`` are caller
    supplied ISO-8601 strings (may be ``None``); this module never reads a
    clock.
    """
    session_id: str
    turn_index: int = 0
    topic: str = ""                      # current active topic (verbatim anchor)
    subtopic: str = ""
    mode: str = DEFAULT_MODE
    last_user_intent: str = ""
    last_response_objective: str = ""
    modality: str = "text"               # "text" | "voice"
    unresolved_questions: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    corrections_applied: list = field(default_factory=list)
    topic_history: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = field(default_factory=dict)

    # -- lifecycle ---------------------------------------------------------

    def start_turn(self, modality: str = "text", at: str = "") -> "ConversationState":
        """Begin a new turn; returns a new state (immutable update)."""
        state = _copy(self)
        state.turn_index += 1
        state.modality = "voice" if modality == "voice" else "text"
        if at:
            state.updated_at = at
        return state

    # -- queries -----------------------------------------------------------

    def recent_topic(self, distance: int = 1) -> str:
        """Return the topic ``distance`` turns into the past (1 = previous)."""
        topics = [t for t in self.topic_history if t]
        if not topics:
            return ""
        idx = max(0, len(topics) - int(distance))
        return topics[idx]

    def is_correction_of(self, text: str) -> bool:
        """True when ``text`` is phrased as a correction of prior content."""
        return _is_correction(text)

    # -- updates (return new states; input state never mutated) ----------

    def apply_interpretation(self, interpretation) -> "ConversationState":
        """Fold one interpreted turn into the state.

        ``interpretation`` must expose: ``utterance``, ``intent``, ``topic``,
        ``is_correction``, ``unresolved_question``, ``constraints``. All of
        these are read defensively; nothing except primitives is stored.
        """
        state = _copy(self)
        utterance = _clean(_value_of(interpretation, "utterance", ""))
        intent = _clean(_value_of(interpretation, "intent", ""))
        topic = _clean(_value_of(interpretation, "topic", ""))
        new_topic = _clean(_value_of(interpretation, "new_topic", ""))

        # Topic bookkeeping: an explicit new topic replaces the anchor; a bare
        # reference (no new topic signal) keeps the previous topic.
        if new_topic:
            previous = state.topic
            if previous and previous not in state.topic_history:
                state.topic_history.append(previous)
            state.topic_history = state.topic_history[-MAX_TOPIC_STACK:]
            state.topic = new_topic
            state.subtopic = ""
        elif topic:
            state.topic = topic
        elif not state.topic and utterance:
            state.topic = utterance[:80]

        state.last_user_intent = intent

        # Corrections are recorded but never rewrite prior content (directive
        # section 23: "the system must not silently rewrite history").
        if _value_of(interpretation, "is_correction", False):
            note = _clean(_value_of(interpretation, "correction_note", ""))
            state.corrections_applied.append(note or utterance[:80])
            state.corrections_applied = state.corrections_applied[-8:]

        # Unresolved questions accumulate (capped); a plain answer clears the
        # matching entry by reference equality on the resolved id when present.
        unresolved = _clean(_value_of(interpretation, "unresolved_question", ""))
        if unresolved:
            entry = {"question": unresolved[:120],
                     "turn": state.turn_index}
            if entry not in state.unresolved_questions:
                state.unresolved_questions.append(entry)
                state.unresolved_questions = state.unresolved_questions[
                    -MAX_UNRESOLVED:]
        resolved = _clean(_value_of(interpretation, "resolved_question_id", ""))
        if resolved:
            state.unresolved_questions = [
                q for q in state.unresolved_questions
                if q.get("question", "") != resolved]
            state.unresolved_questions = state.unresolved_questions[:MAX_UNRESOLVED]

        constraints = _value_of(interpretation, "constraints", None)
        if constraints:
            for constraint in (list(constraints) or []):
                text = _clean(constraint)
                if text and text not in state.constraints:
                    state.constraints.append(text)
                    state.constraints = state.constraints[-8:]

        # Mode transitions: derived deterministically from intent + text.
        state.mode = _derive_mode(intent, utterance, state.mode)
        return state

    def set_response_objective(self, objective: str) -> "ConversationState":
        state = _copy(self)
        candidate = str(objective or "").strip().lower().replace("-", "_")
        state.last_response_objective = candidate if candidate in RESPONSE_OBJECTIVES \
            else "answer"
        return state

    def set_mode(self, mode: str) -> "ConversationState":
        state = _copy(self)
        if str(mode or "") in MODES:
            state.mode = mode
        return state

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        """Flat, stable dict for logging / equality / cross-interpreter runs."""
        return {
            "session_id": self.session_id,
            "turn_index": self.turn_index,
            "topic": self.topic,
            "subtopic": self.subtopic,
            "mode": self.mode,
            "last_user_intent": self.last_user_intent,
            "last_response_objective": self.last_response_objective,
            "modality": self.modality,
            "unresolved_questions": list(self.unresolved_questions),
            "constraints": list(self.constraints),
            "corrections_applied": list(self.corrections_applied),
            "topic_history": list(self.topic_history),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _copy(state: ConversationState) -> ConversationState:
    return ConversationState(
        session_id=state.session_id,
        turn_index=state.turn_index,
        topic=state.topic,
        subtopic=state.subtopic,
        mode=state.mode,
        last_user_intent=state.last_user_intent,
        last_response_objective=state.last_response_objective,
        modality=state.modality,
        unresolved_questions=list(state.unresolved_questions),
        constraints=list(state.constraints),
        corrections_applied=list(state.corrections_applied),
        topic_history=list(state.topic_history),
        created_at=state.created_at,
        updated_at=state.updated_at,
        metadata=dict(state.metadata),
    )


def _derive_mode(intent: str, utterance: str, current: str) -> str:
    """Deterministic, conservative mode transitions.

    Only strong lexical evidence switches modes; everything else keeps the
    current mode. This is a documented heuristic, not a claim of NLU.
    """
    text = (utterance or "").lower()
    intent = (_clean(intent) or "").lower()

    if _is_correction(text) or "correction" in text:
        return "correction_clarification"
    if intent in ("request_for_explanation", "definition_or_information",
                  "process_or_explanation", "reason_or_cause"):
        if "should" in text or "ought" in text or "ethic" in text or \
                "moral" in text or "duty" in text:
            return "philosophical"
        if "why do people" in text or "why does the brain" in text or \
                any(w in text for w in ("procrastinat", "habit", "bias",
                                        "emotion", "motivat", "attention",
                                        "memory")):
            return "analytical"
        return "informational"
    if intent in ("choice_or_comparison", "comparison"):
        return "analytical"
    if any(w in text for w in ("compare", "contrast", "versus", "vs ",
                               "difference between")):
        return "analytical"
    if any(w in text for w in ("plan", "design", "steps to", "how do i make a",
                               "roadmap", "schedule")):
        return "planning"
    if any(w in text for w in ("debug", "error", "crash", "bug", "traceback",
                               "why does it fail")):
        return "debugging"
    if any(w in text for w in ("teach me", "explain to me like", "tutorial",
                               "lesson", "how does it work")):
        return "instructional"
    if any(w in text for w in ("story", "write a poem", "imagine", "invent",
                               "create a character")):
        return "creative"
    if any(w in text for w in ("consciousness", "free will", "meaning of life",
                               "mind", "soul", "ethics", "existential",
                               "reality", "god", "identity", "truth",
                               "knowledge", "belief")):
        return "philosophical"
    if text.endswith("?"):
        if intent == "person_or_entity":
            return "informational"
        # exploratory questions: hypothetical/what-if
        if any(w in text for w in ("what if", "what would", "could it be",
                                   "might")):
            return "exploratory"
        return "informational"
    return current if current in MODES else DEFAULT_MODE