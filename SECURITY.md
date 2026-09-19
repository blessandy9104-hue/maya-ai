# Security

## Reporting a vulnerability

This project is a personal prototype. If you find a security issue, please open
a private report or email the repository owner directly (do not open a public
issue that describes the exploit).

Please include:

- the affected module and file/line where possible,
- a minimal reproduction,
- the impact you observed.

## Design posture

- **Local and explicit.** The assistant operates only in its working directory;
  application control and background browsing are disabled by default.
- **Owner-gated actions.** Application control requires an owner-enabled fixed
  allowlist, a token, explicit confirmation, an encryption key, and no
  emergency-stop marker.
- **Encrypted audit records.** Audit logging uses `cryptography`; logs fail
  closed rather than weakening when dependencies are missing.
- **No stored secrets.** Keys and tokens are never part of the repository.
  Generated runtime state is git-ignored by policy (`.gitignore`).

## Financial disclaimer

The market-pattern module computes technical indicators for reference and
testing only. Nothing in this repository constitutes financial advice.