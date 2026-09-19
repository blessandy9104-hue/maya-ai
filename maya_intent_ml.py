import re

PHRASE_WEIGHTS = [
    ("can you tell me why", "reason_or_cause", 0.98),
    ("can you tell me what", "definition_or_information", 0.98),
    ("can you tell me how", "process_or_explanation", 0.98),
    ("could you tell me how", "process_or_explanation", 0.98),
    ("can you explain", "request_for_explanation", 0.96),
    ("do you know why", "reason_or_cause", 0.96),
    ("does maya learn", "definition_or_information", 0.94),
    ("could you help me", "polite_request_or_capability", 0.96),
    ("what is", "definition_or_information", 0.82),
    ("why does", "reason_or_cause", 0.84),
    ("how does", "process_or_explanation", 0.84),
    ("which", "choice_or_comparison", 0.78),
    ("where", "location", 0.78),
    ("when", "time_or_history", 0.78),
    ("who", "person_or_entity", 0.78),
    ("tell me", "request_for_explanation", 0.75),
    ("explain", "request_for_explanation", 0.78),
]

def predict(text):
    value = re.sub(r"\\s+", " ", text.strip().lower())
    matches = [(intent, weight) for phrase, intent, weight in PHRASE_WEIGHTS if phrase in value]
    if not matches:
        return None
    matches.sort(key=lambda item: item[1], reverse=True)
    primary, score = matches[0]
    secondary = []
    for intent, _ in matches[1:]:
        if intent != primary and intent not in secondary:
            secondary.append(intent)
    return {"primary_intent": primary, "secondary_intents": secondary, "score": score, "model": "weighted_phrase"}
