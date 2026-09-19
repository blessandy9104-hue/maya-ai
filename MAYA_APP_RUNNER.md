# Maya secure local application runner

`maya_app_runner.py` is a deny-by-default launcher for future local application control. It does not accept a user-supplied executable path, shell command, or arbitrary argument list. Every action must be configured in `maya_app_control_policy.json` with an absolute executable path and fixed arguments.

## Default behavior

The policy starts with `owner_control_enabled: false` and an empty action list. No application can launch until the owner explicitly configures the policy. The runner uses `shell=False`, one launch maximum per request, fixed arguments, and an encrypted audit record. The existing security wall and mission wall must both allow the action. `PRESENCE_STOP` blocks launches.

## Owner setup

Store `MAYA_OWNER_TOKEN` and `MAYA_VAULT_KEY` outside the Maya project folder in a protected Windows secret store. Do not put either value in source code, JSON policy files, chat messages, or screenshots. The vault key must be backed up securely; losing it prevents recovery of encrypted audit records.

## Policy example

Use real executable paths from the owner’s machine. Do not copy this example unchanged.

```json
{
  "owner_control_enabled": true,
  "actions": {
    "open_text_editor": {
      "executable": "C:\\Path\\To\\approved-editor.exe",
      "args": []
    },
    "open_music_player": {
      "executable": "C:\\Path\\To\\approved-player.exe",
      "args": []
    }
  },
  "max_launches_per_request": 1,
  "launch_timeout_seconds": 5
}
```

## Usage

Check the configured actions:

```powershell
py -3 .\maya_app_runner.py status
```

Perform a dry run first:

```powershell
py -3 .\maya_app_runner.py run open_text_editor --token YOUR_TOKEN --confirm CONFIRM --dry-run
```

Only after reviewing the dry-run result should the owner allow a real launch. The runner never creates a shell, interprets pipes or redirects, or accepts arbitrary command text.

## Current test result

```text
{"status": "ok", "default_denied": true, "confirmation_required": true, "allowlist_enforced": true, "shell_syntax_rejected": true, "emergency_stop_blocks": true}
```
