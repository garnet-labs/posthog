# ai_events ClickHouse table design review

Review of partitioning, sharding key, ORDER BY, and skip indices
against ClickHouse docs and the trace view query runners.

## Verdict

The table design is strong. The ORDER BY `(team_id, trace_id, timestamp)`
is the single most important decision and it's exactly right —
it gives O(log N) trace lookups via the sparse primary index
with all trace events physically contiguous on disk.
Daily partitioning with `retention_days` enables clean TTL drops
and stays well within the <1000 partition guideline
even with 3 retention tiers (30/90/180 days = ~540 partitions).
The sharding key co-locates trace data on the same shard for efficient GROUP BY.

The skip indices are harmless but **none of them meaningfully contribute
to trace view performance** — the primary key does all the heavy lifting.
`idx_trace_id` is redundant (trace_id is already #2 in ORDER BY),
and `idx_event` rarely skips granules since the table only contains AI events.
The rest target columns not used as WHERE filters in current queries.
They're fine to keep as low-overhead insurance for future access patterns.

## Skip indices breakdown

| Index             | Used in trace queries? | Provides skip benefit?      | Recommendation             |
| ----------------- | ---------------------- | --------------------------- | -------------------------- |
| `idx_trace_id`    | Yes (WHERE)            | No — primary key handles it | Redundant, keep if desired |
| `idx_session_id`  | No                     | No                          | Forward-looking, keep      |
| `idx_parent_id`   | No                     | No                          | Forward-looking, keep      |
| `idx_span_id`     | No                     | No                          | Forward-looking, keep      |
| `idx_prompt_name` | No                     | No                          | Forward-looking, keep      |
| `idx_model`       | No                     | No                          | Forward-looking, keep      |
| `idx_event`       | Yes (WHERE)            | No — all-AI table           | Low value, keep if desired |
| `idx_is_error`    | No                     | No                          | Forward-looking, keep      |
| `idx_provider`    | No                     | No                          | Forward-looking, keep      |

## Optional improvements

- Reduce `idx_trace_id` precision from 0.001 to 0.01 (redundant anyway, no need for finest precision)
- Consider `optimize_skip_unused_shards` at query/cluster level for single-trace shard pruning
