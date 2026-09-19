def execute(text):
    value = text.strip().lower()
    if value in {"hello maya", "hello maya, what can you do", "what can you do", "maya capabilities"}:
        return "I can report status, perform public read-only research, manage activation, review observations, and learn approved patterns. I do not change permissions or trusted memory without approval."
    if value in {"how are you", "are you okay", "are you awake"}:
        return "I am running locally. Use Status for service state; Presence Mode remains off unless explicitly implemented and enabled."
    if value in {"can you self-evolve", "can maya self-evolve", "can you self evolve", "can maya self evolve"}:
        return "I can improve through supervised research, reviewed patterns, corrections, and approved proposals. I cannot rewrite my permissions or core behavior without approval."
    return None
