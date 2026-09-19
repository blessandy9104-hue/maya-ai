"""Bounded subprocess lifecycle verification suite.

Exercises :mod:`maya_chat_process` against a deterministic fake chat child so
every terminal outcome is reproducible:

- normal completion delivers the reply and a stable correlation id/generation;
- protocol lines ([face]/[semantic]/[pending]) are forwarded in order and only
  to the active turn;
- delayed work completes; cancellation before launch removes queued work without
  running it; cancellation during execution terminates the child cooperatively
  then forcibly, leaving no orphan;
- turn timeout terminates the child; crash, nonzero exit, malformed output and
  partial output are distinguished honestly;
- launch failure is an explicit outcome, never an exception;
- duplicate request ids never run twice and never produce a second terminal;
- a late line after completion is idle text, never a second terminal outcome;
- page close and app shutdown drain queued + active turns and join every thread;
- idle TTL and the bounded queue keep the child count finite.

Skills: this module may print only benign lines (``=OK`` labels). No free-form
text, no tracebacks on the passing path.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import maya_chat_process as proc  # noqa: E402

_FAKE_SOURCE = '''\
import os
import sys
import time


def emit(text):
    sys.stdout.write(text + "\\n")
    sys.stdout.flush()


emit("Maya chat fake ready.")
emit("Face protocol on.")

for raw in sys.stdin:
    text = raw.rstrip("\\n")
    if text == "":
        continue
    sys.stderr.write("[Intent JSON: {\\"text\\": \\"x\\"}]\\n")
    sys.stderr.flush()
    if text == "exit":
        emit("")
        emit("Maya: Goodbye.")
        break
    if text.startswith("slow:"):
        time.sleep(float(text.split(":", 1)[1]))
        emit("[semantic] theme slow")
        emit("Maya: slow reply")
        emit("[face] idle")
        continue
    if text == "hang":
        emit("[face] processing")
        time.sleep(60)
        continue
    if text == "crash":
        os._exit(3)
    if text == "exitcode":
        sys.exit(4)
    if text == "malformed":
        emit("Maya: ")
        continue
    if text == "partial":
        emit("[semantic] partial")
        os._exit(0)
    if text == "pending":
        emit('[pending] {"items": [{"id": "p1", "status": "open"}]}')
        emit("Maya: needs approval")
        emit("[face] idle")
        continue
    if text == "late":
        emit("[semantic] first")
        emit("Maya: first reply")
        emit("[face] idle")
        time.sleep(0.15)
        emit("[semantic] late")
        emit("Maya: late reply")
        continue
    emit("[face] processing")
    emit("Maya: echo " + text)
    emit("[face] idle")
'''

_TMP = Path(tempfile.mkdtemp(prefix="maya_chatproc_"))
_FAKE = _TMP / "fake_chat.py"
_FAKE.write_text(_FAKE_SOURCE, encoding="utf-8", newline="\n")


def _ok(label):
    print("=" + label + "=OK")


class _Sink:
    def __init__(self):
        self.lock = threading.Lock()
        self.lines = []
        self.idle = []
        self.err = []
        self.results = []
        self.exits = []

    def line(self, kind, text, meta):
        with self.lock:
            self.lines.append((kind, text, meta))

    def idle_line(self, text):
        with self.lock:
            self.idle.append(text)

    def stderr_line(self, text):
        with self.lock:
            self.err.append(text)

    def done(self, result):
        with self.lock:
            self.results.append(result)

    def exited(self, code):
        with self.lock:
            self.exits.append(code)

    def results_for(self, request_id):
        with self.lock:
            return [r for r in self.results if r["request_id"] == request_id]

    def one(self, request_id):
        rows = self.results_for(request_id)
        assert len(rows) == 1, rows
        return rows[0]

    def kinds(self):
        with self.lock:
            return [k for k, _t, _m in self.lines]


def _make(sink, **kwargs):
    kwargs.setdefault("script", str(_FAKE))
    kwargs.setdefault("python", sys.executable)
    kwargs.setdefault("idle_ttl", 0.0)
    kwargs.setdefault("max_lifetime", 0.0)
    kwargs.setdefault("turn_timeout", 5.0)
    kwargs.setdefault("grace", 1.0)
    kwargs.setdefault("kill_grace", 1.0)
    kwargs.setdefault("poll", 0.02)
    kwargs.setdefault("on_line", sink.line)
    kwargs.setdefault("on_idle_line", sink.idle_line)
    kwargs.setdefault("on_stderr", sink.stderr_line)
    kwargs.setdefault("on_exit", sink.exited)
    return proc.ChatProcessManager(**kwargs)


def _wait(predicate, timeout=6.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _wait_active(manager, request_id, timeout=6.0):
    return _wait(lambda: manager.stats()["active"] == request_id, timeout)


# ---- 1. normal completion --------------------------------------------------

def test_chatproc_normal_completion_ok():
    sink = _Sink()
    m = _make(sink)
    try:
        ack = m.submit("hello", request_id="t1", generation=1,
                       on_done=sink.done)
        assert ack["accepted"] is True
        assert _wait(lambda: len(sink.results) == 1)
        result = sink.one("t1")
        assert result["outcome"] == proc.COMPLETED, result
        assert result["reply"].strip() == "Maya: echo hello"
        assert result["generation"] == 1
        assert "reply" in sink.kinds()
    finally:
        m.close()
    _ok("chatproc_normal_completion_ok")


# ---- 2. protocol lines in order -------------------------------------------

def test_chatproc_protocol_lines_ordered_ok():
    sink = _Sink()
    m = _make(sink)
    try:
        m.submit("pending", request_id="t2", generation=2, on_done=sink.done)
        assert _wait(lambda: len(sink.results) == 1)
        kinds = sink.kinds()
        assert kinds == ["pending", "reply"], kinds
        for _kind, _text, meta in sink.lines:
            assert meta == {"request_id": "t2", "generation": 2}, meta
        payload = [t for k, t, _m in sink.lines if k == "pending"][0]
        assert '"p1"' in payload
        assert sink.one("t2")["outcome"] == proc.COMPLETED
    finally:
        m.close()
    _ok("chatproc_protocol_lines_ordered_ok")


# ---- 3. delayed completion -------------------------------------------------

def test_chatproc_delayed_completion_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=5.0)
    try:
        started = time.monotonic()
        m.submit("slow:0.5", request_id="t3", on_done=sink.done)
        assert _wait(lambda: len(sink.results) == 1)
        elapsed = time.monotonic() - started
        assert elapsed >= 0.4, elapsed
        assert sink.one("t3")["outcome"] == proc.COMPLETED
    finally:
        m.close()
    _ok("chatproc_delayed_completion_ok")


# ---- 4. cancel before launch ----------------------------------------------

def test_chatproc_cancel_before_launch_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=5.0)
    try:
        m.submit("slow:0.6", request_id="t4a", on_done=sink.done)
        assert _wait_active(m, "t4a")
        m.submit("hello", request_id="t4b", on_done=sink.done)
        assert m.cancel("t4b") == "queued"
        result = sink.one("t4b")
        assert result["outcome"] == proc.CANCELLED, result
        assert result["reason"] == "cancelled_before_execution"
        assert _wait(lambda: len(sink.results_for("t4a")) == 1)
        assert sink.results_for("t4b")[0]["outcome"] == proc.CANCELLED
        assert not any(k == "reply" and m2 == "t4b"
                       for k, _t, m2 in sink.lines)
    finally:
        m.close()
    _ok("chatproc_cancel_before_launch_ok")


# ---- 5. cancel during execution -------------------------------------------

def test_chatproc_cancel_during_execution_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=30.0)
    try:
        m.submit("hang", request_id="t5", on_done=sink.done)
        assert _wait_active(m, "t5")
        assert m.cancel("t5") == "running"
        result = sink.one("t5")
        assert result["outcome"] == proc.CANCELLED, result
        assert result["reason"] == "cancelled_by_user"
        assert _wait(lambda: m.child_alive() == 0)
    finally:
        m.close()
    assert m.child_alive() == 0
    _ok("chatproc_cancel_during_execution_ok")


# ---- 6. timeout terminates ------------------------------------------------

def test_chatproc_timeout_terminates_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=0.3)
    try:
        m.submit("hang", request_id="t6", on_done=sink.done)
        assert _wait(lambda: len(sink.results_for("t6")) == 1)
        result = sink.one("t6")
        assert result["outcome"] == proc.TIMEOUT, result
        assert result["reason"] == "turn_timeout"
        assert _wait(lambda: m.child_alive() == 0)
    finally:
        m.close()
    _ok("chatproc_timeout_terminates_ok")


# ---- 7. crash / nonzero exit ----------------------------------------------

def test_chatproc_crash_nonzero_ok():
    sink = _Sink()
    m = _make(sink)
    try:
        m.submit("crash", request_id="t7", on_done=sink.done)
        assert _wait(lambda: len(sink.results_for("t7")) == 1)
        result = sink.one("t7")
        assert result["outcome"] == proc.NONZERO_EXIT, result
        assert result["returncode"] == 3, result
        assert m.child_alive() == 0
    finally:
        m.close()
    _ok("chatproc_crash_nonzero_ok")


# ---- 8. partial output -----------------------------------------------------

def test_chatproc_partial_output_ok():
    sink = _Sink()
    m = _make(sink)
    try:
        m.submit("partial", request_id="t8", on_done=sink.done)
        assert _wait(lambda: len(sink.results_for("t8")) == 1)
        result = sink.one("t8")
        assert result["outcome"] == proc.PARTIAL, result
        assert result["reply"] is None
        assert "semantic" in sink.kinds()
    finally:
        m.close()
    _ok("chatproc_partial_output_ok")


# ---- 9. malformed output ---------------------------------------------------

def test_chatproc_malformed_output_ok():
    sink = _Sink()
    m = _make(sink)
    try:
        m.submit("malformed", request_id="t9", on_done=sink.done)
        assert _wait(lambda: len(sink.results_for("t9")) == 1)
        result = sink.one("t9")
        assert result["outcome"] == proc.MALFORMED, result
        assert result["reason"] == "empty_reply"
    finally:
        m.close()
    _ok("chatproc_malformed_output_ok")


# ---- 10. launch failure ----------------------------------------------------

def test_chatproc_launch_failure_ok():
    sink = _Sink()
    m = _make(sink, python=str(_TMP / "does_not_exist_python.exe"))
    try:
        ack = m.submit("hello", request_id="t10", on_done=sink.done)
        assert ack["accepted"] is True
        assert _wait(lambda: len(sink.results_for("t10")) == 1)
        result = sink.one("t10")
        assert result["outcome"] == proc.LAUNCH_FAILED, result
        assert m.child_alive() == 0
    finally:
        m.close()
    _ok("chatproc_launch_failure_ok")


# ---- 11. duplicate request id ---------------------------------------------

def test_chatproc_duplicate_request_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=5.0)
    try:
        m.submit("slow:0.5", request_id="t11", on_done=sink.done)
        assert _wait_active(m, "t11")
        again = m.submit("hello", request_id="t11", on_done=sink.done)
        assert again["accepted"] is False
        assert again["error"] == "duplicate"
        assert _wait(lambda: len(sink.results_for("t11")) == 1)
        assert sink.one("t11")["outcome"] == proc.COMPLETED
        assert m.stats()["duplicate"] == 1
    finally:
        m.close()
    _ok("chatproc_duplicate_request_ok")


# ---- 12. late line never a second terminal ---------------------------------

def test_chatproc_late_result_no_second_terminal_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=5.0)
    try:
        m.submit("late", request_id="t12", on_done=sink.done)
        assert _wait(lambda: len(sink.results_for("t12")) == 1)
        assert _wait(lambda: any("late reply" in t for t in sink.idle), 3.0)
        assert len(sink.results_for("t12")) == 1
        assert sink.one("t12")["reply"].strip() == "Maya: first reply"
    finally:
        m.close()
    _ok("chatproc_late_result_no_second_terminal_ok")


# ---- 13. page close drains active + queued --------------------------------

def test_chatproc_page_close_drains_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=30.0)
    try:
        m.submit("hang", request_id="t13a", on_done=sink.done)
        assert _wait_active(m, "t13a")
        m.submit("hello", request_id="t13b", on_done=sink.done)
        m.close()
        active = sink.one("t13a")
        queued = sink.one("t13b")
        assert active["outcome"] == proc.CANCELLED
        assert active["reason"] == "closed_during_execution"
        assert queued["outcome"] == proc.CANCELLED
        assert queued["reason"] == "closed_before_execution"
        assert m.child_alive() == 0
        assert m.threads_alive() == 0
    finally:
        m.close()
    _ok("chatproc_page_close_drains_ok")


# ---- 14. shutdown idempotent ----------------------------------------------

def test_chatproc_shutdown_idempotent_ok():
    sink = _Sink()
    m = _make(sink)
    try:
        m.submit("hello", request_id="t14", on_done=sink.done)
        assert _wait(lambda: len(sink.results) == 1)
        m.close()
        m.close()
        assert m.child_alive() == 0
        assert m.submit("hello", request_id="t14b")["accepted"] is False
    finally:
        m.close()
    _ok("chatproc_shutdown_idempotent_ok")


# ---- 15. idle TTL ----------------------------------------------------------

def test_chatproc_idle_ttl_terminates_ok():
    sink = _Sink()
    m = _make(sink, idle_ttl=0.3)
    try:
        m.submit("hello", request_id="t15", on_done=sink.done)
        assert _wait(lambda: len(sink.results) == 1)
        assert m.child_alive() == 1
        assert _wait(lambda: m.child_alive() == 0, 5.0)
        assert m.stats()["terminated"] >= 1
    finally:
        m.close()
    _ok("chatproc_idle_ttl_terminates_ok")


# ---- 16. bounded queue -----------------------------------------------------

def test_chatproc_bounded_queue_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=30.0, max_queue=1)
    try:
        m.submit("slow:1.0", request_id="t16a", on_done=sink.done)
        assert _wait_active(m, "t16a")
        second = m.submit("hello", request_id="t16b", on_done=sink.done)
        third = m.submit("hello", request_id="t16c", on_done=sink.done)
        assert second["accepted"] is True
        assert third["accepted"] is False, third
        assert third["error"] == proc.QUEUE_FULL
        assert m.queued_count() == 1
    finally:
        m.close()
    _ok("chatproc_bounded_queue_ok")


# ---- 17. stderr forwarded --------------------------------------------------

def test_chatproc_stderr_forwarded_ok():
    sink = _Sink()
    m = _make(sink)
    try:
        m.submit("hello", request_id="t17", on_done=sink.done)
        assert _wait(lambda: len(sink.results) == 1)
        assert _wait(lambda: any("[Intent JSON" in t for t in sink.err), 3.0)
    finally:
        m.close()
    _ok("chatproc_stderr_forwarded_ok")


# ---- 18. banner idle line --------------------------------------------------

def test_chatproc_banner_idle_line_ok():
    sink = _Sink()
    m = _make(sink)
    try:
        assert m.start() is not None
        assert _wait(lambda: any("fake ready" in t for t in sink.idle), 5.0)
        assert m.queued_count() == 0
    finally:
        m.close()
    _ok("chatproc_banner_idle_line_ok")


# ---- 19. no orphan after close --------------------------------------------

def test_chatproc_no_orphan_after_close_ok():
    sink = _Sink()
    m = _make(sink, turn_timeout=30.0)
    try:
        m.submit("hang", request_id="t19", on_done=sink.done)
        assert _wait_active(m, "t19")
        assert m.child_alive() == 1
        m.close()
        assert m.child_alive() == 0
        assert m.threads_alive() == 0
    finally:
        m.close()
    _ok("chatproc_no_orphan_after_close_ok")


if __name__ == "__main__":
    for _name in sorted(k for k in list(globals()) if k.startswith("test_")):
        globals()[_name]()
