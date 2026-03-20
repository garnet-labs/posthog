# ruff: noqa: T201 allow print statements
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

MIGRATIONS_DIR = Path("posthog/clickhouse/migrations")
TEMPLATES_DIR = Path("posthog/clickhouse/migrations/templates")

VALID_TYPES = ("add-column", "new-table", "add-mv")

INIT_PY_CONTENT = """\
# Auto-generated for migrate_clickhouse compatibility. See manifest.yaml.
from infi.clickhouse_orm import migrations  # type: ignore

operations = []
"""

UP_SQL_HEADER = """\
-- TODO: Write your SQL here.
-- Use section markers (-- :section <name>) for multi-step migrations.
"""

DOWN_SQL_HEADER = """\
-- TODO: Write rollback SQL here.
"""


def _read_max_migration(migrations_dir: Path) -> tuple[int, str]:
    """Read max_migration.txt and return (number, full_name)."""
    max_file = migrations_dir / "max_migration.txt"
    if not max_file.exists():
        return 0, ""
    content = max_file.read_text().strip()
    match = re.match(r"^(\d+)_(.+)$", content)
    if match:
        return int(match.group(1)), content
    return 0, content


def _format_number(num: int) -> str:
    return f"{num:04d}"


def _load_template(migration_type: str, table: str, templates_dir: Path = TEMPLATES_DIR) -> str:
    """Load a YAML template and fill in the table name."""
    type_to_file = {
        "add-column": "add_column.yaml",
        "new-table": "new_table.yaml",
        "add-mv": "add_mv.yaml",
    }
    template_file = templates_dir / type_to_file[migration_type]
    content = template_file.read_text()
    return content.replace("{table}", table)


def create_migration(
    *,
    name: str,
    migration_type: str,
    table: str,
    migrations_dir: Path = MIGRATIONS_DIR,
    templates_dir: Path = TEMPLATES_DIR,
) -> Path:
    """Create a directory-based migration. Returns the created directory path."""
    if migration_type not in VALID_TYPES:
        raise ValueError(f"Invalid type '{migration_type}'. Valid types: {VALID_TYPES}")

    current_number, _ = _read_max_migration(migrations_dir)
    next_number = current_number + 1
    dir_name = f"{_format_number(next_number)}_{name}"
    mig_dir = migrations_dir / dir_name

    mig_dir.mkdir(parents=True, exist_ok=False)

    # manifest.yaml from template
    manifest_content = _load_template(migration_type, table, templates_dir)
    (mig_dir / "manifest.yaml").write_text(manifest_content)

    # up.sql
    (mig_dir / "up.sql").write_text(UP_SQL_HEADER)

    # down.sql
    (mig_dir / "down.sql").write_text(DOWN_SQL_HEADER)

    # __init__.py for infi compatibility
    (mig_dir / "__init__.py").write_text(INIT_PY_CONTENT)

    # Update max_migration.txt
    max_file = migrations_dir / "max_migration.txt"
    max_file.write_text(dir_name + "\n")

    return mig_dir


if TYPE_CHECKING:
    pass


class Command:
    """Django management command wrapper. Imported lazily to avoid Django dep in tests."""

    help = "Create a new ClickHouse migration"

    def add_arguments(self, parser: object) -> None:
        parser.add_argument("--name", type=str, required=True, help="Migration name (snake_case)")  # type: ignore[union-attr]
        parser.add_argument(  # type: ignore[union-attr]
            "--type",
            type=str,
            choices=VALID_TYPES,
            default="add-column",
            help="Migration type: add-column, new-table, add-mv",
        )
        parser.add_argument("--table", type=str, default="TODO_table_name", help="Target table name")  # type: ignore[union-attr]

    def handle(self, *args: object, **options: object) -> None:
        name: str = options["name"]  # type: ignore[index]
        migration_type: str = options.get("type", "add-column")  # type: ignore[assignment]
        table: str = options.get("table", "TODO_table_name")  # type: ignore[assignment]

        mig_dir = create_migration(
            name=name,
            migration_type=migration_type,
            table=table,
        )
        print(f"Created migration: {mig_dir}")
        print("  Files: manifest.yaml, up.sql, down.sql, __init__.py")
        print("  Next steps:")
        print("    1. Edit manifest.yaml — fill in TODO placeholders")
        print("    2. Write SQL in up.sql (use section markers for multi-step)")
        print("    3. Write rollback SQL in down.sql")


# Re-export for Django management command discovery
try:
    from django.core.management.base import BaseCommand

    class Command(BaseCommand):  # type: ignore[no-redef]
        help = "Create a new ClickHouse migration"

        def add_arguments(self, parser: object) -> None:
            parser.add_argument("--name", type=str, required=True, help="Migration name (snake_case)")  # type: ignore[union-attr]
            parser.add_argument(  # type: ignore[union-attr]
                "--type",
                type=str,
                choices=VALID_TYPES,
                default="add-column",
                help="Migration type: add-column, new-table, add-mv",
            )
            parser.add_argument("--table", type=str, default="TODO_table_name", help="Target table name")  # type: ignore[union-attr]

        def handle(self, *args: object, **options: object) -> None:
            name: str = options["name"]  # type: ignore[index]
            migration_type: str = options.get("type", "add-column")  # type: ignore[assignment]
            table: str = options.get("table", "TODO_table_name")  # type: ignore[assignment]

            mig_dir = create_migration(
                name=name,
                migration_type=migration_type,
                table=table,
            )
            self.stdout.write(f"Created migration: {mig_dir}")
            self.stdout.write("  Files: manifest.yaml, up.sql, down.sql, __init__.py")

except ImportError:
    pass
