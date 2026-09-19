"""Persistent conversation history for Maya.

Plain JSONL conversation events only. This store is deliberately separate
from approval-gated memory (andy_profile.json, maya_world_model.py, etc.):
it holds no status/approval fields and never promotes anything into
approved memory.

One event per line:
{"event_id": ..., "timestamp": ..., "session_id": ..., "role": "user"|"assistant", "content": ...}
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONVERSATIONS_DIR = ROOT / "knowledge" / "conversations"
CONVERSATION_LOG = CONVERSATIONS_DIR / "maya_conversation_log.jsonl"

DEFAULT_LOAD_LIMIT = 8


def new_session_id() -> str:
    return str(uuid.uuid4())


def append_turn(role: str, content: str, session_id: str = "") -> dict | None:
    """Append one conversation turn. Returns the stored event, or None on failure.

    Failures are swallowed so persistence problems can never crash the chat loop.
    """
    content = str(content or "")
    if not content.strip():
        return None
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id or new_session_id(),
        "role": "user" if role == "user" else "assistant",
        "content": content,
    }
    try:
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        with CONVERSATION_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event
    except OSError:
        return None


def append_exchange(user_content: str, assistant_content: str, session_id: str = "") -> list[dict] | None:
    """Append a user/assistant exchange in one JSONL append operation.

    Returns both stored events on success, or None when either content is blank
    or the complete append cannot be written.
    """
    user_content = str(user_content or "")
    assistant_content = str(assistant_content or "")
    if not user_content.strip() or not assistant_content.strip():
        return None
    shared_session_id = session_id or new_session_id()
    events = [
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": shared_session_id,
            "role": "user",
            "content": user_content,
        },
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": shared_session_id,
            "role": "assistant",
            "content": assistant_content,
        },
    ]
    try:
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        serialized = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)
        with CONVERSATION_LOG.open("a", encoding="utf-8") as handle:
            handle.write(serialized)
        return events
    except OSError:
        return None


def load_recent(limit: int = DEFAULT_LOAD_LIMIT) -> list[dict]:
    """Return the last `limit` valid events as {"role", "content"} dicts.

    Malformed lines are skipped. Missing/corrupt file returns [].
    """
    if limit <= 0:
        return []
    try:
        raw = CONVERSATION_LOG.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    events: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content:
            events.append({"role": role, "content": content})
    return events[-limit:]


def load_events(limit: int = 4000) -> list[dict]:
    """Return the last `limit` valid events with all stored fields.

    Unlike load_recent (which returns chat-context role/content pairs), this
    keeps event_id, timestamp, and session_id so downstream tools such as the
    session recap can group by session. Malformed lines are skipped;
    missing/corrupt file returns [].
    """
    if limit <= 0:
        return []
    try:
        raw = CONVERSATION_LOG.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    events: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content:
            events.append(item)
    return events[-limit:]


if __name__ == "__main__":
    print(json.dumps(load_recent(10), indent=2, ensure_ascii=False))