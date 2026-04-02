# ClickHouse migration tools

Declarative, Terraform-style schema management for PostHog's ClickHouse clusters. Define what you want in YAML, and the system figures out the DDL to get there.

## Quick start

### Adding a new table with full ingestion pipeline

```bash
# Generate a schema YAML from the ingestion_pipeline template
python manage.py ch_migrate generate --template ingestion_pipeline --table my_new_table

# Review and edit the generated YAML
$EDITOR posthog/clickhouse/schema/my_new_table.yaml

# See what will change (dry run)
python manage.py ch_migrate plan

# Apply the changes
python manage.py ch_migrate apply
```

### Adding a column to an existing table

Edit the table's YAML file directly and add your column to the sharded table's `columns` list. Inherited columns propagate automatically.

```bash
$EDITOR posthog/clickhouse/schema/events.yaml
python manage.py ch_migrate plan    # verify the diff
python manage.py ch_migrate apply
```

### Checking for schema drift

```bash
# Compare live ClickHouse schema against desired-state YAML
python manage.py ch_migrate drift
```

### Importing current schema to YAML

```bash
# Dump the live schema into YAML files (useful for bootstrapping)
python manage.py ch_migrate reconcile import
```

## Available commands

| Command | What it does |
| --- | --- |
| `ch_migrate plan` | Diff desired YAML vs live ClickHouse, show what would change |
| `ch_migrate apply` | Execute the reconciliation plan |
| `ch_migrate reconcile import` | Dump current live schema to YAML |
| `ch_migrate drift` | Detect per-host schema divergence |
| `ch_migrate schema` | Dump current live schema |
| `ch_migrate generate --template <name> --table <name>` | Generate a new schema YAML from a template |

## Available templates

| Template | What it creates |
| --- | --- |
| `ingestion_pipeline` | Full Kafka-to-ClickHouse pipeline: kafka + sharded + writable + readable + MV |
| `sharded_table` | Sharded table with distributed read/write layers (no Kafka or MV) |
| `cross_cluster_readable` | Distributed table for cross-cluster reads |
| `materialized_view` | Single materialized view |
| `add_column` | Guidance to edit existing YAML directly |
| `drop_table` | Guidance to remove from existing YAML |

## How it works

1. You declare desired schema in `posthog/clickhouse/schema/*.yaml`
2. `ch_migrate plan` queries live ClickHouse and diffs against your YAML
3. The system generates DDL in the correct dependency order (respecting cross-cluster relationships)
4. `ch_migrate apply` executes the DDL, routing each statement to the correct nodes

The schema graph models table ecosystems (e.g. the sessions pipeline has 9+ interconnected objects across clusters). The validator checks that ecosystems are complete and that tables target appropriate node roles.

## Running tests

```bash
uv run python -m pytest posthog/clickhouse/test/test_reconcile.py -v
uv run python -m pytest posthog/clickhouse/test/test_advisory_lock.py -v
```
