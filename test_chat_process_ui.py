"""Qt chat-subprocess integration suite (offscreen, PySide6 venv).

Delegates to :mod:`qt_chat_harness` on the project venv interpreter and turns
each machine-checkable ``check:<name>:pass`` line into an ``=OK`` label. The
harness drives the real Qt controller against a deterministic fake chat child
and verifies:

- the controller owns a bounded chat manager and warms the child;
- a normal turn streams the reply and returns the UI to idle;
- chat state updates flow through the UI-thread dispatch path;
- a crashed child produces an honest non-completion line and marks chat offline;
- an open pending item is reconciled when the child dies;
- closing the app terminates the child and joins every thread.

Skills: prints only benign ``=OK`` labels; subprocess output is captured and
never echoed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_EXPECTED = (
    "chatproc_launch",
    "chatproc_normal_turn",
    "chatproc_ui_thread_affinity",
    "chatproc_failure_honest",
    "chatproc_pending_reconcile",
    "chatproc_close_no_orphan",
)

_HARNESS = {"done": False, "checks": {}, "error": ""}


def _ok(label):
    print("=" + label + "=OK")


def _venv_python():
    candidates = (
        _REPO / "venv" / "Scripts" / "python.exe",
        _REPO / "venv" / "bin" / "python",
        _REPO / ".venv" / "Scripts" / "python.exe",
        _REPO / ".venv" / "bin" / "python",
    )
    for path in candidates:
        if path.exists():
            return str(path)
    return sys.executable


def _run_harness():
    if _HARNESS["done"]:
        return _HARNESS
    _HARNESS["done"] = True
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    try:
        proc = subprocess.run(
            [_venv_python(), str(_REPO / "qt_chat_harness.py")],
            capture_output=True, text=True, timeout=240, cwd=str(_REPO),
            env=env)
    except Exception as exc:  # noqa: BLE001
        _HARNESS["error"] = "%s: %s" % (type(exc).__name__, exc)
        return _HARNESS
    for line in proc.stdout.splitlines():
        if line.startswith("check:") and line.endswith(":pass"):
            _HARNESS["checks"][line.split(":")[1]] = True
    if not _HARNESS["checks"]:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        _HARNESS["error"] = " | ".join(tail) or "no harness output"
    return _HARNESS


def _require(name):
    data = _run_harness()
    assert name in data["checks"], data["error"] or ("missing check " + name)
    _ok("chatproc_ui_" + name + "_ok")


def test_chatproc_ui_launch_ok():
    _require("chatproc_launch")


def test_chatproc_ui_normal_turn_ok():
    _require("chatproc_normal_turn")


def test_chatproc_ui_thread_affinity_ok():
    _require("chatproc_ui_thread_affinity")


def test_chatproc_ui_failure_honest_ok():
    _require("chatproc_failure_honest")


def test_chatproc_ui_pending_reconcile_ok():
    _require("chatproc_pending_reconcile")


def test_chatproc_ui_close_no_orphan_ok():
    _require("chatproc_close_no_orphan")


def test_chatproc_ui_harness_complete_ok():
    data = _run_harness()
    missing = [n for n in _EXPECTED if n not in data["checks"]]
    assert not missing, data["error"] or ("missing " + ",".join(missing))
    _ok("chatproc_ui_harness_complete_ok")


if __name__ == "__main__":
    for _name in sorted(
            n for n in dir() if n.startswith("test_")
            and callable(globals().get(n))
            and getattr(globals().get(n), "__module__", "") == "__main__"):
        globals()[_name]()
    print("test_chat_process_ui=PASS")
