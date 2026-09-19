"""Maya UX / visual redesign verification suite.

Verifies the student-facing redesign at the pure layer (runs on every
interpreter, no Qt required):

- the Intelligence Core QML is now an abstract, animated orb/pulse with a
  student palette (mint ready / electric thinking / soft gold insight / red
  attention) and remains presentation-only and schema-gated, with no wall
  clock, timers or randomness;
- the facial figure is gone from the runtime surfaces (no FaceView / setFace
  in Home or Main) while the canonical-vector-face Python pipeline is left
  intact for the other suites;
- Home is chat-first with Quick Action cards, a plain "System Healthy"
  indicator, and the technical activity/trust details moved behind an
  "Advanced / Developer" dropdown;
- onboarding, plain-language labels and the additive student bridge block;
- fail-closed honesty: the student label can never show Ready for a failure
  state, and health is only true on a non-failure core with safe resources.

Skills: this module may print only benign lines (``=OK`` labels). No free-form
text, no tracebacks on the passing path.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import maya_intelligence_core as core  # noqa: E402
from maya_runtime.ui.qt import bridge as ui_bridge  # noqa: E402

ROOT = _REPO
QML = ROOT / "maya_runtime" / "ui" / "qt" / "qml"

_GOOD_TRUST = {
    "schema": "trusted_capability.v1",
    "capabilities": {"conversation": "available"},
}

_AUTHORITY_APPROVAL = {
    "capability": "conversation", "action": "generate_text",
    "verdict": "requires_approval", "verification_supported": False,
}
_AUTHORITY_ALLOWED_UNVERIFIED = {
    "capability": "conversation", "action": "generate_text",
    "verdict": "allowed", "verification_supported": False,
}
_AUTHORITY_ALLOWED_VERIFIED = {
    "capability": "conversation", "action": "generate_text",
    "verdict": "allowed", "verification_supported": True,
}


def _ok(name: str) -> None:
    print(f"={name}=OK")


def _qml(name: str) -> str:
    return (QML / name).read_text(encoding="utf-8")


def _view(activity="idle", resources="safe", authority=None, verified=None):
    return core.build_core_view(activity=activity, resources=resources,
                                trust=_GOOD_TRUST, authority=authority,
                                verified=verified)


# ---- 1. the core surface is an animated orb/pulse --------------------------

def test_ux_core_orb_animated_ok():
    qml = _qml("IntelligenceCore.qml")
    for token in ("property real breath", "property real spin",
                  "property real pulse", "SequentialAnimation",
                  "NumberAnimation", "coreSchema", "setCore", "clearRect"):
        assert token in qml, token
    assert "Canvas {" in qml
    _ok("ux_core_orb_animated_ok")


def test_ux_core_palette_ok():
    qml = _qml("IntelligenceCore.qml")
    for token in ("#4fe0b0", "#3b9dff", "#ffd36e", "#ff5c7a"):
        assert token in qml, token
    _ok("ux_core_palette_ok")


def test_ux_core_tone_map_ok():
    qml = _qml("IntelligenceCore.qml")
    assert "function toneFor" in qml
    for token in ('return "mint"', 'return "electric"',
                  'return "gold"', 'return "bad"', 'return "muted"'):
        assert token in qml, token
    assert "isKnownState" in qml and "unavailable" in qml
    _ok("ux_core_tone_map_ok")


def test_ux_core_no_wall_clock_ok():
    qml = _qml("IntelligenceCore.qml")
    for token in ("Math.random", "Date", "Timer", "wallClock", "time_now"):
        assert token not in qml, token
    _ok("ux_core_no_wall_clock_ok")


# ---- 2. the facial figure is gone from the runtime surfaces ----------------

def test_ux_home_no_face_ok():
    home = _qml("Home.qml")
    main = _qml("Main.qml")
    assert "FaceView" not in home and "FaceView" not in main
    assert "setFace" not in home and "setFace" not in main
    assert "IntelligenceCore {" in home
    assert "setCore" in home and "coreColor" in home and "setCore" in main
    _ok("ux_home_no_face_ok")


def test_ux_faces_pipeline_kept_ok():
    assert (QML / "FaceView.qml").exists()
    assert (QML / "ShapeView.qml").exists()
    import maya_identity.vector_face as vector_face
    assert callable(vector_face.to_qml_payload)
    _ok("ux_faces_pipeline_kept_ok")


# ---- 3. Home is chat-first with quick actions and plain health -------------

def test_ux_home_action_cards_ok():
    home = _qml("Home.qml")
    assert home.count("ActionCard {") == 3
    for title in ("Summarize This", "Find Connections", "Organize My Day"):
        assert title in home, title
    assert "ui.chatSend(" in home
    assert "Console {" in home
    _ok("ux_home_action_cards_ok")


def test_ux_home_health_indicator_ok():
    home = _qml("Home.qml")
    for token in ("System Healthy", "Needs attention", "healthy()",
                  "implies_failure", "resources === \"safe\""):
        assert token in home, token
    _ok("ux_home_health_indicator_ok")


def test_ux_home_advanced_dropdown_ok():
    home = _qml("Home.qml")
    assert "Advanced / Developer" in home
    assert "advancedOpen" in home
    assert "Activity (technical)" in home and "Trust list" in home
    assert "live_lines" in home and "indicators" in home
    _ok("ux_home_advanced_dropdown_ok")


# ---- 4. onboarding overlay -------------------------------------------------

def test_ux_welcome_overlay_ok():
    overlay = _qml("WelcomeOverlay.qml")
    assert "Welcome to Maya" in overlay
    for token in ("Mint — Ready", "Blue — Thinking", "Gold — All done",
                  "Red — Needs attention"):
        assert token in overlay, token
    assert "signal dismissed()" in overlay
    main = _qml("Main.qml")
    assert "WelcomeOverlay {" in main
    assert "showWelcome" in main and "onHelpRequested" in main
    _ok("ux_welcome_overlay_ok")


# ---- 5. plain-language vocabulary -----------------------------------------

def test_ux_plain_language_ok():
    settings = _qml("Settings.qml")
    thinking = _qml("Thinking.qml")
    control = _qml("Control.qml")
    assert "Maya's Status" in settings and "SAVED KNOWLEDGE" in settings
    assert "Presence Mode" not in settings
    assert "RESEARCH CACHE" not in settings
    assert "Connecting Ideas" in thinking
    assert "How Maya Thinks" not in thinking
    assert "MAYA'S STATUS" in control and "PRESENCE MODE" not in control
    _ok("ux_plain_language_ok")


def test_ux_advanced_on_other_pages_ok():
    for page in ("Settings.qml", "Control.qml"):
        text = _qml(page)
        assert "Advanced / Developer" in text, page
        assert "advancedOpen" in text, page
    nav = _qml("Navigation.qml")
    for token in ("Connecting Ideas", "My Day", "Knowledge", "Controls"):
        assert token in nav, token
    _ok("ux_advanced_on_other_pages_ok")


def test_ux_console_chat_hook_ok():
    console = _qml("Console.qml")
    assert "Keys.onPressed: ui.notifyTyping()" in console
    assert "ui.chatSend(" in console
    _ok("ux_console_chat_hook_ok")


# ---- 6. additive student bridge block -------------------------------------

def test_ux_bridge_ui_additive_ok():
    ticker = ui_bridge.UiTicker()
    view = ticker.apply_tick_snapshot(ticker.make_tick_payload("idle"))
    assert isinstance(view.get("ui"), dict)
    for key in ("status_label", "status_tone", "status_detail", "state",
                "healthy", "core_legend"):
        assert key in view["ui"], key
    assert len(view["ui"]["core_legend"]) == 4
    assert len(view["live_lines"]) == 7
    assert "core" in view and "face" in view and "shape" in view
    _ok("ux_bridge_ui_additive_ok")


def test_ux_bridge_status_mapping_ok():
    expected = {
        "idle": ("Ready", "mint"),
        "observing": ("Listening", "electric"),
        "reasoning": ("Thinking", "electric"),
        "acting": ("Working", "electric"),
        "verifying": ("Checking", "electric"),
        "approval": ("Needs your OK", "gold"),
        "complete": ("All done", "gold"),
        "unavailable": ("Paused", "muted"),
        "error": ("Something's wrong", "red"),
    }
    cases = {
        "idle": _view(),
        "observing": _view(activity="listening"),
        "reasoning": _view(activity="processing"),
        "acting": _view(activity="research"),
        "verifying": _view(authority=_AUTHORITY_ALLOWED_UNVERIFIED),
        "approval": _view(authority=_AUTHORITY_APPROVAL),
        "complete": _view(authority=_AUTHORITY_ALLOWED_VERIFIED),
        "unavailable": _view(resources="unavailable"),
        "error": _view(resources="unsafe"),
    }
    for state, view in cases.items():
        assert view["state"] == state, (state, view["state"])
        ui = ui_bridge.student_view(view, "safe")
        assert (ui["status_label"], ui["status_tone"]) == expected[state], state
    _ok("ux_bridge_status_mapping_ok")


def test_ux_bridge_healthy_logic_ok():
    assert ui_bridge.student_view(_view(), "safe")["healthy"] is True
    assert ui_bridge.student_view(_view(resources="unsafe"), "unsafe")["healthy"] is False
    assert ui_bridge.student_view(_view(), "unavailable")["healthy"] is False
    assert ui_bridge.student_view(None, "safe")["healthy"] is False
    _ok("ux_bridge_healthy_logic_ok")


def test_ux_bridge_fail_closed_labels_ok():
    error_ui = ui_bridge.student_view(_view(resources="unsafe"), "unsafe")
    assert error_ui["status_label"] == "Something's wrong"
    assert error_ui["status_tone"] == "red"
    unavailable_ui = ui_bridge.student_view(_view(resources="unavailable"),
                                            "unavailable")
    assert unavailable_ui["status_label"] == "Paused"
    assert unavailable_ui["status_tone"] == "muted"
    unknown = ui_bridge.student_view(None, "safe")
    assert unknown["status_label"] == "Paused"
    assert unknown["state"] == "unavailable"
    assert unknown["healthy"] is False
    _ok("ux_bridge_fail_closed_labels_ok")


def test_ux_bridge_ui_deterministic_ok():
    a = ui_bridge.student_view(_view(), "safe")
    b = ui_bridge.student_view(_view(), "safe")
    assert a == b
    tones = [row["tone"] for row in a["core_legend"]]
    assert tones == ["mint", "electric", "gold", "red"]
    _ok("ux_bridge_ui_deterministic_ok")


if __name__ == "__main__":
    for _name in sorted(globals()):
        if _name.startswith("test_") and callable(globals()[_name]):
            globals()[_name]()
    print("test_ux_redesign=PASS")
