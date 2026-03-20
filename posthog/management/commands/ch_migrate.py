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

    def handle(self, *args: object, **options: object) -> None:
        subcommand = options.get("subcommand")
        if subcommand == "bootstrap":
            self.handle_bootstrap()
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
