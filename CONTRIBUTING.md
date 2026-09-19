# Contributing

Thanks for your interest. This is a personal, human-supervised prototype, so
please keep changes consistent with that scope.

## Local setup

Requires Python 3.10 or later.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Running the tests

Run the public suite battery (this is what CI runs; 15 of the 86 registered
suites are skipped because they need personal/private runtime state that is
intentionally not published):

```powershell
python -c "from verification.runner import sweep; r=sweep(); print(r['clean'])"
```

In a full private checkout, the complete readiness harness is also available:

```powershell
py -3 -m verification
```

The sweep runs every registered suite in its own subprocess and reports the
per-suite `ok=` counts and an overall `clean=` verdict.

## Guiding rules

- **Source comes first.** Generated state (task queues, learning/presence
  status, reports) is tracked only in the working tree, never committed.
  See `.gitignore` — the runtime-state block is policy, not noise.
- **No secrets or personal data.** Never commit API keys, tokens, account paths,
  or personal profiling data. When in doubt, leave it untracked.
- **Consistency is enforced.** Cross-module definitions of shared values are
  mandated (see the math-module consistency rule). A change that breaks that
  consistency fails the verification harness.

## Development loop

1. Run the harness before and after your change:

   ```powershell
   py -3 -m verification
   ```

2. Add a regression fixture alongside any behaviour change. Suites are
   registered in `verification/manifest.py`; new suites need an entry there.
3. Keep the working tree clean of generated artifacts.

## Pull requests

- Describe the problem and the evidence (harness output, fixtures).
- Do not bump versions or touch licenses unless asked.
- Be prepared to remove generated state from the diff.

## Code style

- Python, no third-party dependencies beyond `requirements.txt` unless agreed.
- No new runtime behaviour behind comments; comments explain why, not what.
- Match the surrounding style of the file you change.