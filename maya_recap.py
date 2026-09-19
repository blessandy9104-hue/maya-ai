"""Deterministic session recap from the conversation log.

Builds a review-only digest of topics, questions Maya was asked, and open
follow-ups for one or more recent sessions, plus "continue later" thread
markers. Everything is derived from the existing JSONL exchange log
(maya_conversation_store); this module writes nothing to identity, memory,
or the world model. Digests are byte-stable for the same log bytes: no
clock reads, no randomness, sorted output fields.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from maya_conversation_store import load_events

ROOT = Path(__file__).resolve().parent
THREAD_STATE = ROOT / "knowledge" / "conversations" / "recap_threads.json"

FOLLOWUP_MARKERS = (
    "request andy's approval",
    "requires your approval",
    "needs your approval",
    "human approval",
    "say the word",
    "would you like",
    "not available yet",
    "could not be generated",
    "nothing was changed",
    "is not available",
)

_TOPIC_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "because", "of",
    "to", "in", "on", "for", "with", "about", "from", "by", "at", "as", "is",
    "are", "was", "were", "be", "been", "being", "am", "do", "does", "did",
    "can", "could", "should", "would", "will", "shall", "may", "might", "must",
    "have", "has", "had", "i", "me", "my", "we", "our", "you", "your", "it",
    "its", "this", "that", "these", "those", "what", "which", "who", "whom",
    "whose", "when", "where", "why", "how", "there", "here", "not", "no",
    "yes", "into", "than", "them", "they", "their", "she", "he", "her", "his",
    "him", "us", "up", "out", "just", "some", "any", "more", "most", "other",
    "mayas", "maya",
}

_QUESTION_SUFFIX = "?"
_ASSISTANT_DEFLECTIONS = (
    "i'm not sure",
    "i don't know",
    "i cannot",
    "i can't",
    "i'm unable",
)

# Natural-language continue phrases: "continue the <topic> thread", or the
# report's own instruction "resume thread t003". Bare "continue" / "go on"
# deliberately do NOT match — they stay with the router's ambiguous phrases.
_MAYA_PREFIX = r"(?:maya,?\s+)?(?:please\s+)?"
_THREAD_ID_RE = re.compile(_MAYA_PREFIX + r"(?:resume|continue)\s+thread\s+(t\d{3})$")
_CONTINUE_RE = re.compile(
    _MAYA_PREFIX
    + r"(?:continue|resume|go back to|pick up|return to)\s+"
    + r"(?:the|that|this|our|my)?\s*"
    + r"(?P<topic>.+)$"
)
# Words a user may use to refer to "the thread" that carry no topic meaning.
_GENERIC_TOPIC_WORDS = {
    "thread", "threads", "discussion", "topic", "conversation",
    "question", "thing", "things",
}


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _sorted_terms(counter: dict[str, int]) -> list[str]:
    return sorted(counter, key=lambda term: (-counter[term], term))


def _timestamp_key(event: dict[str, Any]) -> str:
    value = event.get("timestamp")
    return value if isinstance(value, str) else ""


def _group_by_session(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group events by session id (missing ids bucketed together)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        session_id = event.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            session_id = "(no session id)"
        groups.setdefault(session_id, []).append(event)
    return groups


def _session_stamps(group: list[dict[str, Any]]) -> list[str]:
    """Sorted timestamp strings of a session's events (blank stamps dropped)."""
    return sorted(s for s in (_timestamp_key(event) for event in group) if s)


def _question_items(events: list[dict[str, Any]], cap: int) -> list[str]:
    questions = []
    for event in events:
        if event.get("role") != "user":
            continue
        content = _norm_text(event.get("content"))
        if content.endswith(_QUESTION_SUFFIX):
            questions.append(content)
    questions = sorted(set(questions))
    return questions[:cap] if cap is not None else questions


def _topic_terms(user_contents: list[str], cap: int) -> list[str]:
    counter: dict[str, int] = {}
    for content in user_contents:
        for word in re.findall(r"[a-z][a-z0-9']{2,}", content.lower()):
            if word in _TOPIC_STOPWORDS:
                continue
            counter[word] = counter.get(word, 0) + 1
    terms = _sorted_terms(counter)
    return terms[:cap] if cap is not None else terms


def _followup_items(events: list[dict[str, Any]], cap: int) -> list[dict[str, str]]:
    followups = []
    for event in events:
        if event.get("role") != "assistant":
            continue
        content = _norm_text(event.get("content"))
        lowered = content.lower()
        for marker in FOLLOWUP_MARKERS:
            if marker in lowered:
                followups.append({"marker": marker, "excerpt": content[:200]})
                break
    return followups[:cap] if cap is not None else followups


def _new_threads_state() -> dict[str, Any]:
    return {"version": 1, "threads": {}}


def _load_threads_state() -> dict[str, Any]:
    try:
        data = json.loads(THREAD_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _new_threads_state()
    if not isinstance(data, dict) or not isinstance(data.get("threads"), dict):
        return _new_threads_state()
    return data


def _marker_session(events: list[dict[str, Any]], marker_text: str, direction: int) -> str | None:
    """Find the session id of the nearest event containing marker_text.

    Scans the log (a bounded window) from the end when direction is -1,
    otherwise from the start. Marker text matching is case-insensitive on
    whitespace-normalized content.
    """
    lowered = marker_text.lower()
    ordered = events if direction > 0 else list(reversed(events))
    for event in ordered:
        if lowered in _norm_text(event.get("content")).lower():
            session_id = event.get("session_id")
            return session_id if isinstance(session_id, str) and session_id else "(no session id)"
    return None


def _active_sessions(events: list[dict[str, Any]]) -> list[str]:
    sessions = []
    for event in events:
        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id not in sessions:
            sessions.append(session_id)
    return sessions


def recap_digest(sessions: int = 1, log: list[dict[str, Any]] | None = None, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic digest for the last `sessions` session ids in the log.

    When `log` is provided, uses those events instead of reading the store
    (used by the verification suite and for deterministic testing).
    """
    events = log if log is not None else load_events()
    ordered_sessions = _active_sessions(events)
    if sessions <= 0 or not ordered_sessions:
        return {
            "status": "empty",
            "session_count": 0,
            "topics": [],
            "questions": [],
            "open_followups": [],
            "open_threads": [],
            "note": "No session activity in the conversation log.",
        }
    groups = _group_by_session(events)
    stamps = {sid: _session_stamps(group) for sid, group in groups.items()}
    recency = {sid: (stamp_list[-1] if stamp_list else "") for sid, stamp_list in stamps.items()}
    chosen = sorted(recency, key=lambda sid: (recency[sid], sid))[-sessions:]
    selected = [sid for sid in sorted(chosen, key=lambda sid: (stamps[sid][0] if stamps[sid] else "", sid))]

    state_data = state if state is not None else _load_threads_state()
    threads = state_data.get("threads", {})

    session_rows = []
    all_topics: dict[str, int] = {}
    all_questions: list[str] = []
    all_followups: list[dict[str, str]] = []
    for sid in selected:
        group_events = groups[sid]
        user_contents = [_norm_text(event.get("content")) for event in group_events if event.get("role") == "user"]
        topics = _topic_terms(user_contents, cap=8)
        questions = _question_items(group_events, cap=10)
        followups = _followup_items(group_events, cap=10)
        for topic in topics:
            all_topics[topic] = all_topics.get(topic, 0) + 1
        all_questions.extend(questions)
        all_followups.extend(followups)
        stamp_list = stamps[sid]
        session_rows.append({
            "session_id": sid,
            "event_count": len(group_events),
            "first_timestamp": stamp_list[0] if stamp_list else "",
            "last_timestamp": stamp_list[-1] if stamp_list else "",
            "topics": topics,
            "questions": questions,
            "open_followups": followups,
        })

    open_threads = []
    for thread_id, thread in sorted(threads.items()):
        if not isinstance(thread, dict) or thread.get("status") != "paused":
            continue
        session_id = thread.get("session_id")
        open_threads.append({
            "thread_id": thread_id,
            "session_id": session_id if isinstance(session_id, str) else "",
            "topic": str(thread.get("topic") or ""),
            "resumed_count": int(thread.get("resumed_count") or 0),
        })

    all_questions = sorted(set(all_questions))
    seen_excerpts = set()
    deduped_followups = []
    for item in all_followups:
        key = item["excerpt"]
        if key not in seen_excerpts:
            seen_excerpts.add(key)
            deduped_followups.append(item)

    return {
        "status": "ok",
        "session_count": len(session_rows),
        "sessions": session_rows,
        "topics": _sorted_terms(all_topics)[:12],
        "questions": all_questions[:15],
        "open_followups": deduped_followups[:15],
        "open_threads": open_threads,
        "note": "Review-only digest of the conversation log. Open follow-ups are excerpts containing deferral language, not commitments.",
    }


def recap_report(digest: dict[str, Any]) -> str:
    """Human-readable rendering of a recap digest."""
    lines = ["# Session Recap", ""]
    if digest.get("status") == "empty":
        lines.append("No session activity in the conversation log.")
        return "\n".join(lines) + "\n"
    lines.append(f"Sessions summarized: {digest['session_count']}")
    lines.append("")
    for row in digest.get("sessions", []):
        lines.append(f"## Session {row['session_id'][:8]}… ({row['event_count']} turns)")
        lines.append("")
        if row.get("first_timestamp"):
            lines.append(f"Started: {row['first_timestamp']}")
        if row.get("topics"):
            lines.append("Topics: " + ", ".join(row["topics"]))
        if row.get("questions"):
            lines.append("")
            lines.append("Questions asked:")
            for question in row["questions"]:
                lines.append(f"- {question}")
        if row.get("open_followups"):
            lines.append("")
            lines.append("Open follow-ups:")
            for item in row["open_followups"]:
                lines.append(f"- ({item['marker']}) {item['excerpt']}")
        lines.append("")
    if digest.get("topics"):
        lines.append("Combined topics: " + ", ".join(digest["topics"]))
    if digest.get("open_threads"):
        lines.append("")
        lines.append("Continue-later threads:")
        for thread in digest["open_threads"]:
            label = thread.get("topic") or "(untitled thread)"
            lines.append(f"- {label} [thread {thread['thread_id']}] — paused; say “resume thread {thread['thread_id']}” to continue")
    if digest.get("questions") and digest.get("session_count", 0) > 1:
        lines.append("")
        lines.append("All questions across sessions:")
        for question in digest["questions"]:
            lines.append(f"- {question}")
    lines.append("")
    lines.append(digest.get("note", ""))
    return "\n".join(lines) + "\n"


def pause_thread(topic: str, session_id: str = "", marker: str = "", state: dict[str, Any] | None = None, log: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Record a continue-later marker for a topic.

    The marker is pinned to the session whose events contain `marker` text
    (last match wins, falling back to the most recent session). When `state`
    is provided it is returned without writing the state file (pure mode for
    verification); otherwise the state file is updated in place.
    """
    topic = _norm_text(topic)
    if not topic:
        return {"status": "error", "detail": "Usage: :recap pause <topic>"}
    events = log if log is not None else load_events()
    resolved_session = session_id
    if not resolved_session:
        resolved_session = None
        if marker.strip():
            resolved_session = _marker_session(events, marker, direction=-1)
        if resolved_session is None:
            active = _active_sessions(events)
            resolved_session = active[-1] if active else ""
    state_data = state if state is not None else _load_threads_state()
    if "version" not in state_data:
        state_data["version"] = 1
    if not isinstance(state_data.get("threads"), dict):
        state_data["threads"] = {}
    thread_id = "t" + str(len(state_data["threads"]) + 1).zfill(3)
    while thread_id in state_data["threads"]:
        thread_id = "t" + str(int(thread_id[1:]) + 1).zfill(3)
    thread = {
        "thread_id": thread_id,
        "topic": topic,
        "session_id": resolved_session,
        "status": "paused",
        "resumed_count": 0,
        "created_from_log_length": len(events),
        "marker": _norm_text(marker),
    }
    state_data["threads"][thread_id] = thread
    result = {
        "status": "ok",
        "thread": dict(thread),
        "wrote_state": state is None,
    }
    if state is None:
        try:
            THREAD_STATE.parent.mkdir(parents=True, exist_ok=True)
            THREAD_STATE.write_text(json.dumps(state_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            return {"status": "error", "detail": f"Could not save thread state: {exc}", "thread": dict(thread)}
    return result


def resume_thread(thread_id: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mark a paused thread as resumed and return its pinned context."""
    thread_id = _norm_text(thread_id)
    state_data = state if state is not None else _load_threads_state()
    threads = state_data.get("threads")
    if not isinstance(threads, dict) or thread_id not in threads:
        return {"status": "error", "detail": f"Unknown thread id: {thread_id or '(missing)'}. Use :recap to list open threads."}
    thread = threads[thread_id]
    if not isinstance(thread, dict):
        return {"status": "error", "detail": f"Corrupt thread entry: {thread_id}"}
    thread["status"] = "active"
    thread["resumed_count"] = int(thread.get("resumed_count") or 0) + 1
    result = {
        "status": "ok",
        "thread": dict(thread),
        "wrote_state": state is None,
        "context_note": "Pinned context: " + (str(thread.get("topic") or "untitled thread")),
    }
    if state is None:
        try:
            THREAD_STATE.write_text(json.dumps(state_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            return {"status": "error", "detail": f"Could not save thread state: {exc}", "thread": dict(thread)}
    return result


def _open_paused_threads(threads: Any) -> list[dict[str, Any]]:
    """Paused thread rows from a threads mapping, sorted by thread id."""
    if not isinstance(threads, dict):
        return []
    return sorted(
        (t for t in threads.values()
         if isinstance(t, dict) and t.get("status") == "paused"),
        key=lambda t: str(t.get("thread_id") or ""))


def _topic_tokens(text: str) -> set[str]:
    """Meaningful topic words: recap stopwords plus thread-referring generics."""
    return {word for word in re.findall(r"[a-z][a-z0-9']+", text.lower())
            if word not in _TOPIC_STOPWORDS and word not in _GENERIC_TOPIC_WORDS}


def _thread_label(thread: dict[str, Any]) -> str:
    return "%s [%s]" % (thread.get("topic") or "untitled thread",
                        thread.get("thread_id"))


def resolve_continue_phrase(text: str, state: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Resolve a natural-language continue request against open threads.

    Returns None when the input is not a continue phrase (the caller falls
    through — bare "continue" stays with the router's ambiguous phrases).
    Otherwise returns a result dict: "ok" (thread resumed via
    ``resume_thread``, the single writer of thread state), "ambiguous" with
    the matching candidates when several open threads fit, or "no_match"
    with an honest detail. With ``state`` provided nothing is written (pure
    mode, same contract as pause_thread/resume_thread).
    """
    lowered = _norm_text(text).lower().rstrip(" .!?;:,)")
    id_match = _THREAD_ID_RE.match(lowered)
    if id_match:
        return resume_thread(id_match.group(1), state=state)
    topic_match = _CONTINUE_RE.match(lowered)
    if not topic_match:
        return None
    tokens = _topic_tokens(topic_match.group("topic"))
    state_data = state if state is not None else _load_threads_state()
    open_threads = _open_paused_threads(state_data.get("threads"))
    if not open_threads:
        return {
            "status": "no_match",
            "detail": ("There are no open threads to continue. Say \":recap\" "
                       "to see recent sessions, or \":recap pause <topic>\" to mark one."),
        }
    if tokens:
        matches = [t for t in open_threads
                   if tokens <= _topic_tokens(str(t.get("topic") or ""))]
    else:
        matches = open_threads
    if not matches:
        names = ", ".join(_thread_label(t) for t in open_threads) or "(none)"
        return {
            "status": "no_match",
            "detail": ("No open thread matches \"%s\". Open threads: %s."
                       % (_norm_text(topic_match.group("topic")), names)),
        }
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "candidates": [{"thread_id": t.get("thread_id"), "topic": t.get("topic")}
                           for t in matches],
            "detail": ("Several open threads match; name one explicitly: "
                       + ", ".join(_thread_label(t) for t in matches) + "."),
        }
    return resume_thread(str(matches[0].get("thread_id") or ""), state=state)


def continue_reply(text: str) -> str | None:
    """Natural-language entry: render a continue-phrase resolution.

    Returns None when the input is not a continue phrase; the conversation
    owner then falls through. Successful resumes persist through
    resume_thread's single write path.
    """
    result = resolve_continue_phrase(text)
    if result is None:
        return None
    status = result.get("status")
    if status == "ok":
        thread = result.get("thread") or {}
        session = str(thread.get("session_id") or "(no session)")
        return ("Resumed thread %s — \"%s\" (pinned to session %s). "
                "It is marked active; say \":recap\" for the digest."
                % (thread.get("thread_id"), thread.get("topic") or "untitled thread",
                   session[:8]))
    if status == "ambiguous":
        labels = ", ".join(_thread_label(t) for t in result.get("candidates", []))
        return "Several open threads match — name one: %s." % labels
    return result.get("detail") or "No open thread matched that request."


def recap_command(user_text: str) -> str | None:
    """Handle :recap subcommands; return None when input is not a :recap command."""
    text = user_text.strip()
    lowered = text.lower()
    if lowered in (":recap", "session recap", "show session recap", "recap session", "recap my sessions"):
        return recap_report(recap_digest())
    if lowered == ":recap 3" or lowered == "recap 3":
        return recap_report(recap_digest(sessions=3))
    if lowered == ":recap 7":
        return recap_report(recap_digest(sessions=7))
    if lowered.startswith(":recap pause "):
        topic = text[len(":recap pause "):].strip()
        return json.dumps(pause_thread(topic), indent=2, ensure_ascii=False)
    if lowered.startswith(":recap resume "):
        thread_id = text[len(":recap resume "):].strip()
        return json.dumps(resume_thread(thread_id), indent=2, ensure_ascii=False)
    if lowered == ":recap resume":
        return "Usage: :recap resume <thread_id> — or say \"continue the <topic> thread\"."
    if lowered == ":recap help":
        return ("Usage: :recap [3|7] — deterministic digest of recent sessions; "
                ":recap pause <topic> — mark a continue-later thread; "
                ":recap resume <thread_id> — resume a paused thread. "
                "You can also say \"continue the <topic> thread\".")
    if lowered.startswith(":recap ") or lowered == ":recap":
        return "Usage: :recap [3|7], :recap pause <topic>, :recap resume <thread_id>, or :recap help"
    return None
