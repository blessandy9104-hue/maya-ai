"""Cognitive state bridge between Maya Core and the face (must stay read-only)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

import maya_state_signals as signals

ALL_ACTIVITIES = ("idle", "processing", "listening", "research")


def _snapshot_is_read_only():
    for path in (signals.SERVICE_STATE, signals.ACTIVATION_STATE,
                 signals.PRESENCE_STATUS, signals.RESOURCE_STATE):
        try:
            before = path.read_bytes() if path.exists() else None
            signals.snapshot("idle")
            after = path.read_bytes() if path.exists() else None
            assert before == after, f"{path.name} was modified by snapshot()"
        except FileNotFoundError:
            pass
    return True


def test_snapshot_shape():
    snap = signals.snapshot("idle")
    for key in ("presence", "activity", "learning", "conversation",
                "expression_signal", "resources", "raw"):
        assert key in snap, key
    assert snap["activity"] == "idle"
    assert snap["conversation"] == "idle"
    assert snap["expression_signal"] == "calm"


def test_snapshot_activity_mapping():
    expected = {"idle": "calm", "processing": "focused",
                "listening": "attentive", "research": "analytical"}
    for activity, expr in expected.items():
        snap = signals.snapshot(activity)
        assert snap["activity"] == activity
        assert snap["expression_signal"] == expr
        assert snap["conversation"] == ("active" if activity != "idle" else "idle")


def test_snapshot_invalid_activity_falls_back():
    snap = signals.snapshot("sleepy")
    assert snap["activity"] == "idle"


def test_snapshot_is_read_only():
    assert _snapshot_is_read_only()


def test_activity_whitelist():
    for a in ALL_ACTIVITIES:
        assert a in signals.ACTIVITY_KEYS


def test_resource_signal_safe_mapping():
    assert signals.resource_signal({"safe": True, "monitor_available": True}) == "safe"
    assert signals.resource_signal({"safe": False, "monitor_available": True}) == "unsafe"
    assert signals.resource_signal({"safe": True, "monitor_available": False}) == "unavailable"
    assert signals.resource_signal({"safe": False, "monitor_available": False}) == "unavailable"


def test_resource_signal_fails_closed_on_malformed():
    assert signals.resource_signal([]) == "unavailable"
    assert signals.resource_signal("NOPE") == "unavailable"
    assert signals.resource_signal({}) == "unavailable"
    assert signals.resource_signal({"safe": True}) == "unavailable"


def test_snapshot_carries_authoritative_resource_signal():
    for expected in ("safe", "unsafe", "unavailable"):
        _real = signals.resource_signal

        def _inject():
            return expected

        try:
            signals.resource_signal = _inject
            snap = signals.snapshot("processing")
            assert snap["resources"] == expected
            assert snap["raw"]["resources"] == expected
        finally:
            signals.resource_signal = _real


def test_resource_signal_propagates_from_monitor_failure():
    import maya_safety_monitor as monitor
    _real_status = monitor.status

    def _boom():
        raise RuntimeError("monitor down")

    try:
        monitor.status = _boom
        assert signals.resource_signal() == "unavailable"
    finally:
        monitor.status = _real_status


for _name, _fn in sorted(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        _fn()
print("state_signals=OK")
print("signals_read_only=OK")