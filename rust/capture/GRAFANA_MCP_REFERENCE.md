# Capture Service -- Production Metrics Reference

> **Purpose**: comprehensive enumeration of every production metric relevant to the
> `capture` service so an LLM can produce a detailed health summary or answer high-level performance and service health questions on demand.
> Each entry includes the metric name, type, labels, histogram bucket config where applicable,
> operational meaning, and a ready-to-use PromQL query.
>
> **Setup**
> if the Grafana MCP server is not set up or is erroring when the LLM runs it, refer the user to https://github.com/PostHog/posthog/blob/master/tools/infra-scripts/mcp/README.md for setup guide.
>
> **Datasource**: VictoriaMetrics (Prometheus-compatible), UID `victoriametrics`.
> MSK broker-side metrics are scraped into the same datasource with the `aws_msk_` prefix.
>
> **Global labels on all capture metrics** (set in `prometheus.rs`):
>
> - `role` -- deployment role. Known values: `capture`, `capture-ai`, `capture-replay`, and others.
> - `capture_mode` -- `events` or `recordings`.
>
> **Common Grafana variables** used in queries below:
>
> - `$role` -- matches `role` label (e.g. `capture`)
> - `$namespace` -- k8s namespace (e.g. `posthog`)
> - `$pod` -- specific pod name
> - `$environment` -- MSK environment label: `prod-us` (us-east-1) or `prod-eu` (eu-central-1)
>
> **MSK cluster naming**:
>
> - US: `posthog-prod-us-<date>` in us-east-1, labeled `environment="prod-us"`
> - EU: `posthog-prod-eu-<date>` in eu-central-1, labeled `environment="prod-eu"`
>
> All MSK queries below use `environment=~"$environment"` to scope to the correct region.
> The `cluster_name` label contains the full dated name (e.g. `posthog-prod`).

---

## Table of Contents

1. [Capture Application Metrics](#1-capture-application-metrics)
   - [1.1 HTTP Layer](#11-http-layer)
   - [1.2 Payload Processing](#12-payload-processing)
   - [1.3 Event Lifecycle](#13-event-lifecycle)
   - [1.4 Kafka Producer (Client-Side)](#14-kafka-producer-client-side)
   - [1.5 S3 Sink](#15-s3-sink)
   - [1.6 AI / OTel Ingestion](#16-ai--otel-ingestion)
   - [1.7 Quota and Rate Limiting](#17-quota-and-rate-limiting)
   - [1.8 Event Restrictions](#18-event-restrictions)
   - [1.9 Error Tracking and Internal Errors](#19-error-tracking-and-internal-errors)
   - [1.10 Hyper Server Internals](#110-hyper-server-internals)
   - [1.11 Fallback Sink](#111-fallback-sink)
2. [Contour / Envoy Ingress Metrics](#2-contour--envoy-ingress-metrics)
   - [2.1 Request Throughput and Response Codes](#21-request-throughput-and-response-codes)
   - [2.2 Upstream Latency](#22-upstream-latency)
   - [2.3 Active Connections and Requests](#23-active-connections-and-requests)
   - [2.4 Connection Errors](#24-connection-errors)
   - [2.5 Timeouts and Retries](#25-timeouts-and-retries)
   - [2.6 Backend Membership and Health](#26-backend-membership-and-health)
   - [2.7 Circuit Breakers](#27-circuit-breakers)
   - [2.8 Bytes Transferred](#28-bytes-transferred)
3. [Kubernetes Pod and Node Health](#3-kubernetes-pod-and-node-health)
   - [3.1 Container Resource Usage (cAdvisor)](#31-container-resource-usage-cadvisor)
   - [3.2 Pod Status (kube-state-metrics)](#32-pod-status-kube-state-metrics)
   - [3.3 Node Health](#33-node-health)
   - [3.4 HPA / Autoscaling](#34-hpa--autoscaling)
4. [Kafka / AWS MSK Cluster Metrics](#4-kafka--aws-msk-cluster-metrics)
   - [4.1 Broker Topic Metrics](#41-broker-topic-metrics)
   - [4.2 Request / Network Metrics](#42-request--network-metrics)
   - [4.3 Broker Resource Saturation and Throttling](#43-broker-resource-saturation-and-throttling)
   - [4.4 Controller and Replica Health](#44-controller-and-replica-health)
   - [4.5 Consumer Lag](#45-consumer-lag)
   - [4.6 MSK Node (Broker Host) Metrics](#46-msk-node-broker-host-metrics)
5. [Query Template Patterns](#5-query-template-patterns)
   - [5.1 Current Rate](#51-current-rate)
   - [5.2 Latency Percentiles](#52-latency-percentiles)
   - [5.3 Saturation](#53-saturation)
   - [5.4 Error Ratios](#54-error-ratios)
   - [5.5 Alert Threshold Suggestions](#55-alert-threshold-suggestions)

---

## 1. Capture Application Metrics

Source: [`src/prometheus.rs`](src/prometheus.rs) and metric emission sites across the crate.

### 1.1 HTTP Layer

#### `http_requests_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `method` (GET, POST, ...), `path` (/batch, /capture, /e, ...), `status` (200, 400, 429, 503, ...) |
| **Source** | `metrics_middleware.rs` |
| **Meaning** | Total HTTP requests handled. Primary throughput signal. |
| **PromQL** | `sum(rate(http_requests_total{role=~"$role"}[5m])) by (status)` |
| **Alert** | Spike in 4xx/5xx rate relative to total indicates client or server issues. |

#### `http_requests_duration_seconds`

| | |
|---|---|
| **Type** | histogram |
| **Labels** | `method`, `path`, `status` |
| **Buckets** | 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0 (seconds) |
| **Source** | `metrics_middleware.rs` |
| **Meaning** | Request latency distribution end-to-end. The primary latency signal. |
| **PromQL (p99)** | `histogram_quantile(0.99, sum(rate(http_requests_duration_seconds_bucket{role=~"$role"}[5m])) by (le))` |
| **PromQL (p50)** | `histogram_quantile(0.50, sum(rate(http_requests_duration_seconds_bucket{role=~"$role"}[5m])) by (le))` |
| **Alert** | p99 > 1s sustained indicates backpressure or Kafka slowness. p99 > 10s is critical. |

#### `capture_active_connections`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Source** | `metrics_middleware.rs` -- incremented on request start, decremented on response |
| **Meaning** | Current in-flight HTTP connections. Saturation signal. |
| **PromQL** | `sum(capture_active_connections{role=~"$role"})` |
| **Alert** | Sustained high value (relative to pod count) indicates connection pooling issues or slow backends. |

#### `middleware_pass_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `method`, `path`, `status`, `threshold` (`exceeded` or `respected`) |
| **Source** | `metrics_middleware.rs` |
| **Meaning** | Tracks requests that hit internal request-time thresholds. `exceeded` means the request took longer than the configured middleware threshold. |
| **PromQL** | `sum(rate(middleware_pass_total{role=~"$role", threshold="exceeded"}[5m]))` |
| **Note** | ⚠️ No active series in prod — this metric is defined in code but only emitted when middleware thresholds are configured. |

#### `middleware_request_timed_out_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `method`, `path`, `threshold` (`exceeded` or `respected`) |
| **Source** | `metrics_middleware.rs` |
| **Meaning** | Requests that timed out in middleware. Indicates requests dropped before reaching handler. |
| **PromQL** | `sum(rate(middleware_request_timed_out_total{role=~"$role", threshold="exceeded"}[5m]))` |
| **Alert** | Any non-zero rate means requests are being shed. |
| **Note** | ⚠️ No active series in prod — same as `middleware_pass_total`. |

---

### 1.2 Payload Processing

#### `capture_full_payload_size`

| | |
|---|---|
| **Type** | histogram |
| **Labels** | `oversize` (`true` / `false`) |
| **Buckets** | 1KB, 5KB, 10KB, 50KB, 100KB, 1MB, 10MB, 20MB |
| **Source** | `payload/decompression.rs` |
| **Meaning** | Size of the fully decompressed payload. Oversize=true means the payload exceeded the max allowed size but was still measured. |
| **PromQL (p95)** | `histogram_quantile(0.95, sum(rate(capture_full_payload_size_bucket{role=~"$role", oversize="false"}[5m])) by (le))` |
| **Alert** | Growth in oversize=true count means clients sending excessively large batches. |

#### `capture_raw_payload_size`

| | |
|---|---|
| **Type** | histogram |
| **Labels** | none |
| **Buckets** | default (not explicitly configured -- uses library defaults) |
| **Source** | `payload/decompression.rs` |
| **Meaning** | Size of the raw (pre-decompression) payload. Useful to compare with full payload to gauge compression ratio. |
| **PromQL** | `histogram_quantile(0.95, sum(rate(capture_raw_payload_size_bucket{role=~"$role"}[5m])) by (le))` |

#### `capture_gzip_decompression_ratio`

| | |
|---|---|
| **Type** | histogram |
| **Labels** | none |
| **Buckets** | default |
| **Source** | `payload/decompression.rs` |
| **Meaning** | Ratio of decompressed size to compressed size. High ratios may indicate gzip bomb attempts or unusually compressible data. |
| **PromQL (avg)** | `sum(rate(capture_gzip_decompression_ratio_sum{role=~"$role"}[5m])) / sum(rate(capture_gzip_decompression_ratio_count{role=~"$role"}[5m]))` |

#### `capture_payload_size_exceeded`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `kind` (`gzip`, `none`) |
| **Source** | `payload/decompression.rs` |
| **Meaning** | Payloads rejected for exceeding the max size limit. `kind` indicates whether the payload was gzip-compressed. |
| **PromQL** | `sum(rate(capture_payload_size_exceeded{role=~"$role"}[5m])) by (kind)` |
| **Alert** | Sustained non-zero rate from a single team token could indicate a misbehaving SDK. |

#### `capture_body_read_timeout_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `path` |
| **Source** | `extractors.rs` |
| **Meaning** | Requests where the HTTP body could not be fully read before timeout. Indicates slow clients or network issues. |
| **PromQL** | `sum(rate(capture_body_read_timeout_total{role=~"$role"}[5m]))` |
| **Alert** | Sustained rate > 1/s may indicate network degradation. |

---

### 1.3 Event Lifecycle

#### `capture_events_received_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Source** | `payload/analytics.rs`, `payload/recordings.rs` |
| **Meaning** | Total events parsed from incoming payloads (before any filtering/dropping). Top-of-funnel count. |
| **PromQL** | `sum(rate(capture_events_received_total{role=~"$role"}[5m]))` |

#### `capture_events_ingested_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Source** | `sinks/producer.rs`, `sinks/noop.rs`, `sinks/print.rs` |
| **Meaning** | Events successfully handed off to the sink (Kafka, S3, etc). Bottom-of-funnel count. |
| **PromQL** | `sum(rate(capture_events_ingested_total{role=~"$role"}[5m]))` |
| **Key ratio** | `ingested / received` = effective acceptance rate. Drop below ~0.95 warrants investigation. |

#### `capture_events_dropped_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `cause` |
| **Known `cause` values** | `ai_opt_in`, `encoding`, `event_restriction_drop`, `event_too_big`, `events_over_quota`, `exceptions_over_quota`, `gathering`, `invalid_session`, `kafka_message_size`, `llm_events_over_quota`, `no_distinct_id`, `no_event_name`, `no_session_id`, `oversize_event`, `recordings_over_quota`, `retryable_sink`, `survey_responses_over_quota`, `token_dropper` |
| **Source** | `prometheus.rs` `report_dropped_events()`, called from many sites |
| **Meaning** | Events intentionally dropped with the reason in `cause`. Critical for understanding data loss. |
| **PromQL** | `sum(rate(capture_events_dropped_total{role=~"$role"}[5m])) by (cause)` |
| **Alert** | Any `retryable_sink` drops indicate Kafka producer failures. Large `*_over_quota` drops are normal but worth monitoring per-team. |

#### `capture_events_rerouted_overflow`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `reason` (`event_restriction`, `force_limited`, `rate_limited`) |
| **Source** | `sinks/kafka.rs` |
| **Meaning** | Events sent to the overflow topic instead of the primary topic. |
| **PromQL** | `sum(rate(capture_events_rerouted_overflow{role=~"$role"}[5m])) by (reason)` |
| **Alert** | High `rate_limited` overflow means the global rate limiter is active and shedding load. |

#### `capture_events_rerouted_custom_topic`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `reason` (`event_restriction`) |
| **Source** | `sinks/kafka.rs` |
| **Meaning** | Events redirected to a custom Kafka topic via event restrictions config. |
| **PromQL** | `sum(rate(capture_events_rerouted_custom_topic{role=~"$role"}[5m]))` |

#### `capture_events_rerouted_dlq` *(code-only)*

| | |
|---|---|
| **Type** | counter |
| **Labels** | `reason` (`event_restriction`) |
| **Source** | `sinks/kafka.rs` |
| **Meaning** | Events sent to the dead-letter queue topic due to event restrictions. |
| **PromQL** | `sum(rate(capture_events_rerouted_dlq{role=~"$role"}[5m]))` |
| **Note** | ⚠️ No active series in prod — DLQ routing is defined in code but not currently triggered. |

#### `capture_events_rerouted_historical` *(code-only)*

| | |
|---|---|
| **Type** | counter |
| **Labels** | `reason` (`timestamp`) |
| **Source** | `events/analytics.rs` |
| **Meaning** | Events rerouted to the historical ingestion topic because their timestamp is far in the past. |
| **PromQL** | `sum(rate(capture_events_rerouted_historical{role=~"$role"}[5m]))` |
| **Note** | ⚠️ No active series in prod — metric name not registered in VictoriaMetrics. |

#### `capture_exception_events_dual_written` *(code-only)*

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Source** | `events/analytics.rs` |
| **Meaning** | Exception events that were dual-written to the error tracking pipeline (when error tracking dual-write is enabled). |
| **PromQL** | `sum(rate(capture_exception_events_dual_written{role=~"$role"}[5m]))` |
| **Note** | ⚠️ No active series in prod — metric name not registered in VictoriaMetrics. |

#### `capture_distinct_id_has_whitespace_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Meaning** | Events where the distinct_id contained whitespace (trimmed before processing). Indicates SDK bugs or user error. |
| **PromQL** | `sum(rate(capture_distinct_id_has_whitespace_total{role=~"$role"}[5m]))` |

#### `capture_logs_timestamps_overridden`

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Meaning** | Log events where the client-provided timestamp was overridden by the server (e.g. future timestamps clamped). |
| **PromQL** | `sum(rate(capture_logs_timestamps_overridden{role=~"$role"}[5m]))` |

#### `capture_internal_event_submitted_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Meaning** | Internal capture events submitted (e.g. from Django `capture_internal` endpoint). |
| **PromQL** | `sum(rate(capture_internal_event_submitted_total{role=~"$role"}[5m]))` |

---

### 1.4 Kafka Producer (Client-Side)

These metrics come from the librdkafka statistics callback and are emitted in `sinks/kafka.rs`.

#### `capture_kafka_any_brokers_down`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Meaning** | 1 if any Kafka broker is unreachable, 0 otherwise. **Top-level health signal.** |
| **PromQL** | `max(capture_kafka_any_brokers_down{role=~"$role"})` |
| **Alert** | Any pod reporting 1 is critical -- indicates Kafka connectivity issues. |

#### `capture_kafka_callback_queue_depth`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Meaning** | Number of messages waiting in the delivery report callback queue. High values indicate the callback handler is falling behind. |
| **PromQL** | `max(capture_kafka_callback_queue_depth{role=~"$role"})` |

#### `capture_kafka_producer_queue_depth`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Meaning** | Messages queued in the producer buffer waiting to be sent. |
| **PromQL** | `max(capture_kafka_producer_queue_depth{role=~"$role"})` |

#### `capture_kafka_producer_queue_depth_limit`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Meaning** | Configured maximum producer queue depth. Compare with `queue_depth` to gauge saturation. |
| **PromQL** | `capture_kafka_producer_queue_depth{role=~"$role"} / capture_kafka_producer_queue_depth_limit{role=~"$role"}` |
| **Alert** | Ratio > 0.8 means the producer is near saturation and will start blocking or dropping. |

#### `capture_kafka_producer_queue_bytes`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Meaning** | Bytes queued in the producer buffer. |
| **PromQL** | `max(capture_kafka_producer_queue_bytes{role=~"$role"})` |

#### `capture_kafka_producer_queue_bytes_limit`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Meaning** | Max bytes allowed in producer queue. |
| **PromQL** | `capture_kafka_producer_queue_bytes{role=~"$role"} / capture_kafka_producer_queue_bytes_limit{role=~"$role"}` |

#### `capture_kafka_produce_avg_batch_size_bytes`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `topic` |
| **Meaning** | Average size in bytes of Kafka produce batches per topic. |
| **PromQL** | `avg(capture_kafka_produce_avg_batch_size_bytes{role=~"$role"}) by (topic)` |

#### `capture_kafka_produce_avg_batch_size_events`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `topic` |
| **Meaning** | Average number of events per Kafka produce batch per topic. |
| **PromQL** | `avg(capture_kafka_produce_avg_batch_size_events{role=~"$role"}) by (topic)` |

#### `capture_kafka_broker_connected`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `broker` |
| **Meaning** | 1 if the broker is connected, 0 otherwise. Per-broker connectivity status. |
| **PromQL** | `min(capture_kafka_broker_connected{role=~"$role"}) by (broker)` |
| **Alert** | Any broker showing 0 across all pods needs immediate investigation. |

#### `capture_kafka_produce_rtt_latency_us`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `quantile` (p50, p90, p95, p99), `broker` |
| **Meaning** | Produce request round-trip time in microseconds, reported by librdkafka per broker at various quantiles. |
| **PromQL (p99)** | `max(capture_kafka_produce_rtt_latency_us{role=~"$role", quantile="p99"}) by (broker)` |
| **Alert** | p99 > 100000 (100ms) sustained may indicate broker overload or network issues. p99 > 500000 (500ms) is critical. |

#### `capture_kafka_broker_requests_pending`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `broker` |
| **Meaning** | Number of produce requests in flight to each broker. |
| **PromQL** | `max(capture_kafka_broker_requests_pending{role=~"$role"}) by (broker)` |

#### `capture_kafka_broker_responses_awaiting`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `broker` |
| **Meaning** | Number of responses being waited on from each broker. |
| **PromQL** | `max(capture_kafka_broker_responses_awaiting{role=~"$role"}) by (broker)` |

#### `capture_kafka_broker_tx_errors_total`

| | |
|---|---|
| **Type** | counter (absolute) |
| **Labels** | `broker` |
| **Meaning** | Cumulative transmit errors to each broker. Set as absolute value from librdkafka stats. |
| **PromQL** | `sum(rate(capture_kafka_broker_tx_errors_total{role=~"$role"}[5m])) by (broker)` |
| **Alert** | Any sustained non-zero rate indicates network-level errors to a broker. |

#### `capture_kafka_broker_rx_errors_total`

| | |
|---|---|
| **Type** | counter (absolute) |
| **Labels** | `broker` |
| **Meaning** | Cumulative receive errors from each broker. |
| **PromQL** | `sum(rate(capture_kafka_broker_rx_errors_total{role=~"$role"}[5m])) by (broker)` |

#### `capture_kafka_broker_request_timeouts`

| | |
|---|---|
| **Type** | counter (absolute) |
| **Labels** | `broker` |
| **Meaning** | Cumulative request timeouts to each broker. |
| **PromQL** | `sum(rate(capture_kafka_broker_request_timeouts{role=~"$role"}[5m])) by (broker)` |
| **Alert** | Non-zero rate indicates the broker is too slow to respond within the configured timeout. |

#### `capture_kafka_produce_errors_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Source** | `sinks/producer.rs` |
| **Meaning** | Failed Kafka produce calls (delivery failures, queue full, etc). |
| **PromQL** | `sum(rate(capture_kafka_produce_errors_total{role=~"$role"}[5m]))` |
| **Alert** | Any sustained rate > 0 is a critical signal -- events may be lost. |

#### `capture_kafka_produce_bytes_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `topic` |
| **Source** | `sinks/kafka.rs` |
| **Meaning** | Total bytes produced to Kafka, broken down by topic. Primary throughput metric. |
| **PromQL** | `sum(rate(capture_kafka_produce_bytes_total{role=~"$role"}[5m])) by (topic)` |

#### `capture_event_batch_size`

| | |
|---|---|
| **Type** | histogram |
| **Labels** | none |
| **Buckets** | 1, 10, 25, 50, 75, 100, 250, 500, 750, 1000 (suffix match `_batch_size`) |
| **Source** | `sinks/kafka.rs`, `sinks/noop.rs`, `sinks/print.rs` |
| **Meaning** | Number of events per batch sent to the sink. |
| **PromQL (p95)** | `histogram_quantile(0.95, sum(rate(capture_event_batch_size_bucket{role=~"$role"}[5m])) by (le))` |

---

### 1.5 S3 Sink

> ⚠️ **No active series in prod.** All `capture_s3_*` metrics below are defined in the Rust code but are
> not present in VictoriaMetrics. The `capture-replay` role uses S3 for session recordings, but these
> metrics are either not scraped or the S3 sink is not emitting to Prometheus. Queries will return empty
> results until this is resolved. Included here for completeness when the metrics become available.

Used by `capture-replay` role for session recording data.

#### `capture_s3_upload_duration_seconds`

| | |
|---|---|
| **Type** | histogram |
| **Buckets** | 0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24 (seconds, 2x steps) |
| **Source** | `s3_client.rs` |
| **Meaning** | Latency of individual S3 PutObject calls. |
| **PromQL (p99)** | `histogram_quantile(0.99, sum(rate(capture_s3_upload_duration_seconds_bucket{role=~"$role"}[5m])) by (le))` |
| **Alert** | p99 > 2s sustained likely means S3 is throttling or there's a network issue. |

#### `capture_s3_upload_body_size_bytes`

| | |
|---|---|
| **Type** | histogram |
| **Buckets** | 1KB to 32MB (2x steps) |
| **Source** | `s3_client.rs` |
| **Meaning** | Size of each S3 upload body. |
| **PromQL (p95)** | `histogram_quantile(0.95, sum(rate(capture_s3_upload_body_size_bytes_bucket{role=~"$role"}[5m])) by (le))` |

#### `capture_s3_upload_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `outcome` (`success`, `error`), `reason` (`ok`, or error reason) |
| **Source** | `s3_client.rs` |
| **Meaning** | Total S3 upload attempts with outcome. |
| **PromQL** | `sum(rate(capture_s3_upload_total{role=~"$role"}[5m])) by (outcome)` |
| **Alert** | `outcome=error` rate > 0 sustained indicates S3 issues. |

#### `capture_s3_flush_duration_ms`

| | |
|---|---|
| **Type** | histogram |
| **Source** | `sinks/s3.rs` |
| **Meaning** | Duration of flushing a batch of events to S3 (includes serialization + upload). |
| **PromQL** | `histogram_quantile(0.99, sum(rate(capture_s3_flush_duration_ms_bucket{role=~"$role"}[5m])) by (le))` |

#### `capture_s3_batch_size_events` / `capture_s3_batch_size_bytes` / `capture_s3_batch_size`

| | |
|---|---|
| **Type** | histogram |
| **Source** | `sinks/s3.rs` |
| **Meaning** | Events and bytes per S3 flush batch. |

#### `capture_s3_flush_errors_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `error` |
| **Source** | `sinks/s3.rs` |
| **Meaning** | S3 flush failures. |
| **PromQL** | `sum(rate(capture_s3_flush_errors_total{role=~"$role"}[5m])) by (error)` |

#### `capture_s3_events_written_total` / `capture_s3_bytes_written_total`

| | |
|---|---|
| **Type** | counter |
| **Source** | `sinks/s3.rs` |
| **Meaning** | Cumulative events and bytes successfully written to S3. |
| **PromQL** | `sum(rate(capture_s3_events_written_total{role=~"$role"}[5m]))` |

#### `capture_s3_write_errors_total`

| | |
|---|---|
| **Type** | counter |
| **Source** | `sinks/s3.rs` |
| **Meaning** | Individual S3 write failures within a batch. |
| **PromQL** | `sum(rate(capture_s3_write_errors_total{role=~"$role"}[5m]))` |

---

### 1.6 AI / OTel Ingestion

Metrics from the OpenTelemetry-compatible AI ingestion endpoint.

#### `capture_ai_otel_requests_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `format` (protobuf, json, etc.) |
| **Source** | `otel/mod.rs` |
| **Meaning** | Total OTel ingest requests. |
| **PromQL** | `sum(rate(capture_ai_otel_requests_total{role=~"$role"}[5m])) by (format)` |

#### `capture_ai_otel_requests_success`

| | |
|---|---|
| **Type** | counter |
| **Source** | `otel/mod.rs` |
| **Meaning** | OTel requests that completed successfully. |
| **PromQL** | `sum(rate(capture_ai_otel_requests_success{role=~"$role"}[5m]))` |

#### `capture_ai_otel_body_size_bytes`

| | |
|---|---|
| **Type** | histogram |
| **Buckets** | 1KB, 5KB, 10KB, 50KB, 100KB, 1MB, 10MB, 20MB (same as PAYLOAD_SIZES) |
| **Source** | `otel/mod.rs` |
| **Meaning** | Size of the OTel request body after decompression. |
| **PromQL (p95)** | `histogram_quantile(0.95, sum(rate(capture_ai_otel_body_size_bytes_bucket{role=~"$role"}[5m])) by (le))` |

#### `capture_ai_otel_spans_received`

| | |
|---|---|
| **Type** | counter |
| **Source** | `otel/mod.rs` |
| **Meaning** | Total OTel spans received across all requests. |
| **PromQL** | `sum(rate(capture_ai_otel_spans_received{role=~"$role"}[5m]))` |

#### `capture_ai_otel_spans_per_request`

| | |
|---|---|
| **Type** | histogram |
| **Buckets** | 1, 10, 25, 50, 75, 100, 250, 500, 750, 1000 (same as BATCH_SIZES) |
| **Source** | `otel/mod.rs` |
| **Meaning** | Number of spans per OTel request. |
| **PromQL (p95)** | `histogram_quantile(0.95, sum(rate(capture_ai_otel_spans_per_request_bucket{role=~"$role"}[5m])) by (le))` |

#### `capture_ai_otel_events_ingested`

| | |
|---|---|
| **Type** | counter |
| **Source** | `otel/mod.rs` |
| **Meaning** | PostHog events generated from OTel spans and successfully ingested. |
| **PromQL** | `sum(rate(capture_ai_otel_events_ingested{role=~"$role"}[5m]))` |

#### `capture_ai_blob_count_per_event`

| | |
|---|---|
| **Type** | histogram |
| **Buckets** | 1, 2, 4, 8, 16, 32 |
| **Source** | `ai_endpoint.rs` |
| **Meaning** | Number of binary blobs (images, etc.) attached to each AI event. |
| **PromQL** | `histogram_quantile(0.95, sum(rate(capture_ai_blob_count_per_event_bucket{role=~"$role"}[5m])) by (le))` |

#### `capture_ai_blob_size_bytes`

| | |
|---|---|
| **Type** | histogram |
| **Buckets** | 1KB to 32MB (2x steps, same as S3_BODY_SIZES) |
| **Source** | `ai_endpoint.rs` |
| **Meaning** | Size of each individual blob. |

#### `capture_ai_blob_total_bytes_per_event`

| | |
|---|---|
| **Type** | histogram |
| **Buckets** | 1KB to 32MB (same as S3_BODY_SIZES) |
| **Source** | `ai_endpoint.rs` |
| **Meaning** | Total blob bytes per event (sum of all blobs in one event). |

#### `capture_ai_blob_events_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `has_blobs` (`true`, `false`), `content_type` |
| **Source** | `ai_endpoint.rs` |
| **Meaning** | Total AI events processed, partitioned by whether they contain blobs. |
| **PromQL** | `sum(rate(capture_ai_blob_events_total{role=~"$role"}[5m])) by (has_blobs)` |

---

### 1.7 Quota and Rate Limiting

#### `capture_quota_limit_exceeded`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `resource` (see list below) |
| **Known `resource` values** | All `QuotaResource` variants: events, recordings, exceptions, etc. |
| **Source** | `prometheus.rs` `report_quota_limit_exceeded()` |
| **Meaning** | Events rejected because the team exceeded their billing quota for the given resource. |
| **PromQL** | `sum(rate(capture_quota_limit_exceeded{role=~"$role"}[5m])) by (resource)` |
| **Alert** | Spikes here correlate with billing enforcement. Normal operation. |

#### `capture_partition_key_capacity_exceeded_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Source** | `prometheus.rs` `report_overflow_partition()` |
| **Meaning** | Events where the partition key (team token) exceeded capacity and triggered overflow routing. |
| **PromQL** | `sum(rate(capture_partition_key_capacity_exceeded_total{role=~"$role"}[5m]))` |

#### `capture_billing_limits_loaded_tokens`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Meaning** | Number of team tokens with active billing limits loaded in memory. Operational health of the quota system. |
| **PromQL** | `min(capture_billing_limits_loaded_tokens{role=~"$role"})` |
| **Alert** | Drop to 0 means billing limits are not being loaded -- all quota enforcement is disabled. |

---

### 1.8 Event Restrictions

Event restrictions are dynamic rules (loaded from Redis) that drop, reroute, or modify events for specific teams/event types.

#### `capture_event_restrictions_applied`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `restriction_type` (`drop_event`, `force_overflow`, `redirect_to_dlq`, `redirect_to_topic`, `skip_person_processing`), `pipeline` |
| **Source** | `event_restrictions/types.rs` |
| **Meaning** | Event restrictions actually applied. |
| **PromQL** | `sum(rate(capture_event_restrictions_applied{role=~"$role"}[5m])) by (restriction_type, pipeline)` |

#### `capture_event_restrictions_last_refresh_timestamp`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `pipeline` (`analytics`, `clustering`, `session_recordings`, `summarization`) |
| **Source** | `event_restrictions/manager.rs` |
| **Meaning** | Unix timestamp of last successful restriction config refresh. |
| **PromQL** | `time() - capture_event_restrictions_last_refresh_timestamp{role=~"$role"}` |
| **Alert** | If this exceeds several minutes the restrictions config is stale. |

#### `capture_event_restrictions_loaded_count`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `pipeline` |
| **Meaning** | Number of restriction rules currently loaded per pipeline. |
| **PromQL** | `capture_event_restrictions_loaded_count{role=~"$role"}` |

#### `capture_event_restrictions_tokens_count`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `pipeline` |
| **Meaning** | Number of distinct team tokens with restrictions. |

#### `capture_event_restrictions_stale`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `pipeline` |
| **Meaning** | 1 if the restrictions for this pipeline are stale (refresh failed), 0 otherwise. |
| **PromQL** | `max(capture_event_restrictions_stale{role=~"$role"}) by (pipeline)` |
| **Alert** | Any 1 means restrictions may not be applied correctly. |

#### `capture_event_restrictions_redis_fetch`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `restriction_type`, `result` (`success`, `error`, `not_found`, `parse_error`) |
| **Source** | `event_restrictions/repository.rs` |
| **Meaning** | Redis fetch operations for restriction configs with outcome. |
| **PromQL** | `sum(rate(capture_event_restrictions_redis_fetch{role=~"$role", result="error"}[5m]))` |
| **Alert** | Sustained errors indicate Redis connectivity issues. |

---

### 1.9 Error Tracking and Internal Errors

#### `capture_error_by_stage_and_type`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `error`, `stage` |
| **Known `error` values** | `NONE`, `REQUEST_TIMED_OUT`, `UNKNOWN_SERVER_ERROR`, `NOT_LEADER_OR_FOLLOWER`, `UNKNOWN_TOPIC_OR_PARTITION`, `OFFSET_OUT_OF_RANGE`, `body_read_timeout`, `empty_batch`, `empty_payload`, `invalid_session`, `invalid_token`, `no_distinct_id`, `no_event_name`, `no_session_id`, `no_token`, `oversize_event`, `req_decoding`, `req_hydration`, `req_parsing`, `retryable_sink`, and many Kafka error codes |
| **Known `stage` values** | `ALPHA`, `BETA`, `DEPRECATED`, `accept`, `normalized`, `parsing`, `processing`, `received`, `sampled` |
| **Source** | `prometheus.rs` `report_internal_error_metrics()` |
| **Meaning** | Internal errors categorized by type and processing stage. The most detailed error breakdown. |
| **PromQL** | `sum(rate(capture_error_by_stage_and_type{role=~"$role"}[5m])) by (error, stage)` |
| **PromQL (top errors)** | `topk(10, sum(rate(capture_error_by_stage_and_type{role=~"$role"}[5m])) by (error))` |
| **Alert** | `retryable_sink` at `processing` stage indicates Kafka delivery failures. Kafka error codes like `NOT_LEADER_OR_FOLLOWER` at any stage signal broker issues. |

---

### 1.10 Hyper Server Internals

Low-level TCP accept loop metrics from the custom Hyper server implementation.

#### `capture_hyper_accepted_connections`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `stage` (`accept`, `drain`) |
| **Source** | `server.rs` |
| **Meaning** | Total TCP connections accepted. `drain` stage means connections accepted during graceful shutdown. |
| **PromQL** | `sum(rate(capture_hyper_accepted_connections{role=~"$role"}[5m])) by (stage)` |

#### `capture_hyper_accept_error`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `err_type` (`set_tcp_nodelay`, `conn_closed`, `connection`, `resources`), `stage` |
| **Source** | `server.rs` |
| **Meaning** | TCP accept errors. `resources` type indicates file descriptor exhaustion. `connection` is transient. |
| **PromQL** | `sum(rate(capture_hyper_accept_error{role=~"$role"}[5m])) by (err_type)` |
| **Alert** | `resources` errors mean the pod is running out of file descriptors -- needs investigation. |

#### `capture_hyper_header_read_timeout`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `stage` |
| **Source** | `server.rs` |
| **Meaning** | Connections where HTTP headers were not fully read within the timeout. Slowloris-style connections. |
| **PromQL** | `sum(rate(capture_hyper_header_read_timeout{role=~"$role"}[5m]))` |

---

### 1.11 Fallback Sink

> ⚠️ **No active series in prod.** The fallback sink is defined in code (`sinks/fallback.rs`) but these
> metrics are not present in VictoriaMetrics. The fallback sink may not be enabled in the current
> production configuration. Included for completeness.

#### `capture_primary_sink_health` *(code-only)*

| | |
|---|---|
| **Type** | gauge |
| **Labels** | none |
| **Source** | `sinks/fallback.rs` |
| **Meaning** | Health status of the primary sink. Values: 1 = healthy, 0 = degraded/failing. When 0, the fallback sink is used. |
| **PromQL** | `min(capture_primary_sink_health{role=~"$role"})` |
| **Alert** | 0 means all traffic is going through the fallback path. |

#### `capture_fallback_sink_failovers_total` *(code-only)*

| | |
|---|---|
| **Type** | counter |
| **Labels** | none |
| **Source** | `sinks/fallback.rs` |
| **Meaning** | Number of times the sink switched from primary to fallback (or back). |
| **PromQL** | `sum(rate(capture_fallback_sink_failovers_total{role=~"$role"}[5m]))` |
| **Alert** | Flapping (high rate) indicates the primary sink is unstable. |

---

## 2. Contour / Envoy Ingress Metrics

Contour manages Envoy as the L7 ingress proxy in front of all capture services.
Each backend is identified by `envoy_cluster_name` using the scheme `<namespace>_<service>_<port>`.

> **Capture Envoy Cluster Names:**
>
> | `envoy_cluster_name` | Service | Notes |
> |---|---|---|
> | `posthog_capture_3000` | Main capture | Events, decide, batch |
> | `posthog_capture-ai_3000` | Capture AI | AI/LLM event ingestion |
> | `posthog_capture-ai-canary_3000` | Capture AI canary | Canary rollout |
> | `posthog_capture-replay_3000` | Capture replay | Session recording ingestion |
> | `posthog_capture-replay-canary_3000` | Capture replay canary | Canary rollout |
> | `posthog_capture-logs_4318` | Capture logs (OTel) | OpenTelemetry log ingestion |
> | `posthog_capture-logs-canary_4318` | Capture logs canary | Canary rollout |
>
> Use `envoy_cluster_name=~"posthog_capture.*"` to match all capture clusters,
> or scope to specific services (e.g. `envoy_cluster_name="posthog_capture_3000"`).
>
> **Grafana dashboard:** [Contour Ingress](https://grafana.prod-us.posthog.dev/d/contour/contour-ingress) (UID: `contour`)
> — set `endpoint_namespace=posthog` and `envoy_cluster_name=posthog_capture_3000`.

### 2.1 Request Throughput and Response Codes

#### `envoy_cluster_upstream_rq_xx`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name`, `envoy_response_code_class` (1–5) |
| **Meaning** | Total upstream requests bucketed by HTTP response code class. Primary throughput and error signal at the ingress layer. |
| **PromQL — RPS by code class** | `sum(rate(envoy_cluster_upstream_rq_xx{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name, envoy_response_code_class)` |
| **PromQL — 5xx error ratio** | `sum(rate(envoy_cluster_upstream_rq_xx{envoy_cluster_name=~"posthog_capture.*", envoy_response_code_class="5"}[5m])) / sum(rate(envoy_cluster_upstream_rq_xx{envoy_cluster_name=~"posthog_capture.*"}[5m]))` |
| **Alert** | 5xx ratio > 0.1% sustained over 5m is abnormal for capture. |

#### `envoy_cluster_upstream_rq_completed`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Total completed upstream requests (all response codes). Useful as a denominator in ratio calculations. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_completed{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

### 2.2 Upstream Latency

#### `envoy_cluster_upstream_rq_time_bucket` / `_count` / `_sum`

| | |
|---|---|
| **Type** | histogram (milliseconds) |
| **Labels** | `envoy_cluster_name`, `le` |
| **Meaning** | End-to-end upstream request latency as seen by Envoy — includes connection establishment, request send, backend processing, and response receive. This is the **ingress-eye view** of capture latency. |
| **PromQL — p50** | `histogram_quantile(0.50, sum(rate(envoy_cluster_upstream_rq_time_bucket{envoy_cluster_name="posthog_capture_3000"}[5m])) by (le))` |
| **PromQL — p99** | `histogram_quantile(0.99, sum(rate(envoy_cluster_upstream_rq_time_bucket{envoy_cluster_name="posthog_capture_3000"}[5m])) by (le))` |
| **PromQL — p99 all capture** | `histogram_quantile(0.99, sum(rate(envoy_cluster_upstream_rq_time_bucket{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name, le))` |
| **Alert** | p99 > 500ms sustained indicates backend slowness or resource pressure. |

#### `envoy_cluster_upstream_cx_connect_ms_bucket` / `_count` / `_sum`

| | |
|---|---|
| **Type** | histogram (milliseconds) |
| **Labels** | `envoy_cluster_name`, `le` |
| **Meaning** | Time to establish an upstream TCP connection. High values indicate pod scheduling delays, network issues, or exhausted backend capacity. |
| **PromQL — p99** | `histogram_quantile(0.99, sum(rate(envoy_cluster_upstream_cx_connect_ms_bucket{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name, le))` |

#### `envoy_cluster_upstream_cx_length_ms_bucket` / `_count` / `_sum`

| | |
|---|---|
| **Type** | histogram (milliseconds) |
| **Labels** | `envoy_cluster_name`, `le` |
| **Meaning** | Duration of upstream connections from open to close. Very short lifetimes may indicate connection churn. |
| **PromQL — p50** | `histogram_quantile(0.50, sum(rate(envoy_cluster_upstream_cx_length_ms_bucket{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name, le))` |

### 2.3 Active Connections and Requests

#### `envoy_cluster_upstream_cx_active`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Currently active upstream connections. Reflects load distribution across capture pods. |
| **PromQL** | `sum(envoy_cluster_upstream_cx_active{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_rq_active`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Currently in-flight upstream requests. Spikes may indicate backend stalls. |
| **PromQL** | `sum(envoy_cluster_upstream_rq_active{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_rq_pending_active`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Requests queued waiting for an available connection. Non-zero indicates connection pool pressure. |
| **PromQL** | `sum(envoy_cluster_upstream_rq_pending_active{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |
| **Alert** | Sustained non-zero values indicate connection exhaustion. |

### 2.4 Connection Errors

#### `envoy_cluster_upstream_cx_connect_fail`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Failed upstream connection attempts. Indicates pods unreachable, port not listening, or network partition. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_cx_connect_fail{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |
| **Alert** | Any sustained non-zero rate needs investigation. |

#### `envoy_cluster_upstream_cx_connect_timeout`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Connection establishment timeouts. Backend pods may be overloaded or unresponsive. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_cx_connect_timeout{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_cx_overflow`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Connection pool overflow — new connections rejected because the pool is at capacity. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_cx_overflow{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |
| **Alert** | Non-zero means Envoy is dropping connections due to resource limits. |

#### `envoy_cluster_upstream_cx_destroy_remote_with_active_rq`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Backend closed the connection while requests were still in flight. Indicates backend crashes, restarts, or premature connection resets. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_cx_destroy_remote_with_active_rq{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_cx_destroy_local_with_active_rq`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Envoy closed the connection while requests were in flight (e.g. timeout, circuit break). |
| **PromQL** | `sum(rate(envoy_cluster_upstream_cx_destroy_local_with_active_rq{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_cx_protocol_error`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | HTTP protocol errors on upstream connections (malformed responses, HTTP/2 framing errors). |
| **PromQL** | `sum(rate(envoy_cluster_upstream_cx_protocol_error{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

### 2.5 Timeouts and Retries

#### `envoy_cluster_upstream_rq_timeout`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Requests that exceeded the route-level timeout. These return 504 to the client. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_timeout{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |
| **Alert** | Any sustained non-zero rate indicates backend latency exceeding Contour route timeout. |

#### `envoy_cluster_upstream_rq_per_try_timeout`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Individual attempt timeouts (before retry). Distinct from route-level `upstream_rq_timeout`. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_per_try_timeout{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_rq_retry`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Total retry attempts by Envoy. High retry rates amplify backend load. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_retry{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_rq_retry_success`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Retries that succeeded. `retry - retry_success` = wasted retry attempts. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_retry_success{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_rq_retry_limit_exceeded`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Requests that exhausted all retry attempts and still failed. These become 5xx responses. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_retry_limit_exceeded{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |
| **Alert** | Non-zero indicates persistent backend failures. |

#### `envoy_cluster_upstream_rq_retry_overflow`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Retries rejected because the retry budget / circuit breaker was exhausted. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_retry_overflow{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_rq_rx_reset`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Upstream sent a reset (RST_STREAM / connection reset). Indicates backend aborted the response. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_rx_reset{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_rq_tx_reset`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Downstream (client) reset the request before completion. High rates may indicate client timeouts or SDK bugs. |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_tx_reset{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

### 2.6 Backend Membership and Health

#### `envoy_cluster_membership_healthy`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Number of healthy backend endpoints in the cluster. Should equal `membership_total` in steady state. |
| **PromQL** | `sum(envoy_cluster_membership_healthy{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |
| **Alert** | `healthy < total` means some pods are failing health checks. |

#### `envoy_cluster_membership_total`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Total backend endpoints (healthy + unhealthy). Correlates with k8s pod count. |
| **PromQL** | `sum(envoy_cluster_membership_total{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### `envoy_cluster_membership_degraded`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Endpoints in degraded state (health check passing but flagged). |
| **PromQL** | `sum(envoy_cluster_membership_degraded{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### Healthy Ratio

| | |
|---|---|
| **PromQL** | `sum(envoy_cluster_membership_healthy{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name) / sum(envoy_cluster_membership_total{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |
| **Alert** | Ratio < 1.0 means unhealthy endpoints exist. Ratio dropping during deploys is normal (brief). |

### 2.7 Circuit Breakers

#### `envoy_cluster_circuit_breakers_default_rq_open`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Whether the request circuit breaker is tripped (1 = open, shedding requests). |
| **PromQL** | `sum(envoy_cluster_circuit_breakers_default_rq_open{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |
| **Alert** | Any non-zero value means Envoy is actively rejecting requests to this cluster. |

#### `envoy_cluster_circuit_breakers_default_cx_open`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Connection circuit breaker tripped. New connections to the backend are being rejected. |
| **PromQL** | `sum(envoy_cluster_circuit_breakers_default_cx_open{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### `envoy_cluster_circuit_breakers_default_rq_pending_open`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Pending-request circuit breaker tripped. New requests are immediately rejected (503) instead of queuing. |
| **PromQL** | `sum(envoy_cluster_circuit_breakers_default_rq_pending_open{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### `envoy_cluster_circuit_breakers_default_rq_retry_open`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Retry circuit breaker tripped. No further retries will be attempted. |
| **PromQL** | `sum(envoy_cluster_circuit_breakers_default_rq_retry_open{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### `envoy_cluster_circuit_breakers_default_remaining_rq`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Remaining request capacity before circuit break. Low values indicate approaching the limit. |
| **PromQL** | `min(envoy_cluster_circuit_breakers_default_remaining_rq{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### `envoy_cluster_circuit_breakers_default_remaining_cx`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Remaining connection capacity before circuit break. |
| **PromQL** | `min(envoy_cluster_circuit_breakers_default_remaining_cx{envoy_cluster_name=~"posthog_capture.*"}) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_rq_pending_overflow`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Requests rejected by the pending-request circuit breaker. Each count is a dropped request (503 to client). |
| **PromQL** | `sum(rate(envoy_cluster_upstream_rq_pending_overflow{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |
| **Alert** | Non-zero rate indicates connection pool / circuit breaker saturation. |

### 2.8 Bytes Transferred

#### `envoy_cluster_upstream_cx_rx_bytes_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Total bytes received from upstream (capture response bodies). |
| **PromQL** | `sum(rate(envoy_cluster_upstream_cx_rx_bytes_total{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |

#### `envoy_cluster_upstream_cx_tx_bytes_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `envoy_cluster_name` |
| **Meaning** | Total bytes sent to upstream (capture request bodies — event payloads). |
| **PromQL** | `sum(rate(envoy_cluster_upstream_cx_tx_bytes_total{envoy_cluster_name=~"posthog_capture.*"}[5m])) by (envoy_cluster_name)` |
| **Alert** | Sudden drops in TX bytes may indicate traffic routing issues or upstream errors preventing payload delivery. |

---

## 3. Kubernetes Pod and Node Health

Filter all queries with `container="capture"` or `namespace="posthog"` as appropriate.
The `role` label on capture metrics maps to the k8s deployment name (e.g. `capture`, `capture-ai`, `capture-replay`).

### 3.1 Container Resource Usage (cAdvisor)

#### `container_cpu_usage_seconds_total`

| | |
|---|---|
| **Type** | counter |
| **Meaning** | CPU time consumed by the container. |
| **PromQL (usage rate)** | `sum(rate(container_cpu_usage_seconds_total{container="capture", namespace="posthog"}[5m])) by (pod)` |
| **PromQL (% of request)** | `sum(rate(container_cpu_usage_seconds_total{container="capture", namespace="posthog"}[5m])) by (pod) / on(pod) group_left() sum(kube_pod_container_resource_requests{container="capture", resource="cpu"}) by (pod) * 100` |
| **Alert** | Sustained > 90% of CPU request means pods may need more resources or more replicas. |

#### `container_cpu_cfs_throttled_periods_total` / `container_cpu_cfs_periods_total`

| | |
|---|---|
| **Type** | counter |
| **Meaning** | CFS throttling. The ratio of throttled / total periods indicates how often the container is being CPU-capped. |
| **PromQL (throttle %)** | `sum(rate(container_cpu_cfs_throttled_periods_total{container="capture", namespace="posthog"}[5m])) by (pod) / sum(rate(container_cpu_cfs_periods_total{container="capture", namespace="posthog"}[5m])) by (pod) * 100` |
| **Alert** | > 25% throttling sustained degrades request latency. |

#### `container_memory_working_set_bytes`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Current working set memory (used for OOM decisions). |
| **PromQL** | `sum(container_memory_working_set_bytes{container="capture", namespace="posthog"}) by (pod)` |
| **PromQL (% of limit)** | `sum(container_memory_working_set_bytes{container="capture", namespace="posthog"}) by (pod) / on(pod) group_left() sum(kube_pod_container_resource_limits{container="capture", resource="memory"}) by (pod) * 100` |
| **Alert** | > 85% of memory limit means OOM kill risk. |

#### `container_memory_rss`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Resident set size. More stable than working_set for tracking actual memory usage of the Rust process. |
| **PromQL** | `sum(container_memory_rss{container="capture", namespace="posthog"}) by (pod)` |

#### `container_oom_events_total`

| | |
|---|---|
| **Type** | counter |
| **Meaning** | OOM events for the container. |
| **PromQL** | `sum(increase(container_oom_events_total{container="capture", namespace="posthog"}[1h])) by (pod)` |
| **Alert** | Any value > 0 indicates memory pressure severe enough to trigger OOM kills. |

#### `container_network_receive_bytes_total` / `container_network_transmit_bytes_total`

| | |
|---|---|
| **Type** | counter |
| **Meaning** | Network I/O. Useful for correlating with Kafka throughput. |
| **PromQL** | `sum(rate(container_network_receive_bytes_total{namespace="posthog", pod=~"capture-.*"}[5m])) by (pod)` |

#### `container_file_descriptors`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Open file descriptors. Capture uses many for TCP connections and Kafka connections. |
| **PromQL** | `max(container_file_descriptors{container="capture", namespace="posthog"}) by (pod)` |
| **Alert** | Approaching ulimit indicates connection leak or extreme load. |

---

### 3.2 Pod Status (kube-state-metrics)

#### `kube_pod_status_phase`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `phase` (Pending, Running, Succeeded, Failed, Unknown) |
| **PromQL** | `sum(kube_pod_status_phase{namespace="posthog", pod=~"capture-.*"}) by (phase)` |
| **Alert** | Any pods stuck in Pending or Failed need investigation. |

#### `kube_pod_container_status_restarts_total`

| | |
|---|---|
| **Type** | counter |
| **PromQL (recent restarts)** | `sum(increase(kube_pod_container_status_restarts_total{container="capture", namespace="posthog"}[1h])) by (pod)` |
| **Alert** | > 2 restarts per hour indicates CrashLoopBackOff or OOM issues. |

#### `kube_pod_container_status_waiting_reason`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `reason` (CrashLoopBackOff, ImagePullBackOff, CreateContainerConfigError, etc.) |
| **PromQL** | `sum(kube_pod_container_status_waiting_reason{container="capture", namespace="posthog"}) by (pod, reason)` |
| **Alert** | Any CrashLoopBackOff is critical. |

#### `kube_pod_container_status_terminated_reason`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `reason` (OOMKilled, Error, Completed, etc.) |
| **PromQL** | `sum(kube_pod_container_status_terminated_reason{container="capture", namespace="posthog"}) by (pod, reason)` |

#### `kube_pod_container_resource_requests` / `kube_pod_container_resource_limits`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `resource` (cpu, memory) |
| **Meaning** | Configured resource requests/limits. Useful for computing utilization percentages. |
| **PromQL** | `kube_pod_container_resource_requests{container="capture", resource="cpu"}` |

---

### 3.3 Node Health

#### `node_cpu_seconds_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `mode` (user, system, idle, iowait, etc.) |
| **PromQL (node CPU %)** | `100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)` |
| **Alert** | Node CPU > 85% sustained may cause scheduling issues. |

#### `node_memory_MemAvailable_bytes`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Available memory on the node (kernel estimate). Not directly scraped with this name -- use `node_memory_MemAvailable_bytes` if available, otherwise compute from `node_memory_MemTotal_bytes - node_memory_MemFree_bytes - node_memory_Buffers_bytes - node_memory_Cached_bytes`. |
| **PromQL** | Check `node_memory_MemAvailable_bytes` or compute from sub-metrics. |

#### `node_load1` / `node_load5` / `node_load15`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Node load averages. Compare with CPU core count. |
| **PromQL** | `node_load5{instance=~".*"}` |

#### `kube_node_status_condition`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `condition` (Ready, MemoryPressure, DiskPressure, PIDPressure, NetworkUnavailable), `status` |
| **PromQL (not ready)** | `kube_node_status_condition{condition="Ready", status="true"} == 0` |
| **Alert** | Any node with Ready=false or pressure conditions active affects scheduling. |

#### `kube_node_status_allocatable`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `resource` (cpu, memory, pods) |
| **Meaning** | Allocatable resources per node. Compare with pod requests to gauge headroom. |

#### `kube_node_labels`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Node labels including nodepool selectors. Use to filter to the capture nodepool. |
| **PromQL (find capture nodes)** | `kube_node_labels{label_karpenter_sh_nodepool=~".*capture.*"}` or filter by whatever nodepool label convention is used. |

#### `karpenter_cluster_state_node_count`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Number of nodes managed by Karpenter. Useful for tracking autoscaling of the capture nodepool. |
| **PromQL** | `karpenter_cluster_state_node_count` |

---

### 3.4 HPA / Autoscaling

#### `kube_horizontalpodautoscaler_status_current_replicas`

| | |
|---|---|
| **Type** | gauge |
| **PromQL** | `kube_horizontalpodautoscaler_status_current_replicas{namespace="posthog", horizontalpodautoscaler=~"capture.*"}` |

#### `kube_horizontalpodautoscaler_status_desired_replicas`

| | |
|---|---|
| **Type** | gauge |
| **PromQL** | `kube_horizontalpodautoscaler_status_desired_replicas{namespace="posthog", horizontalpodautoscaler=~"capture.*"}` |
| **Alert** | `desired > current` sustained means the cluster can't scale up (resource exhaustion). |

#### `kube_horizontalpodautoscaler_spec_max_replicas` / `kube_horizontalpodautoscaler_spec_min_replicas`

| | |
|---|---|
| **Type** | gauge |
| **PromQL** | `kube_horizontalpodautoscaler_spec_max_replicas{namespace="posthog", horizontalpodautoscaler=~"capture.*"}` |
| **Alert** | `current_replicas == max_replicas` means the HPA is at ceiling. |

#### `kube_horizontalpodautoscaler_status_condition`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `condition` (AbleToScale, ScalingActive, ScalingLimited), `status` |
| **PromQL** | `kube_horizontalpodautoscaler_status_condition{namespace="posthog", horizontalpodautoscaler=~"capture.*", condition="ScalingLimited", status="true"}` |
| **Alert** | ScalingLimited=true means the HPA wants to scale but can't (min/max boundary). |

---

## 4. Kafka / AWS MSK Cluster Metrics

All MSK metrics are scraped into VictoriaMetrics with the `aws_msk_` prefix.
These come from MSK's open monitoring (Prometheus-compatible endpoint on each broker).
Scraped via jobs `aws-msk-jmx` (Kafka JMX) and `aws-msk-node` (broker host node-exporter).

**Scoping to the capture ingestion cluster**: filter with `environment=~"$environment"`.
The capture service produces to the ingestion MSK cluster in each region:

- **prod-us**: `environment="prod-us"`, brokers `b-{1..12}.posthogprodusevents*.kafka.us-east-1.amazonaws.com`
- **prod-eu**: `environment="prod-eu"`, same scheme with eu-central-1

### 4.1 Broker Topic Metrics

#### `aws_msk_kafka_server_BrokerTopicMetrics_OneMinuteRate`

| | |
|---|---|
| **Type** | gauge (JMX-sourced rate) |
| **Labels** | `name` (BytesInPerSec, BytesOutPerSec, MessagesInPerSec, TotalFetchRequestsPerSec, TotalProduceRequestsPerSec, FailedFetchRequestsPerSec, FailedProduceRequestsPerSec, etc.), `topic`, `instance` (broker) |
| **Meaning** | Per-topic, per-broker throughput rates. The most important MSK throughput signal. |
| **PromQL (bytes in by topic)** | `sum(aws_msk_kafka_server_BrokerTopicMetrics_OneMinuteRate{environment=~"$environment", name="BytesInPerSec"}) by (topic)` |
| **PromQL (messages in by topic)** | `sum(aws_msk_kafka_server_BrokerTopicMetrics_OneMinuteRate{environment=~"$environment", name="MessagesInPerSec"}) by (topic)` |
| **PromQL (failed produces)** | `sum(aws_msk_kafka_server_BrokerTopicMetrics_OneMinuteRate{environment=~"$environment", name="FailedProduceRequestsPerSec"}) by (topic)` |
| **Alert** | `FailedProduceRequestsPerSec > 0` sustained indicates broker rejecting writes. BytesIn flatlining while capture is running indicates a disconnect. |

#### `aws_msk_kafka_server_BrokerTopicMetrics_Count`

| | |
|---|---|
| **Type** | counter |
| **Labels** | same as above |
| **Meaning** | Cumulative counts (total bytes in, total messages, etc.). Use `rate()` for point-in-time throughput. |
| **PromQL** | `sum(rate(aws_msk_kafka_server_BrokerTopicMetrics_Count{environment=~"$environment", name="BytesInPerSec"}[5m])) by (topic)` |

---

### 4.2 Request / Network Metrics

#### `aws_msk_kafka_network_RequestMetrics_Mean` / `_99thPercentile` / `_999thPercentile`

| | |
|---|---|
| **Type** | gauge (JMX percentile snapshots) |
| **Labels** | `name` (TotalTimeMs, RequestQueueTimeMs, LocalTimeMs, RemoteTimeMs, ResponseQueueTimeMs, ResponseSendTimeMs, ThrottleTimeMs), `request` (Produce, Fetch, etc.) |
| **Meaning** | Broker-side request processing latency broken into stages. `TotalTimeMs` is the end-to-end request time. |
| **PromQL (produce p99)** | `max(aws_msk_kafka_network_RequestMetrics_99thPercentile{environment=~"$environment", name="TotalTimeMs", request="Produce"}) by (instance)` |
| **PromQL (fetch p99)** | `max(aws_msk_kafka_network_RequestMetrics_99thPercentile{environment=~"$environment", name="TotalTimeMs", request="Fetch"}) by (instance)` |
| **Alert** | Produce TotalTimeMs p99 > 100ms is elevated. > 500ms is critical and will back-pressure capture. |

#### `aws_msk_kafka_network_RequestMetrics_OneMinuteRate`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (RequestsPerSec), `request` |
| **Meaning** | Request rate per second to each broker. |
| **PromQL** | `sum(aws_msk_kafka_network_RequestMetrics_OneMinuteRate{environment=~"$environment", name="RequestsPerSec", request="Produce"}) by (instance)` |

#### `aws_msk_kafka_network_RequestChannel_Value`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (RequestQueueSize, ResponseQueueSize) |
| **Meaning** | Broker request/response queue depth. |
| **PromQL** | `max(aws_msk_kafka_network_RequestChannel_Value{environment=~"$environment", name="RequestQueueSize"}) by (instance)` |
| **Alert** | Growing queue sizes indicate the broker is overloaded. |

#### `aws_msk_kafka_network_Processor_Value`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (IdlePercent) |
| **Meaning** | Network processor idle percentage. Low idle = saturated network threads. |
| **PromQL** | `avg(aws_msk_kafka_network_Processor_Value{environment=~"$environment", name="IdlePercent"}) by (instance)` |
| **Alert** | < 30% idle sustained means network threads are near saturation. |

---

### 4.3 Broker Resource Saturation and Throttling

These metrics are the primary signals for detecting whether the MSK cluster itself is
resource-constrained or throttling producers/consumers. All are scraped from JMX into
VictoriaMetrics with the `aws_msk_` prefix.

#### `aws_msk_kafka_network_RequestMetrics_{Mean,99thPercentile}{name="ThrottleTimeMs"}`

| | |
|---|---|
| **Type** | gauge (JMX percentile snapshot) |
| **Labels** | `name` (ThrottleTimeMs), `request` (Produce, Fetch, FetchConsumer, FetchFollower, and ~60 other request types) |
| **Meaning** | Broker-side throttle time applied to requests. **This is the primary Kafka-level throttling signal.** Non-zero means Kafka quotas are actively delaying requests. Quotas can be per-client-id, per-user, or per-IP. |
| **PromQL (mean, produce)** | `max(aws_msk_kafka_network_RequestMetrics_Mean{environment=~"$environment", name="ThrottleTimeMs", request="Produce"}) by (instance)` |
| **PromQL (p99, produce)** | `max(aws_msk_kafka_network_RequestMetrics_99thPercentile{environment=~"$environment", name="ThrottleTimeMs", request="Produce"}) by (instance)` |
| **PromQL (p99, fetch)** | `max(aws_msk_kafka_network_RequestMetrics_99thPercentile{environment=~"$environment", name="ThrottleTimeMs", request="Fetch"}) by (instance)` |
| **PromQL (any request type)** | `max(aws_msk_kafka_network_RequestMetrics_99thPercentile{environment=~"$environment", name="ThrottleTimeMs"}) by (instance, request)` |
| **Alert** | Any non-zero ThrottleTimeMs means active quota enforcement. p99 > 100ms on Produce is significant -- capture will see increased RTT. |

#### `aws_msk_kafka_server_Request_queue_size`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Number of requests queued in the broker's request queue waiting for a handler thread. Saturation signal for request handler pool. |
| **PromQL** | `max(aws_msk_kafka_server_Request_queue_size{environment=~"$environment"}) by (instance)` |
| **Alert** | Sustained > 0 means request handler threads are all busy -- broker is saturated. |

#### `aws_msk_kafka_server_Produce_queue_size`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Produce requests specifically waiting in queue. Purgatory for produce requests that can't be satisfied immediately (e.g. waiting for acks=all replication). |
| **PromQL** | `max(aws_msk_kafka_server_Produce_queue_size{environment=~"$environment"}) by (instance)` |
| **Alert** | Growing values indicate replication can't keep up with produce rate. |

#### `aws_msk_kafka_server_Fetch_queue_size`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Fetch requests waiting in purgatory (waiting for data to become available). |
| **PromQL** | `max(aws_msk_kafka_server_Fetch_queue_size{environment=~"$environment"}) by (instance)` |

#### `aws_msk_kafka_server_KafkaRequestHandlerPool_OneMinuteRate`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` — must filter by `name="RequestHandlerAvgIdlePercent"` (unfiltered returns high-cardinality hash-named series) |
| **Meaning** | Request handler thread pool idle ratio (0.0 - 1.0). Values close to 0 mean all handler threads are busy processing requests — a leading indicator of broker CPU saturation. |
| **PromQL** | `min(aws_msk_kafka_server_KafkaRequestHandlerPool_OneMinuteRate{environment=~"$environment", name="RequestHandlerAvgIdlePercent"}) by (instance)` |
| **Current** | ~0.70-0.80 (healthy — 70-80% idle) |
| **Alert** | < 0.30 (30% idle) sustained is a warning. < 0.10 is critical — broker is severely overloaded. |

#### `aws_msk_kafka_network_Processor_Value{name="IdlePercent"}`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Network processor thread idle percentage (0.0 - 1.0). These threads handle socket I/O. Low idle = network thread saturation. |
| **PromQL** | `avg(aws_msk_kafka_network_Processor_Value{environment=~"$environment", name="IdlePercent"}) by (instance)` |
| **Current** | ~0.78-0.86 (healthy -- 78-86% idle) |
| **Alert** | < 0.30 (30% idle) sustained means network threads are near saturation. < 0.10 is critical. |

#### `aws_msk_kafka_server_socket_server_metrics_MemoryPoolAvgDepletedPercent`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Average percentage of time the broker's network memory pool was fully depleted. When depleted, the broker cannot accept new requests until memory is freed -- effectively a hard bottleneck. |
| **PromQL** | `max(aws_msk_kafka_server_socket_server_metrics_MemoryPoolAvgDepletedPercent{environment=~"$environment"}) by (instance)` |
| **Alert** | Any non-zero value is a serious red flag -- the broker is running out of network buffer memory. |

#### `aws_msk_kafka_server_socket_server_metrics_MemoryPoolDepletedTimeTotal`

| | |
|---|---|
| **Type** | counter |
| **Meaning** | Cumulative time (nanoseconds) the network memory pool was fully depleted. |
| **PromQL** | `rate(aws_msk_kafka_server_socket_server_metrics_MemoryPoolDepletedTimeTotal{environment=~"$environment"}[5m])` |
| **Alert** | Any non-zero rate means the broker was unable to process requests for some period. |

#### `aws_msk_kafka_server_socket_server_metrics_io_ratio`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Fraction of time the socket server spends doing actual I/O (vs waiting). Higher = busier. |
| **PromQL** | `avg(aws_msk_kafka_server_socket_server_metrics_io_ratio{environment=~"$environment"}) by (instance)` |
| **Current** | ~0.10-0.15 (10-15% busy -- healthy) |
| **Alert** | > 0.70 sustained indicates I/O thread saturation. |

#### `aws_msk_kafka_server_socket_server_metrics_connection_count`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Total number of active connections to each broker. Includes producers, consumers, inter-broker, admin clients. |
| **PromQL** | `max(aws_msk_kafka_server_socket_server_metrics_connection_count{environment=~"$environment"}) by (instance)` |
| **Alert** | Check against the broker's `max.connections` config. Approaching the limit causes connection rejections. |

#### `aws_msk_kafka_server_socket_server_metrics_expired_connections_killed_count`

| | |
|---|---|
| **Type** | counter |
| **Meaning** | Connections killed due to expiry (idle timeout). High rates may indicate clients disconnecting/reconnecting frequently. |
| **PromQL** | `rate(aws_msk_kafka_server_socket_server_metrics_expired_connections_killed_count{environment=~"$environment"}[5m])` |

#### `aws_msk_kafka_server_socket_server_metrics_failed_authentication_total`

| | |
|---|---|
| **Type** | counter |
| **Meaning** | Failed authentication attempts. Spikes indicate credential issues or unauthorized access attempts. |
| **PromQL** | `sum(rate(aws_msk_kafka_server_socket_server_metrics_failed_authentication_total{environment=~"$environment"}[5m])) by (instance)` |
| **Alert** | Any sustained rate warrants investigation -- may indicate misconfigured clients or security issues. |

#### `aws_msk_kafka_server_Request_exempt_request_time`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Time spent on requests exempt from throttling (e.g. internal replication). High values indicate even internal operations are slow. |
| **PromQL** | `max(aws_msk_kafka_server_Request_exempt_request_time{environment=~"$environment"}) by (instance)` |

#### Note: CloudWatch-only MSK metrics

The following MSK metrics are **only available via CloudWatch** (datasource UID `P034F075C744B399F`), not through JMX/Prometheus scraping. These are AWS infrastructure-level signals:

| CloudWatch Metric | Meaning | Alert Threshold |
|---|---|---|
| `AWS/Kafka BurstBalance` | EBS volume burst credit balance (%). If using gp2/gp3 volumes. | < 50% declining = risk of I/O throttling |
| `AWS/Kafka CPUCreditBalance` | CPU credit balance (only for burstable instance types like t3/t4g). | < 100 declining = risk of CPU throttling |
| `AWS/Kafka EstimatedTimeLag` | Estimated consumer lag in seconds. | Growing = consumers falling behind |
| `AWS/Kafka KafkaDataLogsDiskUsed` | Percentage of data log disk used. | > 85% = retention reduction needed |
| `AWS/Kafka CpuUser` + `CpuSystem` | Per-broker CPU from AWS perspective (not JMX). | Combined > 70% = scaling signal |
| `AWS/Kafka MemoryUsed` | Per-broker memory usage from AWS. | Compare with instance total |

To query these from CloudWatch, use the CloudWatch datasource directly (not VictoriaMetrics). These metrics require `namespace=AWS/Kafka` and dimension filters for `Cluster Name`.

---

### 4.4 Controller and Replica Health

#### `aws_msk_kafka_controller_KafkaController_Value`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (ActiveControllerCount, OfflinePartitionsCount, PreferredReplicaImbalanceCount, GlobalTopicCount, GlobalPartitionCount) |
| **Meaning** | Cluster-wide controller state. Exactly one broker should have ActiveControllerCount=1. |
| **PromQL (offline partitions)** | `sum(aws_msk_kafka_controller_KafkaController_Value{environment=~"$environment", name="OfflinePartitionsCount"})` |
| **PromQL (controller count)** | `sum(aws_msk_kafka_controller_KafkaController_Value{environment=~"$environment", name="ActiveControllerCount"})` |
| **Alert** | OfflinePartitionsCount > 0 is **critical** -- data unavailable. ActiveControllerCount != 1 indicates controller election issues. |

#### `aws_msk_kafka_server_ReplicaManager_Value`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (UnderReplicatedPartitions, UnderMinIsrPartitionCount, PartitionCount, LeaderCount, OfflineReplicaCount) |
| **Meaning** | Per-broker replica state. |
| **PromQL** | `sum(aws_msk_kafka_server_ReplicaManager_Value{environment=~"$environment", name="UnderReplicatedPartitions"}) by (instance)` |
| **Alert** | UnderReplicatedPartitions > 0 sustained means a broker is falling behind replication. UnderMinIsrPartitionCount > 0 means data durability is at risk. |

#### `aws_msk_kafka_server_KafkaServer_Value`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (BrokerState, etc.) |
| **Meaning** | Broker state. BrokerState=3 is running normally. |

---

### 4.5 Consumer Lag

#### `aws_msk_kafka_consumer_group_ConsumerLagMetrics_Value`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (`SumOffsetLag`, `MaxOffsetLag`, `OffsetLag`), `groupId`, `topic`, `partition` (per-partition only for `OffsetLag`) |
| **Meaning** | Consumer group lag. `SumOffsetLag` = total offset lag across all partitions for a group/topic. `OffsetLag` = per-partition lag. `MaxOffsetLag` = worst-case partition lag. |
| **PromQL (total lag by group)** | `sum(aws_msk_kafka_consumer_group_ConsumerLagMetrics_Value{environment=~"$environment", name="SumOffsetLag"}) by (groupId, topic)` |
| **PromQL (max partition lag)** | `max(aws_msk_kafka_consumer_group_ConsumerLagMetrics_Value{environment=~"$environment", name="OffsetLag", topic="ingestion-events-1024"}) by (groupId)` |
| **Alert** | Growing `SumOffsetLag` on ingestion topics indicates downstream consumers can't keep up. |

#### `aws_msk_kafka_consumer_consumer_coordinator_metrics_commit_latency_avg`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Average offset commit latency. High values indicate coordinator issues. |

#### `aws_msk_kafka_consumer_consumer_coordinator_metrics_rebalance_rate_per_hour`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Consumer group rebalance frequency. Frequent rebalances indicate instability. |
| **Alert** | > 5/hour for a single consumer group warrants investigation. |

---

### 4.6 MSK Node (Broker Host) Metrics

Scraped from the MSK node exporter on each broker host.

#### `aws_msk_node_cpu_seconds_total`

| | |
|---|---|
| **Type** | counter |
| **Labels** | `mode` (user, system, idle, iowait, etc.) |
| **PromQL (CPU %)** | `100 - (avg by (instance) (rate(aws_msk_node_cpu_seconds_total{environment=~"$environment", mode="idle"}[5m])) * 100)` |
| **Alert** | Broker CPU > 70% sustained is a scaling signal. > 90% is critical. |

#### `aws_msk_node_filesystem_avail_bytes` / `aws_msk_node_filesystem_size_bytes`

| | |
|---|---|
| **Type** | gauge |
| **Meaning** | Broker disk usage. MSK uses EBS volumes for log storage. |
| **PromQL (disk usage %)** | `100 - (aws_msk_node_filesystem_avail_bytes{environment=~"$environment"} / aws_msk_node_filesystem_size_bytes{environment=~"$environment"} * 100)` |
| **Alert** | > 80% disk usage requires immediate attention (topic retention reduction or broker scaling). |

#### `aws_msk_node_disk_written_bytes_total` / `aws_msk_node_disk_read_bytes_total`

| | |
|---|---|
| **Type** | counter |
| **Meaning** | Broker disk I/O throughput. |
| **PromQL** | `sum(rate(aws_msk_node_disk_written_bytes_total{environment=~"$environment"}[5m])) by (instance)` |

#### `aws_msk_kafka_log_LogManager_Value`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (LogDirectoryOffline, Size) |
| **Meaning** | Log directory health and total log size on the broker. |
| **PromQL** | `aws_msk_kafka_log_LogManager_Value{environment=~"$environment", name="LogDirectoryOffline"}` |
| **Alert** | LogDirectoryOffline > 0 means a data volume is unavailable. |

#### `aws_msk_kafka_log_LogFlushStats_99thPercentile`

| | |
|---|---|
| **Type** | gauge |
| **Labels** | `name` (LogFlushRateAndTimeMs) |
| **Meaning** | Time to flush log segments to disk (p99). |
| **PromQL** | `max(aws_msk_kafka_log_LogFlushStats_99thPercentile{environment=~"$environment", name="LogFlushRateAndTimeMs"}) by (instance)` |
| **Alert** | > 1000ms indicates disk I/O bottleneck. |

---

## 5. Query Template Patterns

Reusable query patterns that work across the metrics above. Replace `METRIC`, `LABEL`, `VALUE` with actuals.

### 5.1 Current Rate

For any counter metric, use a 5m rate window:

```promql
# Total rate across all pods
sum(rate(METRIC{role=~"$role"}[5m]))

# Rate broken down by a label
sum(rate(METRIC{role=~"$role"}[5m])) by (LABEL)

# Rate per pod
sum(rate(METRIC{role=~"$role"}[5m])) by (pod)
```

### 5.2 Latency Percentiles

For histogram metrics:

```promql
# p50
histogram_quantile(0.50, sum(rate(METRIC_bucket{role=~"$role"}[5m])) by (le))

# p95
histogram_quantile(0.95, sum(rate(METRIC_bucket{role=~"$role"}[5m])) by (le))

# p99
histogram_quantile(0.99, sum(rate(METRIC_bucket{role=~"$role"}[5m])) by (le))

# p99 broken down by a label
histogram_quantile(0.99, sum(rate(METRIC_bucket{role=~"$role"}[5m])) by (le, LABEL))

# Average (from sum and count)
sum(rate(METRIC_sum{role=~"$role"}[5m])) / sum(rate(METRIC_count{role=~"$role"}[5m]))
```

### 5.3 Saturation

```promql
# Kafka producer queue saturation (0-1 ratio)
capture_kafka_producer_queue_depth{role=~"$role"}
  / capture_kafka_producer_queue_depth_limit{role=~"$role"}

# Kafka producer queue bytes saturation
capture_kafka_producer_queue_bytes{role=~"$role"}
  / capture_kafka_producer_queue_bytes_limit{role=~"$role"}

# Memory saturation (container vs limit)
container_memory_working_set_bytes{container="capture"}
  / on(pod) group_left()
  kube_pod_container_resource_limits{container="capture", resource="memory"}

# CPU saturation (usage vs request)
sum(rate(container_cpu_usage_seconds_total{container="capture"}[5m])) by (pod)
  / on(pod) group_left()
  sum(kube_pod_container_resource_requests{container="capture", resource="cpu"}) by (pod)

# HPA saturation (current vs max)
kube_horizontalpodautoscaler_status_current_replicas{horizontalpodautoscaler=~"capture.*"}
  / kube_horizontalpodautoscaler_spec_max_replicas{horizontalpodautoscaler=~"capture.*"}

# MSK disk saturation
1 - (aws_msk_node_filesystem_avail_bytes{environment=~"$environment"}
  / aws_msk_node_filesystem_size_bytes{environment=~"$environment"})
```

### 5.4 Error Ratios

```promql
# HTTP error rate (4xx + 5xx as fraction of total)
sum(rate(http_requests_total{role=~"$role", status=~"[45].."}[5m]))
  / sum(rate(http_requests_total{role=~"$role"}[5m]))

# Event drop rate (fraction of received events that were dropped)
sum(rate(capture_events_dropped_total{role=~"$role"}[5m]))
  / sum(rate(capture_events_received_total{role=~"$role"}[5m]))

# Kafka produce error rate
sum(rate(capture_kafka_produce_errors_total{role=~"$role"}[5m]))
  / sum(rate(capture_events_ingested_total{role=~"$role"}[5m]))

# S3 upload error rate
sum(rate(capture_s3_upload_total{role=~"$role", outcome="error"}[5m]))
  / sum(rate(capture_s3_upload_total{role=~"$role"}[5m]))

# Event restrictions Redis fetch error rate
sum(rate(capture_event_restrictions_redis_fetch{role=~"$role", result=~"error|parse_error"}[5m]))
  / sum(rate(capture_event_restrictions_redis_fetch{role=~"$role"}[5m]))

# MSK failed produce requests (broker side)
sum(aws_msk_kafka_server_BrokerTopicMetrics_OneMinuteRate{environment=~"$environment", name="FailedProduceRequestsPerSec"})
  / sum(aws_msk_kafka_server_BrokerTopicMetrics_OneMinuteRate{environment=~"$environment", name="TotalProduceRequestsPerSec"})
```

### 5.5 Alert Threshold Suggestions

| Signal | Warning | Critical | Notes |
|--------|---------|----------|-------|
| `http_requests_duration_seconds` p99 | > 1s | > 10s | Backpressure from Kafka or S3 |
| HTTP 5xx error rate | > 1% | > 5% | Server-side failures |
| `capture_kafka_produce_errors_total` rate | > 0 | > 10/s | Events being lost |
| `capture_kafka_any_brokers_down` | 1 on any pod | 1 on all pods | Kafka connectivity |
| Kafka producer queue saturation | > 0.7 | > 0.9 | Approaching message loss |
| `capture_kafka_produce_rtt_latency_us` p99 | > 100ms (100000) | > 500ms (500000) | Broker overload |
| `capture_events_dropped_total` `retryable_sink` | > 0 | > 100/s | Kafka delivery failures |
| `capture_primary_sink_health` | 0 on any pod | 0 on all pods | Fallback sink active *(code-only, no active series)* |
| Container memory (% of limit) | > 80% | > 90% | OOM kill risk |
| Container CPU throttling | > 25% | > 50% | Latency impact |
| Pod restarts (per hour) | > 1 | > 3 | Stability issues |
| HPA at max replicas | desired > current | current == max | Can't scale further |
| MSK OfflinePartitionsCount | > 0 | > 0 | **Always critical** |
| MSK UnderReplicatedPartitions | > 0 for > 5m | > 0 for > 15m | Replication lag |
| MSK broker CPU | > 70% | > 90% | Need to scale brokers |
| MSK disk usage | > 70% | > 85% | Retention or scaling needed |
| MSK produce TotalTimeMs p99 | > 100ms | > 500ms | Broker overload |
| Consumer lag (records) | growing | growing > 30m | Downstream can't keep up |
| `capture_event_restrictions_stale` | 1 on any pipeline | 1 on all pipelines | Restrictions not applied |
| MSK ThrottleTimeMs (Produce) p99 | > 0 | > 100ms | Kafka quota enforcement active |
| MSK Network Processor idle | < 30% | < 10% | Broker network thread saturation |
| MSK MemoryPoolAvgDepletedPercent | > 0 | > 0.1 | Broker can't accept requests |
| MSK Request_queue_size | > 0 sustained | > 10 sustained | Request handler threads saturated |
| MSK socket I/O ratio | > 0.5 | > 0.7 | Broker I/O thread saturation |
| Envoy upstream p99 latency | > 500ms | > 2s | Backend slowness seen from ingress |
| Envoy 5xx error ratio | > 0.1% | > 1% | Backend returning errors |
| Envoy upstream rq timeout rate | > 0 | > 10/s | Requests timing out at ingress |
| Envoy circuit breaker open | any `_open` = 1 | sustained | Envoy shedding traffic |
| Envoy membership healthy < total | any cluster | sustained > 5m | Backend pods failing health checks |
| Envoy connect failures rate | > 0 sustained | > 10/s | Pods unreachable |
| Envoy pending request overflow rate | > 0 | > 10/s | Connection pool exhaustion |

---

## Appendix: Key Kafka Topics (Capture Produces To)

Topics observed in `capture_kafka_produce_bytes_total{topic=...}` (production).
Only the primary ingestion pipeline topics are listed here -- capture routes events
into these based on event type, quota, and overflow rules.

| Topic | Purpose |
|-------|---------|
| `events_plugin_ingestion` | Primary events for plugin/ingestion processing |
| `events_plugin_ingestion_overflow` | Overflow for high-volume / rate-limited tokens |
| `events_plugin_ingestion_historical` | Historical (backfill) events with old timestamps |
| `events_plugin_ingestion_dlq` | Dead-letter queue for failed events |
| `ingestion-events-1024` | High-partition main ingestion (new pipeline) |
| `ingestion-events-1024-duplicates` | Deduplication tracking for main pipeline |
| `ingestion-events-overflow-128` | Overflow topic (new pipeline) |
| `ingestion-events-historical-128` | Historical events (new pipeline) |
| `ingestion-events_testing-overflow-128` | Testing overflow |
| `ingestion-session_replay-main-256` | Session replay main pipeline |
| `ingestion-session_replay-overflow-32` | Session replay overflow |
| `ingestion-heatmaps-128` | Heatmap ingestion pipeline |
| `ingestion-logs` | Log ingestion pipeline |
| `ingestion-traces` | Trace ingestion pipeline |
| `ingestion-error_tracking-main-128` | Error tracking main pipeline |
| `ingestion-error_tracking-overflow-32` | Error tracking overflow |
| `ingestion-general-turbo-1024` | General turbo ingestion pipeline |

---

## Appendix: Grafana Datasource Reference

| Name | UID | Type | Use |
|------|-----|------|-----|
| VictoriaMetrics | `victoriametrics` | prometheus (default) | All capture, k8s, and MSK metrics |
| VictoriaMetrics-Realtime | `victoriametrics-realtime` | prometheus | Lower-retention, higher-resolution queries |
| CloudWatch | `P034F075C744B399F` | cloudwatch | AWS service metrics (fallback for MSK if not in VM) |
| CloudWatch Root | `PAAE47F430CFD1449` | cloudwatch | Root account AWS metrics |
| Loki | `P8E80F9AEF21F6940` | loki | Log queries |
| Pyroscope | `pyroscope` | pyroscope | Continuous profiling |

## Appendix: Key Grafana Dashboards

| Dashboard | UID | Description |
|-----------|-----|-------------|
| Capture | `capture` | Main capture service dashboard |
| Ingestion - Capture | `ingestion-capture` | Capture-specific ingestion metrics |
| Ingestion - General | `ingestion-general` | Cross-service ingestion overview |
| Ingestion - Reliability | `ingestion-reliability` | Error rates and reliability signals |
| Ingestion - Pipeline Performance | `ingestion-pipeline-performance` | End-to-end pipeline latency |
| Ingestion - Autoscaling | `ingestion-autoscaling` | HPA and scaling metrics |
| AWS MSK - Kafka Cluster | `qZz6iq9Wx` | MSK broker and topic metrics |
| ClickHouse - Kafka consumption | `ddpxkllwxg268e` | ClickHouse Kafka consumer stats |
| KMinion Consumer Group Lag | `dbfgkwxs3gw8owd` | Consumer group lag monitoring |
| Session Replay -- Ingestion | `ingestion-session-recordings` | Session replay pipeline |
| Contour Ingress | `contour` | Envoy L7 proxy metrics per cluster — set `endpoint_namespace=posthog`, `envoy_cluster_name=posthog_capture_3000` |
