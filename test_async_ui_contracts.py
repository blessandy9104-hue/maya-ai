"""Qt UI-thread contract suite for asynchronous orchestration.

Delegates to :mod:`qt_async_harness` (which needs PySide6) on the project venv
interpreter and turns each machine-checkable ``check:<name>:pass`` line into an
``=OK`` label. The harness verifies that:

- the Qt controller owns a bounded worker pool;
- ``_emit_view`` / ``_apply_pending_line`` mutate the bridge model on the UI
  thread even when called from a worker;
- a slow worker does not block the UI event loop;
- the pool stays within its bounds under load;
- ``closeNow`` joins the pool and stops accepting work.

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
    "bounded_executor",
    "emit_view_ui_thread",
    "apply_pending_ui_thread",
    "ui_responsive_during_work",
    "pool_bounded_under_load",
    "close_joins_pool",
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
            [_venv_python(), str(_REPO / "qt_async_harness.py")],
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
    _ok("async_ui_" + name + "_ok")


def test_async_ui_bounded_executor_ok():
    _require("bounded_executor")


def test_async_ui_emit_view_thread_ok():
    _require("emit_view_ui_thread")


def test_async_ui_apply_pending_thread_ok():
    _require("apply_pending_ui_thread")


def test_async_ui_responsive_during_work_ok():
    _require("ui_responsive_during_work")


def test_async_ui_pool_bounded_ok():
    _require("pool_bounded_under_load")


def test_async_ui_close_joins_pool_ok():
    _require("close_joins_pool")


def test_async_ui_harness_complete_ok():
    data = _run_harness()
    missing = [n for n in _EXPECTED if n not in data["checks"]]
    assert not missing, data["error"] or ("missing " + ",".join(missing))
    _ok("async_ui_harness_complete_ok")


if __name__ == "__main__":
    for _name in sorted(
            n for n in dir() if n.startswith("test_")
            and callable(globals().get(n))
            and getattr(globals().get(n), "__module__", "") == "__main__"):
        globals()[_name]()
    print("test_async_ui_contracts=PASS")
