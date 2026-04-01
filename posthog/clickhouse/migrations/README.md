# ClickHouse migrations

This directory contains ClickHouse schema migrations for PostHog.
There are two styles: legacy `.py` files and new-style directory migrations.

## New-style directory migrations

Each migration lives in a numbered directory
(e.g. `NNNN_<name>/`) containing:

```text
NNNN_<name>/
  manifest.yaml   # declares steps, rollback, and metadata
  up.sql           # SQL template(s) for the forward direction
  down.sql         # SQL template(s) for rollback
  __init__.py      # bridge for backward compatibility with the legacy runner
```

### SQL templates

SQL files are Jinja2 templates with access to these variables:

- `{{ database }}` -- the ClickHouse database name
- `{{ cluster }}` -- the ClickHouse cluster name
- `{{ single_shard_cluster }}` -- the single-shard cluster name (if configured)

A single `.sql` file can contain multiple named sections separated by
`-- @section: <name>` comments.
Steps reference a specific section with `up.sql#section_name`
or the entire file with just `up.sql`.

## Creating a new migration

Use the management command:

```bash
python manage.py create_ch_migration \
  --name add_foo_column \
  --type add-column \
  --table events
```

This scaffolds a numbered directory with `manifest.yaml`, `up.sql`, `down.sql`,
and an `__init__.py` bridge.
It also updates `max_migration.txt`.

## Manifest reference

```yaml
description: 'Human-readable summary of the migration'

# Optional: target a single ClickHouse cluster name
cluster: posthog

# Optional: target multiple clusters (overrides `cluster`)
clusters:
  - us-east
  - eu-west

steps:
  - sql: 'up.sql#create_local'
    node_roles: [DATA] # required: DATA, COORDINATOR, or both
    comment: 'Create local table'
    sharded: true # run on each shard (default: false)
    is_alter_on_replicated_table: false # ALTER that replicates (default: false)
    clusters: # per-step override of manifest-level clusters
      - us-east

rollback:
  - sql: 'down.sql'
    node_roles: [DATA, COORDINATOR]
```

### Field details

| Field                          | Scope    | Required | Description                                    |
| ------------------------------ | -------- | -------- | ---------------------------------------------- |
| `description`                  | manifest | yes      | Human-readable summary                         |
| `cluster`                      | manifest | no       | Single target cluster name                     |
| `clusters`                     | manifest | no       | List of target clusters (overrides `cluster`)  |
| `steps`                        | manifest | yes      | Ordered list of forward steps                  |
| `rollback`                     | manifest | no       | Ordered list of rollback steps                 |
| `sql`                          | step     | yes      | SQL file reference, optionally with `#section` |
| `node_roles`                   | step     | yes      | `["DATA"]`, `["COORDINATOR"]`, or both         |
| `comment`                      | step     | no       | Human-readable description of the step         |
| `sharded`                      | step     | no       | Execute on each shard separately               |
| `is_alter_on_replicated_table` | step     | no       | ALTERs that replicate across nodes             |
| `clusters`                     | step     | no       | Per-step cluster override                      |

### Multi-cluster behavior

When `clusters` is set at the manifest or step level,
the runner filters steps based on the current cluster identity.

- **Step `clusters`** takes precedence over manifest `clusters`.
- **Manifest `clusters`** takes precedence over manifest `cluster`.
- When no cluster targeting is configured, every step runs everywhere.

In a future iteration, cross-cluster ordering checks will verify
that migration N has been recorded as complete on all target clusters
before applying migration N+1.

## `ch_migrate` commands

All commands are run via Django management:

```bash
python manage.py ch_migrate <subcommand>
```

### `bootstrap`

Create the tracking table (`clickhouse_schema_migrations`) on all nodes.
Run this once when setting up a new environment.

```bash
python manage.py ch_migrate bootstrap
```

### `plan`

Show pending migrations without executing them.

```bash
python manage.py ch_migrate plan
```

### `apply`

Apply pending migrations in order. Automatically checks for active mutations
on target tables before applying (use `--skip-mutation-check` to bypass).

```bash
python manage.py ch_migrate apply [--upto N] [--skip-mutation-check] [--force]
```

- `--upto N` -- apply migrations up to number N (inclusive)
- `--skip-mutation-check` -- skip the automatic active mutation check
- `--force` -- apply even if active mutations are found

### `down`

Roll back a specific migration by number.

```bash
python manage.py ch_migrate down <migration_number>
```

### `validate`

Run static analysis on a migration (checks for `ON CLUSTER`, rollback completeness,
node role consistency, DROP statements).

```bash
python manage.py ch_migrate validate <migration_number> [--strict]
```

### `trial`

Sandbox validation: runs up, verifies schema, rolls back, verifies schema is restored.

```bash
python manage.py ch_migrate trial <migration_number>
```

### `status`

Show per-host migration state (both legacy infi and new-style tracking tables).

```bash
python manage.py ch_migrate status [--node <hostname>]
```

## The `__init__.py` bridge

Each new-style migration directory includes an `__init__.py`
so the legacy `migrate_clickhouse` runner can discover it.
The bridge file contains an empty `operations = []` list,
which signals that the migration is handled by `ch_migrate` instead.

## Schema safety

The validator understands ClickHouse table _ecosystems_ — the set of objects
(sharded table, distributed tables, Kafka table, MV, dictionaries) that must
stay in sync for a data pipeline to work.

### Table ecosystems

A typical sharded table in PostHog involves several linked objects:

| Object              | Engine              | Purpose                              |
| ------------------- | ------------------- | ------------------------------------ |
| `sharded_events`    | ReplicatedMergeTree | Stores data on each shard            |
| `writable_events`   | Distributed         | Sharding-key router for writes       |
| `events`            | Distributed         | Read-path aggregation across shards  |
| `kafka_events_json` | Kafka               | Consumes from Kafka topic            |
| `events_json_mv`    | MaterializedView    | Pipes Kafka rows into writable table |

Cross-cluster ecosystems (like sessions) also include remote tables and
dictionaries that bridge clusters.

### Ecosystem completeness check

When a migration touches any table in a known ecosystem, the validator warns
if companion tables are not also present in the SQL. This catches the common
mistake of ALTERing `sharded_events` without updating `writable_events`.

To opt in explicitly, add `ecosystem: <name>` to your manifest:

```yaml
description: 'Add column to sessions'
ecosystem: sessions_v3
steps:
  - sql: 'up.sql#alter_sharded'
    node_roles: [DATA]
    sharded: true
    is_alter_on_replicated_table: true
  - sql: 'up.sql#alter_distributed'
    node_roles: [COORDINATOR]
```

### Creation order check

Within a migration, objects must be created in dependency order:

1. **Kafka tables** (tier 0) — source of data
2. **MergeTree tables** (tier 1) — local storage
3. **Distributed tables** (tier 2) — read from MergeTree
4. **Materialized views and dictionaries** (tier 3) — read from Kafka/Distributed

Creating a MV before its source Kafka table is an error.

### Cross-cluster targeting check

The validator warns when step metadata suggests a mismatch between table type
and node role. For example, a step creating a Distributed table should target
COORDINATOR nodes, not DATA nodes.

## Templates

Templates let you declare _what_ you want (a table, a column, a pipeline)
and the system generates the SQL, node roles, ordering, and rollback automatically.

### Available templates

| Template                 | Objects created                                | Use case                          |
| ------------------------ | ---------------------------------------------- | --------------------------------- |
| `ingestion_pipeline`     | kafka + sharded + writable + readable + MV (5) | New table consuming from Kafka    |
| `sharded_table`          | sharded + writable + readable (3)              | New table without Kafka ingestion |
| `add_column`             | drop MV + ALTER all tables + recreate MV       | Adding a column to an ecosystem   |
| `cross_cluster_readable` | distributed + optional dictionary              | Reading from another cluster      |
| `materialized_view`      | MV                                             | Custom MV between tables          |
| `drop_table`             | DROP in reverse dependency order               | Removing an ecosystem             |

### Template manifest format

Instead of `steps`, use `template` + `config`:

```yaml
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

The system generates all SQL at apply time. No `up.sql` or `down.sql` needed.

### `ingestion_pipeline` config

| Field            | Required | Default               | Description                              |
| ---------------- | -------- | --------------------- | ---------------------------------------- |
| `table`          | yes      |                       | Base table name                          |
| `columns`        | yes      |                       | List of `{name, type, default?, codec?}` |
| `order_by`       | yes      |                       | ORDER BY columns                         |
| `partition_by`   | no       |                       | PARTITION BY expression                  |
| `kafka_topic`    | yes      |                       | Kafka topic name                         |
| `kafka_group`    | no       | `{table}_consumer`    | Consumer group                           |
| `kafka_format`   | no       | `JSONEachRow`         | Kafka format                             |
| `engine`         | no       | `ReplicatedMergeTree` | Table engine                             |
| `engine_params`  | no       |                       | Engine parameters (e.g. ver)             |
| `sharding_key`   | no       | `rand()`              | Distributed sharding key                 |
| `storage_policy` | no       | `false`               | Use hot_to_cold policy                   |
| `ingestion_role` | no       | `INGESTION_EVENTS`    | Node role for kafka/MV                   |

### `add_column` config

```yaml
description: 'Add foo_bar column to events'
template: add_column
config:
  ecosystem: events
  column:
    name: foo_bar
    type: String
    default: "''"
  after: existing_column # optional
```

The MV recreate step is a placeholder that requires manual editing
(the full SELECT cannot be auto-generated from config alone).

### `cross_cluster_readable` config

```yaml
description: 'Add channel_definition readable on sessions cluster'
template: cross_cluster_readable
config:
  source_table: channel_definition
  source_cluster: main
  target_cluster: sessions
  create_dictionary: true
  dict_layout: flat
  dict_lifetime: 300
```

### `sharded_table` config

Same as `ingestion_pipeline` minus the Kafka fields.

### Generating a migration

```bash
python manage.py ch_migrate generate \
  --template ingestion_pipeline \
  --table sessions_v4 \
  --cluster sessions
```

This creates a numbered directory with `manifest.yaml` and `__init__.py`.
Edit the manifest to customize, then validate and apply:

```bash
python manage.py ch_migrate validate <N>
python manage.py ch_migrate plan
python manage.py ch_migrate apply
```

## CI integration

CI integration (validation steps, SQL linting, trial runs) will be added in a
follow-up PR once the core migration engine is merged.
