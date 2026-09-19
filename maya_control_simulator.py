"""Dry-run simulator for Maya's future local desktop controls.

No subprocess, media API, brightness API, fan API, or hardware call is made.
Every operation returns a planned result and appends to an in-memory audit log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maya_safety_monitor import ResourceSnapshot, evaluate
from maya_system_wall import validate_launch


@dataclass
class SimulatedDesktop:
    allowlisted_apps: dict[str, str] = field(default_factory=lambda: {"text_editor": "C:/Apps/editor.exe", "music_player": "C:/Apps/player.exe"})
    media_capable: bool = True
    brightness_capable: bool = False
    cooling_capable: bool = False
    stopped: bool = False
    log: list[dict[str, Any]] = field(default_factory=list)

    def _record(self, result: dict[str, Any]) -> dict[str, Any]:
        self.log.append(result)
        return result

    def emergency_stop(self, reason: str = "simulation stop") -> dict[str, Any]:
        self.stopped = True
        return self._record({"allowed": True, "simulated": True, "operation": "emergency_stop", "reason": reason, "host_changed": False})

    def open_application(self, app: str, confirmation: str = "") -> dict[str, Any]:
        if self.stopped:
            return self._record({"allowed": False, "simulated": True, "operation": "open_application", "reason": "emergency stop active", "host_changed": False})
        executable = self.allowlisted_apps.get(app)
        if not executable:
            return self._record({"allowed": False, "simulated": True, "operation": "open_application", "reason": "application not allowlisted", "host_changed": False})
        if confirmation.strip().upper() != "CONFIRM":
            return self._record({"allowed": False, "simulated": True, "operation": "open_application", "reason": "explicit confirmation required", "host_changed": False})
        system = validate_launch("open_" + app, executable, [])
        return self._record({"allowed": system["allowed"], "simulated": True, "operation": "open_application", "application": app, "executable": executable, "reason": system.get("reasons", []), "planned_only": True, "host_changed": False})

    def play_song(self, song: str, confirmation: str = "") -> dict[str, Any]:
        if self.stopped:
            return self._record({"allowed": False, "simulated": True, "operation": "play_song", "reason": "emergency stop active", "host_changed": False})
        if not self.media_capable:
            return self._record({"allowed": False, "simulated": True, "operation": "play_song", "reason": "media capability unavailable", "host_changed": False})
        if not song.strip():
            return self._record({"allowed": False, "simulated": True, "operation": "play_song", "reason": "song title required", "host_changed": False})
        if confirmation.strip().upper() != "CONFIRM":
            return self._record({"allowed": False, "simulated": True, "operation": "play_song", "reason": "explicit confirmation required", "host_changed": False})
        return self._record({"allowed": True, "simulated": True, "operation": "play_song", "song": song.strip(), "planned_only": True, "host_changed": False})

    def set_brightness(self, level: int, confirmation: str = "") -> dict[str, Any]:
        if self.stopped:
            return self._record({"allowed": False, "simulated": True, "operation": "brightness", "reason": "emergency stop active", "host_changed": False})
        if not isinstance(level, int) or not 0 <= level <= 100:
            return self._record({"allowed": False, "simulated": True, "operation": "brightness", "reason": "brightness must be an integer from 0 to 100", "host_changed": False})
        if not self.brightness_capable:
            return self._record({"allowed": False, "simulated": True, "operation": "brightness", "level": level, "reason": "hardware brightness API unavailable; no-op", "host_changed": False})
        if confirmation.strip().upper() != "CONFIRM":
            return self._record({"allowed": False, "simulated": True, "operation": "brightness", "level": level, "reason": "explicit confirmation required", "host_changed": False})
        return self._record({"allowed": True, "simulated": True, "operation": "brightness", "level": level, "planned_only": True, "host_changed": False})

    def cool_down(self, snapshot: ResourceSnapshot) -> dict[str, Any]:
        safety = evaluate(snapshot)
        if self.stopped:
            return self._record({"allowed": False, "simulated": True, "operation": "cool_down", "reason": "emergency stop active", "host_changed": False})
        if not safety["safe"]:
            return self._record({"allowed": True, "simulated": True, "operation": "cool_down", "reason": "resource threshold detected", "recommendations": ["pause Maya workload", "stop new launches", "check vents and physical airflow", "let the host cool naturally"], "hardware_fan_control": self.cooling_capable, "planned_only": True, "host_changed": False})
        return self._record({"allowed": True, "simulated": True, "operation": "cool_down", "reason": "no threshold breach", "hardware_fan_control": self.cooling_capable, "planned_only": True, "host_changed": False})
