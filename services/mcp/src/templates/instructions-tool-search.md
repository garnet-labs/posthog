This MCP server uses tool search mode. Instead of having all tools loaded at once, you discover and call them on demand using three meta-tools that MUST be called in order:

1. **tool_search** (required) — Find tools by keyword. Returns names and short summaries. You must always start here — do not guess tool names.
2. **tool_schema** (required) — Get the full input schema for a tool by its exact name. You must call this before tool_call to know the accepted parameters.
3. **tool_call** — Execute a tool with the parameters matching the schema from step 2.

IMPORTANT: Always follow the sequence tool_search → tool_schema → tool_call. Do not skip steps. Do not call tool_call without first retrieving the schema via tool_schema.

### Tool naming conventions

Tools use lowercase kebab-case with a domain prefix. Common domains: dashboard, insight, feature-flag, experiment, survey, cohort, error-tracking, logs, action, workflows, organization, projects, docs, llm.
Typical action suffixes: list, get, get-all, create, update, delete, query.
Example search queries: "feature flag", "experiment results", "dashboard create".
