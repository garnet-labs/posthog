# Signals Report Generation

This directory contains the new agentic report-research flow for Signals.
It is exercised locally via management commands, and it is also used by the production
Temporal summary flow behind a feature flag. In production, the summary workflow runs
the safety judge first, then calls into this flow via a Temporal activity if the report is safe.

## What lives here

- `research.py`
  Orchestrates a multi-turn sandbox session over a report's signals.
  The agent researches each signal, then produces:
  - per-signal findings
  - actionability assessment
  - priority assessment when actionable
  - final report title
  - very short factual summary
- `fixtures/analyze_report_funnel_research_output.json`
  Saved previous research output used by local `update` testing.

## Mental model

`run_multi_turn_research()` is the main entrypoint.

- `research` behavior:
  start from raw signals only
  research each signal as new
  produce findings + assessments + title/summary
- `update` behavior:
  start from raw signals plus a previous `ReportResearchOutput`
  match previous findings by `signal_id`
  lightly validate old findings before reusing them
  fully research only new or stale signals
  show previous actionability, priority, title, and summary as context
  regenerate those outputs only as much as needed

This flow is intentionally prompt-orchestration only right now.
Do not assume DB persistence or production artefact storage exists here unless you add it explicitly.
Production persistence is handled outside `run_multi_turn_research()`, in the caller activity,
so this module stays isolated from report DB writes.

## Local debug commands

These commands are debug-only local-dev tools.
They are not production entrypoints.

### `analyze_report`

File: `../management/commands/analyze_report.py`

Runs the agentic flow against synthetic signals.

- `python manage.py analyze_report research`
  Fresh research run from the hardcoded synthetic signals.
- `python manage.py analyze_report update`
  Loads `fixtures/analyze_report_funnel_research_output.json` as previous report research,
  appends one extra synthetic signal,
  and tests the re-research path.

Use this command when changing prompt logic in `research.py`.

### `parse_sandbox_log`

File: `../management/commands/parse_sandbox_log.py`

Takes a verbose sandbox log file and renders a concise timeline of:

- prompts
- tool calls
- tool outputs
- agent messages
- optional thought chunks

Use it to inspect long `analyze_report --verbose` runs without reading raw JSONL.

## When editing this flow

- Keep the roles separate:
  summary/title describe what the report is about;
  actionability/priority explain what to do and how urgent it is.
- If you change the output shape of `ReportResearchOutput`,
  update `fixtures/analyze_report_funnel_research_output.json` too.
- Keep persistence out of `run_multi_turn_research()`.
  If production needs new report artefacts or state transitions, do that in the caller activity/workflow.
- If you change how local debug commands exercise this flow,
  update this file and `../management/AGENTS.md`.
- **If you change any command or the flow, update this file to match**
