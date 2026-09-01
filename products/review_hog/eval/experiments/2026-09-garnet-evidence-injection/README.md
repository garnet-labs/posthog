# Garnet evidence-injection A/B (2026-09)

Does automatically injecting a compact, exact-head Garnet Runtime Review block into the
trusted reviewer context change ReviewHog-style review outcomes on dependency/toolchain PRs?

## Design

- **Corpus**: the 50 replay PRs #139–#188 on garnet-labs/posthog (real upstream
  dependency-only commits replayed under Garnet recording). All 50 have a live head SHA and
  an exact-head Garnet record (`garnet:commit` marker equal to the head). Frozen in
  `harness/corpus.json`.
- **Arms** (byte-identical inputs otherwise):
  - _control_: ReviewHog's own review + validation prompts, unmodified.
  - _treatment_: the same prompts with a `<garnet_runtime_evidence>` block inserted after
    `<pr_intent>` — receipt_id, head SHA, compared SHA (or explicit "comparison
    unavailable"), added/removed recorded network/process/file evidence, deterministic
    detections. Machine-derived from the Garnet record (`harness/build_block.py`), never
    hand-written. Injected as TRUSTED pipeline content, not PR-author content — ReviewHog's
    prompt declares everything quoted from the PR untrusted, so the PR-body channel is wrong
    by design.
- **Drill-down parity**: both arms get the same read-only `garnet_drilldown` tool returning
  the full recorded evidence for the head. Every invocation is logged per (PR, arm, stage)
  and reported separately — drill-down is never the verdict source.
- **Stages**: review (issues_review template + schema) then per-finding validation
  (issue_validation template + schema), mirroring the production funnel.
- **Metrics** (`harness/score.py`): findings raised/validated/dismissed, post-validator
  severity mix, tier/escalation proxy (highest validated severity per PR),
  evidence-grounded findings, recall vs an adjudicated set (`adjudicated.json`), and
  drill-down invocations per stage.
- **Human attention**: not measured — no-publish eval runs; requires a publish path.

## Fidelity and documented deviations

Prompts, output schemas, and the untrusted-content contract are ReviewHog's own
(`products/review_hog/backend/reviewer/prompts/`). Deviations, identical across arms:
single chunk per PR (small dependency-only diffs), no repo checkout (full patches are in
the prompt), skills served by a stubbed `skill-get` tool (`harness/skills.py`), direct
Anthropic API instead of the sandbox agent loop.

## Running

```bash
cd harness
python3 fetch_corpus.py            # freeze corpus.json (gh auth required)
python3 build_block.py             # derive blocks.json evidence blocks
ANTHROPIC_API_KEY=... python3 run_arms.py --prs 139,145,150,155,160,165,170,175,180,188
python3 score.py                   # results.md
```

`run_arms.py` is idempotent per (PR, arm) — rerun to fill failed rows.
