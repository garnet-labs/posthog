"""StateDiff -> human-readable plan + ManifestStep list + rollback steps."""

from __future__ import annotations

from posthog.clickhouse.migration_tools.manifest import ManifestStep
from posthog.clickhouse.migration_tools.state_diff import StateDiff

# Map action to plan symbol
_ACTION_SYMBOL: dict[str, str] = {
    "create": "+",
    "drop": "-",
    "alter_add_column": "~",
    "alter_drop_column": "-",
    "alter_modify_column": "~",
    "recreate_mv": "-/+",
    "recreate": "-/+",
}


def generate_plan_text(diffs: list[StateDiff]) -> str:
    if not diffs:
        return "No changes. Infrastructure is up to date."

    lines: list[str] = ["ch_migrate plan:\n"]

    creates = 0
    destroys = 0
    modifies = 0

    for diff in diffs:
        symbol = _ACTION_SYMBOL.get(diff.action, "?")
        if diff.action == "alter_modify_column":
            lines.append(
                f"  \u26a0 {diff.table:40s} ({diff.detail} \u2014 rewrites data, may take hours on large tables)"
            )
        else:
            lines.append(f"  {symbol} {diff.table:40s} ({diff.detail})")

        if diff.action == "create":
            creates += 1
        elif diff.action == "drop":
            destroys += 1
        elif diff.action in ("recreate", "recreate_mv"):
            destroys += 1
            creates += 1
        else:
            modifies += 1

    parts = []
    if modifies:
        parts.append(f"{modifies} to modify")
    if destroys:
        parts.append(f"{destroys} to destroy")
    if creates:
        parts.append(f"{creates} to create")

    lines.append(f"\nPlan: {', '.join(parts)}.")
    return "\n".join(lines)


def generate_manifest_steps(diffs: list[StateDiff]) -> list[tuple[ManifestStep, str]]:
    steps: list[tuple[ManifestStep, str]] = []

    for diff in diffs:
        if diff.action in ("recreate", "recreate_mv"):
            # Split into DROP + CREATE
            sql_parts = diff.sql.split(";\n", 1)
            if len(sql_parts) == 2:
                drop_sql, create_sql = sql_parts
                steps.append(
                    (
                        ManifestStep(
                            sql=f"_reconcile:drop_{diff.table}",
                            node_roles=diff.node_roles,
                            comment=f"Drop {diff.table} for recreation",
                            sharded=diff.sharded,
                        ),
                        drop_sql,
                    )
                )
                steps.append(
                    (
                        ManifestStep(
                            sql=f"_reconcile:create_{diff.table}",
                            node_roles=diff.node_roles,
                            comment=f"Recreate {diff.table}",
                            sharded=diff.sharded,
                        ),
                        create_sql,
                    )
                )
            else:
                steps.append(
                    (
                        ManifestStep(
                            sql=f"_reconcile:{diff.action}_{diff.table}",
                            node_roles=diff.node_roles,
                            comment=diff.detail,
                            sharded=diff.sharded,
                        ),
                        diff.sql,
                    )
                )
        else:
            steps.append(
                (
                    ManifestStep(
                        sql=f"_reconcile:{diff.action}_{diff.table}",
                        node_roles=diff.node_roles,
                        comment=diff.detail,
                        sharded=diff.sharded,
                        is_alter_on_replicated_table=diff.is_alter_on_replicated_table,
                    ),
                    diff.sql,
                )
            )

    return steps


def generate_rollback_steps(diffs: list[StateDiff]) -> list[tuple[ManifestStep, str]]:
    """Only create and alter_add_column are auto-reversible; everything else loses data."""
    steps: list[tuple[ManifestStep, str]] = []

    for diff in reversed(diffs):
        if diff.action == "create":
            steps.append(
                (
                    ManifestStep(
                        sql=f"_reconcile:rollback_drop_{diff.table}",
                        node_roles=diff.node_roles,
                        comment=f"Rollback: drop created table {diff.table}",
                        sharded=diff.sharded,
                    ),
                    f"DROP TABLE IF EXISTS {diff.table}",
                )
            )
        elif diff.action == "alter_add_column":
            # Extract column name from the ADD COLUMN SQL
            col_name = _extract_column_name_from_add(diff.sql)
            if col_name:
                db_table = diff.sql.split("ALTER TABLE ", 1)[1].split(" ADD", 1)[0]
                steps.append(
                    (
                        ManifestStep(
                            sql=f"_reconcile:rollback_drop_col_{diff.table}_{col_name}",
                            node_roles=diff.node_roles,
                            comment=f"Rollback: drop added column {col_name} from {diff.table}",
                            sharded=diff.sharded,
                            is_alter_on_replicated_table=diff.is_alter_on_replicated_table,
                        ),
                        f"ALTER TABLE {db_table} DROP COLUMN IF EXISTS {col_name}",
                    )
                )

    return steps


def _extract_column_name_from_add(sql: str) -> str | None:
    upper = sql.upper()
    marker = "ADD COLUMN"
    idx = upper.find(marker)
    if idx == -1:
        return None
    remainder = sql[idx + len(marker) :].strip()
    if remainder.upper().startswith("IF NOT EXISTS "):
        remainder = remainder[len("IF NOT EXISTS ") :].strip()
    return remainder.split()[0] if remainder.split() else None
