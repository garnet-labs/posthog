---
name: exploring-logs-mcp
description: >
  How to query and explore application logs using PostHog's logs MCP tools.
  Use when debugging production issues, investigating errors, or searching
  for log entries by service, severity, time range, or content.
---

# Exploring logs with MCP tools

Three MCP tools are available for log exploration:

| Tool                                 | Purpose                                   |
| ------------------------------------ | ----------------------------------------- |
| `posthog:logs-list-attributes`       | Discover filterable attribute keys        |
| `posthog:logs-list-attribute-values` | Get possible values for a given attribute |
| `posthog:logs-query`                 | Search and query log entries              |

## Step-by-step workflow

### 1. Find the correct service name

Service names are resource-level attributes. Never guess — always look them up first.

```json
posthog:logs-list-attribute-values
{
  "key": "service.name",
  "attributeType": "resource",
  "search": "<partial name>"
}
```

The `search` parameter filters by substring, so `"temporal"` returns all temporal worker services.

### 2. Discover available attributes (optional)

If you need to filter on something beyond the log message, discover what attributes exist:

```json
posthog:logs-list-attributes
{
  "attributeType": "log",
  "search": "<partial key name>"
}
```

```json
posthog:logs-list-attributes
{
  "attributeType": "resource",
  "search": "<partial key name>"
}
```

The `search` parameter filters attribute keys by substring. Use `limit` (1-100, default 100) and `offset` (default 0) for pagination.

To find possible values for a specific attribute:

```json
posthog:logs-list-attribute-values
{
  "key": "level",
  "attributeType": "log"
}
```

### 3. Query logs

All queries require `dateFrom` and `dateTo` in ISO 8601 format.

**Search by message content:**

```json
posthog:logs-query
{
  "dateFrom": "2026-03-29T00:00:00Z",
  "dateTo": "2026-03-30T00:00:00Z",
  "serviceNames": ["temporal-worker-max-ai"],
  "filters": [
    {"key": "message", "type": "log", "operator": "icontains", "value": "some-uuid-or-keyword"}
  ],
  "limit": 100
}
```

**Filter by severity:**

```json
posthog:logs-query
{
  "dateFrom": "2026-03-29T00:00:00Z",
  "dateTo": "2026-03-30T00:00:00Z",
  "serviceNames": ["temporal-worker-max-ai"],
  "severityLevels": ["error", "fatal"]
}
```

**Filter by attribute:**

```json
posthog:logs-query
{
  "dateFrom": "2026-03-29T00:00:00Z",
  "dateTo": "2026-03-30T00:00:00Z",
  "filters": [
    {"key": "conversation_id", "type": "log_attribute", "operator": "exact", "value": "some-uuid"}
  ]
}
```

## Filter reference

Each filter has three required fields:

| Field      | Values                                                                                                                                  |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `type`     | `"log"` (message body), `"log_attribute"` (log-level), `"log_resource_attribute"` (resource-level e.g. k8s labels)                      |
| `operator` | `exact`, `is_not`, `icontains`, `not_icontains`, `regex`, `not_regex`, `is_set`, `is_not_set`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in` |
| `key`      | For type `"log"` use `"message"`. For attributes use the attribute key (e.g. `"conversation_id"`, `"k8s.pod.name"`)                     |

Combine multiple filters with `filtersType: "AND"` (default) or `"OR"`.

## Pagination

If `hasMore` is `true` in the response, pass `nextCursor` as the `after` parameter in the next call.

## Tips

- Start with a narrow time range and widen if needed — broad queries can be slow
- Use `icontains` for message search, `exact` for UUIDs and known values
- Filter by `serviceNames` whenever possible to narrow results
- Use `orderBy: "earliest"` to see events chronologically, `"latest"` (default) for most recent first
- The `limit` parameter accepts 1-1000 (default 100)
