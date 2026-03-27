from prometheus_client import Counter, Histogram

ENDPOINT_EXECUTION_TOTAL = Counter(
    "posthog_endpoint_execution_total",
    "Total endpoint execution attempts",
    labelnames=["execution_type", "status"],
)

ENDPOINT_EXECUTION_DURATION_SECONDS = Histogram(
    "posthog_endpoint_execution_duration_seconds",
    "End-to-end endpoint execution duration",
    labelnames=["execution_type"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, float("inf")),
)

ENDPOINT_MATERIALIZATION_EVENT_TOTAL = Counter(
    "posthog_endpoint_materialization_event_total",
    "Materialization lifecycle events (enable/disable/deactivate_stale)",
    labelnames=["action", "status"],
)

ENDPOINT_DUCKLAKE_FALLBACK_TOTAL = Counter(
    "posthog_endpoint_ducklake_fallback_total",
    "DuckLake executions that fell back to inline",
)

ENDPOINT_RATE_LIMITED_TOTAL = Counter(
    "posthog_endpoint_rate_limited_total",
    "Rate-limited endpoint requests",
    labelnames=["scope"],
)
