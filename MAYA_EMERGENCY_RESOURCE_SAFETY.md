# Maya emergency stop and resource safety

## Emergency stop

The Tkinter desktop window binds `Ctrl+Alt+Esc` to Maya's emergency-stop handler. The handler writes the persistent `PRESENCE_STOP` marker, requests the Presence controller stop, and asks Maya's own local chat child to exit. It does not terminate unrelated Windows processes.

The existing **EMERGENCY STOP** button remains available and has the same persistent-stop semantics. Resetting the stop remains a separate explicit action. The hotkey is active while the Maya window has keyboard focus; a system-wide Windows hotkey would require a separate carefully scoped registration and should not be added casually because it could conflict with other software.

## Resource monitoring

`maya_safety_monitor.py` uses conservative limits for Maya's own process activity: 85% CPU, 85% overall memory, four Maya-related processes, and two launches per minute. A threshold breach requests Maya's own emergency stop. If the optional system metric provider is unavailable, the monitor reports unavailable rather than making an uncontrolled action.

## Simulation result

The test used injected simulated metrics and a temporary emergency-stop marker. It did not launch a real text editor, music player, or other user application and did not touch unrelated processes.

```text
{"status": "ok", "simulated_safe_launch": true, "resource_limit_stop": true, "hotkey_stop_marker": true, "stop_reset": true, "unrelated_processes_untouched": true}
{"status": "ok", "default_denied": true, "confirmation_required": true, "allowlist_enforced": true, "shell_syntax_rejected": true, "emergency_stop_blocks": true}
```

This is a fail-safe policy layer, not a guarantee against a compromised host, administrator malware, or a malicious executable that the owner explicitly allowlists. Keep the allowlist small and review every path before enabling it.
