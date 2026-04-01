# ClickHouse migrations

This directory contains ClickHouse schema migrations for PostHog.

## Migration approaches

### Desired-state YAML (new)

Schema is declared in `posthog/clickhouse/schema/*.yaml`.
The system diffs desired state against live ClickHouse and generates a plan.

Developer flow:

```bash
# Generate a schema YAML from a template
python manage.py ch_migrate generate --template ingestion_pipeline --table sessions_v4

# Diff desired vs current, show plan
python manage.py ch_migrate plan

# Execute the plan
python manage.py ch_migrate apply
```

### Legacy .py migrations

The numbered `.py` files (0001 through 0223) are legacy migrations
managed by `migrate_clickhouse`.
They are untouched and still discoverable by `ch_migrate check`.

## Schema YAML format

Each YAML file declares one table ecosystem:

```yaml
ecosystem: events
cluster: main

tables:
    sharded_events:
        engine: ReplicatedReplacingMergeTree
        sharded: true
        on_nodes: DATA
        order_by: [team_id, "toDate(timestamp)", event]
        partition_by: "toYYYYMM(timestamp)"
        columns:
            - name: uuid
              type: UUID
            - name: event
              type: String

    writable_events:
        engine: Distributed
        source: sharded_events
        on_nodes: COORDINATOR
        columns: inherit sharded_events

    events:
        engine: Distributed
        source: sharded_events
        on_nodes: ALL
        columns: inherit sharded_events
```

## `ch_migrate` subcommands

| Command     | Description                                    |
| ----------- | ---------------------------------------------- |
| `plan`      | Diff schema YAML vs live ClickHouse            |
| `apply`     | Execute the reconciliation plan                |
| `generate`  | Scaffold a schema YAML from a template         |
| `drift`     | Detect per-host schema divergence              |
| `schema`    | Dump current live schema                       |
| `status`    | Show per-host migration tracking records       |
| `bootstrap` | Create the tracking table                      |
| `check`     | Show pending legacy migrations                 |
| `lint`      | Validate schema YAML files                     |
| `down`      | Roll back a legacy migration by number         |

## Schema safety

The diff engine respects ClickHouse ecosystem rules:

- DROP MV before altering source tables
- CREATE local tables before Distributed tables
- CREATE Kafka tables before MVs
- ALTER all ecosystem tables when adding a column

The `lint` command checks for ecosystem completeness
and cross-cluster targeting mismatches.

## Node roles

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
