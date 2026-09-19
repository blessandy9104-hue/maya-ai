"""Maya Intelligence Core — presentation-only visual state model.

This module turns Maya's *authoritative* runtime state into a bounded,
deterministic visual description of what Maya is doing and what she is
authorized to do. It is the data source for the ``IntelligenceCore.qml``
surface: concentric structured layers, orbital rings, signal lines and
connection nodes that surround the canonical face.

Contract:
- It never executes anything, never writes, never touches memory, identity,
  permissions, or the trust registry. It is a pure read of already-authoritative
  state plus a pure projection into unit-space geometry.
- It is fail-closed. ``complete`` (the only success state) is only ever returned
  on an affirmative authorization *and* an affirmative verification flag.
  Missing, empty, unknown, or contradictory authority data resolves to
  ``unavailable``; an unsafe resource report resolves to ``error``.
- ``unavailable`` and ``error`` can never carry active capability/authority
  nodes, so a failure can never be painted as capable, authorized or successful.
- No randomness, no wall clock. Identical inputs give byte-identical payloads
  (including the self-consistent ``digest``), so the surface can be replayed
  and validated exactly.

State inputs are read read-only from ``maya_safety_monitor`` (resource signal),
``maya_trust`` (validated-capability overlay) and the trust action log (latest
authorization/verification decision). Nothing here is imported by those layers,
so the core keeps working if this module is absent.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA = "maya/intelligence-core/1.0.0"

STATES = (
    "idle", "observing", "reasoning", "approval", "acting",
    "verifying", "complete", "unavailable", "error",
)
SUCCESS_STATES = ("complete",)
FAILURE_STATES = ("unavailable", "error")

LABELS = {
    "idle": "IDLE",
    "observing": "OBSERVING",
    "reasoning": "REASONING",
    "approval": "APPROVAL REQUIRED",
    "acting": "ACTING",
    "verifying": "VERIFYING",
    "complete": "COMPLETE",
    "unavailable": "UNAVAILABLE",
    "error": "ERROR",
}

DESCRIPTIONS = {
    "idle": "present and ready; no task in progress",
    "observing": "collecting permitted context only",
    "reasoning": "reasoning over permitted context",
    "approval": "waiting for your approval before doing anything",
    "acting": "performing a permitted, bounded action",
    "verifying": "authorized; result not yet verified",
    "complete": "verified result",
    "unavailable": "authority data unavailable; Maya is not acting",
    "error": "action or resource error; Maya is not acting",
}

COLOR_KEYS = {
    "idle": "accent",
    "observing": "cyan",
    "reasoning": "accent2",
    "approval": "warn",
    "acting": "ok",
    "verifying": "cyan",
    "complete": "ok",
    "unavailable": "muted",
    "error": "bad",
}

PATTERNS = {
    "idle": {"ticks": 8, "dash_on": 3, "dash_off": 5, "contours": 3, "wobble": 0.0},
    "observing": {"ticks": 12, "dash_on": 4, "dash_off": 4, "contours": 3, "wobble": 0.010},
    "reasoning": {"ticks": 16, "dash_on": 2, "dash_off": 2, "contours": 4, "wobble": 0.020},
    "approval": {"ticks": 4, "dash_on": 1, "dash_off": 3, "contours": 3, "wobble": 0.0},
    "acting": {"ticks": 20, "dash_on": 5, "dash_off": 1, "contours": 4, "wobble": 0.015},
    "verifying": {"ticks": 14, "dash_on": 1, "dash_off": 1, "contours": 5, "wobble": 0.010},
    "complete": {"ticks": 24, "dash_on": 6, "dash_off": 0, "contours": 5, "wobble": 0.0},
    "unavailable": {"ticks": 0, "dash_on": 0, "dash_off": 8, "contours": 2, "wobble": 0.0},
    "error": {"ticks": 2, "dash_on": 1, "dash_off": 5, "contours": 2, "wobble": 0.030},
}

NODES = ("presence", "capabilities", "trust", "memory",
         "tasks", "authority", "learning", "context")

NODE_LABELS = {
    "presence": "presence",
    "capabilities": "capabilities",
    "trust": "trust",
    "memory": "memory",
    "tasks": "tasks",
    "authority": "authority",
    "learning": "learning",
    "context": "context",
}

VERDICTS = ("allowed", "prepare_only", "requires_approval", "refused")
TRUST_STATUSES = ("available", "unavailable", "untrusted", "pending_validation")
TRUST_SCHEMA = "trusted_capability.v1"

_TAU = 6.283185307179586
_CONTOUR_RADII = (0.440, 0.350, 0.260, 0.170, 0.100)
_RING_RADII = ((0.460, 0.300), (0.300, 0.460))
_NODE_RADIUS = 0.460
_CONTOUR_SAMPLES = 48
_RING_SAMPLES = 32
_MAX_INDICATORS = 64


def _round(value: float, ndigits: int = 6) -> float:
    return round(float(value), int(ndigits))


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def trust_ok(overview: Any) -> bool:
    """True only for a well-formed trust overlay with a non-empty inventory.

    Any other shape (None, a non-dict, a missing/empty inventory, or an
    unrecognized status) is treated as unavailable authority data.
    """
    if not isinstance(overview, dict):
        return False
    if overview.get("schema") not in (TRUST_SCHEMA, None):
        return False
    capabilities = overview.get("capabilities")
    if not isinstance(capabilities, dict) or not capabilities:
        return False
    for status in capabilities.values():
        if status not in TRUST_STATUSES:
            return False
    return True


def _authority_verdict(authority: Any) -> str | None:
    if not isinstance(authority, dict):
        return None
    verdict = authority.get("verdict", authority.get("decision"))
    return verdict if verdict in VERDICTS else None


def derive_state(activity: str = "idle", resources: Any = "unavailable",
                 trust: Any = None, authority: Any = None,
                 verified: bool | None = None) -> tuple[str, str]:
    """Resolve the nine-state visual state, fail-closed. Returns (state, why)."""
    if resources not in ("safe", "unsafe"):
        return "unavailable", f"resource signal not affirmative ({resources!r})"
    if resources == "unsafe":
        return "error", "resource monitor reports unsafe"
    if not trust_ok(trust):
        return "unavailable", "authority data missing, empty or malformed"

    if authority is not None:
        if not isinstance(authority, dict):
            return "unavailable", "authority record malformed"
        verdict = _authority_verdict(authority)
        if verdict is None:
            return "unavailable", "authority verdict unknown"
        vf = bool(authority.get("verification_supported"))
        if verdict == "requires_approval":
            return "approval", "owner approval required before any action"
        if verdict == "refused":
            status = authority.get("status")
            if status in ("unavailable", "untrusted"):
                return "unavailable", f"capability {status}"
            return "error", "action refused"
        if verdict == "prepare_only":
            return "acting", "safe preparation only; not execution"
        if verdict == "allowed":
            if verified if verified is not None else vf:
                return "complete", "authorized and result verified"
            return "verifying", "authorized; result not yet verified"

    if activity == "listening":
        return "observing", "collecting permitted context only"
    if activity == "processing":
        return "reasoning", "reasoning over permitted context"
    if activity == "research":
        return "acting", "permitted, bounded research action"
    return "idle", "present and ready"


def _node_active(node: str, state: str, activity: str,
                 trusted_count: int) -> bool:
    if state in FAILURE_STATES:
        return False
    if node == "presence":
        return state != "unavailable"
    if node == "context":
        return True
    if node == "learning":
        return activity != "idle"
    if node == "capabilities":
        return trusted_count > 0
    if node == "trust":
        return state == "complete" or trusted_count > 0
    if node == "authority":
        return state in ("approval", "acting", "verifying", "complete")
    if node == "tasks":
        return state in ("acting", "verifying", "complete")
    if node == "memory":
        return state in ("observing", "reasoning", "acting",
                         "verifying", "complete")
    return False


def _contour(radius: float, wobble: float, phase: float) -> list:
    pts = []
    for i in range(_CONTOUR_SAMPLES):
        theta = phase + _TAU * i / _CONTOUR_SAMPLES
        r = radius + wobble * math.sin(3.0 * theta)
        pts.append([_round(0.5 + r * math.cos(theta)),
                    _round(0.5 + r * math.sin(theta))])
    return pts


def _ring_segments(rx: float, ry: float, dash_on: int, dash_off: int,
                   phase: float) -> list:
    if dash_on <= 0:
        return []
    period = dash_on + dash_off
    segments, current = [], []
    for i in range(_RING_SAMPLES + 1):
        theta = phase + _TAU * (i % _RING_SAMPLES) / _RING_SAMPLES
        keep = (i % period) < dash_on if i < _RING_SAMPLES else False
        if keep:
            current.append([_round(0.5 + rx * math.cos(theta)),
                            _round(0.5 + ry * math.sin(theta))])
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def _geometry(state: str, activity: str, trusted_count: int) -> dict:
    pattern = PATTERNS[state]
    phase = 0.0
    contours = [_contour(_CONTOUR_RADII[i], pattern["wobble"], phase)
                for i in range(pattern["contours"])]
    rings = [{"rx": rx, "ry": ry,
              "segments": _ring_segments(rx, ry, pattern["dash_on"],
                                         pattern["dash_off"], phase)}
             for rx, ry in _RING_RADII]
    nodes, signals = [], []
    for i, node in enumerate(NODES):
        theta = _TAU * i / len(NODES)
        nx = 0.5 + _NODE_RADIUS * math.cos(theta)
        ny = 0.5 + _NODE_RADIUS * math.sin(theta)
        active = _node_active(node, state, activity, trusted_count)
        nodes.append({"id": node, "label": NODE_LABELS[node],
                      "x": _round(nx), "y": _round(ny),
                      "active": bool(active)})
        signals.append({"node": node, "active": bool(active),
                        "x1": 0.5, "y1": 0.5,
                        "x2": _round(nx), "y2": _round(ny)})
    return {"center": [0.5, 0.5], "contours": contours,
            "rings": rings, "nodes": nodes, "signals": signals}


def _trust_summary(overview: Any) -> dict:
    if not isinstance(overview, dict):
        return {"counts": {s: 0 for s in TRUST_STATUSES}, "total": 0,
                "trusted": 0, "inventory_ok": False}
    capabilities = overview.get("capabilities")
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    counts = {s: 0 for s in TRUST_STATUSES}
    for status in capabilities.values():
        if status in counts:
            counts[status] += 1
    return {"counts": counts, "total": len(capabilities),
            "trusted": counts["available"],
            "inventory_ok": trust_ok(overview)}


def _authority_summary(authority: Any) -> dict | None:
    if not isinstance(authority, dict):
        return None
    verdict = _authority_verdict(authority)
    if verdict is None:
        return None
    return {
        "capability": str(authority.get("capability") or ""),
        "action": str(authority.get("action") or ""),
        "verdict": verdict,
        "decision": verdict,
        "result": str(authority.get("result") or ""),
        "status": str(authority.get("status") or ""),
        "approval_required": bool(authority.get("approval_required")),
        "owner_approval": bool(authority.get("owner_approval")),
        "verification_supported": bool(authority.get("verification_supported")),
    }


def build_core_view(activity: str = "idle", resources: Any = "unavailable",
                    trust: Any = None, authority: Any = None,
                    verified: bool | None = None) -> dict:
    """Pure projection of authoritative state into a deterministic payload."""
    activity = activity if activity in ("idle", "processing", "listening",
                                        "research") else "idle"
    state, reason = derive_state(activity=activity, resources=resources,
                                 trust=trust, authority=authority,
                                 verified=verified)
    summary = _trust_summary(trust)
    indicators = []
    if isinstance(trust, dict) and isinstance(trust.get("capabilities"), dict):
        for name in sorted(trust["capabilities"])[:_MAX_INDICATORS]:
            status = trust["capabilities"][name]
            if status not in TRUST_STATUSES:
                status = "pending_validation"
            active = status == "available" and state not in FAILURE_STATES
            indicators.append({"name": str(name), "status": status,
                               "active": active})
    pattern = dict(PATTERNS[state])
    payload = {
        "schema": SCHEMA,
        "state": state,
        "reason": reason,
        "label": LABELS[state],
        "description": DESCRIPTIONS[state],
        "color_key": COLOR_KEYS[state],
        "pattern": pattern,
        "severity": ("failure" if state in FAILURE_STATES
                     else "success" if state in SUCCESS_STATES
                     else "attention" if state == "approval"
                     else "active" if state != "idle" else "neutral"),
        "implies_success": state in SUCCESS_STATES,
        "implies_failure": state in FAILURE_STATES,
        "implies_authority_waiting": state == "approval",
        "fail_closed": state in FAILURE_STATES,
        "activity": activity,
        "trust": summary,
        "indicators": indicators,
        "authority": _authority_summary(authority),
        "geometry": _geometry(state, activity, summary["trusted"]),
    }
    payload["digest"] = _digest(payload)
    return payload


def _read_resources() -> str:
    try:
        from maya_safety_monitor import status
        result = status()
    except Exception:
        return "unavailable"
    if not isinstance(result, dict) or not result.get("monitor_available"):
        return "unavailable"
    return "safe" if result.get("safe") else "unsafe"


def _read_trust() -> Any:
    try:
        from maya_trust import registry_overview
        return registry_overview()
    except Exception:
        return None


def _read_authority() -> Any:
    try:
        from maya_trust import ACTION_LOG
        path = Path(ACTION_LOG)
        if not path.exists():
            return None
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and _authority_verdict(row) is not None:
                return row
        return None
    except Exception:
        return None


def runtime_core_view(activity: str = "idle", resources: Any = None) -> dict:
    """Read the live authoritative state and build the core view (never raises)."""
    try:
        if resources is None:
            resources = _read_resources()
        return build_core_view(activity=activity, resources=resources,
                               trust=_read_trust(),
                               authority=_read_authority())
    except Exception:
        return build_core_view(activity="idle", resources="unavailable")


if __name__ == "__main__":
    print(json.dumps(runtime_core_view(), indent=2, ensure_ascii=False))
