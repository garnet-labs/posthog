---
name: regenerating-ci-diagrams
description: >
  Regenerate Mermaid CI workflow diagrams after modifying GitHub Actions
  workflow files or composite actions. Use when changes are made to
  .github/workflows/ or .github/actions/ files.
---

# Regenerating CI diagrams

When you modify files under `.github/workflows/` or `.github/actions/`,
regenerate the CI visualization diagrams so they stay in sync.

## When to trigger

- Any change to `.github/workflows/*.yml` or `.github/workflows/*.yaml`
- Any change to `.github/actions/` composite actions
  (these may affect job behavior shown in diagrams)

## Steps

1. Run the generator:

   ```bash
   hogli build:ci-diagrams
   ```

2. Review the diff in `docs/internal/ci/` to verify the diagrams
   reflect your workflow changes.
3. Include the updated diagram files in the same commit as
   the workflow changes.

## Regenerating a single workflow

```bash
hogli build:ci-diagrams ci-backend.yml
```

## Adding a new workflow to the diagram set

Edit the `DEFAULT_WORKFLOWS` list in `bin/generate-ci-diagrams.py`
and re-run.
