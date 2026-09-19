"""Bridge update change-detection + coalescing suite.

Two layers, one constant contract (anchored in ``verification/manifest.py``
``SUITE_CONTRACTS["test_bridge_updates.py"]``):

- pure, interpreter-invariant checks of the deterministic helpers added to
  ``maya_runtime.ui.qt.bridge`` (canonical equality, volatile-field-excluded
  view fingerprints, monotonic revisioning, bounded latest-state coalescing,
  meaningful-event bypass, sanitized versioned deltas);
- an offscreen Qt harness (``qt_update_harness.py``) executed on the PySide6
  project venv that proves the real ``Controller`` never re-emits an identical
  or volatile-only view, coalesces rapid real changes to the latest state,
  bypasses coalescing for safety transitions and meaningful events, resets
  immediately, stamps a strictly increasing revision, and force-flushes a held
  update when the window closes.

Skills: prints only benign ``=OK`` labels and ``key=value`` summaries. No
free-form text, no tracebacks on the passing path.
"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# --- import the pure bridge FIRST: it must never require PySide6 ----------
from maya_runtime.ui.qt import bridge as ui_bridge  # noqa: E402


def _ok(name):
    print(f"={name}=OK")


def _view(**over):
    base = {
        "frame": 0,
        "shape": [0, 1],
        "ring": [0, 1],
        "pointer": {"x": 0.0},
        "face": {"frame": 0},
        "face_digest": "d",
        "learning": "off",
        "resources": "safe",
        "core": {"state": "idle", "implies_failure": False},
        "ui": {"healthy": True, "pending": []},
        "live_lines": ["l1", "l2", "l3", "l4", "l5", "l6", "l7"],
    }
    base.update(over)
    return base


# ---- 1. pure import surface ----------------------------------------------
assert "PySide6" not in ui_bridge.__dict__, "bridge references PySide6"
for _name in ("canonical", "canonical_json", "stable_projection",
              "view_fingerprint", "input_signature", "changed_keys",
              "minimize_payload", "payload_is_sanitized", "is_meaningful",
              "ChangeTracker", "UpdateCoalescer", "MEANINGFUL_EVENTS",
              "VOLATILE_VIEW_FIELDS"):
    assert hasattr(ui_bridge, _name), _name
_ok("bridgeupd_pure_import_ok")


# ---- 2. canonical form is deterministic and non-mutating -----------------
_original = {"b": 1, "a": {"d": 2, "c": [3, {"z": 0, "y": 1}]}}
_canon = ui_bridge.canonical(_original)
assert _canon == {"a": {"c": [3, {"y": 1, "z": 0}], "d": 2}, "b": 1}, _canon
assert list(_canon) == ["a", "b"]
assert ui_bridge.canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
assert _original == {"b": 1, "a": {"d": 2, "c": [3, {"z": 0, "y": 1}]}}
_ok("bridgeupd_canonical_ok")


# ---- 3. view fingerprints ignore volatile animation fields ---------------
_base = _view()
_volatile = _view(frame=99, shape=[9], ring=[9], pointer={"x": 9.0},
                  face={"frame": 99}, face_digest="z")
assert ui_bridge.view_fingerprint(_base) == \
    ui_bridge.view_fingerprint(_volatile)
_meaningful_change = _view(learning="on")
assert ui_bridge.view_fingerprint(_base) != \
    ui_bridge.view_fingerprint(_meaningful_change)
assert ui_bridge.stable_projection(_base)["learning"] == "off"
assert "frame" not in ui_bridge.stable_projection(_base)
_ok("bridgeupd_volatile_fingerprint_ok")


# ---- 4. change tracker: first / changed / unchanged / reset --------------
_tracker = ui_bridge.ChangeTracker()
assert _tracker.classify({"a": 1}) == "first"
assert _tracker.commit({"a": 1}) == 1
assert _tracker.classify({"a": 1}) == "unchanged"
assert _tracker.classify({"a": 2}) == "changed"
assert _tracker.commit({"a": 2}) == 2
assert _tracker.revision == 2
_tracker.reset()
assert _tracker.revision == 0 and _tracker.classify({"a": 1}) == "first"
_ok("bridgeupd_change_tracker_ok")


# ---- 5. coalescer: first due, interval gates the rest --------------------
_co = ui_bridge.UpdateCoalescer(interval_ms=50)
assert _co.offer("v1", revision=1, now_ms=0) is True
assert _co.offer("v2", revision=2, now_ms=10) is False
assert _co.has_pending
assert _co.flush(20) is None
_pending = _co.flush(50)
assert _pending == {"view": "v2", "revision": 2, "reason": None}, _pending
assert not _co.has_pending
assert _co.offer("v3", revision=3, now_ms=100) is True
_ok("bridgeupd_coalescer_first_interval_ok")


# ---- 6. coalescer is bounded and keeps only the latest state -------------
_co = ui_bridge.UpdateCoalescer(interval_ms=50)
_co.offer("a", revision=1, now_ms=0)
_co.offer("b", revision=2, now_ms=5)
_co.offer("c", revision=3, now_ms=10)
assert isinstance(_co.pending, dict)
assert _co.pending["view"] == "c" and _co.pending["revision"] == 3
_ok("bridgeupd_coalescer_latest_bounded_ok")


# ---- 7. meaningful events always bypass coalescing -----------------------
_co = ui_bridge.UpdateCoalescer(interval_ms=50)
_co.offer("a", revision=1, now_ms=0)
assert _co.offer("b", revision=2, reason="approval", now_ms=5) is True
assert not _co.has_pending
for _reason in ("approval", "denial", "refusal", "cancellation", "timeout",
                "failure", "completion", "safety", "conversation"):
    assert ui_bridge.is_meaningful(_reason), _reason
assert not ui_bridge.is_meaningful(None)
assert not ui_bridge.is_meaningful("tick")
assert ui_bridge.MEANINGFUL_EVENTS == frozenset(
    {"approval", "denial", "refusal", "cancellation", "timeout", "failure",
     "completion", "safety", "conversation"})
_ok("bridgeupd_coalescer_meaningful_ok")


# ---- 8. force flush drains a pending update, once ------------------------
_co = ui_bridge.UpdateCoalescer(interval_ms=1000)
_co.offer("a", revision=1, now_ms=0)
_co.offer("b", revision=2, now_ms=1)
assert _co.flush(2) is None
assert _co.flush(2, force=True)["view"] == "b"
assert not _co.has_pending
assert _co.flush(2, force=True) is None
_ok("bridgeupd_coalescer_force_flush_ok")


# ---- 9. deltas are versioned, minimal and ordered ------------------------
_prev = {"a": 1, "b": 2}
_curr = {"a": 1, "b": 3, "c": 4}
assert ui_bridge.minimize_payload(_prev, _prev) is None
_delta = ui_bridge.minimize_payload(_curr, _prev, base_revision=2,
                                    revision=3, generation=7)
assert _delta["changed"] == ["b", "c"], _delta
assert _delta["patch"] == {"b": 3, "c": 4}, _delta
assert _delta["base_revision"] == 2 and _delta["revision"] == 3
assert _delta["generation"] == 7
assert ui_bridge.changed_keys(_prev, _curr) == ["b", "c"]
_ok("bridgeupd_minimize_payload_ok")


# ---- 10. payload sanitization rejects secret-shaped keys -----------------
assert ui_bridge.payload_is_sanitized(
    {"a": 1, "nested": {"b": [{"c": "x"}]}})
assert ui_bridge.payload_is_sanitized(_view())
assert not ui_bridge.payload_is_sanitized({"api_key": "x"})
assert not ui_bridge.payload_is_sanitized({"nested": {"password": "x"}})
assert not ui_bridge.payload_is_sanitized([{"private_key_id": "x"}])
assert not ui_bridge.payload_is_sanitized({"auth_token": "x"})
_ok("bridgeupd_payload_sanitized_ok")


# ---- 11. input signatures are canonical and state-sensitive --------------
assert ui_bridge.input_signature({"a": 1}, {"b": 2}) == \
    ui_bridge.input_signature({"a": 1}, {"b": 2})
assert ui_bridge.input_signature({"a": 1}) != \
    ui_bridge.input_signature({"a": 2})
assert ui_bridge.input_signature(None, {"b": 2}) != \
    ui_bridge.input_signature(None, {"b": 3})
assert ui_bridge.input_signature({"a": 1, "b": 2}) == \
    ui_bridge.input_signature({"b": 2, "a": 1})
_ok("bridgeupd_input_signature_ok")


# ==========================================================================
# offscreen Qt harness (venv): controller update policy
# ==========================================================================
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


_QT_CHECKS = (
    "identical_suppressed",
    "volatile_only_suppressed",
    "coalesced_flush_latest",
    "pending_bounded",
    "view_level_suppressed",
    "meaningful_bypasses",
    "safety_bypasses",
    "revision_monotonic",
    "reset_immediate",
    "delta_versioned_sanitized",
    "close_flushes_final",
)

_HARNESS = {"done": False, "checks": {}, "error": ""}


def _run_harness():
    if _HARNESS["done"]:
        return _HARNESS
    _HARNESS["done"] = True
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    try:
        proc = subprocess.run(
            [_venv_python(), str(_REPO / "qt_update_harness.py")],
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
    _ok("bridgeupd_qt_" + name + "_ok")


def _assert_harness_complete():
    data = _run_harness()
    missing = [n for n in _QT_CHECKS if n not in data["checks"]]
    assert not missing, data["error"] or ("missing " + ",".join(missing))
    _ok("bridgeupd_qt_harness_complete_ok")


def main():
    for _name in _QT_CHECKS:
        _require(_name)
    _assert_harness_complete()
    print("status=pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
