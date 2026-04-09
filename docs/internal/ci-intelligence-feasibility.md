# Feasibility Assessment: AI-Native CI/CD Runner Product in PostHog

## Context

PostHog's CI is under severe strain. The backend CI alone runs **50+ parallel jobs** (38 core Django shards, 7 persons-on-events shards, 7 Temporal shards, plus dynamic product matrix jobs), each requiring a full Docker stack (ClickHouse, Kafka, Redis, PostgreSQL, Temporal, Elasticsearch, Minio). The test suite contains **34,556 tests** totaling **6.4 hours of serial execution time** across 75 workflow files (14,256 lines of YAML). Despite already using Depot runners and Turborepo-based selective testing, there are hours-long periods of degraded performance that kill developer productivity.

The question: should PostHog build an AI-native CI/CD runner product — like GitHub Actions or Depot CI — as a new product within PostHog?

---

## Executive Summary: Don't Build a CI Runner. Build CI Intelligence.

**Building a full CI/CD runner is not feasible or advisable.** The infrastructure challenge is enormous, it's a poor strategic fit for PostHog, and the competitive moat is thin. However, there is a genuinely compelling opportunity to build an **AI-native CI intelligence product** that plays to PostHog's strengths in analytics, observability, and AI.

---

## Part 1: Why a Full CI Runner is a Bad Idea

### Strategic Misfit

PostHog is a product analytics and data platform. CI/CD runners are low-level infrastructure — a fundamentally different business:

- **Different buyer**: CI runners sell to platform engineering teams on cost/speed. PostHog sells to product teams on insights.
- **Different expertise**: Running sandboxed compute at scale requires deep infrastructure expertise (kernel-level isolation, network security, storage drivers, multi-tenancy). PostHog's strength is analytics pipelines and product UX.
- **Different economics**: CI runners are a commodity race to the bottom on price-per-minute. GitHub Actions at $0.008/min is hard to undercut.
- **Market timing**: The CI runner market is mature and crowded (GitHub Actions, CircleCI, GitLab CI, Jenkins, Buildkite, Depot, BuildJet, Namespace, Dagger, Earthly). Entering now means competing on execution speed — a hardware/infrastructure problem, not a software one.

### Technical Complexity is Staggering

Even with PostHog's existing infrastructure, the gap to a production CI runner is enormous:

| Component | PostHog Has | What CI Needs | Gap |
|-----------|------------|---------------|-----|
| Job execution | Modal sandboxes (4 CPU, 16GB) | Arbitrary container images, service containers, GPU support | **Massive** — need to run user-specified Docker images, not just PostHog's sandbox |
| Scheduling | Temporal workflows | Sub-second webhook-to-execution, intelligent queue routing, priority lanes | **Large** — Temporal adds ~1-5s overhead, CI needs <500ms dispatch |
| Configuration | None | Full YAML DSL parser with conditionals, expressions, matrix expansion, reusable workflows | **From scratch** — this alone is months of work |
| Caching | None | Docker layer caching, dependency caching, build output caching across runs | **From scratch** — this is where Depot differentiates and it took them years |
| GitHub integration | OAuth + repo cloning | Webhooks, Check Runs API, Check Suites, commit status, PR comments, OIDC, deployment environments | **Significant** — need deep GitHub App integration, not just OAuth |
| Security | Modal sandboxes | Network egress control, secrets scoping per environment, OIDC token exchange, audit logging | **Large** — CI runners are high-value attack targets |
| Self-hosted runners | None | Runner agent, registration protocol, work distribution, NAT traversal, update mechanism | **Entire subsystem from scratch** |
| Ecosystem | None | Marketplace of reusable actions/steps, pre-built integrations | **Years of community building** |

**Rough effort estimate for a minimal viable CI runner**: 4-6 engineers, 12-18 months, before it could run PostHog's own CI.

### PostHog's Own CI Would Be the Hardest Test Case

The irony: PostHog's CI is one of the most demanding workloads imaginable:
- Each test job needs **7 services** (ClickHouse, Kafka, Redis, PostgreSQL, Temporal, Elasticsearch, Minio)
- Tests require Rust compilation alongside Python
- Jobs need large runners (the equivalent of 16-32 vCPU machines)
- 50+ concurrent jobs during peak development

Building a CI runner that can handle this from day one is unrealistic. You'd need to dogfood on simpler repos first — but then you're building for customers you don't understand yet.

---

## Part 2: What PostHog *Should* Build Instead

### The Opportunity: CI Intelligence Layer

PostHog has unique advantages that no CI runner company has:
1. **Analytics DNA** — world-class at collecting, storing, querying, and visualizing event data
2. **AI infrastructure** — the Tasks product already runs AI agents in sandboxes
3. **Product analytics expertise** — understanding user behavior (developer = user, CI = product)
4. **ClickHouse** — perfect for storing and querying massive CI telemetry data

The idea: **a product that makes any CI system smarter**, rather than replacing GitHub Actions.

### Concrete Product: "CI Analytics" or "Developer Velocity"

A new PostHog product that ingests CI telemetry and provides AI-powered insights:

#### Feature Set

**1. CI Telemetry Ingestion**
- GitHub Actions webhook integration (workflow_run, check_suite, check_run events)
- OpenTelemetry collector for CI traces
- Test result ingestion (JUnit XML, pytest JSON)
- Ingest from any CI system (GitHub Actions, CircleCI, GitLab CI, Jenkins)

**2. Intelligent Test Selection (the killer feature)**
- Analyze which tests actually fail given specific code changes
- Build a statistical model: "file X changed → tests Y, Z are likely to fail"
- Provide a `posthog ci suggest-tests` CLI that outputs the minimal test set
- This is the #1 thing that would fix PostHog's own CI: instead of running 34,556 tests, run the 500 that matter
- Prior art: Meta's TestPilot, Google's TAP, Launchable, Buildpulse

**3. Flaky Test Detection & Quarantine**
- Detect tests that pass/fail non-deterministically across runs
- Auto-quarantine flaky tests so they don't block PRs
- PostHog already has 20+ tests timing out at exactly 60.0s — these are likely flaky or misconfigured

**4. AI-Powered Failure Analysis**
- When CI fails, use LLMs to analyze the failure log + code diff
- Generate a "here's what likely went wrong and how to fix it" summary
- PostHog's Tasks product already has the sandbox infrastructure for running AI agents
- Could auto-suggest PR fixes for common failure patterns

**5. Developer Velocity Dashboard**
- CI time trends (are we getting slower?)
- Queue wait time analysis (when are runners saturated?)
- Per-team/per-product build time breakdown
- Cost analysis (which tests cost the most compute?)
- Merge queue analytics

**6. Performance Regression Detection**
- Track test execution times across commits
- Alert when a change causes significant test slowdown
- Correlate with code changes ("this PR added 45s to batch_export tests")

### Why This is Better Than Building a Runner

| Dimension | CI Runner | CI Intelligence |
|-----------|-----------|----------------|
| Time to value | 12-18 months | 2-3 months for first feature |
| Strategic fit | Infrastructure company | Analytics/AI company |
| Competitive moat | Hardware speed (commodity) | Data + AI models (defensible) |
| Market | Crowded | Emerging (Launchable, Buildpulse, but no dominant player) |
| Dogfooding | Can't run own CI initially | Can analyze own CI from day 1 |
| Customer base | New buyer persona | Existing PostHog customers |
| Revenue model | Compute minutes (race to bottom) | Per-seat or per-repo (analytics model) |

---

## Part 3: Technical Implementation Path

### Phase 1: CI Telemetry + Flaky Test Detection (4-6 weeks)

**New product**: `products/ci_analytics/`

**Models**:
- `CIWorkflowRun`: workflow run metadata (repo, branch, duration, status, cost)
- `CIJobRun`: individual job execution data
- `CITestResult`: per-test pass/fail/skip with duration
- `CIFlakyTest`: detected flaky tests with confidence scores

**Ingestion**:
- GitHub App webhook listener for `workflow_run`, `check_run`, `check_suite` events
- JUnit XML / pytest JSON test result upload API
- Store telemetry in ClickHouse for analytics, metadata in product DB

**Leverage existing**:
- ClickHouse analytics queries (PostHog's core competency)
- GitHub OAuth integration from `products/integrations/`
- Celery tasks for background processing
- Product architecture patterns (facade, contracts)

### Phase 2: Intelligent Test Selection (6-8 weeks)

- Build code-change-to-test-failure correlation model
- Use git diff analysis + historical test result data
- Ship `posthog ci suggest-tests` CLI tool
- Integrate with GitHub Actions as a step: "only run these tests"

### Phase 3: AI Failure Analysis (4-6 weeks)

- Leverage Tasks product's LLM infrastructure
- When CI fails, pipe logs + diff to AI agent
- Post analysis as PR comment
- Optionally generate fix PRs

### Key Files to Build On

- `products/tasks/backend/temporal/` — workflow orchestration patterns
- `products/tasks/backend/services/sandbox.py` — sandbox execution for AI agents
- `products/integrations/` — GitHub OAuth integration
- `products/batch_exports/` — ClickHouse data pipeline patterns
- `posthog/temporal/common/` — Temporal worker infrastructure
- `.github/workflows/ci-backend.yml` — understand the CI we're optimizing
- `.test_durations` — 34,558 test timing entries to seed the model

---

## Part 4: Risk Analysis

### Risks of the Intelligence Approach (manageable)
- **Data quality**: CI telemetry is noisy; test selection models need high accuracy or developers lose trust
- **Cold start**: Need enough historical data before intelligent test selection is useful
- **Integration friction**: Customers need to install a GitHub App and add a CI step — adoption barrier

### Risks of the Runner Approach (severe)
- **Scope creep**: CI runners have infinite feature surface; you'll always be missing something
- **Security liability**: Running arbitrary code is a massive attack surface
- **Operational burden**: 24/7 infrastructure SLA expectations
- **Talent mismatch**: Need infrastructure engineers, not product engineers
- **Opportunity cost**: 12-18 months of 4-6 engineers not building PostHog's core product

---

## Part 5: Immediate Optimizations (parallel track)

While building CI Intelligence, these changes could help PostHog's CI today:

1. **Fix the 60s timeout tests**: 20+ tests are timing out — these are either flaky or need investigation
2. **Better test isolation**: The `posthog/` directory alone has 22,015 tests (271 min). Break out more products.
3. **Shared Docker stack**: Consider running multiple product test suites against a single Docker stack instead of spinning up 50+ independent stacks
4. **Test dependency analysis**: Use `pytest-testmon` or similar to only run tests whose code actually changed
5. **Smarter caching**: The turbo-discover system is good but could be enhanced with test-level granularity

---

## Verification

This is a research/feasibility document, not a code change. No verification steps needed.

---

## Recommendation

**Do not build a CI/CD runner.** Instead, build a **CI Intelligence** product that:
1. Provides immediate value by analyzing PostHog's own CI (dogfooding from day 1)
2. Plays to PostHog's analytics and AI strengths
3. Can ship incremental value in weeks, not months
4. Has a defensible moat (data + ML models, not commodity compute)
5. Serves existing customers without requiring a new sales motion

The biggest single impact would be **intelligent test selection**: reducing PostHog's test suite from 34,556 tests to the ~500 that matter for any given change would be transformative — cutting CI time by 90%+ without any infrastructure changes.
