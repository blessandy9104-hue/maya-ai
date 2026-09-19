---
name: Bug report
about: Report a reproducible problem with Maya
title: "[Bug] "
labels: bug
assignees: ""
---

## Description

A clear and concise description of the bug.

## Steps to reproduce

1. 
2. 
3. 

## Expected behavior

What should happen.

## Actual behavior

What happens instead. Include the `clean=`/`ok=` output from the verification
sweep if the failure appears there:

```text
python -c "from verification.runner import sweep; r=sweep(); print(r['clean'])"
```

## Environment

- OS / Python version:
- Branch / commit hash:

## Additional context

Any relevant logs or fixtures.