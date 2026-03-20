# ruff: noqa: T201 allow print statements

from django.conf import settings
from django.core.management.base import BaseCommand

from posthog.clickhouse.cluster import Query, get_cluster
from posthog.clickhouse.migrations.tracking import get_tracking_ddl


class Command(BaseCommand):
    help = "ClickHouse migration management"

    def add_arguments(self, parser: object) -> None:
        subparsers = parser.add_subparsers(dest="subcommand")  # type: ignore[union-attr]
        subparsers.add_parser("bootstrap", help="Create tracking table on all nodes")
        subparsers.add_parser("plan", help="Show pending migrations without executing")

        up_parser = subparsers.add_parser("up", help="Apply pending migrations")
        up_parser.add_argument(
            "--upto",
            type=int,
            default=99_999,
            help="Apply migrations up to this number (inclusive).",
        )

    def handle(self, *args: object, **options: object) -> None:
        subcommand = options.get("subcommand")
        if subcommand == "bootstrap":
            self.handle_bootstrap()
        elif subcommand == "plan":
            self.handle_plan()
        elif subcommand == "up":
            self.handle_up(options)
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

    def handle_plan(self) -> None:
        from posthog.clickhouse.client.migration_tools import get_migrations_cluster
        from posthog.clickhouse.migrations.new_style import NewStyleMigration
        from posthog.clickhouse.migrations.runner import get_pending_migrations, is_new_style

        database: str = settings.CLICKHOUSE_DATABASE
        cluster = get_migrations_cluster()

        def _get_client_for_query(client):  # type: ignore[no-untyped-def]
            return client

        pending = get_pending_migrations(
            client=cluster.any_host(_get_client_for_query).result(),
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
                    for i, (step, _rendered_sql) in enumerate(steps):
                        roles = ", ".join(step.node_roles)
                        flags = []
                        if step.sharded:
                            flags.append("sharded")
                        if step.is_alter_on_replicated_table:
                            flags.append("alter-replicated")
                        flag_str = f" ({', '.join(flags)})" if flags else ""
                        print(f"    step {i}: {step.sql} -> [{roles}]{flag_str}")
                except Exception as exc:
                    print(f"    (error reading steps: {exc})")

        print(f"\nTotal: {len(pending)} pending migration(s).")

    def handle_up(self, options: object) -> None:
        from posthog.clickhouse.client.migration_tools import get_migrations_cluster
        from posthog.clickhouse.migrations.new_style import NewStyleMigration
        from posthog.clickhouse.migrations.runner import get_pending_migrations, is_new_style, run_migration_up

        database: str = settings.CLICKHOUSE_DATABASE
        upto: int = options.get("upto", 99_999)  # type: ignore[union-attr]
        cluster = get_migrations_cluster()

        def _get_client_for_query(client):  # type: ignore[no-untyped-def]
            return client

        pending = get_pending_migrations(
            client=cluster.any_host(_get_client_for_query).result(),
            database=database,
        )

        pending = [m for m in pending if m["number"] <= upto]

        if not pending:
            print("All migrations are up to date.")
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
                # Legacy .py migration: delegate to the existing infi runner
                print("(legacy, skipping — use migrate_clickhouse)")

        print("\nAll migrations applied successfully.")
