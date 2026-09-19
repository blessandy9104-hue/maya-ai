"""Maya Intelligence Core verification suite.

Verifies the presentation-only visual state model end to end at the pure Python
layer (runs on every interpreter, no Qt required):

- the nine states (idle, observing, reasoning, approval, acting, verifying,
  complete, unavailable, error) each resolve deterministically from
  authoritative runtime inputs;
- fail-closed rules: missing / empty / malformed / unknown authority data and a
  malformed or unavailable resource signal all resolve to ``unavailable``; an
  unsafe resource signal resolves to ``error``; ``complete`` (the only success
  state) requires an affirmative authorization *and* verification;
- unavailable / error can never carry an active capability, authority, task or
  trust node, so a failure can never be painted as safe, authorized or
  successful, and a calm/active state never implies success;
- bounded, deterministic unit-space geometry and a self-consistent digest;
- the QML surface is presentation-only and schema-gated, Home keeps a single
  canonical face surface, and Main routes the core payload;
- the pure bridge exposes the core additively without changing existing keys;
- real-runtime drive: the actual trust gate + action log produce
  complete/unavailable states that the core view matches;
- the real registry and action log are never written.

Skills: this module may print only benign lines (``=OK`` labels). No free-form
text, no tracebacks on the passing path.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import maya_intelligence_core as core  # noqa: E402
import maya_trust as trust  # noqa: E402
import maya_trust_commands as trust_cmd  # noqa: E402
from maya_runtime.ui.qt import bridge as ui_bridge  # noqa: E402

ROOT = _REPO
QML = ROOT / "maya_runtime" / "ui" / "qt" / "qml"

trust.set_clock(lambda: 1234.0)
PROBE_OK = {"available": True}

_GOOD_TRUST = {
    "schema": "trusted_capability.v1",
    "capabilities": {"conversation": "available",
                     "research": "pending_validation",
                     "world model": "untrusted"},
}


def _ok(name: str) -> None:
    print(f"={name}=OK")


def _auth(verdict, **over):
    row = {"capability": "language_model", "action": "generate_text",
           "context": "personal", "verdict": verdict, "decision": verdict,
           "status": "available", "result": "", "approval_required": False,
           "owner_approval": False, "verification_supported": False}
    row.update(over)
    return row


def _view(**over):
    args = {"activity": "idle", "resources": "safe", "trust": _GOOD_TRUST,
            "authority": None}
    args.update(over)
    return core.build_core_view(**args)


_REAL_FILES = (trust.TRUST_FILE, trust.ACTION_LOG)
_REAL_BEFORE = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
                for p in _REAL_FILES}


# ---- 1. the nine states resolve exactly, with a full bounded description --

def test_core_all_states_resolve_ok():
    assert core.SCHEMA == "maya/intelligence-core/1.0.0"
    assert len(core.STATES) == 9 and len(set(core.STATES)) == 9
    cases = {
        "idle": {},
        "observing": {"activity": "listening"},
        "reasoning": {"activity": "processing"},
        "acting": {"activity": "research"},
        "approval": {"authority": _auth("requires_approval")},
        "verifying": {"authority": _auth("allowed",
                                         verification_supported=False)},
        "complete": {"authority": _auth("allowed",
                                        verification_supported=True)},
        "error": {"resources": "unsafe"},
        "unavailable": {"trust": None},
    }
    seen = set()
    for state, kwargs in cases.items():
        view = _view(**kwargs)
        assert view["state"] == state, (state, view["state"], view["reason"])
        assert view["label"] == core.LABELS[state]
        assert view["description"] and view["color_key"] in (
            "accent", "accent2", "cyan", "ok", "warn", "bad", "muted")
        assert set(view["pattern"]) == {"ticks", "dash_on", "dash_off",
                                        "contours", "wobble"}
        seen.add(view["state"])
    assert seen == set(core.STATES)
    _ok("core_all_states_resolve_ok")


# ---- 2. individual state derivations --------------------------------------

def test_core_idle_ok():
    view = _view(activity="idle")
    assert view["state"] == "idle" and view["severity"] == "neutral"
    assert view["implies_success"] is False
    _ok("core_idle_ok")


def test_core_observing_ok():
    view = _view(activity="listening")
    assert view["state"] == "observing" and view["implies_success"] is False
    assert any(n["active"] for n in view["geometry"]["nodes"]
               if n["id"] == "memory")
    _ok("core_observing_ok")


def test_core_reasoning_ok():
    view = _view(activity="processing")
    assert view["state"] == "reasoning" and view["implies_success"] is False
    _ok("core_reasoning_ok")


def test_core_acting_ok():
    view = _view(activity="research")
    assert view["state"] == "acting" and view["implies_success"] is False
    _ok("core_acting_ok")


def test_core_approval_ok():
    view = _view(authority=_auth("requires_approval", approval_required=True))
    assert view["state"] == "approval"
    assert view["implies_authority_waiting"] is True
    assert view["implies_success"] is False
    _ok("core_approval_ok")


def test_core_verifying_ok():
    view = _view(authority=_auth("allowed", verification_supported=False))
    assert view["state"] == "verifying" and view["implies_success"] is False
    assert view["authority"]["verification_supported"] is False
    _ok("core_verifying_ok")


def test_core_complete_ok():
    view = _view(authority=_auth("allowed", verification_supported=True))
    assert view["state"] == "complete"
    assert view["implies_success"] is True
    assert view["implies_failure"] is False
    _ok("core_complete_ok")


def test_core_error_from_refused_ok():
    view = _view(authority=_auth("refused", status="available"))
    assert view["state"] == "error" and view["implies_failure"] is True
    _ok("core_error_from_refused_ok")


def test_core_unavailable_from_refused_untrusted_ok():
    view = _view(authority=_auth("refused", status="untrusted"))
    assert view["state"] == "unavailable" and view["implies_failure"] is True
    _ok("core_unavailable_from_refused_untrusted_ok")


# ---- 3. fail-closed resource and authority handling -----------------------

def test_core_resource_unsafe_error_ok():
    view = _view(resources="unsafe")
    assert view["state"] == "error" and view["implies_failure"] is True
    _ok("core_resource_unsafe_error_ok")


def test_core_resource_unavailable_ok():
    view = _view(resources="unavailable")
    assert view["state"] == "unavailable" and view["implies_success"] is False
    _ok("core_resource_unavailable_ok")


def test_core_resource_malformed_unavailable_ok():
    for bad in (None, "", "ok", 1, {"safe": True}):
        assert _view(resources=bad)["state"] == "unavailable", bad
    _ok("core_resource_malformed_unavailable_ok")


def test_core_trust_missing_unavailable_ok():
    for bad in (None, [], "trust", 3):
        assert _view(trust=bad)["state"] == "unavailable", bad
    _ok("core_trust_missing_unavailable_ok")


def test_core_trust_empty_inventory_unavailable_ok():
    empty = {"schema": "trusted_capability.v1", "capabilities": {}}
    assert _view(trust=empty)["state"] == "unavailable"
    assert core.trust_ok(empty) is False
    _ok("core_trust_empty_inventory_unavailable_ok")


def test_core_trust_unknown_status_unavailable_ok():
    bad = {"schema": "trusted_capability.v1",
           "capabilities": {"conversation": "totally_fine"}}
    assert _view(trust=bad)["state"] == "unavailable"
    _ok("core_trust_unknown_status_unavailable_ok")


def test_core_authority_malformed_unavailable_ok():
    for bad in ([], "allowed", 7, {"unrelated": True}):
        assert _view(authority=bad)["state"] == "unavailable", bad
    _ok("core_authority_malformed_unavailable_ok")


def test_core_authority_unknown_verdict_unavailable_ok():
    view = _view(authority=_auth("probably"))
    assert view["state"] == "unavailable"
    _ok("core_authority_unknown_verdict_unavailable_ok")


# ---- 4. no state may imply safety/authority/success it does not hold ------

def test_core_failure_never_success_ok():
    for state, kwargs in (("unavailable", {"trust": None}),
                          ("error", {"resources": "unsafe"}),
                          ("unavailable", {"authority": _auth(
                              "refused", status="unavailable")})):
        view = _view(**kwargs)
        assert view["state"] == state
        assert view["implies_failure"] is True
        assert view["implies_success"] is False
        assert view["fail_closed"] is True
        assert all(not n["active"] for n in view["geometry"]["nodes"])
        assert all(not i["active"] for i in view["indicators"])
    _ok("core_failure_never_success_ok")


def test_core_success_only_complete_ok():
    builders = [
        {}, {"activity": "listening"}, {"activity": "processing"},
        {"activity": "research"},
        {"authority": _auth("requires_approval")},
        {"authority": _auth("allowed", verification_supported=False)},
        {"authority": _auth("refused", status="available")},
        {"resources": "unsafe"}, {"trust": None},
    ]
    for kwargs in builders:
        assert _view(**kwargs)["implies_success"] is False, kwargs
    assert _view(authority=_auth("allowed",
                                 verification_supported=True)
                 )["implies_success"] is True
    _ok("core_success_only_complete_ok")


def test_core_indicators_authoritative_ok():
    view = _view()
    for indicator in view["indicators"]:
        assert indicator["active"] == (indicator["status"] == "available")
    trusted = [i["name"] for i in view["indicators"] if i["active"]]
    assert trusted == ["conversation"], trusted
    caps_node = [n for n in view["geometry"]["nodes"]
                 if n["id"] == "capabilities"][0]
    assert caps_node["active"] is (view["trust"]["trusted"] > 0)
    empty = _view(trust={"schema": "trusted_capability.v1",
                         "capabilities": {"conversation": "pending_validation"}})
    assert all(not i["active"] for i in empty["indicators"])
    assert not [n for n in empty["geometry"]["nodes"]
                if n["id"] == "capabilities"][0]["active"]
    _ok("core_indicators_authoritative_ok")


# ---- 5. deterministic, bounded geometry and self-consistent digest --------

def test_core_geometry_bounded_ok():
    view = _view(activity="research",
                 authority=_auth("allowed", verification_supported=True))
    coords = []
    for contour in view["geometry"]["contours"]:
        coords.extend(contour)
    for ring in view["geometry"]["rings"]:
        for segment in ring["segments"]:
            coords.extend(segment)
    for node in view["geometry"]["nodes"]:
        coords.append([node["x"], node["y"]])
    for signal in view["geometry"]["signals"]:
        coords.append([signal["x1"], signal["y1"]])
        coords.append([signal["x2"], signal["y2"]])
    assert coords
    for x, y in coords:
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0, (x, y)
    assert len(view["geometry"]["nodes"]) == 8
    assert len(view["geometry"]["signals"]) == 8
    _ok("core_geometry_bounded_ok")


def test_core_determinism_and_digest_ok():
    a = _view(activity="processing")
    b = _view(activity="processing")
    assert a == b
    assert a["digest"] == b["digest"] and len(a["digest"]) == 64
    payload = {k: v for k, v in a.items() if k != "digest"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == a["digest"]
    _ok("core_determinism_and_digest_ok")


# ---- 6. QML is a presentation-only, schema-gated surface -------------------

def test_core_qml_presentation_gate_ok():
    qml = (QML / "IntelligenceCore.qml").read_text(encoding="utf-8")
    assert core.SCHEMA in qml
    assert qml.strip().startswith("import QtQuick")
    for token in ("Math.random", "Date", "Timer", "wallClock", "time_now"):
        assert token not in qml, token
    assert "geometry" in qml and "clearRect" in qml
    _ok("core_qml_presentation_gate_ok")


def test_core_qml_wiring_ok():
    home = (QML / "Home.qml").read_text(encoding="utf-8")
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    assert home.count("FaceView {") == 0
    assert "IntelligenceCore {" in home
    assert "setCore" in home and "coreColor" in home
    assert "setCore" in main and "setFace" not in main
    for path in QML.glob("*.qml"):
        if path.name in ("ShapeView.qml", "FaceView.qml"):
            continue
        count = path.read_text(encoding="utf-8").count("FaceView {")
        assert count == 0, path.name
    _ok("core_qml_wiring_ok")


# ---- 7. pure bridge exposes the core additively ---------------------------

def test_core_bridge_additive_ok():
    ticker = ui_bridge.UiTicker()
    view = ticker.apply_tick_snapshot(ticker.make_tick_payload("idle"))
    assert isinstance(view.get("core"), dict)
    assert view["core"]["schema"] == core.SCHEMA
    assert view["core"]["state"] in core.STATES
    assert len(view["live_lines"]) == 7
    assert "face" in view and "shape" in view
    assert ticker.apply_tick_snapshot(None) is None
    _ok("core_bridge_additive_ok")


def test_core_bridge_fail_closed_resources_ok():
    monitor = importlib.import_module("maya_safety_monitor")
    original = monitor.status
    try:
        for report, expected in (
                ({"safe": True, "monitor_available": True}, "acting"),
                ({"safe": False, "monitor_available": True}, "error"),
                ({"safe": True, "monitor_available": False}, "unavailable")):
            monitor.status = lambda _r=report: dict(_r)
            ticker = ui_bridge.UiTicker()
            view = ticker.apply_tick_snapshot(
                ticker.make_tick_payload("research"))
            assert view["core"]["state"] == expected, expected
            assert view["core"]["implies_success"] is False
    finally:
        monitor.status = original
    _ok("core_bridge_fail_closed_resources_ok")


# ---- 8. real-runtime drive: the actual trust gate + action log ------------

def test_core_real_runtime_allowed_verified_ok():
    tmp = Path(tempfile.mkdtemp())
    reg, log = tmp / "reg.jsonl", tmp / "log.jsonl"
    trust_cmd.trust_command(":trust validate language_model confirm",
                            registry_path=reg, actions_path=log,
                            probe=PROBE_OK)
    out = trust.authorize("language_model", "generate_text", "personal",
                          path=reg, action_log=log)
    assert out["verdict"] == "allowed", out
    rows = [json.loads(line) for line in
            log.read_text(encoding="utf-8").splitlines() if line.strip()]
    authority = rows[-1]
    view = core.build_core_view(activity="idle", resources="safe",
                                trust=trust.registry_overview(path=reg),
                                authority=authority)
    assert view["state"] == "complete", (view["state"], view["reason"])
    assert view["implies_success"] is True
    assert view["authority"]["verification_supported"] is True
    _ok("core_real_runtime_allowed_verified_ok")


def test_core_real_runtime_revoked_unavailable_ok():
    tmp = Path(tempfile.mkdtemp())
    reg, log = tmp / "reg.jsonl", tmp / "log.jsonl"
    trust_cmd.trust_command(":trust validate language_model confirm",
                            registry_path=reg, actions_path=log,
                            probe=PROBE_OK)
    trust_cmd.trust_command(":trust revoke language_model confirm",
                            registry_path=reg, actions_path=log)
    out = trust.authorize("language_model", "generate_text", "personal",
                          path=reg, action_log=log)
    assert out["verdict"] == "refused" and out["status"] == "untrusted", out
    rows = [json.loads(line) for line in
            log.read_text(encoding="utf-8").splitlines() if line.strip()]
    view = core.build_core_view(activity="idle", resources="safe",
                                trust=trust.registry_overview(path=reg),
                                authority=rows[-1])
    assert view["state"] == "unavailable", (view["state"], view["reason"])
    assert view["implies_failure"] is True
    assert view["implies_success"] is False
    _ok("core_real_runtime_revoked_unavailable_ok")


def test_core_real_inventory_honest_ok():
    view = core.build_core_view(activity="idle", resources="safe",
                                trust=trust.registry_overview(),
                                authority=None)
    assert view["state"] == "idle", (view["state"], view["reason"])
    assert view["trust"]["total"] > 0
    for indicator in view["indicators"]:
        assert indicator["active"] == (indicator["status"] == "available")
    _ok("core_real_inventory_honest_ok")


# ---- 9. the real registry and action log were never written ---------------

def test_core_real_files_untouched_ok():
    after = {str(p): (p.exists(), p.stat().st_size if p.exists() else 0)
             for p in _REAL_FILES}
    assert after == _REAL_BEFORE, (after, _REAL_BEFORE)
    _ok("core_real_files_untouched_ok")


if __name__ == "__main__":
    for _name in sorted(globals()):
        if _name.startswith("test_") and callable(globals()[_name]):
            globals()[_name]()
    print("test_intelligence_core=PASS")
