# Maya

_Project Veldt Meridian_

[![CI](https://github.com/blessandy9104-hue/maya-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/blessandy9104-hue/maya-ai/actions/workflows/ci.yml)

**A local, human-supervised Python assistant prototype with a sandboxed command
surface, persona layer, and market-pattern analysis module — no account-specific
paths, no external services required.**

Maya is a local, human-supervised Python assistant prototype. It runs from
whichever folder contains the source — no account-specific paths are required —
and stores its own in-memory and on-disk state beside the code, so moving or
copying the folder needs no source edits.

## What it does

- **Deterministic command surface** — a sandboxed set of operators (file,
  process, archive, network) with explicit routing; commands stay available even
  without external services.
- **Personas** — an identity layer (`maya_identity/`) and a persona runtime
  (`persona_layer/`) that shape tone and behavior, including a market-analysis
  persona built on the market pattern module.
- **Conversation & learning** — long/short-term memory stores, topic isolation,
  and learning metrics under `maya_conversation/`.
- **Math core** — `maya_math/` plus a mandated cross-module consistency rule
  (the same definition of a value is enforced everywhere).
- **Market pattern module** — `maya_runtime/market/mpm.py` computes technical
  indicators (RSI, ATR, EMAs) and pattern classifications for reference and
  testing. It is not investment advice.
- **Verification harness** — `verification/` runs the bundled suite of feature
  and regression checks. See [Test](#test).

## Setup

Requires Python 3.10 or later, then install the small optional runtime
dependencies:

```powershell
py -3 -m pip install -r requirements.txt
```

`cryptography` enables encrypted audit records and their tests. `psutil` enables
live resource monitoring (Maya fails closed when it is absent). The free-form
chat fallback expects a local Ollama server with the configured model:
`qwen2.5-coder:3b`. Deterministic commands remain available when that server is
unavailable.

## Run

From this folder:

```powershell
py -3 .\maya_chat.py
# or
py -3 .\maya_app.py
```

The desktop interface starts the colocated Python chat directly; WSL and an
account-specific path are not required. Application control and background
browsing are disabled by default.

## Test

Run the public suite battery (71 of 86 suites; the other 15 require
personal/private runtime state that is intentionally not published):

```powershell
python -c "from verification.runner import sweep; r=sweep(); print(r['clean'])"
```

This is the same command CI runs. In the full private workspace, the complete
readiness harness is also available:

```powershell
py -3 -m verification
```

The harness discovers the registered suites from `verification/manifest.py`,
runs each, and reports an aggregate verdict. Some suites depend on datasets
that are bundled separately; those are reported as such by the harness.

## Safety boundary

Maya's learning session is local and explicit. Public research is read-only and
happens only for an explicit topic request. Application control requires an
owner-enabled fixed allowlist, token, confirmation, encryption key, and no
emergency-stop marker.

## Scope

Maya is a personal assistant prototype, not a product. It is not a
replacement for human judgment. The market-pattern module computes indicators
and pattern labels for reference and testing only; nothing in this repository
constitutes financial advice.

## Releases

- **v0.1.0 — Initial public release** files and notes are published on the
  [releases page](https://github.com/blessandy9104-hue/maya-ai/releases).
- Version history is maintained in [CHANGELOG](CHANGELOG.md).

## Contributing & security

See [CONTRIBUTING](CONTRIBUTING.md) for setup, test, and PR guidance, and
[SECURITY](SECURITY.md) for the vulnerability reporting process.

## License

[MIT](LICENSE)