"""Maya Cognitive State Layer — read-only state signal provider.

Sits on the Maya Core side of the boundary. It reads existing Maya state files
(never writes, never executes commands) and emits normalized cognitive signals
for the Identity Presentation / Visual Interface layers.

It does NOT depend on, or import, the maya_identity package. If the visual
layer is absent, the core keeps working; if this layer is absent, the visual
layer defaults to a safe sleeping state.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SERVICE_STATE = ROOT / "maya_service_state.json"
ACTIVATION_STATE = ROOT / "maya_activation_state.json"
PRESENCE_STATUS = ROOT / "presence_status.json"
RESOURCE_STATE = ROOT / "maya_resource_policy.json"

ACTIVITY_KEYS = ("idle", "processing", "listening", "research")


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def logical_state() -> dict:
    service = _read_json(SERVICE_STATE)
    activation = _read_json(ACTIVATION_STATE)
    presence = _read_json(PRESENCE_STATUS)

    service_status = None
    if service:
        service_status = service.get("status")
    if presence and isinstance(presence, dict):
        presence_mode = presence.get("status", "off")
    else:
        presence_mode = "off"
    learning = "on" if (activation and activation.get("active")) else "off"

    if service_status == "awake":
        presence = "awake"
    elif service_status is None:
        presence = "offline"
    else:
        presence = "sleeping"

    return {
        "service": service_status if service_status else "unknown",
        "presence": presence,
        "presence_mode": presence_mode,
        "learning": learning,
    }


def resource_signal(status_result: dict | None = None) -> str:
    """Normalized resource signal for GUI/state consumers.

    The authoritative source is ``maya_safety_monitor.status()``. This layer
    never fabricates resource state: ``safe`` is reported only when the
    monitor is available AND reports safe; an unsafe report maps to
    ``unsafe``; and any unavailable, malformed, or erroring report maps to
    ``unavailable`` (fail closed). Consumers render anything other than
    ``safe`` as a warning/error, so the mapping keeps them fail-closed.
    """
    if status_result is None:
        try:
            from maya_safety_monitor import status
            status_result = status()
        except Exception:
            return "unavailable"
    if not isinstance(status_result, dict):
        return "unavailable"
    if not status_result.get("monitor_available"):
        return "unavailable"
    return "safe" if status_result.get("safe") else "unsafe"


def snapshot(activity: str = "idle") -> dict:
    activity = activity if activity in ACTIVITY_KEYS else "idle"
    state = logical_state()
    expression = {
        "idle": "calm",
        "processing": "focused",
        "listening": "attentive",
        "research": "analytical",
    }[activity]
    resources = resource_signal()
    return {
        "presence": state["presence"],
        "activity": activity,
        "learning": state["learning"],
        "conversation": "active" if activity != "idle" else "idle",
        "expression_signal": expression,
        "resources": resources,
        "raw": {
            "service": state["service"],
            "learning": state["learning"],
            "presence_mode": state["presence_mode"],
            "resources": resources,
        },
    }


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(snapshot(), indent=2))