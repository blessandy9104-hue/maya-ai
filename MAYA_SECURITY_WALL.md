# Maya Security Wall

## Current protection

The new `maya_security_wall.py` module is deny-by-default for future local application and device control. An action is allowed only when owner control is enabled, the owner token matches, the action is explicitly confirmed with `CONFIRM`, the action is present in the local allowlist, and `PRESENCE_STOP` is absent. Observation remains a separate capability.

Control audit entries are encrypted with Fernet and integrity-checked. The decryption key must be supplied through `MAYA_VAULT_KEY`; it is not written beside Maya's data. The owner authentication value is supplied through `MAYA_OWNER_TOKEN`; only its digest is used for comparison.

## Important limitation

This first security-wall pass does not automatically encrypt every existing Maya JSON file. Existing profile, research, task, and conversation files remain in their current format so that the current MVP does not lose data unexpectedly. A later migration must encrypt selected sensitive stores only after a tested backup and a confirmed recovery-key procedure.

## Required recovery discipline

The owner must store `MAYA_VAULT_KEY` and `MAYA_OWNER_TOKEN` outside the Maya project directory, preferably in a Windows credential manager or another protected secret store. Losing the vault key means encrypted audit data cannot be recovered. The owner must keep an offline recovery copy before migrating existing state.

## Test result

The regression test passed:

```text
{"status": "ok", "default_denied": true, "encrypted_audit": true, "confirmation_required": true, "emergency_stop_blocks": true}
```
