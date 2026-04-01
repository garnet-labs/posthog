# ClickHouse Migration Tools

A structured migration system for PostHog's ClickHouse cluster. Supports hand-written SQL migrations and declarative templates that auto-generate SQL for common patterns.

## Quick Start

```bash
# Generate a migration from a template
python manage.py ch_migrate generate --template ingestion_pipeline --table sessions_v4 --cluster sessions

# Validate a migration
python manage.py ch_migrate validate posthog/clickhouse/migrations/0230_add_sessions_v4/

# Plan (dry run)
python manage.py ch_migrate plan

# Apply pending migrations
python manage.py ch_migrate apply
```

## Migration Styles

### Step-Based (hand-written SQL)

Write SQL files and a manifest that maps each SQL section to the correct node roles:

```text
0230_add_sessions_v4/
├── manifest.yaml
├── up.sql
└── __init__.py
```

```yaml
# manifest.yaml
description: 'Add sessions v4 table'
steps:
  - sql: up.sql#create_sharded
    node_roles: ['DATA']
    sharded: true
  - sql: up.sql#create_distributed
    node_roles: ['COORDINATOR']
rollback:
  - sql: up.sql#drop_distributed
    node_roles: ['COORDINATOR']
  - sql: up.sql#drop_sharded
    node_roles: ['DATA']
    sharded: true
```

### Template-Based (declarative)

Declare what you want in YAML. The system generates all SQL, node role assignments, and rollback steps:

```yaml
# manifest.yaml
description: 'Add sessions v4 ingestion pipeline'
template: ingestion_pipeline
config:
  table: sessions_v4
  columns:
    - name: session_id
      type: UUID
    - name: team_id
      type: Int64
    - name: timestamp
      type: "DateTime64(6, 'UTC')"
  order_by: [team_id, 'toStartOfHour(timestamp)', session_id]
  partition_by: 'toYYYYMM(timestamp)'
  kafka_topic: session_recordings
  kafka_group: sessions_v4_consumer
```

No SQL to write. The template engine generates a Kafka table, sharded local table, writable distributed table, readable distributed table, and materialized view with correct node roles and creation order.

## Templates

### `ingestion_pipeline`

Full Kafka-to-ClickHouse ingestion pipeline. Creates 5 objects:

| Object             | Engine                | Node Role        |
| ------------------ | --------------------- | ---------------- |
| `kafka_{table}`    | Kafka()               | INGESTION_EVENTS |
| `sharded_{table}`  | ReplicatedMergeTree() | DATA (sharded)   |
| `writable_{table}` | Distributed()         | COORDINATOR      |
| `{table}`          | Distributed()         | ALL              |
| `{table}_mv`       | MaterializedView      | INGESTION_EVENTS |

**Config:**

```yaml
table: string # Required — base table name
columns: # Required — column definitions
  - name: string
    type: string
    default: string # Optional
    codec: string # Optional
order_by: [string] # Required
partition_by: string # Optional
kafka_topic: string # Required
kafka_group: string # Default: {table}_consumer
kafka_format: string # Default: JSONEachRow
sharding_key: string # Default: rand()
engine: string # Default: ReplicatedMergeTree
ingestion_role: string # Default: INGESTION_EVENTS
storage_policy: bool # Default: false
ttl: string # Optional
settings: string # Optional extra engine settings
```

### `sharded_table`

Sharded table with distributed read/write layers (no Kafka or MV). Creates 3 objects.

**Config:** Same as `ingestion_pipeline` minus kafka/MV fields.

### `add_column`

Adds a column to all tables in an ecosystem. Handles the MV drop/recreate dance automatically.

Generated steps:

1. Drop materialized view
2. `ALTER TABLE sharded_{table} ADD COLUMN` (DATA, sharded, is_alter_on_replicated_table)
3. `ALTER TABLE writable_{table} ADD COLUMN` (COORDINATOR)
4. `ALTER TABLE {table} ADD COLUMN` (ALL)
5. `ALTER TABLE kafka_{table} ADD COLUMN` (ALL)
6. Recreate MV (placeholder — requires manual edit for the SELECT)

**Config:**

```yaml
ecosystem: string # Required — name from schema_graph.py (events, sessions_v3, etc.)
column:
  name: string # Required
  type: string # Required
  default: string # Optional
after: string # Optional — insert after this column
```

The MV recreation step is a placeholder. After generating, edit the MV SQL to include the full `SELECT` with the new column.

### `cross_cluster_readable`

Creates a distributed table on one cluster that reads from another. Optionally creates a dictionary for faster point lookups.

**Config:**

```yaml
source_table: string # Required
source_cluster: string # Required — cluster the source table lives on
target_cluster: string # Required — cluster to create the readable on
create_dictionary: bool # Default: false
dict_layout: string # Default: flat
dict_lifetime: int # Default: 300 (seconds)
```

### `materialized_view`

Single materialized view creation.

**Config:**

```yaml
name: string # Required — MV name
target_table: string # Required — table the MV writes to
source_table: string # Required — table the MV reads from
select_columns: string # Default: "*"
node_roles: [string] # Default: ["ALL"]
```

### `drop_table`

Drops an entire ecosystem or specific tables in reverse dependency order.

**Config (option A — ecosystem):**

```yaml
ecosystem: string # Drops all objects: MV → dictionaries → distributed → sharded → kafka
```

**Config (option B — explicit tables):**

```yaml
tables:
  - name: string
    type: string # Default: TABLE (or MATERIALIZED VIEW, DICTIONARY)
    node_roles: [string] # Default: ["ALL"]
    sharded: bool # Default: false
```

## Node Roles

The migration runner routes each step to the correct ClickHouse nodes based on `node_roles`:

| Role             | Meaning                                         |
| ---------------- | ----------------------------------------------- |
| DATA             | Data storage nodes (sharded local tables)       |
| COORDINATOR      | Coordinator nodes (writable distributed tables) |
| ALL              | All nodes in the cluster                        |
| INGESTION_EVENTS | Events ingestion nodes (Kafka tables, MVs)      |
| INGESTION_SMALL  | Small ingestion pipeline nodes                  |
| INGESTION_MEDIUM | Medium ingestion pipeline nodes                 |
| SHUFFLEHOG       | Shufflehog nodes                                |
| ENDPOINTS        | Endpoint nodes                                  |
| LOGS             | Log nodes                                       |

## Validation Rules

`ch_migrate validate` checks for common mistakes:

- **on_cluster**: SQL must not contain `ON CLUSTER` (the runner handles routing)
- **rollback_completeness**: Forward and rollback step counts must match
- **node_role_consistency**: Sharded operations should target DATA nodes
- **ecosystem_completeness**: Altering one table in an ecosystem should alter all companion tables
- **creation_order**: Kafka (tier 0) → MergeTree (tier 1) → Distributed (tier 2) → MV (tier 3)
- **cross_cluster_targeting**: Distributed tables should target COORDINATOR, not DATA

## Ecosystems

The schema graph tracks which tables form a logical ecosystem. Known ecosystems:

- **events**: sharded_events, writable_events, events, kafka_events_json, events_json_mv
- **events_recent**: sharded_events_recent, writable_events_recent, events_recent, kafka_events_json, events_json_recent_mv
- **sessions_v3**: sharded_session_replay_events, writable_session_replay_events, session_replay_events (+ cross-cluster remote tables and dictionaries)
- **person**: sharded_person, person (distributed)
- **session_replay_events**: sharded_session_replay_events, writable_session_replay_events, session_replay_events, kafka_session_replay_events, session_replay_events_mv

## SQL Placeholders

All SQL (both hand-written and template-generated) uses Jinja2 placeholders:

- `{{ database }}` — resolved to `CLICKHOUSE_DATABASE` at runtime
- `{{ cluster }}` — resolved to `CLICKHOUSE_CLUSTER` at runtime

## Running Tests

The migration tools tests run without Django or a ClickHouse connection:

```bash
python3 posthog/clickhouse/test/test_migration_tools.py
python3 posthog/clickhouse/test/test_migration_runner.py
python3 posthog/clickhouse/test/test_trial.py
```
