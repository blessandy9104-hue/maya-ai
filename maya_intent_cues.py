from maya_intent_ml import predict
import re

CUES = {
    "what": "definition_or_information",
    "who": "person_or_entity",
    "where": "location",
    "when": "time_or_history",
    "why": "reason_or_cause",
    "how": "process_or_explanation",
    "which": "choice_or_comparison",
    "can": "capability_or_permission",
    "could": "polite_request_or_capability",
    "is": "fact_check_or_definition",
    "are": "fact_check_or_definition",
    "do": "action_or_capability",
    "does": "action_or_explanation",
    "tell": "request_for_explanation",
    "explain": "request_for_explanation",
}
CONTRAST_MARKERS = {"although", "but", "however", "instead", "rather", "except", "not", "despite"}
CONTRAST_CUES = {"what": "definition_or_information", "why": "reason_or_cause", "how": "process_or_explanation", "which": "choice_or_comparison", "who": "person_or_entity", "where": "location", "when": "time_or_history", "tell": "request_for_explanation", "explain": "request_for_explanation"}

def _cue(words):
    first = words[0] if words else ""
    intent = CUES.get(first, "statement_or_general_request")
    if first in {"can", "could", "is", "are", "do", "does"} and any(value in words[:5] for value in ("maya", "you")):
        intent = "maya_capability_or_action"
    return first, intent

def classify_opening(text):
    cleaned = re.sub(r"^[\\s\\\"\x27\\[\\(]+", "", text.strip().lower())
    words = re.findall(r"[a-z]+", cleaned)
    first, raw_intent = _cue(words)
    adjusted_intent = raw_intent
    markers = [word for word in words if word in CONTRAST_MARKERS]
    cue_positions = [(index, CUES[word]) for index, word in enumerate(words) if word in CUES]
    secondary = []
    if first in {"can", "could", "is", "are", "do", "does"} and any(value in words[:5] for value in ("maya", "you")):
        primary_capability = "maya_capability_or_action"
    else:
        primary_capability = raw_intent
    if markers:
        last_marker = max(index for index, word in enumerate(words) if word in CONTRAST_MARKERS)
        for index, word in enumerate(words[last_marker + 1:], start=last_marker + 1):
            if word in CONTRAST_CUES:
                adjusted_intent = CONTRAST_CUES[word]
                break
    for index, candidate in cue_positions:
        if candidate != adjusted_intent and candidate not in secondary:
            secondary.append(candidate)
    if primary_capability not in (adjusted_intent, "statement_or_general_request") and primary_capability not in secondary:
        secondary.insert(0, primary_capability)
    ambiguous = bool(markers) or len(secondary) > 0 or adjusted_intent == "statement_or_general_request"
    confidence = 0.9 if not ambiguous and adjusted_intent != "statement_or_general_request" else (0.62 if len(secondary) == 1 and not markers else 0.45)
    ml = predict(cleaned)
    if ml is not None:
        adjusted_intent = ml["primary_intent"]
        secondary = [value for value in ml["secondary_intents"] if value != adjusted_intent] + [value for value in secondary if value != adjusted_intent and value not in ml["secondary_intents"]]
        confidence = max(confidence, ml["score"])
        ambiguous = ambiguous or bool(secondary)
    model_name = ml["model"] if ml is not None else "heuristic"
    negated = []
    for index, word in enumerate(words[:-1]):
        if word == "not":
            next_word = words[index + 1]
            negated.append("execution" if next_word in {"execute", "act", "change", "rewrite"} else CUES.get(next_word, next_word))
    discourse_opening = words[0] in {"although", "however", "rather", "instead", "despite"} if words else False
    negated_clauses = []
    for index, word in enumerate(words):
        if word == "not": negated_clauses.append(" ".join(words[index:index+5]))
    structured = {"primary": adjusted_intent, "secondary": secondary, "negated": negated, "negated_clauses": negated_clauses, "discourse_opening": discourse_opening, "confidence": round(confidence, 2), "ambiguous": ambiguous}
    return {"first_word": first, "raw_intent": raw_intent, "intent": adjusted_intent, "primary_intent": adjusted_intent, "secondary_intents": secondary, "contrastive_markers": markers, "contrastive_filter_applied": adjusted_intent != raw_intent, "confidence": round(confidence, 2), "ambiguous": ambiguous, "model": model_name, "negated_intents": negated, "negated_clauses": negated_clauses, "discourse_opening": discourse_opening, "structured_intent": structured, "used_as_hint_only": True}



