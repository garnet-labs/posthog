"""Run all database migrations in a single Django process.

Combines migrate, apply_persons_migrations, and migrate_clickhouse into one
command to avoid three separate Django cold starts (~15s each). Used by the
sandbox entrypoint to speed up boot time.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run all migrations (Django, persons, ClickHouse) in a single process"

    def handle(self, *args, **options):
        self.stdout.write("Running Django migrations...")
        call_command("migrate", "--noinput")

        self.stdout.write("Running persons migrations...")
        call_command("apply_persons_migrations", "--database=persons_db_writer", "--ensure-database")

        self.stdout.write("Running ClickHouse migrations...")
        call_command("migrate_clickhouse")

        self.stdout.write(self.style.SUCCESS("All migrations complete."))
