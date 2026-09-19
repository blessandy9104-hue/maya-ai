import json

from maya_control_simulator import SimulatedDesktop
from maya_safety_monitor import ResourceSnapshot


def main():
    desktop = SimulatedDesktop()

    assert desktop.open_application("text_editor", "")["allowed"] is False
    app = desktop.open_application("text_editor", "CONFIRM")
    assert app["allowed"] is True and app["host_changed"] is False and app["planned_only"] is True

    song = desktop.play_song("Jujutsu Kaisen opening", "CONFIRM")
    assert song["allowed"] is True and song["host_changed"] is False

    brightness = desktop.set_brightness(60, "CONFIRM")
    assert brightness["allowed"] is False
    assert "unavailable" in brightness["reason"]

    hot = desktop.cool_down(ResourceSnapshot(92.0, 88.0, 3, 0))
    assert hot["allowed"] is True and "pause Maya workload" in hot["recommendations"]

    unsupported = desktop.open_application("unknown", "CONFIRM")
    assert unsupported["allowed"] is False

    desktop.emergency_stop("simulated Ctrl+Alt+Esc")
    assert desktop.play_song("Anything", "CONFIRM")["allowed"] is False
    assert desktop.open_application("text_editor", "CONFIRM")["allowed"] is False

    assert all(entry.get("host_changed") is False for entry in desktop.log if "host_changed" in entry)
    print(json.dumps({"status": "ok", "application_open_simulated": True, "song_playback_simulated": True, "brightness_fallback_safe": True, "cooling_recommendation_safe": True, "emergency_stop_blocks_controls": True, "host_changed": False}))


if __name__ == "__main__":
    main()
