# RFC: PostHog AI Migration to Agents SDK Harness

## Context

PostHog AI ("Max") currently runs as a Python LangGraph agent inside the Django process (`ee/hogai/`).
This creates tight coupling, limits execution capabilities, and diverges from the sandbox-based architecture
already powering PostHog Code (`products/tasks/`).

This RFC proposes migrating Max to the **@posthog/agent harness** running inside a sandbox,
connecting to PostHog via MCP tools -- unifying the AI infrastructure and unlocking code execution,
repository access, and richer tool capabilities.

---

## Phase 0: Foundation -- MCP tool parity & latency (prerequisite)

### 0a. MCP: CF Workers -> in-house infra

**Problem:** Every MCP tool call from the sandbox goes to Cloudflare Workers, adding ~100-300ms RTT per call.
The agent makes 5-15 tool calls per conversation turn.

**Current:** `services/mcp/` -- Cloudflare Worker + Durable Object (`wrangler.jsonc`, `src/integrations/mcp/`).

**Decision:** Single MCP service -- both internal (sandbox) and external (Claude Desktop, Cursor) move to in-house infra.

**Plan:**

- Deploy MCP as a regular Node.js service behind internal load balancer (same infra as other services)
- Replace Durable Object state with Redis for per-user caching (region, distinctId)
- Preserve OAuth flow and regional routing (US/EU)
- All clients (sandbox agent, Claude Desktop, Cursor, etc.) connect to the same in-house endpoint
- Removes CF Workers dependency entirely from the MCP path

**Key files:**

- `services/mcp/src/integrations/mcp/index.ts` -- Worker entry (to be replaced)
- `services/mcp/src/integrations/mcp/mcp.ts` -- Durable Object (state moves to Redis)
- `services/mcp/wrangler.jsonc` -- CF config (to be removed)

### 0b. MCP tool quality audit

**Problem:** MCP tools are less optimized than MaxTools. MaxTools have carefully tuned prompts,
context injection, and specialized handling (e.g., `ReadDataTool` generates HogQL, executes it,
formats results; `ReadTaxonomyTool` does entity search with RAG).

**Current MaxTools to map -> MCP equivalents:**

| MaxTool                             | Purpose                                | MCP equivalent                        | Gap                                         |
| ----------------------------------- | -------------------------------------- | ------------------------------------- | ------------------------------------------- |
| `ReadTaxonomyTool`                  | Browse event/property taxonomy via RAG | `search_events`, `search_properties`  | RAG quality, prompt engineering             |
| `ReadDataTool`                      | Generate & run HogQL queries           | `run_hogql_query`                     | Query generation prompts, result formatting |
| `SearchTool`                        | Full-text search across entities       | `search_*` tools                      | Breadth of search                           |
| `ListDataTool`                      | List dashboards, insights, etc.        | `list_*` tools                        | Pagination, filtering                       |
| `CreateFormTool`                    | Create multi-question forms            | Needs new MCP tool                    | No equivalent                               |
| `CreateNotebookTool`                | Create/update notebooks                | `create_notebook`                     | May need updates                            |
| `TodoWriteTool`                     | Internal task tracking                 | Built into harness                    | Different implementation                    |
| `SwitchModeTool`                    | Switch agent modes                     | **Deprecated**                        | Replaced by tool search                     |
| `ManageMemoriesTool`                | CRUD on agent memories                 | Needs new MCP tool or harness feature | No equivalent                               |
| `CallMCPServerTool`                 | Call external MCP servers              | Native in harness                     | Already supported                           |
| `FinalizePlanTool`                  | Finalize plan in plan mode             | Harness plan mode                     | Different implementation                    |
| `ExecuteSQLTool` (SQL mode)         | Run raw SQL                            | `run_hogql_query`                     | Need SQL passthrough                        |
| Replay tools                        | Search/summarize replays               | `search_recordings`, `get_recording`  | Prompt quality                              |
| `ReadBillingTool`                   | Read billing info                      | Needs new MCP tool                    | No equivalent                               |
| `SearchTracesTool`                  | Search LLM traces                      | `search_traces`                       | Check parity                                |
| Task tools (`CreateTaskTool`, etc.) | Manage Code tasks                      | Already MCP-native                    | Already working                             |

**Action items:**

1. Audit each MaxTool's prompt engineering and result formatting -- port to MCP tool descriptions/schemas
2. Create missing MCP tools: `CreateFormTool`, `ManageMemoriesTool`, `ReadBillingTool`
3. Run comparative evals (MaxTools vs MCP tools) on existing eval suite
4. Enrich MCP tool descriptions with the guidance currently in `context_prompt_template` fields

---

## Phase 1: Backend -- Headless/harness feature migration

### 1a. Context engine -> system_reminders + precalculation

**Current:** `AssistantContextManager` (`ee/hogai/context/context.py`) injects `ContextMessage` objects
into the conversation before the start human message. It precalculates:

- UI context (dashboards, insights, notebooks the user is looking at)
- Billing context
- Group names
- Core memory
- Mode context
- Contextual tools reminders

Each context type has a dedicated provider:

- `ee/hogai/context/dashboard/` -- dashboard + insight context
- `ee/hogai/context/insight/` -- individual insight context
- `ee/hogai/context/notebook/` -- notebook context
- `ee/hogai/context/survey/` -- survey context
- `ee/hogai/context/experiment/` -- experiment context
- `ee/hogai/context/feature_flag/` -- feature flag context
- `ee/hogai/context/error_tracking/` -- error tracking context
- `ee/hogai/context/activity_log/` -- activity log context
- `ee/hogai/context/entity_search/` -- entity search context

**Migration plan:**

**Decision:** Precalculate in Django, inject as system_reminders.

Before sending `user_message` to the agent-server, the Django backend:

1. Runs all context providers (dashboard, insight, notebook, etc.)
2. Formats context into a structured text block
3. Injects as a `system_reminder` in the agent-server message

This keeps the heavy DB/query work in Django where it has direct access.
The agent harness receives rich context without needing PostHog DB access.

**Implementation:**

1. Create a `ContextPrecalculator` service in Django that takes `(team, user, ui_context)` and returns formatted text
2. In the task workflow's `start_agent_server` or `relay_sandbox_events` activity,
   include precalculated context in the first `user_message` as a system_reminder block
3. Port prompt templates from `ee/hogai/context/prompts.py` to the new format

**Large context / attached files -- S3 offloading:**

Precalculated context and user-attached files (CSVs, screenshots, logs, etc.) can exceed
what's practical to inline in a system_reminder. Above a configurable threshold (e.g., 32 KB),
context payloads should be stored on S3 and passed to the sandbox as presigned URLs.

- Django uploads the context blob to S3 (`s3://<bucket>/conversations/<convo_id>/context/<hash>`)
- The agent-server message includes the presigned URL instead of inline content
- The harness fetches the content from S3 on startup (fast -- same region, internal network)
- TTL on presigned URLs matches sandbox TTL (30 min) to avoid dangling access
- Attached files (images, CSVs) follow the same path -- uploaded to S3 by Django,
  URL passed to sandbox, agent reads via presigned URL or file written into sandbox filesystem
- This keeps the agent-server JSON-RPC messages small and avoids Temporal payload size limits

### 1b. Modes -> deprecated, replaced by tool search

**Current:** 7 modes (PRODUCT_ANALYTICS, SQL, SESSION_REPLAY, ERROR_TRACKING, FLAGS, SURVEY, LLM_ANALYTICS)
each with specialized toolkits and prompts. `SwitchModeTool` lets the agent change modes.

**Migration:**

- The @posthog/agent harness uses **tool search** (similar to Claude Code's ToolSearch)
  where tools are discovered dynamically rather than pre-loaded by mode
- All MCP tools are available via tool search -- the agent discovers the right tools for the task
- Mode-specific prompt engineering (e.g., "you are in SQL mode, prefer HogQL") becomes:
  - Tool-level descriptions in MCP tool schemas
  - Skills (`.agents/skills/`) for domain-specific guidance
  - System prompt sections that describe available capabilities

**Action items:**

1. Port mode-specific system prompts to skills or MCP tool descriptions
2. Ensure tool search surfaces the right tools for common queries
3. Eval: compare mode-based routing accuracy vs tool-search-based discovery

### 1c. Conversation history -> text injection

**Current:** `DjangoCheckpointer` stores LangGraph state. `ConversationCompactionManager` manages
window boundaries (100k tokens), summarization.

**Migration:**

- Old conversations will NOT be migrated to the new system's format
- When a user continues an old conversation, history is injected as text content
  (similar to how compaction already summarizes old messages)
- New conversations use the harness's native conversation management

**Implementation:**

1. Add a `legacy_history_formatter` that reads from `DjangoCheckpointer` and formats as text
2. On first message in a migrated conversation, inject formatted history as context
3. New conversations start fresh in the harness

### 1d. Memory system

**Current:** `ManageMemoriesTool` in `ee/hogai/tools/manage_memories.py` + memory onboarding flow
(`ee/hogai/chat_agent/memory/`) + memory collectors (`ee/hogai/chat_agent/memory/nodes.py`).

**Migration:**

- Create an MCP tool for memory CRUD (or extend existing MCP tools)
- Core memory injection already handled by context engine (Phase 1a)
- **Memory onboarding flow and memory collectors are removed** (see "Removed features" section)

### 1e. Plan mode

**Current:** Separate mode with `ChatAgentPlanToolkit`, `FinalizePlanTool`, approval workflows.

**Migration:**

- The @posthog/agent harness has its own plan mode concept
- Map PostHog's plan mode to the harness's plan mode
- Approval workflows: port `interrupt()` / `ApprovalRequest` pattern to harness equivalent

### 1f. Subagent execution

**Current:** Research agent, parallel task execution, subagent mode registries.

**Migration:**

- Map to harness's agent spawning capabilities
- Research agent -> harness agent with web search tools

### 1g. Streaming & SSE

**Current:** `ee/hogai/stream/redis_stream.py` + SSE from Django via `ConversationViewSet`.

**Migration:**

- Sandbox already supports streaming via `relay_sandbox_events` activity
- Django becomes a thin proxy: receives events from sandbox, forwards to client via SSE/WebSocket
- Port `AssistantSSESerializer` format or adopt harness's native format

---

## Phase 2: Frontend migration

### 2a. Message format adaptation

**Current frontend components:**

- `frontend/src/scenes/max/` -- Max UI
- `maxLogic.tsx` / `maxThreadLogic.tsx` -- Kea logic managing conversation state
- `Thread.tsx` -- renders messages
- `MaxTool.tsx` / `useMaxTool.ts` -- renders tool calls
- `sidePanelMaxAPI.ts` -- API client for SSE streaming

**Migration:**

- The streaming endpoint changes from Django SSE to sandbox relay
- Message types may change (harness format vs current schema)
- Tool call rendering needs to handle MCP tool results instead of MaxTool artifacts

**Implementation:**

1. Create adapter layer in `maxThreadLogic.tsx` to normalize both old and new message formats
2. Update `sidePanelMaxAPI.ts` to connect to new streaming endpoint
3. Tool rendering: map MCP tool names to UI components (many already exist for Code tasks)
4. Feature flag the new backend so both paths coexist during migration

### 2b. Conversation management

- New conversation creation -> creates a TaskRun (or equivalent) instead of just a Conversation row
- Conversation list/history -> reads from both old Conversation model and new TaskRun model during transition

---

## Phase 3: Eval migration

### Current eval architecture:

- CI evals: `ee/hogai/eval/ci/` -- 15+ eval files testing different capabilities
- Run via `pytest ee/hogai/eval/ci` with Braintrust integration
- Each eval: creates a team, builds an `AssistantGraph`, invokes it, scores output

### Migration:

1. **Parallel eval harness:** Create new eval runner that:
   - Spins up a sandbox (Docker for CI)
   - Sends messages via agent-server JSON-RPC
   - Collects responses and scores them
2. **Port existing test cases:** Same inputs/expected outputs, different execution path
3. **Run both old and new evals in parallel** during migration to detect regressions
4. **New eval dimension:** Add latency scoring (cold start, tool call latency, total response time)

**Key files:**

- `ee/hogai/eval/base.py` -- base eval class
- `ee/hogai/eval/ci/conftest.py` -- CI eval fixtures
- `ee/hogai/eval/scorers/` -- scoring functions

---

## Phase 4: Latency mitigation

### Problem:

Sandbox cold start is expensive (image pull + boot + agent-server start).
Even warm starts have overhead vs current in-process execution.

### Strategy 1: Pre-warm for online users

- When a user loads a page with Max available, backend signals sandbox pool
- Pool maintains N ready-to-use sandboxes per template
- User gets a pre-warmed sandbox assigned on first message
- **Implementation:** Add `pre_warm_sandbox` Temporal activity triggered by page load / WebSocket connect

### Strategy 2: Start on typing

- Frontend detects user starting to type in Max input
- Sends a lightweight "prepare" signal to backend
- Backend starts sandbox provisioning (clone repo, boot)
- By the time user sends message, sandbox is ready or nearly ready
- **Implementation:** New API endpoint `POST /api/conversations/prepare` that starts sandbox without sending a message

### Strategy 3: Keep-alive for active sessions

- Don't destroy sandbox immediately after response
- Keep alive for 5-10 minutes of inactivity (already TTL=30min in SandboxConfig)
- Reuse for follow-up messages in same conversation

### Latency budget:

| Component     | Current            | Target | Notes                  |
| ------------- | ------------------ | ------ | ---------------------- |
| Cold start    | N/A (in-process)   | <3s    | With pre-warm pool     |
| Warm start    | N/A                | <500ms | Reuse existing sandbox |
| MCP tool call | ~50ms (in-process) | <100ms | With in-house MCP      |
| First token   | ~1-2s              | <3s    | Including context prep |

### Keep-alive cost analysis (Modal)

Using a reduced sandbox spec for Max conversations (no repo cloning, no code execution --
just agent + MCP calls): **0.5 vCPU, 1 GB RAM, 5-minute keep-alive**.

Modal pricing (per-second billing, [modal.com/pricing](https://modal.com/pricing)):

- CPU: $0.00003942/physical-core/sec (1 physical core = 2 vCPU)
- Memory: $0.00000672/GiB/sec

| Resource                    | Calculation                              | 5 min cost                |
| --------------------------- | ---------------------------------------- | ------------------------- |
| CPU (0.5 vCPU = 0.25 cores) | 0.25 cores x 300s x $0.00003942/core/sec | **$0.00296**              |
| Memory (1 GiB)              | 1 GiB x 300s x $0.00000672/GiB/sec       | **$0.00202**              |
| **Total per sandbox**       |                                          | **$0.00497** (~0.5 cents) |

**Single conversation:** One 5-minute keep-alive window costs ~**$0.005**.
If the user sends follow-up messages within the window, no additional sandbox cost
(just extends the timer). A typical multi-turn conversation might keep alive
for 2-3 windows = **$0.01-0.015** in sandbox compute.

**At scale (10,000 conversations/day):**

| Scenario                          | Assumption                                  | Daily cost               | Monthly cost (30d)          |
| --------------------------------- | ------------------------------------------- | ------------------------ | --------------------------- |
| Single window                     | Each convo uses 1x 5min keep-alive          | $49.70                   | **$1,491**                  |
| Multi-turn (avg 2 windows)        | Users send follow-ups, extending keep-alive | $99.40                   | **$2,982**                  |
| Pre-warm pool (50 hot sandboxes)  | 50 sandboxes kept warm continuously 24h     | $71.60/day pool overhead | **$2,148** pool + per-convo |
| Pre-warm + 10k convos (2 windows) | Pool + actual usage                         | $171                     | **$5,130**                  |

**Key takeaway:** Keep-alive is cheap at ~0.5 cents per conversation.
The pre-warm pool of 50 sandboxes adds ~$72/day ($2.1k/month).
At 10k conversations/day, the total sandbox compute is ~$3k-5k/month --
modest compared to LLM inference costs for the same volume.

**Comparison to current architecture:** Current in-process execution has zero marginal
compute cost per conversation (Django process is already running). The sandbox model
adds ~$0.005-0.015 per conversation in compute overhead, which is negligible relative
to the ~$0.10-1.00+ LLM cost per conversation (depending on tool calls and context size).

---

## Phase 5: Quality & personality

### 5a. Prompt merging

**Problem:** The @posthog/agent harness has its own system prompt (general-purpose coding agent).
PostHog AI needs to be focused on product engineering with PostHog.

**Plan:**

1. Create a PostHog-specific system prompt layer that:
   - Establishes Max's identity and personality
   - Focuses on PostHog product analytics workflows
   - Includes domain knowledge (events, properties, HogQL, etc.)
   - References available MCP tools and their best uses
2. Merge with harness base prompt (harness provides tool use mechanics, PostHog provides domain)
3. Use skills (`.agents/skills/`) for specialized domain knowledge

**Key prompt sources to port:**

- `ee/hogai/chat_agent/prompts/` -- main agent prompts
- `ee/hogai/core/agent_modes/prompts.py` -- mode reminders
- `ee/hogai/core/agent_modes/presets/` -- per-mode prompt definitions
- `ee/hogai/PROMPTING_GUIDE.md` -- guidelines

### 5b. Quality eval

1. Run existing eval suite against new architecture **before** any migration
2. Establish baseline scores
3. After migration, compare scores -- no regression allowed on:
   - Tool selection accuracy (does agent pick right tool?)
   - Query correctness (SQL/HogQL)
   - Response helpfulness
   - Personality consistency
4. Add new eval dimensions:
   - Tool search effectiveness (finding right MCP tool)
   - End-to-end latency
   - Context utilization (does agent use injected context?)

---

## Migration sequence (recommended order)

```text
Phase 0 (parallel, prerequisite):
  0a. MCP infra migration (CF Workers -> in-house)
  0b. MCP tool quality audit & gap filling

Phase 1 (sequential):
  1a. Context engine precalculation service
  1b. Mode deprecation + tool search validation
  1c. Conversation history text injection
  1d. Memory system MCP tool
  1e. Plan mode mapping
  1f. Subagent execution mapping
  1g. Streaming adapter

Phase 2 (after Phase 1):
  2a. Frontend message format adapter (behind feature flag)
  2b. Conversation management dual-path

Phase 3 (parallel with Phase 2):
  3. Eval migration + parallel running

Phase 4 (parallel with Phase 1):
  4. Latency mitigation (pre-warm, typing detection)

Phase 5 (continuous):
  5a. Prompt merging + personality tuning
  5b. Quality eval baseline + regression tracking
```

## Rollout strategy

1. **Feature flag:** `hogai-agents-sdk-migration` gates new path
2. **Shadow mode:** Run both old and new in parallel, compare outputs (no user-facing)
3. **Internal dogfood:** Enable for PostHog team first
4. **Gradual rollout:** 5% -> 25% -> 50% -> 100% of users
5. **Fallback:** Old path remains available for 2 months post-full-rollout

## Removed features

These features will **not** be migrated and are intentionally dropped:

1. **Memory onboarding flow** (`ee/hogai/chat_agent/memory/nodes.py`):
   The multi-step wizard (MemoryOnboardingNode, MemoryInitializerNode, MemoryOnboardingEnquiryNode, etc.)
   that walks users through setting up core memories about their product.
   Memory CRUD via `ManageMemoriesTool` is still migrated as an MCP tool, but the onboarding wizard is removed.

2. **Memory collectors** (`ee/hogai/chat_agent/memory/nodes.py` -- MemoryCollectorNode, MemoryCollectorToolsNode):
   The background memory collection system that automatically extracts and stores memories from conversations.
   Memories will be managed explicitly by the user or agent via the memory MCP tool.

3. **Agent modes** (`ee/hogai/core/agent_modes/`):
   The 7-mode system (PRODUCT_ANALYTICS, SQL, SESSION_REPLAY, ERROR_TRACKING, FLAGS, SURVEY, LLM_ANALYTICS)
   and `SwitchModeTool`. Replaced by MCP tool search -- the agent discovers relevant tools dynamically.

4. **LangGraph state machine** (`ee/hogai/core/base.py`, `DjangoCheckpointer`):
   The LangGraph StateGraph + Django checkpoint system. Replaced by @posthog/agent harness's native
   conversation management.

---

## Open questions

1. Approval workflow mapping -- does the harness have a native interrupt/approval mechanism
   to replace `interrupt()` / `ApprovalRequest`?
2. Billing/quota enforcement -- currently in Django middleware, needs to work with sandbox model
3. How to handle the `DangerousOperationApprovalCard` UI pattern in the new architecture?
4. Slash commands (`ee/hogai/chat_agent/slash_commands/`) -- port as skills or drop?

## Verification

- Run existing CI evals (`pytest ee/hogai/eval/ci`) against new architecture
- A/B test latency: measure p50/p95/p99 for first token and full response
- Monitor MCP tool call success rates and latency
- User satisfaction survey comparing old vs new experience
- Track conversation completion rates (do users get answers?)
