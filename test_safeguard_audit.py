from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    # Browser observation must be blocked under the default policy.
    blocked = subprocess.run(
        [sys.executable, str(ROOT / "browser_observe.py")], cwd=ROOT,
        capture_output=True, text=True, timeout=15,
    )
    output = blocked.stdout + blocked.stderr
    assert blocked.returncode == 2, output
    assert "OBSERVATION_BLOCKED" in output, output

    policy = json.loads((ROOT / "observation_policy.json").read_text(encoding="utf-8"))
    assert policy["enabled_sources"]["browser_tabs"] is False
    assert policy["enabled_sources"]["screen_capture"] is False
    assert policy["enabled_sources"]["keystrokes"] is False
    assert policy["storage"]["raw_content"] is False

    # Inference must create pending candidates only; it must not approve them.
    profile_before = json.loads((ROOT / "andy_profile.json").read_text(encoding="utf-8"))
    subprocess.run([sys.executable, str(ROOT / "andy_infer.py")], cwd=ROOT, capture_output=True, text=True, timeout=15, check=True)
    profile_after = json.loads((ROOT / "andy_profile.json").read_text(encoding="utf-8"))
    assert profile_after.get("inferred_preferences_pending_review", []) is not None
    assert all(item.get("status") == "pending_review" for item in profile_after.get("inferred_preferences_pending_review", []))
    assert profile_after.get("privacy", {}).get("memory_updates_require_approval") is True

    # The evolution entry point has candidate and syntax-test commands only;
    # status must not activate a candidate or alter activation flags.
    activation_before = json.loads((ROOT / "maya_activation_state.json").read_text(encoding="utf-8"))
    status = subprocess.run([sys.executable, str(ROOT / "evolve.py"), "status"], cwd=ROOT, capture_output=True, text=True, timeout=15, check=True)
    assert status.stdout.strip()
    activation_after = json.loads((ROOT / "maya_activation_state.json").read_text(encoding="utf-8"))
    assert activation_before.get("presence_mode") == activation_after.get("presence_mode")

    print(json.dumps({
        "status": "ok",
        "browser_observation_blocked_by_default": True,
        "inference_pending_only": True,
        "evolution_does_not_activate": True,
    }))


if __name__ == "__main__":
    main()
