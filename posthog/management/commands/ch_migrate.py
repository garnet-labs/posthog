# ruff: noqa: T201 allow print statements
import re
import sys
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from posthog.clickhouse.cluster import Query, get_cluster
from posthog.clickhouse.migration_tools.schema_introspect import detect_drift, dump_schema
from posthog.clickhouse.migration_tools.tracking import (
    acquire_apply_lock,
    get_infi_migration_status,
    get_migration_status_all_hosts,
    get_tracking_ddl,
    release_apply_lock,
)

MAX_MIGRATION_NUMBER = 99_999
MAX_DRIFT_DISPLAY = 10


def _any_client(cluster: Any) -> Any:
    return cluster.any_host(lambda c: c).result()


def _resolve_new_style_migration(target: int) -> tuple[dict | None, str]:
    """Look up a new-style migration by number. Returns (migration_dict, error_message)."""
    from posthog.clickhouse.migration_tools.runner import discover_migrations, is_new_style

    all_migrations = discover_migrations()
    target_mig = next((m for m in all_migrations if m["number"] == target), None)

    if target_mig is None:
        return None, f"Migration {target} not found."

    if target_mig["style"] != "new" or not is_new_style(target_mig["path"]):
        return None, f"Migration {target_mig['name']} is not a new-style migration."

    return target_mig, ""


class Command(BaseCommand):
    help = "ClickHouse migration management"

    def add_arguments(self, parser: Any) -> None:
        subparsers = parser.add_subparsers(dest="subcommand")
        subparsers.add_parser("bootstrap", help="Create tracking table on all nodes")
        subparsers.add_parser("check", help="Exit non-zero if unapplied new-style migrations exist")
        subparsers.add_parser("plan", help="Show pending migrations without executing")

        apply_parser = subparsers.add_parser("apply", help="Apply pending migrations")
        apply_parser.add_argument("--upto", type=int, default=MAX_MIGRATION_NUMBER)
        apply_parser.add_argument("--skip-mutation-check", action="store_true", default=False)
        apply_parser.add_argument("--force", action="store_true", default=False)
        apply_parser.add_argument(
            "--halt-on-drift",
            action="store_true",
            default=True,
            help="Check for schema drift between hosts before applying (default: on)",
        )
        apply_parser.add_argument(
            "--no-halt-on-drift",
            action="store_false",
            dest="halt_on_drift",
            help="Skip schema drift check before applying",
        )

        down_parser = subparsers.add_parser("down", help="Roll back a specific migration")
        down_parser.add_argument("migration_number", type=int)

        status_parser = subparsers.add_parser("status", help="Show per-host migration state")
        status_parser.add_argument("--node", type=str, default=None)

        validate_parser = subparsers.add_parser("validate", help="Static analysis validation of a migration")
        validate_parser.add_argument("migration_number", type=int)
        validate_parser.add_argument("--strict", action="store_true", default=False)

        trial_parser = subparsers.add_parser("trial", help="Sandbox validation: apply, verify, down, verify")
        trial_parser.add_argument("migration_number", type=int)

        generate_parser = subparsers.add_parser("generate", help="Generate a migration from a template")
        generate_parser.add_argument(
            "--template", type=str, required=True, help="Template type (e.g. ingestion_pipeline, add_column)"
        )
        generate_parser.add_argument("--table", type=str, default=None, help="Table name")
        generate_parser.add_argument(
            "--name", type=str, default=None, help="Migration name (auto-generated if omitted)"
        )
        generate_parser.add_argument("--cluster", type=str, default=None, help="Target cluster")

        lint_parser = subparsers.add_parser("lint", help="Lint SQL files with sqlfluff")
        lint_parser.add_argument("--fix", action="store_true", default=False, help="Auto-fix violations")
        lint_parser.add_argument("--path", type=str, default=None, help="Lint a specific migration directory")

        subparsers.add_parser("drift", help="Detect schema drift between cluster hosts")
        subparsers.add_parser("schema", help="Dump current schema state from ClickHouse")

        reconcile_parser = subparsers.add_parser("reconcile", help="Terraform-style desired-state reconciliation")
        reconcile_sub = reconcile_parser.add_subparsers(dest="reconcile_action")

        reconcile_plan = reconcile_sub.add_parser("plan", help="Diff desired vs current, show plan")
        reconcile_plan.add_argument(
            "--schema-dir",
            type=str,
            default="posthog/clickhouse/schema",
            help="Directory with desired-state YAML files",
        )

        reconcile_apply = reconcile_sub.add_parser("apply", help="Execute the reconciliation plan")
        reconcile_apply.add_argument(
            "--schema-dir",
            type=str,
            default="posthog/clickhouse/schema",
            help="Directory with desired-state YAML files",
        )
        reconcile_apply.add_argument("--force", action="store_true", default=False)

        reconcile_import = reconcile_sub.add_parser("import", help="Dump current schema to desired-state YAML")
        reconcile_import.add_argument(
            "--output-dir",
            type=str,
            default="posthog/clickhouse/schema",
            help="Output directory for YAML files",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        subcommand = options.get("subcommand")
        if subcommand == "bootstrap":
            self.handle_bootstrap()
        elif subcommand == "check":
            self.handle_check(options)
        elif subcommand == "plan":
            self.handle_plan()
        elif subcommand == "apply":
            self.handle_apply(options)
        elif subcommand == "status":
            self.handle_status(options)
        elif subcommand == "down":
            self.handle_down(options)
        elif subcommand == "validate":
            self.handle_validate(options)
        elif subcommand == "trial":
            self.handle_trial(options)
        elif subcommand == "generate":
            self.handle_generate(options)
        elif subcommand == "lint":
            self.handle_lint(options)
        elif subcommand == "drift":
            self.handle_drift()
        elif subcommand == "schema":
            self.handle_schema()
        elif subcommand == "reconcile":
            self.handle_reconcile(options)
        else:
            self.print_help("manage.py", "ch_migrate")

    def handle_bootstrap(self) -> None:
        database: str = settings.CLICKHOUSE_DATABASE
        ddl = get_tracking_ddl(database)
        cluster = get_cluster()

        print(f"Creating tracking table on all nodes (database={database})...")

        futures_map = cluster.map_all_hosts(Query(ddl))
        try:
            results = futures_map.result()
            for host_info in results:
                print(f"  OK: {host_info}")
            print("Bootstrap complete.")
        except ExceptionGroup as eg:
            for exc in eg.exceptions:
                print(f"  FAILED: {exc}")
            raise

    def handle_check(self, options: dict[str, Any]) -> None:
        from posthog.clickhouse.client.migration_tools import get_migrations_cluster
        from posthog.clickhouse.migration_tools.runner import get_pending_migrations

        database: str = settings.CLICKHOUSE_DATABASE
        cluster = get_migrations_cluster()

        pending = get_pending_migrations(
            client=_any_client(cluster),
            database=database,
        )

        # Only check new-style (directory-based) migrations — legacy .py
        # migrations are tracked in the infi clickhouseorm_migrations table,
        # not in our tracking table, so they always appear as "pending".
        pending = [m for m in pending if m["style"] == "new"]

        if pending:
            self.stderr.write(f"{len(pending)} unapplied new-style migration(s)")
            sys.exit(1)

        self.stdout.write("All new-style migrations applied.")

    def handle_plan(self) -> None:
        from posthog.clickhouse.client.migration_tools import get_migrations_cluster
        from posthog.clickhouse.migration_tools.new_style import NewStyleMigration
        from posthog.clickhouse.migration_tools.runner import get_pending_migrations, is_new_style

        database: str = settings.CLICKHOUSE_DATABASE
        cluster = get_migrations_cluster()

        pending = get_pending_migrations(
            client=_any_client(cluster),
            database=database,
        )

        if not pending:
            print("All migrations are up to date.")
            return

        print(f"Pending migrations ({len(pending)}):\n")
        for mig in pending:
            style_label = "new-style" if mig["style"] == "new" else "legacy .py"
            print(f"  [{style_label}] {mig['name']}")

            if mig["style"] == "new" and is_new_style(mig["path"]):
                try:
                    migration = NewStyleMigration(mig["path"])
                    steps = migration.get_steps()
                    for i, (step, rendered_sql) in enumerate(steps):
                        roles = ", ".join(step.node_roles)
                        flags = []
                        if step.sharded:
                            flags.append("sharded")
                        if step.is_alter_on_replicated_table:
                            flags.append("alter-replicated")
                        flag_str = f" ({', '.join(flags)})" if flags else ""
                        comment = f"  # {step.comment}" if step.comment else ""
                        print(f"    step {i}: {step.sql} -> [{roles}]{flag_str}{comment}")
                        for sql_line in rendered_sql.strip().splitlines():
                            print(f"      | {sql_line}")
                except Exception as exc:
                    print(f"    (error reading steps: {exc})")

        print(f"\nTotal: {len(pending)} pending migration(s).")

    def handle_apply(self, options: dict[str, Any]) -> None:
        import socket

        from posthog.clickhouse.client.migration_tools import get_migrations_cluster

        database: str = settings.CLICKHOUSE_DATABASE
        upto: int = options.get("upto", MAX_MIGRATION_NUMBER)
        skip_mutation_check: bool = options.get("skip_mutation_check", False)
        force: bool = options.get("force", False)
        halt_on_drift: bool = options.get("halt_on_drift", True)
        cluster = get_migrations_cluster()
        client = _any_client(cluster)
        hostname = socket.gethostname()

        # Pre-apply drift check
        if halt_on_drift and not force:
            print("Checking for schema drift before applying...")
            try:
                diffs = detect_drift(cluster, database)
                if diffs:
                    print(f"\nSchema drift detected between hosts ({len(diffs)} difference(s)):")
                    for diff in diffs[:MAX_DRIFT_DISPLAY]:
                        label = f"{diff.table}.{diff.column}" if diff.column else diff.table
                        print(f"  {diff.diff_type}: {label}")
                    if len(diffs) > MAX_DRIFT_DISPLAY:
                        print(f"  ... and {len(diffs) - MAX_DRIFT_DISPLAY} more")
                    print("\nRun 'ch_migrate drift' for details. Use --force to apply anyway.")
                    return
            except Exception as exc:
                print(f"Warning: drift check failed ({exc}), proceeding with apply...")

        acquired, reason = acquire_apply_lock(client, database, hostname, force=force)
        if not acquired:
            print(reason)
            return

        try:
            self._do_apply(cluster, client, database, upto, skip_mutation_check, force)
        finally:
            release_apply_lock(client, database, hostname)

    def _do_apply(
        self,
        cluster: Any,
        client: Any,
        database: str,
        upto: int,
        skip_mutation_check: bool,
        force: bool,
    ) -> None:
        from posthog.clickhouse.migration_tools.new_style import NewStyleMigration
        from posthog.clickhouse.migration_tools.runner import (
            check_active_mutations,
            get_pending_migrations,
            is_new_style,
            run_migration_up,
        )

        pending = get_pending_migrations(
            client=client,
            database=database,
        )

        pending = [m for m in pending if m["number"] <= upto]

        if not pending:
            print("All migrations are up to date.")
            return

        if not skip_mutation_check:
            tables_to_check: list[str] = []
            for mig in pending:
                if mig["style"] == "new" and is_new_style(mig["path"]):
                    try:
                        m = NewStyleMigration(mig["path"])
                        for step, _sql in m.get_steps():
                            if step.sharded or step.is_alter_on_replicated_table:
                                match = re.search(r"ALTER\s+TABLE\s+(\S+)", _sql, re.IGNORECASE)
                                if match:
                                    tables_to_check.append(match.group(1).split(".")[-1])
                    except Exception as exc:
                        self.stderr.write(f"Warning: could not read steps for {mig['name']}: {exc}")

            if tables_to_check:
                active = check_active_mutations(cluster, database, tables_to_check)
                if active and not force:
                    print("Active mutations found on target tables:")
                    for mut in active:
                        print(f"  table={mut.get('table')}, mutation_id={mut.get('mutation_id')}")
                    print("\nUse --force to apply anyway.")
                    return

        print(f"Applying {len(pending)} migration(s)...\n")

        for mig in pending:
            print(f"  Applying {mig['name']}...", end=" ", flush=True)

            if mig["style"] == "new" and is_new_style(mig["path"]):
                migration = NewStyleMigration(mig["path"])
                success = run_migration_up(
                    cluster=cluster,
                    migration=migration,
                    database=database,
                    migration_number=mig["number"],
                    migration_name=mig["name"],
                )
                if success:
                    print("OK")
                else:
                    print("FAILED")
                    print(f"\nMigration {mig['name']} failed. Halting.")
                    return
            else:
                print("(legacy, skipping — use migrate_clickhouse)")

        print("\nAll migrations applied successfully.")

    def handle_status(self, options: dict[str, Any]) -> None:
        database: str = settings.CLICKHOUSE_DATABASE
        cluster = get_cluster()
        node_filter: str | None = options.get("node")

        new_status = get_migration_status_all_hosts(cluster, database)
        infi_status = get_infi_migration_status(cluster, database)

        all_hosts = sorted(set(list(new_status.keys()) + list(infi_status.keys())))

        if node_filter:
            all_hosts = [h for h in all_hosts if h == node_filter]

        if not all_hosts:
            self.stdout.write("No migrations found on any host.\n")
            return

        for host in all_hosts:
            self.stdout.write(f"\n== {host} ==\n")

            infi_data = infi_status.get(host)
            if infi_data and infi_data.get("migrations"):
                self.stdout.write("  Legacy (infi) migrations:\n")
                for mig_name in infi_data["migrations"]:
                    self.stdout.write(f"    [applied] {mig_name}\n")
            else:
                self.stdout.write("  Legacy (infi) migrations: none\n")

            new_data = new_status.get(host)
            if new_data and new_data.get("migrations"):
                self.stdout.write("  New-style migrations:\n")
                for row in new_data["migrations"]:
                    if isinstance(row, (tuple, list)):
                        number, name, last_step, _host, direction, all_success = row
                        status_label = "applied" if all_success else "PARTIAL"
                        self.stdout.write(f"    [{status_label}] {name} (steps: {last_step + 1})\n")
                    else:
                        self.stdout.write(f"    {row}\n")
            else:
                self.stdout.write("  New-style migrations: none\n")

        self.stdout.write("\n")

    def handle_validate(self, options: dict[str, Any]) -> None:
        from posthog.clickhouse.migration_tools.validator import validate_migration

        target: int = options.get("migration_number")  # type: ignore[assignment]
        strict: bool = options.get("strict", False)

        target_mig, err = _resolve_new_style_migration(target)
        if target_mig is None:
            print(err)
            return

        print(f"Validating {target_mig['name']}...")
        results = validate_migration(target_mig["path"], strict=strict)

        if not results:
            print("  No issues found.")
            return

        has_errors = False
        for r in results:
            icon = "ERROR" if r.severity == "error" else "WARN"
            print(f"  [{icon}] ({r.rule}) {r.message}")
            if r.severity == "error":
                has_errors = True

        if has_errors:
            print(f"\nValidation FAILED for {target_mig['name']}.")
            raise SystemExit(1)
        else:
            print(f"\nValidation passed with warnings for {target_mig['name']}.")

    def handle_down(self, options: dict[str, Any]) -> None:
        from posthog.clickhouse.client.migration_tools import get_migrations_cluster
        from posthog.clickhouse.migration_tools.new_style import NewStyleMigration
        from posthog.clickhouse.migration_tools.runner import run_migration_down

        database: str = settings.CLICKHOUSE_DATABASE
        target: int = options.get("migration_number")  # type: ignore[assignment]
        cluster = get_migrations_cluster()

        target_mig, err = _resolve_new_style_migration(target)
        if target_mig is None:
            print(err)
            return

        migration = NewStyleMigration(target_mig["path"])

        if not migration.get_rollback_steps():
            print(f"Migration {target_mig['name']} has no rollback steps defined.")
            return

        print(f"Rolling back {target_mig['name']}...", end=" ", flush=True)

        success = run_migration_down(
            cluster=cluster,
            migration=migration,
            database=database,
            migration_number=target_mig["number"],
            migration_name=target_mig["name"],
        )

        if success:
            print("OK")
        else:
            print("FAILED")

    def handle_trial(self, options: dict[str, Any]) -> None:
        from posthog.clickhouse.client.migration_tools import get_migrations_cluster
        from posthog.clickhouse.migration_tools.new_style import NewStyleMigration
        from posthog.clickhouse.migration_tools.trial import run_trial

        database: str = settings.CLICKHOUSE_DATABASE
        target: int = options.get("migration_number")  # type: ignore[assignment]
        cluster = get_migrations_cluster()

        target_mig, err = _resolve_new_style_migration(target)
        if target_mig is None:
            print(err)
            return

        migration = NewStyleMigration(target_mig["path"])

        print(f"Running trial for {target_mig['name']}...")
        print("  Phase 1: APPLY...")

        success = run_trial(
            cluster=cluster,
            migration=migration,
            database=database,
            migration_number=target_mig["number"],
            migration_name=target_mig["name"],
        )

        if success:
            print("  Phase 2: DOWN... OK")
            print(f"\nTrial PASSED for {target_mig['name']}.")
        else:
            print(f"\nTrial FAILED for {target_mig['name']}.")

    def handle_lint(self, options: dict[str, Any]) -> None:
        import subprocess
        from pathlib import Path

        from posthog.clickhouse.migration_tools.runner import MIGRATIONS_DIR, discover_migrations

        fix = options.get("fix", False)
        target_path = options.get("path")
        action = "fix" if fix else "lint"

        if target_path:
            sql_files = list(Path(target_path).glob("*.sql"))
        else:
            migrations_dir = MIGRATIONS_DIR
            sql_files = []
            for mig in discover_migrations(migrations_dir):
                if mig["style"] == "new":
                    sql_files.extend(Path(mig["path"]).glob("*.sql"))

        if not sql_files:
            print("No SQL files to lint.")
            return

        has_violations = False
        for sql_file in sql_files:
            result = subprocess.run(
                ["sqlfluff", action, "--dialect", "clickhouse", str(sql_file)],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                print(result.stdout)
            if result.returncode != 0:
                has_violations = True

        if has_violations:
            print(f"\nsqlfluff {action}: violations found.")
            raise SystemExit(1)
        else:
            print(f"\nsqlfluff {action}: all files clean.")

    def handle_drift(self) -> None:
        database: str = settings.CLICKHOUSE_DATABASE
        cluster = get_cluster()

        print(f"Checking schema drift across cluster hosts (database={database})...")
        diffs = detect_drift(cluster, database)

        if not diffs:
            print("No schema drift detected. All hosts are in sync.")
            return

        print(f"\nSchema drift detected ({len(diffs)} difference(s)):\n")
        for diff in diffs:
            host_label = f" [{diff.host}]" if diff.host else ""
            if diff.column:
                print(f"  {diff.diff_type}: {diff.table}.{diff.column}{host_label}")
            else:
                print(f"  {diff.diff_type}: {diff.table}{host_label}")
            if diff.expected:
                print(f"    expected: {diff.expected}")
            if diff.actual:
                print(f"    actual:   {diff.actual}")

        sys.exit(1)

    def handle_schema(self) -> None:
        database: str = settings.CLICKHOUSE_DATABASE
        cluster = get_cluster()

        client = _any_client(cluster)
        schema = dump_schema(client, database)

        if not schema:
            print("No tables found.")
            return

        print(f"Schema for database '{database}' ({len(schema)} table(s)):\n")
        for table_name in sorted(schema.keys()):
            table = schema[table_name]
            print(f"  {table_name} (engine={table.engine})")
            if table.sorting_key:
                print(f"    ORDER BY {table.sorting_key}")
            if table.partition_key:
                print(f"    PARTITION BY {table.partition_key}")
            for col in table.columns:
                default_str = f" DEFAULT {col.default_expression}" if col.default_expression else ""
                print(f"    - {col.name}: {col.type}{default_str}")
            print()

    def handle_generate(self, options: dict[str, Any]) -> None:
        import yaml

        from posthog.clickhouse.migration_tools.runner import MIGRATIONS_DIR, discover_migrations
        from posthog.clickhouse.migration_tools.templates import MigrationTemplate

        template_name: str = options["template"]
        table: str | None = options.get("table")
        name: str | None = options.get("name")
        cluster: str | None = options.get("cluster")

        # Validate template
        valid_templates = [t.value for t in MigrationTemplate]
        if template_name not in valid_templates:
            print(f"Unknown template '{template_name}'. Valid templates: {', '.join(valid_templates)}")
            return

        # Determine next migration number
        existing = discover_migrations()
        next_number = max((m["number"] for m in existing), default=0) + 1

        # Generate migration name
        if not name:
            name = f"{template_name}_{table}" if table else template_name

        dir_name = f"{next_number:04d}_{name}"
        migration_dir = MIGRATIONS_DIR / dir_name

        if migration_dir.exists():
            print(f"Migration directory already exists: {migration_dir}")
            return

        migration_dir.mkdir(parents=True)

        # Build config based on template type
        config: dict[str, Any] = {}
        if table:
            config["table"] = table
        if cluster:
            config["cluster"] = cluster

        # Write scaffold config with example columns for table-creating templates
        if template_name in ("ingestion_pipeline", "sharded_table"):
            config.setdefault(
                "columns",
                [
                    {"name": "id", "type": "UUID"},
                    {"name": "team_id", "type": "Int64"},
                    {"name": "timestamp", "type": "DateTime64(6, 'UTC')"},
                ],
            )
            config.setdefault("order_by", ["team_id", "id"])
            if template_name == "ingestion_pipeline":
                config.setdefault("kafka_topic", f"clickhouse_{table or 'TOPIC'}")
                config.setdefault("kafka_group", f"{table or 'TABLE'}_consumer")
        elif template_name == "add_column":
            config.setdefault("ecosystem", table or "ECOSYSTEM_NAME")
            config.setdefault("column", {"name": "new_column", "type": "String"})
        elif template_name == "cross_cluster_readable":
            config.setdefault("source_table", table or "SOURCE_TABLE")
            config.setdefault("source_cluster", "main")
            config.setdefault("target_cluster", cluster or "TARGET_CLUSTER")

        # Write manifest.yaml
        manifest_data: dict[str, Any] = {
            "description": f"{template_name} for {table or name}",
            "template": template_name,
            "config": config,
        }
        if cluster:
            manifest_data["cluster"] = cluster

        manifest_path = migration_dir / "manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False)

        # Write __init__.py bridge
        init_path = migration_dir / "__init__.py"
        init_path.write_text(
            "from posthog.clickhouse.migration_tools.new_style import NewStyleMigration\n"
            "from pathlib import Path\n\n"
            "operations = []  # Handled by ch_migrate\n"
        )

        # Update max_migration.txt if it exists
        max_migration_path = MIGRATIONS_DIR / "max_migration.txt"
        if max_migration_path.exists():
            max_migration_path.write_text(str(next_number))

        print(f"Generated migration: {migration_dir}")
        print(f"  manifest.yaml: template={template_name}")
        print(f"\nEdit {manifest_path} to customize the config, then:")
        print(f"  python manage.py ch_migrate validate {next_number}")
        print(f"  python manage.py ch_migrate plan")

    def handle_reconcile(self, options: dict[str, Any]) -> None:
        action = options.get("reconcile_action")
        if action == "plan":
            self._reconcile_plan(options)
        elif action == "apply":
            self._reconcile_apply(options)
        elif action == "import":
            self._reconcile_import(options)
        else:
            print("Usage: ch_migrate reconcile {plan|apply|import}")

    def _compute_reconcile_diffs(
        self, client: Any, database: str, schema_dir: Any
    ) -> tuple[list, str | None]:
        """Compute desired-vs-current diffs. Returns (diffs, error_message)."""
        from posthog.clickhouse.migration_tools.desired_state import parse_desired_state_dir
        from posthog.clickhouse.migration_tools.state_diff import diff_state

        desired_states = parse_desired_state_dir(schema_dir)
        if not desired_states:
            return [], f"No YAML files found in {schema_dir}"

        current = dump_schema(client, database)

        all_diffs = []
        for desired in desired_states:
            ecosystem_current = {name: table for name, table in current.items() if name in desired.tables}
            diffs = diff_state(desired, ecosystem_current, database=database)
            all_diffs.extend(diffs)

        return all_diffs, None

    def _reconcile_plan(self, options: dict[str, Any]) -> None:
        from pathlib import Path

        from posthog.clickhouse.migration_tools.plan_generator import generate_plan_text

        database: str = settings.CLICKHOUSE_DATABASE
        cluster = get_cluster()
        schema_dir = Path(options.get("schema_dir", "posthog/clickhouse/schema"))

        if not schema_dir.exists():
            print(f"Schema directory not found: {schema_dir}")
            print("Run 'ch_migrate reconcile import' first to generate desired-state YAML files.")
            return

        client = _any_client(cluster)
        all_diffs, err = self._compute_reconcile_diffs(client, database, schema_dir)
        if err:
            print(err)
            return

        print(generate_plan_text(all_diffs))

    def _reconcile_apply(self, options: dict[str, Any]) -> None:
        import socket
        from pathlib import Path

        from posthog.clickhouse.client.migration_tools import get_migrations_cluster
        from posthog.clickhouse.migration_tools.plan_generator import generate_manifest_steps, generate_plan_text
        from posthog.clickhouse.migration_tools.runner import execute_migration_step
        from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock, release_apply_lock

        database: str = settings.CLICKHOUSE_DATABASE
        force: bool = options.get("force", False)
        schema_dir = Path(options.get("schema_dir", "posthog/clickhouse/schema"))

        if not schema_dir.exists():
            print(f"Schema directory not found: {schema_dir}")
            return

        cluster_obj = get_migrations_cluster()
        client = _any_client(cluster_obj)
        hostname = socket.gethostname()

        all_diffs, err = self._compute_reconcile_diffs(client, database, schema_dir)
        if err:
            print(err)
            return

        if not all_diffs:
            print("No changes. Infrastructure is up to date.")
            return

        print(generate_plan_text(all_diffs))
        print()

        acquired, reason = acquire_apply_lock(client, database, hostname, force=force)
        if not acquired:
            print(reason)
            return

        try:
            steps = generate_manifest_steps(all_diffs)
            print(f"Applying {len(steps)} step(s)...\n")

            for i, (step, rendered_sql) in enumerate(steps):
                print(f"  Step {i}: {step.comment}...", end=" ", flush=True)
                try:
                    execute_migration_step(cluster_obj, step, rendered_sql)
                    print("OK")
                except Exception as exc:
                    print(f"FAILED: {exc}")
                    print("\nReconciliation halted. Review the error and retry.")
                    return
        finally:
            release_apply_lock(client, database, hostname)

        print("\nReconciliation applied successfully.")

    def _reconcile_import(self, options: dict[str, Any]) -> None:
        from pathlib import Path

        import yaml as yaml_lib

        from posthog.clickhouse.migration_tools.schema_introspect import build_ecosystems_from_schema

        database: str = settings.CLICKHOUSE_DATABASE
        cluster_obj = get_cluster()
        output_dir = Path(options.get("output_dir", "posthog/clickhouse/schema"))

        client = _any_client(cluster_obj)
        current = dump_schema(client, database)

        if not current:
            print("No tables found in database.")
            return

        ecosystems = build_ecosystems_from_schema(current)

        output_dir.mkdir(parents=True, exist_ok=True)

        for eco in ecosystems:
            tables_data: dict[str, Any] = {}

            for table_name in sorted(eco.all_tables()):
                if table_name not in current:
                    continue
                table = current[table_name]
                table_data: dict[str, Any] = {"engine": table.engine}

                columns = []
                for col in table.columns:
                    col_data: dict[str, str] = {"name": col.name, "type": col.type}
                    if col.default_expression:
                        col_data["default_kind"] = col.default_kind
                        col_data["default_expression"] = col.default_expression
                    columns.append(col_data)

                table_data["columns"] = columns

                if table.sorting_key:
                    table_data["order_by"] = [k.strip() for k in table.sorting_key.split(",")]
                if table.partition_key:
                    table_data["partition_by"] = table.partition_key

                engine_lower = table.engine.lower()
                if "mergetree" in engine_lower:
                    table_data["on_nodes"] = "DATA"
                    if table_name == eco.sharded_table:
                        table_data["sharded"] = True
                elif engine_lower == "distributed":
                    table_data["on_nodes"] = "ALL"
                    table_data["source"] = eco.sharded_table
                elif engine_lower == "kafka":
                    table_data["on_nodes"] = "INGESTION_EVENTS"
                elif engine_lower == "materializedview":
                    table_data["on_nodes"] = "INGESTION_EVENTS"
                else:
                    table_data["on_nodes"] = "ALL"

                tables_data[table_name] = table_data

            if not tables_data:
                continue

            yaml_data = {
                "ecosystem": eco.base_name,
                "cluster": "main",
                "tables": tables_data,
            }

            output_path = output_dir / f"{eco.base_name}.yaml"
            with open(output_path, "w") as f:
                yaml_lib.dump(yaml_data, f, default_flow_style=False, sort_keys=False)

            print(f"  Exported: {output_path} ({len(tables_data)} table(s))")

        print(f"\nImported {len(ecosystems)} ecosystem(s) to {output_dir}/")
