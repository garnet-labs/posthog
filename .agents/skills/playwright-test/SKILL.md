---
name: playwright-test
description: Write a playwright test, make sure it runs, and is not flaky.
---

Read @playwright/README.md for best practices, gotchas, and how to run tests.

## Prerequisites

The e2e stack must be running (`./bin/e2e-test-runner`). If the database needs to be set up:

1. Trigger `rebuild-snapshot` in phrocs (first time only, or when migrations change)
2. Trigger `restore-db` in phrocs to restore from the snapshot (fast)

## Rules

- Follow the best practices in the README strictly
- After UI interactions, always assert on UI changes, do not assert on network requests resolving
- **Keep looping until all tests pass.** Do not give up or ask the user for help. You must resolve every failure yourself.

## Instructions

You are to plan an end to end playwright test for a feature.

### Step 1: Plan the test(s) to be done.

Use the Playwright MCP tools (e.g., `mcp__playwright__browser_navigate`, `mcp__playwright__browser_click`, `mcp__playwright__browser_screenshot`) to interact with the browser and plan your tests.

After your exploration, present the plan to me for confirmation or any changes.

### Step 2: Implement the test plan

- Write the tests, making sure to use common patterns used in neighbouring files.
- Run the tests with `pnpm --filter=@posthog/playwright exec playwright test <file name>`
- Debug any failures. Look at screen shots, if needed launch the playwright mcp skills to interact with the browser. Go back to step 1 after attempting a fix.

### Step 3: Ensure no flaky tests

After all tests pass in the file, run with `--repeat-each 10` added to the command. This will surface any flaky tests.

If any test fails across the 10 runs, treat it as a real failure: go back to Step 2, debug, fix, and re-run Step 3. Do not proceed to Step 4 until every run of every test passes.

### Step 4: Report

Once all tests pass, output a single line: **Testing Complete**
