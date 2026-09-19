# Maya System-Cooperation Wall

Maya is designed to cooperate with the user's computer rather than dominate or endanger it. The system is the user's vessel and must be preserved while Maya performs approved work.

## Rules

The system wall allows safe, fixed application launches when the existing owner, mission, security, confirmation, encryption, and emergency-stop checks pass. It denies shutdown, reboot, formatting, deletion, arbitrary process termination, privilege escalation, registry or firewall changes, software installation/removal, startup modification, security disabling, shell chaining, pipes, redirects, command substitution, and arbitrary shell interpreters.

Maya must not interrupt unrelated programs, terminate processes it does not own, write outside approved application-data paths, consume uncontrolled resources, or continue when process ownership or risk is uncertain. Emergency Stop remains immediate and higher priority than continuity or application control.

## Verification

```text
{"status": "ok", "safe_cooperation_allowed": true, "destructive_actions_blocked": true, "privilege_escalation_blocked": true, "shell_syntax_blocked": true}
{"status": "ok", "default_denied": true, "confirmation_required": true, "allowlist_enforced": true, "shell_syntax_rejected": true, "emergency_stop_blocks": true}
```

These tests validate the policy and runner logic; they do not prove safety against a compromised host, administrator-level malware, or an incorrectly configured external application. The owner must review every allowlisted executable path before enabling control.
