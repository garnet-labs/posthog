import os
import re
import sys
import logging

from django.core.management.base import BaseCommand, CommandError

from git import Repo

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = "posthog/clickhouse/migrations"
MAX_MIGRATION_FILE = os.path.join(MIGRATIONS_DIR, "max_migration.txt")

# Pre-existing duplicate migration numbers to ignore.
# DO NOT ADD NEW ENTRIES - fix the duplicate instead!
IGNORED_DUPLICATE_MIGRATION_NUMBERS = frozenset(
    [
        "0029",
        "0050",
        "0054",
        "0055",
        "0064",
        "0072",
        "0073",
        "0083",
    ]
)


def get_all_migrations() -> list[tuple[str, str]]:
    """Get all migrations as (index, name) tuples.

    Matches both .py files (0001_name.py) and directories (0220_name/).
    """
    migrations: list[tuple[str, str]] = []
    for filename in os.listdir(MIGRATIONS_DIR):
        # Match .py files: 0001_name.py
        match = re.match(r"([0-9]+)_([a-zA-Z_0-9]+)\.py", filename)
        if match:
            groups = match.groups()
            migrations.append((groups[0], groups[1]))
            continue
        # Match directories: 0220_name/ (must contain manifest.yaml to count)
        dir_match = re.match(r"([0-9]+)_([a-zA-Z_0-9]+)$", filename)
        if dir_match:
            dir_path = os.path.join(MIGRATIONS_DIR, filename)
            if os.path.isdir(dir_path) and os.path.exists(os.path.join(dir_path, "manifest.yaml")):
                groups = dir_match.groups()
                migrations.append((groups[0], groups[1]))
    return sorted(migrations, key=lambda x: (int(x[0]), x[1]))


def check_no_duplicate_migration_numbers() -> bool:
    """Check for duplicate migration numbers (excluding known legacy duplicates)."""
    seen: dict[str, list[str]] = {}
    for index, name in get_all_migrations():
        seen.setdefault(index, []).append(name)

    duplicates = {
        idx: names for idx, names in seen.items() if len(names) > 1 and idx not in IGNORED_DUPLICATE_MIGRATION_NUMBERS
    }

    if duplicates:
        for index, names in sorted(duplicates.items()):
            logger.error(f"Duplicate migration {index}: {', '.join(f'{index}_{n}' for n in names)}")
        return False
    return True


def check_max_migration_file() -> bool:
    """Check that max_migration.txt matches the highest numbered migration."""
    migrations = get_all_migrations()
    if not migrations:
        return True

    max_migration = max(migrations, key=lambda x: (int(x[0]), x[1]))
    expected = f"{max_migration[0]}_{max_migration[1]}"

    if not os.path.exists(MAX_MIGRATION_FILE):
        logger.error("max_migration.txt not found")
        return False

    with open(MAX_MIGRATION_FILE) as f:
        actual = f.read().strip()

    if actual != expected:
        logger.error(f"max_migration.txt outdated: has '{actual}', expected '{expected}'")
        return False
    return True


class Command(BaseCommand):
    help = "Automated test to make sure ClickHouse migrations are safe"

    def handle(self, *args, **options):
        if not check_no_duplicate_migration_numbers() or not check_max_migration_file():
            sys.exit(1)

        if sys.stdin.isatty():
            logger.warning("Not running migration-specific checks. See .github/workflows/ci-backend.yml for usage.")
            return

        raw_paths = [m.strip() for m in sys.stdin.readlines() if m.strip()]

        # Extract unique migration identifiers from file paths.
        # Paths may be:
        #   posthog/clickhouse/migrations/0123_name.py          (old-style .py file)
        #   posthog/clickhouse/migrations/0222_name/up.sql      (new-style directory contents)
        #   posthog/clickhouse/migrations/runner.py             (library file, not a migration)
        migration_paths: dict[str, str] = {}  # migration_id -> representative path
        for path in raw_paths:
            # Old-style: .py file directly under migrations/
            m = re.match(r".*/clickhouse/migrations/([0-9]+_[a-zA-Z_0-9]+)\.py$", path)
            if m:
                mid = m.group(1)
                migration_paths.setdefault(mid, path)
                continue
            # New-style: file inside a numbered directory
            m = re.match(r".*/clickhouse/migrations/([0-9]+_[a-zA-Z_0-9]+)/", path)
            if m:
                mid = m.group(1)
                migration_paths.setdefault(mid, path)
                continue
            # Library file (runner.py, manifest.py, etc.) — skip silently

        migrations = list(migration_paths.values())

        if len(migrations) > 1:
            logger.error(
                "Multiple migrations in PR (%s). Please limit to one migration per PR.",
                ", ".join(migration_paths.keys()),
            )
            sys.exit(1)

        if not migrations:
            logger.info("No migrations to check.")
            return

        for new_migration in migrations:
            logger.info("Checking new migration %s", new_migration)
            self._check_migration_against_master(new_migration)

    @staticmethod
    def _check_migration_against_master(new_migration: str) -> None:
        """Check that new migration number doesn't conflict with migrations on master."""
        repo = Repo(os.getcwd())

        try:
            original_ref = repo.active_branch.name
        except TypeError:
            original_ref = repo.head.commit.hexsha

        try:
            repo.git.checkout("master")
            master_migrations = os.listdir(MIGRATIONS_DIR)
        finally:
            repo.git.checkout(original_ref)

        old_migrations = []
        for filename in master_migrations:
            # Match .py files
            match = re.findall(r"([0-9]+)_([a-zA-Z_0-9]+)\.py", filename)
            if match:
                old_migrations.append(match[0])
                continue
            # Match directories
            dir_match = re.findall(r"^([0-9]+)_([a-zA-Z_0-9]+)$", filename)
            if dir_match:
                old_migrations.append(dir_match[0])

        try:
            # Try .py file pattern first
            matches = re.findall(r"([a-z]+)/clickhouse/migrations/([0-9]+)_([a-zA-Z_0-9]+)\.py", new_migration)
            if not matches:
                # Try directory pattern: path may be the directory itself or a file inside it
                matches = re.findall(r"([a-z]+)/clickhouse/migrations/([0-9]+)_([a-zA-Z_0-9]+)(?:/|$)", new_migration)
            _, index, name = matches[0]
        except (IndexError, CommandError) as exc:
            logger.warning("Could not parse migration path '%s': %s", new_migration, exc)
            return

        collisions = [f"{idx}_{n}" for idx, n in old_migrations if idx == index]
        if collisions:
            logger.error(f"Migration {index}_{name} conflicts with master: {', '.join(collisions)}")
            sys.exit(1)
