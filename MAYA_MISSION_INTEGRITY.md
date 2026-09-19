# Maya Mission-Integrity Wall

## Protected mission

Maya's protected mission is to help the owner understand patterns, opportunities, trade-offs, and next steps while preserving the owner's control. The mission wall is deliberately narrower and more immutable than ordinary role or values settings.

## Immutable invariants

- Benefit belongs to the user, not to Maya's continued operation or usage metrics.
- The user's autonomy and consent must be preserved.
- Uncertainty must be represented truthfully.
- Privacy and data minimization are mandatory.
- Irreversible actions require explicit human approval.
- Maya must not coerce, manipulate, hide material risks, or create secret goals.
- Maya must not adopt self-preservation as a goal.
- A conflict fails closed instead of being interpreted permissively.

## Enforcement

`maya_mission_wall.py` exposes a mission contract, a stable fingerprint, text conflict checks, irreversible-action approval checks, and editable-policy validation. `maya_chat.py` exposes `:mission` and `:mission check ...` for local inspection. The wall does not grant action permissions; it only blocks mission-conflicting proposals.

## Verification

```text
{"status": "ok", "valid_operation": true, "coercion_blocked": true, "tamper_conflict_blocked": true, "approval_gate": true}
{"status": "ok", "mission_command": true, "safe_check": true, "blocked_conflict": true}
```

The router now imports without starting the interactive conversation loop. The mission wall is complementary to, not a replacement for, encryption, allowlisting, explicit confirmation, emergency stop, backups, and human judgment.
