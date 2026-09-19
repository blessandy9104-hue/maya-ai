"""Conversation-driven face verification suite.

Pins the bounded pathway from live conversation phases to the face pipeline:
the ``[face]`` machine-line protocol (producer in maya_chat, parser owner in
maya_runtime.face_drive, consumers in both interface readers), the mapping of
every conversation state onto a pre-validated semantic anchor, and the
end-to-end phase sequence of a real spawned chat process. The suite itself
never drives the face outside the existing VisualCommand contract.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_runtime.face_drive import (
    CONVERSATION_STATES,
    FACE_LINE_PREFIX,
    VISUAL_TO_SEMANTIC,
    parse_face_line,
    resolve_semantic,
)


def _ok(label: str) -> None:
    print(label + " =OK")


ROOT = Path(__file__).resolve().parent


def check_wire_protocol() -> None:
    assert FACE_LINE_PREFIX == "[face] "
    assert CONVERSATION_STATES == ("idle", "processing", "listening", "research")
    assert set(CONVERSATION_STATES) <= set(VISUAL_TO_SEMANTIC), "every conversation state must have a pre-validated semantic anchor"
    _ok("wire protocol bounded to pre-validated anchors")


def check_parser_tolerant() -> None:
    assert parse_face_line('[face] {"state": "listening"}') == "listening"
    assert parse_face_line('You: [face] {"state": "research"}') == "research"
    assert parse_face_line('garbage [face] {"state": "processing"} x') == "processing"
    assert parse_face_line('[face] {"state": "bogus"}') is None
    assert parse_face_line('[face] {"state": null}') is None
    assert parse_face_line('[face] not-json') is None
    assert parse_face_line('[face] []') is None
    assert parse_face_line('Maya: hello') is None
    assert parse_face_line(None) is None
    assert parse_face_line(123) is None
    assert parse_face_line('') is None
    _ok("parser tolerant to prompt-merged and malformed lines")


def check_anchor_mapping() -> None:
    assert resolve_semantic("listening") == "listening"
    assert resolve_semantic("processing") == "focused"
    assert resolve_semantic("research") == "focused"
    assert resolve_semantic("idle") == "neutral"
    _ok("conversation states map onto bounded semantic anchors")


def check_producer_gate() -> None:
    code = (
        "import io, sys, os;"
        "os.environ['MAYA_FACE_LINES']='1';"
        "import maya_chat;"
        "buf = io.StringIO(); old = sys.stdout; sys.stdout = buf;"
        "maya_chat._emit_face_state('listening'); maya_chat._emit_face_state('bogus');"
        "sys.stdout = old; print(repr(buf.getvalue()))"
    )
    enabled = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    assert enabled.returncode == 0
    assert enabled.stdout.count("[face]") == 1 and '"listening"' in enabled.stdout, enabled.stdout
    code_off = (
        "import io, sys, os;"
        "os.environ.pop('MAYA_FACE_LINES', None);"
        "import maya_chat;"
        "buf = io.StringIO(); old = sys.stdout; sys.stdout = buf;"
        "maya_chat._emit_face_state('listening');"
        "sys.stdout = old; print(repr(buf.getvalue()))"
    )
    disabled = subprocess.run([sys.executable, "-c", code_off], capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    assert disabled.returncode == 0
    assert "[face]" not in disabled.stdout
    _ok("producer emits only allowed states and only when enabled")


def check_spawner_enables_protocol() -> None:
    tk_source = (ROOT / "maya_app.py").read_text(encoding="utf-8")
    qt_source = (ROOT / "maya_runtime" / "ui" / "qt" / "app.py").read_text(encoding="utf-8")
    assert 'MAYA_FACE_LINES' in tk_source and tk_source.count('MAYA_FACE_LINES": "1"') == 1
    assert 'MAYA_FACE_LINES' in qt_source and qt_source.count('MAYA_FACE_LINES": "1"') == 1
    assert "parse_face_line" in tk_source and "parse_face_line" in qt_source
    _ok("both interface spawners enable the protocol and share the parser")


def check_chat_turn_sequence() -> None:
    """Real spawned chat: a deterministic turn goes listening -> idle."""
    env = dict(os.environ)
    env["MAYA_FACE_LINES"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "maya_chat.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1,
        cwd=str(ROOT), env=env,
    )
    lines: list[str] = []

    def reader() -> None:
        for line in proc.stdout:
            lines.append(line)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        time.sleep(2.0)
        proc.stdin.write("what is 2+2\n")
        proc.stdin.flush()
        time.sleep(2.5)
    finally:
        try:
            proc.stdin.write("exit\n")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(8)
        except Exception:
            proc.kill()
    states = [parse_face_line(line) for line in lines]
    states = [state for state in states if state is not None]
    assert "listening" in states, states
    assert states[0] == "listening", states
    assert states[-1] == "idle", states
    assert all(state in CONVERSATION_STATES for state in states)
    _ok("spawned chat turn: listening first, bounded throughout, idle at settle")


def check_research_phase_sequence() -> None:
    """Real spawned chat: an explicit research turn reaches the research phase."""
    env = dict(os.environ)
    env["MAYA_FACE_LINES"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "maya_chat.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1,
        cwd=str(ROOT), env=env,
    )
    lines: list[str] = []

    def reader() -> None:
        for line in proc.stdout:
            lines.append(line)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        time.sleep(2.0)
        proc.stdin.write("research black holes\n")
        proc.stdin.flush()
        deadline = time.time() + 25.0
        while time.time() < deadline:
            if any(parse_face_line(line) == "research" for line in lines):
                break
            time.sleep(0.2)
        time.sleep(1.0)
    finally:
        try:
            proc.stdin.write("exit\n")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(8)
        except Exception:
            proc.kill()
    states = [parse_face_line(line) for line in lines]
    states = [state for state in states if state is not None]
    assert "research" in states, states
    idx = states.index("research")
    assert states[0] == "listening", states
    assert states[-1] == "idle", states
    assert idx >= 1 and states[idx - 1] in ("listening", "processing")
    _ok("research turn passes through the research phase and settles to idle")


def check_plain_terminal_silent() -> None:
    result = subprocess.run(
        [sys.executable, "-u", str(ROOT / "maya_chat.py")],
        input="what is 2+2\nexit\n", capture_output=True, text=True,
        encoding="utf-8", timeout=45, cwd=str(ROOT),
        env={k: v for k, v in os.environ.items() if k != "MAYA_FACE_LINES"},
    )
    assert result.returncode == 0
    assert "[face]" not in result.stdout
    _ok("plain terminal use emits no face lines")


def check_typing_policy() -> None:
    """Typing overlay policy is owned by face_drive and bounded."""
    from maya_runtime.face_drive import TYPING_SETTLE_SECONDS, typing_activity
    assert typing_activity("idle") == "listening"
    assert typing_activity("listening") is None, "already listening"
    assert typing_activity("processing") is None, "never degrade a working state"
    assert typing_activity("research") is None, "never degrade a working state"
    assert typing_activity("bogus") is None
    assert TYPING_SETTLE_SECONDS > 0
    # The overlay value is itself a pre-validated anchor.
    assert "listening" in VISUAL_TO_SEMANTIC
    _ok("typing overlay bounded: only idle lifts, working states win")


def check_tk_typing_hook() -> None:
    """Tk interface: keystrokes overlay listening, settle is guarded."""
    tk_source = (ROOT / "maya_app.py").read_text(encoding="utf-8")
    assert 'self.chat_in.bind("<KeyRelease>", self._on_typing)' in tk_source
    assert "face_drive.typing_activity(self._activity)" in tk_source
    assert "face_drive.TYPING_SETTLE_SECONDS" in tk_source
    # Producer-driven states cancel the pending typing settle.
    assert "self._cancel_typing_settle()" in tk_source
    assert tk_source.count("_cancel_typing_settle") >= 4  # chat_send, run_action, _read_chat, consumer
    # Settle goes through the single state owner with a working-state guard.
    assert 'self.mail("activity_settle", None)' in tk_source
    assert 'elif kind == "activity_settle":' in tk_source
    settle_block = tk_source.split('elif kind == "activity_settle":', 1)[1]
    assert 'if self._activity == "listening":' in settle_block.split("elif", 1)[0]
    _ok("Tk typing hook cancels on producer state and settles guarded")


def check_qt_typing_hook() -> None:
    """Qt interface: QML keystrokes notify the controller; settle guarded;
    the chat reader thread never touches the QTimer."""
    qt_source = (ROOT / "maya_runtime" / "ui" / "qt" / "app.py").read_text(encoding="utf-8")
    qml_source = (ROOT / "maya_runtime" / "ui" / "qt" / "qml" / "Console.qml").read_text(encoding="utf-8")
    assert "Keys.onPressed: ui.notifyTyping()" in qml_source
    assert "def notifyTyping(self):" in qt_source
    assert "typing_activity(self._activity)" in qt_source
    assert "self._typing_timer.start()" in qt_source
    # Producer-driven paths stop the timer on the GUI thread only.
    assert qt_source.count("self._typing_timer.stop()") >= 3  # chatSend, enterCommand, _typing_settle
    # Thread-safety invariant: the chat reader (worker thread) must not
    # touch the QTimer; state changes flow through _set_activity only.
    reader_body = qt_source.split("def _read_chat", 1)[1].split("\n    def ", 1)[0]
    assert "_typing_timer" not in reader_body, "QTimer touched from worker thread"
    # Late settle fire is a no-op once a producer state took over.
    settle_body = qt_source.split("def _typing_settle", 1)[1].split("\n    def ", 1)[0]
    assert 'if self._activity == "listening":' in settle_body
    _ok("Qt typing hook thread-safe, producer-cancelled, settle guarded")


def main() -> int:
    check_wire_protocol()
    check_parser_tolerant()
    check_anchor_mapping()
    check_typing_policy()
    check_tk_typing_hook()
    check_qt_typing_hook()
    check_producer_gate()
    check_spawner_enables_protocol()
    check_chat_turn_sequence()
    check_research_phase_sequence()
    check_plain_terminal_silent()
    print("test_conversation_face=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
