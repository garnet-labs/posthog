"""Tests for deprecation warnings and ch_migrate --check flag.

Pattern 1: unittest.TestCase — no Django, no ClickHouse connection.
Runs standalone via ``PYTHONPATH=. python posthog/clickhouse/test/test_deprecation.py``.
"""

from __future__ import annotations

import warnings
from io import StringIO
from pathlib import Path

import unittest
from unittest.mock import MagicMock

import posthog.clickhouse.test._stubs  # noqa: F401

# ---------------------------------------------------------------------------
# run_sql_with_exceptions deprecation warning
# ---------------------------------------------------------------------------


class TestRunSqlWithExceptionsDeprecation(unittest.TestCase):
    def test_run_sql_with_exceptions_emits_deprecation(self) -> None:
        from posthog.clickhouse.client.migration_tools import run_sql_with_exceptions

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            run_sql_with_exceptions("SELECT 1")
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            self.assertGreaterEqual(len(deprecation_warnings), 1)

    def test_deprecation_message_references_readme(self) -> None:
        from posthog.clickhouse.client.migration_tools import run_sql_with_exceptions

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            run_sql_with_exceptions("SELECT 1")
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            self.assertGreaterEqual(len(deprecation_warnings), 1)
            self.assertIn("manifest.yaml", str(deprecation_warnings[0].message))


# ---------------------------------------------------------------------------
# ch_migrate check subcommand
# ---------------------------------------------------------------------------


class TestChMigrateCheck(unittest.TestCase):
    def test_check_command_exits_zero_when_no_pending(self) -> None:
        from unittest.mock import patch

        from posthog.management.commands.ch_migrate import Command

        mock_cluster = MagicMock()
        mock_cluster.any_host.return_value.result.return_value = MagicMock()

        with (
            patch("posthog.clickhouse.client.migration_tools.get_migrations_cluster", return_value=mock_cluster),
            patch("posthog.clickhouse.migration_tools.runner.get_pending_migrations", return_value=[]),
        ):
            cmd = Command()
            cmd.stdout = StringIO()  # type: ignore[assignment]
            cmd.stderr = StringIO()  # type: ignore[assignment]

            cmd.handle_check({})

            output = cmd.stdout.getvalue()
            self.assertIn("All new-style migrations applied", output)

    def test_check_command_exits_nonzero_when_pending(self) -> None:
        from unittest.mock import patch

        from posthog.management.commands.ch_migrate import Command

        mock_cluster = MagicMock()
        mock_cluster.any_host.return_value.result.return_value = MagicMock()

        pending = [
            {"number": 1, "name": "0001_test", "style": "new", "path": Path("/tmp/fake")},
            {"number": 2, "name": "0002_test", "style": "new", "path": Path("/tmp/fake2")},
        ]

        with (
            patch("posthog.clickhouse.client.migration_tools.get_migrations_cluster", return_value=mock_cluster),
            patch("posthog.clickhouse.migration_tools.runner.get_pending_migrations", return_value=pending),
        ):
            cmd = Command()
            cmd.stdout = StringIO()  # type: ignore[assignment]
            cmd.stderr = StringIO()  # type: ignore[assignment]

            with self.assertRaises(SystemExit) as ctx:
                cmd.handle_check({})

            self.assertEqual(ctx.exception.code, 1)

            error_output = cmd.stderr.getvalue()
            self.assertIn("2 unapplied new-style migration(s)", error_output)


if __name__ == "__main__":
    unittest.main()
