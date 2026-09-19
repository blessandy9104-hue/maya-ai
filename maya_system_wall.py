"""System-cooperation boundary for Maya's local controls.

Maya may cooperate with the user's computer, but it must not treat the host
system as disposable. This module only validates proposed fixed launch specs;
it does not execute them.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

DENIED_TOKENS = (
    "shutdown", "reboot", "restart-computer", "format", "diskpart", "cipher /w",
    "taskkill", "stop-process", "kill", "pkill", "killall", "rm -rf", "del /f",
    "rmdir /s", "reg delete", "sc delete", "net stop", "sudo", "runas", "chmod",
    "chown", "setfacl", "powershell", "pwsh", "cmd.exe /c", "bash -c", "sh -c",
    "&&", "||", ";", "|", ">", "<", "$(`", "`",
)

DENIED_ACTIONS = {
    "terminate_process", "kill_process", "shutdown_system", "restart_system",
    "change_firewall", "change_registry", "install_software", "uninstall_software",
    "change_permissions", "elevate_privileges", "modify_startup", "disable_security",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_launch(action: str, executable: str, args: list[str]) -> dict[str, Any]:
    values = [action, executable, *args]
    normalized = " ".join(str(value).lower() for value in values)
    reasons = []
    if action.lower() in DENIED_ACTIONS:
        reasons.append("action is destructive or system-level")
    for token in DENIED_TOKENS:
        if token in normalized:
            reasons.append(f"blocked system-control token: {token}")
    if any(not isinstance(arg, str) or "\x00" in arg for arg in args):
        reasons.append("malformed argument")
    if len(args) > 8:
        reasons.append("argument count exceeds conservative limit")
    return {
        "allowed": not reasons,
        "action": action,
        "reasons": sorted(set(reasons)),
        "checked_at": utc_now(),
        "principle": "cooperate with the user's system; do not harm the vessel",
    }


def system_contract() -> dict[str, Any]:
    return {
        "mode": "cooperative_non_interference",
        "rules": [
            "do not interrupt unrelated user programs",
            "do not terminate processes unless a future owner-approved runner explicitly owns them",
            "do not shut down, reboot, format, delete, or alter system configuration",
            "do not elevate privileges",
            "do not write outside approved application data paths",
            "fail closed when ownership or risk is uncertain",
            "respect emergency stop immediately",
        ],
        "checked_at": utc_now(),
    }


if __name__ == "__main__":
    print(json.dumps(system_contract(), indent=2))
