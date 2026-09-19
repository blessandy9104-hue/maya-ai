"""Safe local application runner for Maya.

The runner never accepts a user-supplied executable, shell string, or arbitrary
arguments. All launch specifications come from maya_app_control_policy.json.
It is disabled by default and requires the existing mission/security walls.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from maya_mission_wall import guard
from maya_security_wall import append_encrypted_audit, check_action
from maya_system_wall import validate_launch

ROOT = Path(__file__).parent
POLICY_PATH = ROOT / "maya_app_control_policy.json"

DEFAULT_POLICY = {
    "owner_control_enabled": False,
    "actions": {},
    "max_launches_per_request": 1,
    "launch_timeout_seconds": 5,
}


def load_policy() -> dict[str, Any]:
    if not POLICY_PATH.exists():
        POLICY_PATH.write_text(json.dumps(DEFAULT_POLICY, indent=2) + "\n", encoding="utf-8")
        return dict(DEFAULT_POLICY)
    try:
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        policy = dict(DEFAULT_POLICY)
        policy.update(data if isinstance(data, dict) else {})
        return policy
    except (OSError, ValueError, TypeError):
        return dict(DEFAULT_POLICY)


def _safe_spec(action: str, policy: dict[str, Any]) -> tuple[str, list[str]] | None:
    actions = policy.get("actions")
    if not isinstance(actions, dict):
        return None
    spec = actions.get(action)
    if not isinstance(spec, dict):
        return None
    executable = spec.get("executable")
    args = spec.get("args", [])
    if not isinstance(executable, str) or not executable or not isinstance(args, list):
        return None
    if not all(isinstance(item, str) for item in args):
        return None
    if any(token in executable or token in " ".join(args) for token in ("&&", "||", ";", "|", ">", "<", "$(", "`")):
        return None
    path = Path(executable)
    if not path.is_absolute():
        return None
    if not path.exists() or not path.is_file():
        return None
    return str(path), list(args)


def run_allowed(action: str, owner_token: str = "", confirmation: str = "", dry_run: bool = False) -> dict[str, Any]:
    policy = load_policy()
    if policy.get("owner_control_enabled") is not True:
        return {"allowed": False, "action": action, "reason": "owner control is disabled"}
    if policy.get("max_launches_per_request") != 1:
        return {"allowed": False, "action": action, "reason": "launch limit must remain exactly one"}
    spec = _safe_spec(action, policy)
    if spec is None:
        return {"allowed": False, "action": action, "reason": "action is not a valid allowlisted launch specification"}
    mission = guard("launch local application", f"launch allowlisted application {action}", irreversible=True, approval=confirmation.strip().upper() == "CONFIRM")
    if not mission.get("allowed"):
        return {"allowed": False, "action": action, "reason": "mission wall denied action", "details": mission}
    security = check_action(action, owner_token, confirmation)
    if not security.get("allowed"):
        return {"allowed": False, "action": action, "reason": "security wall denied action", "details": security}
    executable, args = spec
    system = validate_launch(action, executable, args)
    if not system.get("allowed"):
        return {"allowed": False, "action": action, "reason": "system-preservation wall denied action", "details": system}
    result: dict[str, Any] = {"allowed": True, "action": action, "executable": executable, "args": args}
    if dry_run:
        result["dry_run"] = True
        append_encrypted_audit({"event": "dry_run", "action": action, "argv": [executable, *args]})
        return result
    try:
        child = subprocess.Popen(
            [executable, *args],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        result["pid"] = child.pid
        result["started"] = True
        audit = append_encrypted_audit({"event": "launch", "action": action, "pid": child.pid, "argv": [executable, *args]})
        result["audit"] = audit
        return result
    except (OSError, ValueError) as exc:
        append_encrypted_audit({"event": "launch_failed", "action": action, "error": str(exc)})
        return {"allowed": False, "action": action, "reason": "process launch failed", "error": str(exc)}


def usage() -> str:
    return (
        "Usage: python3 maya_app_runner.py status | run ACTION --token TOKEN --confirm CONFIRM [--dry-run]\n"
        "The policy file must explicitly enable owner_control_enabled and define an absolute executable path."
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] == "status":
        print(json.dumps({"owner_control_enabled": load_policy().get("owner_control_enabled", False), "actions": sorted((load_policy().get("actions") or {}).keys())}, indent=2))
        return 0
    if argv[1] != "run" or len(argv) < 3:
        print(usage())
        return 2
    action = argv[2]
    token = ""
    confirmation = ""
    dry_run = "--dry-run" in argv[3:]
    for index, value in enumerate(argv[3:], start=3):
        if value == "--token" and index + 1 < len(argv):
            token = argv[index + 1]
        if value == "--confirm" and index + 1 < len(argv):
            confirmation = argv[index + 1]
    result = run_allowed(action, token, confirmation, dry_run=dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("allowed") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
