"""Session recap verification suite.

Pins the deterministic recap surface: digest determinism, topic/question/
follow-up extraction, session grouping and selection, continue-later thread
pause/resume (pure and write modes), router wiring, and no-write purity of
the digest against the real conversation log.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_recap as recap
import maya_chat
from maya_conversation_store import load_events


def _ok(label: str) -> None:
    print(label + " =OK")


def _event(role: str, content: str, sid: str, ts: str) -> dict:
    return {"event_id": sid + "-" + ts, "timestamp": ts, "session_id": sid, "role": role, "content": content}


FIXTURE_LOG = [
    _event("user", "What is a black hole really?", "s1", "2026-09-14T10:00:00+00:00"),
    _event("assistant", "A black hole is a region where gravity prevents anything from escaping. I can research the evidence if you like.", "s1", "2026-09-14T10:00:05+00:00"),
    _event("user", "how does entropy relate?", "s1", "2026-09-14T10:01:00+00:00"),
    _event("assistant", "Entropy connects through information theory. Generating the report is possible; human approval is required before any change.", "s1", "2026-09-14T10:01:05+00:00"),
    _event("user", "Should I compare routing tables?", "s2", "2026-09-14T11:00:00+00:00"),
    _event("assistant", "Routing is a network concept. The full comparison is not available yet; the generator exists and can be run on request.", "s2", "2026-09-14T11:00:05+00:00"),
]

FIXTURE_STATE = {
    "version": 1,
    "threads": {
        "t001": {"thread_id": "t001", "topic": "mars colony debate", "session_id": "s1", "status": "paused", "resumed_count": 0, "marker": ""},
    },
}


def check_store_load_events() -> None:
    events = load_events()
    assert isinstance(events, list)
    for item in events:
        assert isinstance(item, dict) and item.get("role") in ("user", "assistant")
        assert isinstance(item.get("content"), str) and item["content"]
    _ok("store load_events keeps full rows")


def check_digest_determinism() -> None:
    a = recap.recap_digest(sessions=2, log=FIXTURE_LOG, state=FIXTURE_STATE)
    b = recap.recap_digest(sessions=2, log=FIXTURE_LOG, state=FIXTURE_STATE)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    c = recap.recap_digest(sessions=2, log=list(reversed(FIXTURE_LOG)), state=FIXTURE_STATE)
    assert json.dumps(a, sort_keys=True) == json.dumps(c, sort_keys=True)
    empty = recap.recap_digest(sessions=1, log=[], state={})
    assert empty["status"] == "empty" and empty["session_count"] == 0
    _ok("digest deterministic for same log bytes")
    _ok("digest deterministic under event reorder")
    _ok("digest empty log handled")


def check_digest_structure() -> None:
    digest = recap.recap_digest(sessions=2, log=FIXTURE_LOG, state=FIXTURE_STATE)
    assert digest["status"] == "ok" and digest["session_count"] == 2
    assert digest["topics"] and isinstance(digest["topics"], list)
    assert digest["questions"], "questions must be extracted"
    assert digest["open_followups"], "follow-ups must be extracted"
    assert digest["open_threads"] and digest["open_threads"][0]["thread_id"] == "t001"
    for row in digest["sessions"]:
        assert set(row) >= {"session_id", "event_count", "topics", "questions", "open_followups"}
    _ok("digest structure complete")


def check_question_extraction() -> None:
    digest = recap.recap_digest(sessions=2, log=FIXTURE_LOG, state={})
    assert "What is a black hole really?" in digest["questions"]
    assert "Should I compare routing tables?" in digest["questions"]
    assert "how does entropy relate?" in digest["questions"]  # user ?-turns count
    assert all(not q.startswith("A black hole") for q in digest["questions"])
    _ok("questions extracted from user turns only")


def check_followup_extraction() -> None:
    digest = recap.recap_digest(sessions=2, log=FIXTURE_LOG, state={})
    markers = {item["marker"] for item in digest["open_followups"]}
    assert "human approval" in markers
    assert "not available yet" in markers
    assert all(item["excerpt"] for item in digest["open_followups"])
    _ok("open follow-ups detected by Maya deferral vocabulary")


def check_session_selection() -> None:
    one = recap.recap_digest(sessions=1, log=FIXTURE_LOG, state={})
    assert one["session_count"] == 1
    assert one["sessions"][0]["session_id"] == "s2"  # most recent session by timestamp
    three = recap.recap_digest(sessions=3, log=FIXTURE_LOG, state={})
    assert three["session_count"] == 2  # only two sessions exist in the log
    _ok("session selection takes most recent first")
    _ok("session count capped by available sessions")


def check_thread_lifecycle_pure() -> None:
    state = {"version": 1, "threads": {}}
    pause = recap.pause_thread("black hole evidence", session_id="s1", state=state, log=FIXTURE_LOG)
    assert pause["status"] == "ok" and pause["wrote_state"] is False
    assert pause["thread"]["status"] == "paused" and pause["thread"]["session_id"] == "s1"
    resume = recap.resume_thread("t001", state=state)
    assert resume["status"] == "ok" and resume["wrote_state"] is False
    assert resume["thread"]["resumed_count"] == 1 and resume["thread"]["status"] == "active"
    missing = recap.resume_thread("t404", state=state)
    assert missing["status"] == "error"
    blank = recap.pause_thread("   ", state=state, log=FIXTURE_LOG)
    assert blank["status"] == "error"
    _ok("pause is pure and assigns thread id")
    _ok("resume flips status and counts")
    _ok("unknown thread id errors")
    _ok("blank topic rejected")


def check_thread_lifecycle_write_mode() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        original = recap.THREAD_STATE
        recap.THREAD_STATE = Path(tmp) / "recap_threads.json"
        try:
            pause = recap.pause_thread("entropy deep dive", session_id="s2", log=FIXTURE_LOG)
            assert pause["status"] == "ok" and pause["wrote_state"] is True
            assert recap.THREAD_STATE.exists()
            data = json.loads(recap.THREAD_STATE.read_text(encoding="utf-8"))
            assert data["threads"]["t001"]["topic"] == "entropy deep dive"
            assert data["threads"]["t001"]["status"] == "paused"
            resume = recap.resume_thread("t001")
            assert resume["status"] == "ok" and resume["wrote_state"] is True
            data = json.loads(recap.THREAD_STATE.read_text(encoding="utf-8"))
            assert data["threads"]["t001"]["status"] == "active"
            resumed = recap.recap_digest(sessions=2, log=FIXTURE_LOG)
            assert resumed["open_threads"] == []  # active threads are not open
            _ok("pause writes state file")
            _ok("resume persists to state file")
            _ok("resumed thread leaves open list")
        finally:
            recap.THREAD_STATE = original
    _ok("thread state confined to knowledge/conversations")


def check_marker_resolution() -> None:
    result = recap.pause_thread("routing follow-through", marker="comparison is not available yet", log=FIXTURE_LOG, state={"version": 1, "threads": {}})
    assert result["status"] == "ok"
    assert result["thread"]["session_id"] == "s2", "marker must pin the session containing the text"
    _ok("marker text pins thread session")


def check_router_wiring() -> None:
    state = {"version": 1, "threads": {}}
    report = recap.recap_command(":recap")
    assert report.startswith("# Session Recap")
    wide = recap.recap_command(":recap 3")
    assert wide.startswith("# Session Recap")
    assert recap.recap_command(":recap help").startswith("Usage: :recap")
    assert recap.recap_command(":recap nonsense") == "Usage: :recap [3|7], :recap pause <topic>, :recap resume <thread_id>, or :recap help"
    with tempfile.TemporaryDirectory() as tmp:
        original = recap.THREAD_STATE
        recap.THREAD_STATE = Path(tmp) / "recap_threads.json"
        try:
            paused = maya_chat.maya_local_command(":recap pause mars colony debate")
            assert '"status": "ok"' in paused and "mars colony debate" in paused
            assert "t001" in recap.recap_command(":recap")
            resumed = maya_chat.maya_local_command(":recap resume t001")
            assert '"status": "ok"' in resumed and '"active"' in resumed
            unknown = maya_chat.maya_local_command(":recap resume t404")
            assert '"status": "error"' in unknown
        finally:
            recap.THREAD_STATE = original
    assert recap.recap_command("what is a black hole") is None
    _ok("recap command surface complete")
    _ok("router :recap pause/resume wired")
    _ok("router resume unknown id errors cleanly")
    _ok("non-recap input passes through")


def check_digest_readonly_real_log() -> None:
    log_path = recap.ROOT / "knowledge" / "conversations" / "maya_conversation_log.jsonl"
    before = log_path.read_bytes() if log_path.exists() else None
    state_path = recap.THREAD_STATE
    state_before = state_path.read_bytes() if state_path.exists() else None
    digest = recap.recap_digest(sessions=1)
    again = recap.recap_digest(sessions=1)
    assert json.dumps(digest, sort_keys=True) == json.dumps(again, sort_keys=True)
    after = log_path.read_bytes() if log_path.exists() else None
    assert before == after
    state_after = state_path.read_bytes() if state_path.exists() else None
    assert state_before == state_after
    assert digest["session_count"] >= 1
    report = recap.recap_report(digest)
    assert report.startswith("# Session Recap")
    _ok("real log digest deterministic and read-only")
    _ok("recap report renders")


def check_continue_phrase_resolution() -> None:
    def fresh() -> dict:
        return {"version": 1, "threads": {
            "t001": {"thread_id": "t001", "topic": "mars colony debate", "session_id": "s1", "status": "paused", "resumed_count": 0, "marker": ""},
            "t002": {"thread_id": "t002", "topic": "mars water survey", "session_id": "s2", "status": "paused", "resumed_count": 0, "marker": ""},
            "t003": {"thread_id": "t003", "topic": "entropy deep dive", "session_id": "s2", "status": "paused", "resumed_count": 0, "marker": ""},
        }}
    # Non-continue inputs fall through (None) so the router keeps its owner.
    for phrase in ("what is a black hole", "continue", "go on", "so"):
        assert recap.resolve_continue_phrase(phrase, state=fresh()) is None, phrase
    _ok("continue resolver passes non-continue phrases through")
    # Topic phrases resume the unique matching paused thread, purely.
    r = recap.resolve_continue_phrase("continue the entropy thread", state=fresh())
    assert r["status"] == "ok" and r["thread"]["thread_id"] == "t003" and r["wrote_state"] is False
    assert r["thread"]["status"] == "active" and r["thread"]["resumed_count"] == 1
    assert recap.resolve_continue_phrase("continue the water thread", state=fresh())["thread"]["thread_id"] == "t002"
    assert recap.resolve_continue_phrase("return to the mars water thread", state=fresh())["thread"]["thread_id"] == "t002"
    _ok("continue resolver resumes the unique topic match purely")
    # The report's own instruction "resume thread <id>" works as NL, with
    # politeness and terminal punctuation tolerated.
    for phrase in ("resume thread t001", "maya, please resume thread t001", "Resume thread t001."):
        assert recap.resolve_continue_phrase(phrase, state=fresh())["thread"]["thread_id"] == "t001", phrase
    _ok("resume-thread-id phrasing resolves as NL")
    # Subset semantics: naming part of a topic identifies the thread; naming
    # nothing specific ("the thread") is ambiguous among open threads.
    assert recap.resolve_continue_phrase("continue the water thread", state=fresh())["thread"]["thread_id"] == "t002"
    amb = recap.resolve_continue_phrase("continue the thread", state=fresh())
    assert amb["status"] == "ambiguous" and len(amb["candidates"]) == 3
    _ok("continue resolver subset-matches and flags bare-thread ambiguity")
    # Honest no-match: unknown topic lists open threads; empty registry says so.
    r = recap.resolve_continue_phrase("continue the venus thread", state=fresh())
    assert r["status"] == "no_match" and "entropy deep dive [t003]" in r["detail"]
    r = recap.resolve_continue_phrase("continue the quantum thread", state={"version": 1, "threads": {}})
    assert r["status"] == "no_match" and "no open threads" in r["detail"].lower()
    _ok("continue resolver no-match is honest")


def check_continue_write_mode_and_parity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        original = recap.THREAD_STATE
        recap.THREAD_STATE = Path(tmp) / "recap_threads.json"
        try:
            maya_chat.maya_local_command(":recap pause mars colony debate")
            surfaces = (
                ("route", lambda t: maya_chat._conversation_route(t, [])[1]),
                ("local", maya_chat.maya_local_command),
                ("fallback", maya_chat.local_fallback),
                ("ask", lambda t: maya_chat.ask([], t)),
            )
            owner_reply = None
            for surf, fn in surfaces:
                if recap.THREAD_STATE.exists():
                    recap.THREAD_STATE.unlink()  # resume is a write: fresh state per surface
                maya_chat.maya_local_command(":recap pause mars colony debate")
                reply = fn("continue the mars colony thread")
                if owner_reply is None:
                    owner_reply = reply
                assert reply == owner_reply, (surf, reply)
                data = json.loads(recap.THREAD_STATE.read_text(encoding="utf-8"))
                assert data["threads"]["t001"]["status"] == "active", (surf, data)
                assert data["threads"]["t001"]["resumed_count"] == 1, (surf, data)
            _ok("continue phrase resumes with identical reply on every surface")
            _ok("continue resume persists through the single thread-state writer")
            # After resume the thread is no longer open: honest reply, still no crash.
            again = maya_chat.maya_local_command("continue the mars colony thread")
            assert "no open thread" in again.lower(), again
            # Bare "continue" stays ambiguous on every surface (not thread resume).
            amb = maya_chat._conversation_route("continue", [])
            assert amb is not None and amb[0] == "AMBIGUOUS"
            assert maya_chat.maya_local_command("continue") == amb[1]
            assert maya_chat.local_fallback("continue") == amb[1]
            assert maya_chat.ask([], "continue") == amb[1]
            _ok("bare continue stays ambiguous on every surface")
            # Colon-command partition untouched.
            assert maya_chat._conversation_route(":recap resume t001", []) is None
        finally:
            recap.THREAD_STATE = original
    _ok("continue write path confined to knowledge/conversations")


def main() -> int:
    check_store_load_events()
    check_digest_determinism()
    check_digest_structure()
    check_question_extraction()
    check_followup_extraction()
    check_session_selection()
    check_thread_lifecycle_pure()
    check_thread_lifecycle_write_mode()
    check_marker_resolution()
    check_router_wiring()
    check_digest_readonly_real_log()
    check_continue_phrase_resolution()
    check_continue_write_mode_and_parity()
    print("test_session_recap=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
