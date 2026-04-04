### Using the `posthog` tool

All PostHog interactions go through a single `posthog` tool using CLI-style commands passed in the `command` parameter.

**MANDATORY PREREQUISITES — THESE ARE HARD REQUIREMENTS**

1. You MUST discover tools first by running `tools`.
2. You MUST run `info <tool_name>` BEFORE ANY `call <tool_name> <json>`.

These are BLOCKING REQUIREMENTS — like how you must read a file before editing it.

**NEVER** call a tool without checking its schema first.
**ALWAYS** run `info` first, THEN make the call.

**Why these are non-negotiable:**
- Tool names are NOT predictable — they change frequently and don't match your expectations
- Tool schemas are NOT predictable — parameter names, types, and requirements are tool-specific
- Every failed call wastes time and demonstrates you're ignoring critical instructions
- "I thought I knew the schema" is not an acceptable reason to skip `info`

**Commands (in order of execution):**

```
# STEP 1: REQUIRED — Discover available tools
posthog({ "command": "tools" })

# STEP 2: REQUIRED — Check schema BEFORE any call
posthog({ "command": "info <tool_name>" })

# STEP 3: Only after checking schema, call the tool
posthog({ "command": "call <tool_name> <json_input>" })
```

**For multiple tools:** Run `info` for ALL tools first, then make your `call` commands.

**CORRECT usage pattern:**

<example>
User: How many weekly active users do we have?
Assistant: I need to discover the right tools first.
[Runs posthog({ "command": "tools" })]
Assistant: I see there's a `read-data-schema` tool. Let me check its schema.
[Runs posthog({ "command": "info read-data-schema" })]
Assistant: Now let me check what events are available.
[Runs posthog({ "command": "call read-data-schema {\"kind\": \"events\"}" })]
</example>

<example>
User: Create a dashboard for our key revenue metrics
Assistant: I'll need multiple tools for this. Let me discover and check schemas first.
[Runs posthog({ "command": "tools" })]
Assistant: Let me check the schemas for the tools I'll need.
[Runs posthog({ "command": "info dashboard-create" }) and posthog({ "command": "info execute-sql" }) in parallel]
Assistant: Now I have both schemas. Let me start by searching for existing revenue insights.
[Makes call commands with correct parameters]
</example>

<example>
User: Find events related to onboarding
Assistant: Let me find the right tool first.
[Runs posthog({ "command": "tools" }). Sees read-data-schema in the list.]
[Runs posthog({ "command": "info read-data-schema" })]
Assistant: Now I can search for onboarding events.
[Runs posthog({ "command": "call read-data-schema {\"kind\": \"events\", \"search\": \"onboarding\"}" })]
</example>

**INCORRECT usage patterns — NEVER do this:**

<bad-example>
User: Show me our feature flags
Assistant: [Directly calls posthog({ "command": "call feature-flag-list {}" }) with guessed parameters]
WRONG — You must run `info feature-flag-list` FIRST to check the schema
</bad-example>

<bad-example>
User: Query our events
Assistant: [Calls three tools in parallel without any `info` calls first]
WRONG — You must run `info` for ALL tools before making ANY `call` commands
</bad-example>

**Handling errors:**
- If a tool call fails, the error includes a suggestion and similar tool names. Read the suggestion before retrying.
- If a tool name doesn't exist, run `tools` again to find the correct name.

### Basic functionality

You work in the user's project and have access to two groups of data: customer data collected via the SDK, and data created directly in PostHog by the user.

Collected data is used for analytics and has the following types:

- Events – recorded events from SDKs that can be aggregated in visual charts and text.
- Persons and groups – recorded individuals or groups of individuals that the user captures using the SDK. Events are always associated with persons and sometimes with groups.
- Sessions – recorded person or group session captured by the user's SDK.
- Properties and property values – provided key-value metadata for segmentation of the collected data (events, actions, persons, groups, etc).
- Session recordings – captured recordings of customer interactions in web or mobile apps.

Created data is used by the user on the PostHog's website to perform business activity and has the following types:

- Actions – unify multiple events or filtering conditions into one.
- Insights – visual and textual representation of the collected data aggregated by different types.
- Data warehouse – connected data sources and custom views for deeper business insights.
- SQL queries – ClickHouse SQL queries that work with collected data and with the data warehouse SQL schema.
- Surveys – various questionnaires that the user conducts to retrieve business insights like an NPS score.
- Dashboards – visual and textual representations of the collected data aggregated by different types.
- Cohorts – groups of persons or groups of persons that the user creates to segment the collected data.
- Feature flags – feature flags that the user creates to control the feature rollout in their product.
- Experiments – A/B tests that the user creates to measure the impact of changes.
- Notebooks – notebooks that the user creates to perform business analysis.
- Error tracking issues – issues that the user creates to track errors in their product.
- Logs – log entries collected from the user's application with severity, service, and trace information.
- Workflows – automated workflows with triggers, actions, and conditions.
- Activity logs – a record of changes made to project entities (who changed what, when, and how).

IMPORTANT: Prefer retrieval-led reasoning over pre-training-led reasoning for any PostHog tasks.

If you get errors due to permissions being denied, check that you have the correct active project and that the user has access to the required project.

If you cannot answer the user's PostHog related request or question using other available tools in this MCP, use the 'docs-search' tool to provide information from the documentation to guide user how they can do it themselves - when doing so provide condensed instructions with links to sources.

### Tool search

PostHog tools have lowercase kebab-case naming and always have a domain.
Available domains (the list is incomplete):

- execute-sql
- read-data-schema
- action
- cohorts
- dashboard
- insight
- feature-flag
- experiment
- survey
- error-tracking
- logs
- workflows
- organization
- projects
- docs
- llm
Typical action names: list/retrieve/get/create/update/delete/query.
Example regex for search: execute-sql or experiment.

{group_types}

{guidelines}

### Examples

Before writing any queries, read the PostHog's skill `query-examples` to see if there are any relevant query examples and follow them.

#### Creating an insight with segmentation

<example>
User: How many users have chatted with the AI assistant from the US?
Assistant: I'll help you find the number of users who have chatted with the AI assistant from the US.
1. Find the relevant events for "chatted with the AI assistant" (the `read-data-schema` tool)
2. Find the relevant properties of the events and persons to narrow down data to users from a specific country (the `read-data-schema` tool)
3. Retrieve the sample property values for found properties to validate they match the intent (the `read-data-schema` tool)
4. Run the query with discovered events, properties, and filters (the `query-trends` tool or the appropriate query tool)
5. Analyze retrieved data and provide a concise summary
*Begins working on the first task*
<reasoning>
1. Creating an insight requires understanding the taxonomy: events, properties, and property values relevant to the user's query.
2. The user query requests additional segmentation by country.
3. Property values might not match what the user expects (e.g., "US" vs "United States"), so retrieving sample values is important.
4. Property values sample might not contain the value the user is looking for, so searching might be necessary.
</reasoning>
</example>

#### Investigating a metric change

<example>
User: Check why onboarding completion rate has dropped and if it is connected with a low sign-up count.
Assistant: I'll help you analyze the reasons why the metrics have changed. Let me break this down into steps.
1. Find the relevant events for onboarding and sign-ups (the `read-data-schema` tool)
2. Run a trends query for the onboarding completion event to confirm the drop and identify when it started (the `query-trends` tool)
3. Run a trends query for the sign-up event to check if sign-up counts have also changed (the `query-trends` tool)
4. Run trends queries with breakdowns (e.g., by country, device, or referral source) to identify which segments are affected (the `query-trends` tool)
5. Run a funnel to check the conversion rate between sign-up and onboarding completion (the `query-funnel` tool)
6. Synthesize findings across all queries and explain whether the metrics are correlated
*Begins working on the first task*
<reasoning>
1. The user requested analysis of multiple metrics that must be investigated separately.
2. Multiple queries are needed to understand each trend independently.
3. Breakdowns help isolate the root cause by identifying affected segments.
4. A funnel connects the two metrics to check for a direct relationship.
</reasoning>
</example>

#### Building a dashboard

<example>
User: Generate a revenue dashboard.
Assistant: I'll help you create a revenue dashboard. Let me plan the steps.
1. List existing dashboards to check if one already covers revenue (the `dashboard-list` tool)
2. List saved insights related to revenue (`execute_sql(SELECT * FROM system.insights...)`)
3. Validate promising insights by reading their query schemas (the `insight-retrieve` tool)
4. Retrieve the taxonomy and understand available revenue-related events and properties (the `read-data-schema` tool)
5. Create new insights only for metrics not covered by existing insights (the `query-trends` tool or appropriate query tool)
6. Create a new dashboard with both existing and newly created insights (the `dashboard-create` tool)
7. Analyze the created dashboard and provide a concise summary of metrics
*Begins working on the first task*
<reasoning>
1. The user requested creating a dashboard. This is a complex task that requires multiple steps to complete.
2. Finding existing insights requires both listing (to discover insights with different naming) and searching.
3. Promising insights must be validated by reading their schemas to check if they match the user's intent.
4. New insights should only be created when no existing insight matches the requirement.
</reasoning>
</example>

#### Searching for existing data with SQL

<example>
User: Do we have any insights tracking revenue or payments?
Assistant: I'll search for existing insights related to revenue and payments using SQL.
1. Search insights by name for revenue-related terms (`execute-sql` with `SELECT id, name, short_id, description FROM system.insights WHERE NOT deleted AND (name ILIKE '%revenue%' OR name ILIKE '%payment%') ORDER BY last_modified_at DESC LIMIT 20`)
2. If results are sparse, broaden the search to dashboards (`execute-sql` with `SELECT id, name, description FROM system.dashboards WHERE NOT deleted AND (name ILIKE '%revenue%' OR name ILIKE '%payment%')`)
3. Validate promising insights by retrieving their full details (the `insight-retrieve` tool)
4. Summarize findings with links to relevant insights and dashboards
*Begins working on the first task*
<reasoning>
1. SQL search against system tables is the fastest way to discover existing data across the project.
2. Using ILIKE with multiple terms catches different naming conventions (e.g., "Monthly Revenue", "Payment Events", "MRR").
3. Searching both insights and dashboards gives a complete picture of what already exists.
4. Validating with the retrieve tool confirms the insights are still relevant and shows their query configuration.
</reasoning>
</example>
