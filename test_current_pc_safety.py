import json
import tempfile
from pathlib import Path

import maya_safety_monitor as monitor

policy = monitor.load_policy()
assert policy["max_cpu_percent"] <= 60.0
assert policy["max_memory_percent"] <= 70.0
assert policy["max_process_count"] <= 2
assert policy["max_launches_per_minute"] <= 1

with tempfile.TemporaryDirectory() as directory:
    monitor.STOP_PATH = Path(directory) / "PRESENCE_STOP"
    safe = monitor.evaluate(monitor.ResourceSnapshot(cpu_percent=10.0, memory_percent=30.0, maya_process_count=1, launches_last_minute=0), policy)
    assert safe["safe"] is True
    unsafe = monitor.evaluate(monitor.ResourceSnapshot(cpu_percent=61.0, memory_percent=30.0, maya_process_count=1, launches_last_minute=0), policy)
    assert unsafe["safe"] is False
    assert "CPU threshold exceeded" in unsafe["reasons"]

scope = json.loads(Path(__file__).with_name("maya_current_pc_safety_scope.json").read_text(encoding="utf-8"))
assert scope["status"] == "strict_zero_interference_priority"
assert scope["execution_limits"]["max_concurrent_maya_jobs"] == 1
assert scope["execution_limits"]["stop_on_wsl2_stall"] is True
assert scope["execution_limits"]["no_continuous_background_loops"] is True
assert scope["automatic_activation"] is False

print("conservative_thresholds=OK")
print("safe_snapshot=OK")
print("unsafe_snapshot_stops=OK")
print("strict_scope=OK")
print("no_continuous_background=OK")
