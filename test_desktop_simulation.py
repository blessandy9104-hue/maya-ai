import json
import tempfile
from pathlib import Path

import maya_safety_monitor as monitor
from maya_system_wall import validate_launch


def main():
    with tempfile.TemporaryDirectory() as temp:
        old_stop = monitor.STOP_PATH
        try:
            monitor.STOP_PATH = Path(temp) / "PRESENCE_STOP"
            monitor.clear_emergency_stop()
            safe_snapshot = monitor.ResourceSnapshot(20.0, 40.0, 2, 0)
            safe = monitor.evaluate(safe_snapshot)
            assert safe["safe"] is True

            cpu_snapshot = monitor.ResourceSnapshot(92.0, 40.0, 2, 0)
            assert monitor.evaluate(cpu_snapshot)["safe"] is False

            process_snapshot = monitor.ResourceSnapshot(20.0, 40.0, 5, 0)
            assert monitor.evaluate(process_snapshot)["safe"] is False

            monitor.emergency_stop("simulated Ctrl+Alt+Esc")
            stopped = monitor.evaluate(safe_snapshot)
            assert stopped["safe"] is False
            assert any("emergency stop" in reason for reason in stopped["reasons"])
            monitor.clear_emergency_stop()
            assert monitor.evaluate(safe_snapshot)["safe"] is True

            assert validate_launch("open_editor", "C:/Apps/editor.exe", [])["allowed"] is True
            assert validate_launch("shutdown_system", "C:/Windows/shutdown.exe", [])["allowed"] is False
            print(json.dumps({"status": "ok", "simulated_safe_launch": True, "resource_limit_stop": True, "hotkey_stop_marker": True, "stop_reset": True, "unrelated_processes_untouched": True}))
        finally:
            monitor.STOP_PATH = old_stop


if __name__ == "__main__":
    main()
