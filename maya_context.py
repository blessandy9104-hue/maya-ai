from __future__ import annotations


def _latest_user_message(history: list[dict] | None) -> str:
    if not history:
        return ""
    for message in reversed(history):
        if message.get("role") == "user":
            return str(message.get("content", "")).strip()
    return ""


def rewrite_follow_up(text: str, history: list[dict] | None = None) -> str:
    """Resolve short conversational references using only local conversation history."""
    clean = text.strip()
    if not clean or not history:
        return clean

    previous_user_message = _latest_user_message(history)
    if not previous_user_message:
        return clean

    lowered = clean.lower()
    exact_follow_ups = {"why", "why?", "how so", "how come", "and?", "then?", "what now?"}
    follow_up_starts = (
        "tell me more",
        "what about",
        "how about",
        "what are they",
        "what is he",
        "what is she",
        "what happened next",
        "and the ",
        "what about that",
        "what does that mean",
        "make it shorter",
        "short answer",
        "explain that",
    )
    # Keep the original wording and attach context transparently. This does not
    # create memory or infer permission; it only helps the current turn.
    if lowered in exact_follow_ups or lowered.startswith(follow_up_starts):
        return f"{clean} regarding this previous question: {previous_user_message}"

    # Very short deictic questions are usually references to the immediately
    # preceding user turn; do not rewrite ordinary substantive questions.
    words = lowered.replace("?", "").split()
    deictic = {"that", "this", "it", "they", "them", "one", "other"}
    if len(words) <= 8 and any(word in deictic for word in words):
        return f"{clean} regarding this previous question: {previous_user_message}"

    return clean


def relevant_context(history, limit=8):
    if not history:
        return "No earlier dialogue is available."
    lines = []
    for message in history[-limit:]:
        content = str(message.get("content", "")).strip()
        if content:
            lines.append(message.get("role", "").upper() + ": " + content)
    return (
        "Prioritize the latest user request and the immediate topic. Preserve requested answer length "
        "such as one sentence, two sentences, concise, or detailed. Do not repeat general capabilities, "
        "safety, setup, or roadmap material unless asked. Use earlier turns only to resolve references "
        "and maintain continuity.\n" + "\n".join(lines)
    )
