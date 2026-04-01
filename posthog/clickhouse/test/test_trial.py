"""Unit tests for the ClickHouse migration trial runner.

Tests run_trial with mocked ClickhouseCluster — no Django or ClickHouse
connection required.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import posthog.clickhouse.test._stubs  # noqa: F401
from posthog.clickhouse.migration_tools.trial import run_trial


class TestRunTrial(unittest.TestCase):
    """Tests for trial.run_trial."""

    def _make_migration(self) -> MagicMock:
        """Create a mock migration object."""
        mock = MagicMock()
        mock.get_steps.return_value = []
        mock.get_rollback_steps.return_value = []
        mock.manifest = MagicMock()
        return mock

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_up_then_down(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """Trial runs up, then down, in order."""
        pre_schema = [("t", "col1", "UInt64")]
        post_up_schema = [("t", "col1", "UInt64"), ("t", "col2", "String")]

        mock_schema.side_effect = [pre_schema, post_up_schema, pre_schema]
        mock_up.return_value = True
        mock_down.return_value = True

        cluster = MagicMock()
        result = run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        self.assertTrue(result)
        mock_up.assert_called_once()
        mock_down.assert_called_once()
        # Verify up was called with dry_run=True, then down with dry_run=True
        self.assertTrue(mock_up.call_args.kwargs.get("dry_run"))
        self.assertTrue(mock_down.call_args.kwargs.get("dry_run"))

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_verify_after_up(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """After up, _query_schema is called to verify schema changed."""
        pre_schema = [("t", "col1", "UInt64")]
        post_up_schema = [("t", "col1", "UInt64"), ("t", "col2", "String")]

        mock_schema.side_effect = [pre_schema, post_up_schema, pre_schema]
        mock_up.return_value = True
        mock_down.return_value = True

        cluster = MagicMock()
        run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        # _query_schema called 3 times: pre, post-up, post-down
        self.assertEqual(mock_schema.call_count, 3)

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_verify_after_down(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """After down, _query_schema is called to verify schema restored."""
        pre_schema = [("t", "col1", "UInt64")]
        post_up_schema = [("t", "col1", "UInt64"), ("t", "col2", "String")]
        # Schema NOT restored — should fail
        post_down_schema = [("t", "col1", "UInt64"), ("t", "col2", "String")]

        mock_schema.side_effect = [pre_schema, post_up_schema, post_down_schema]
        mock_up.return_value = True
        mock_down.return_value = True

        cluster = MagicMock()
        result = run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        self.assertFalse(result)
        self.assertEqual(mock_schema.call_count, 3)

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_fails_if_up_fails(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """If up fails, trial returns False and does NOT run down."""
        pre_schema = [("t", "col1", "UInt64")]
        mock_schema.return_value = pre_schema
        mock_up.return_value = False

        cluster = MagicMock()
        result = run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        self.assertFalse(result)
        mock_up.assert_called_once()
        mock_down.assert_not_called()

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_fails_if_verify_fails_still_rolls_back(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """If post-up verification fails (schema unchanged), trial fails
        and does not attempt rollback since up was a no-op."""
        pre_schema = [("t", "col1", "UInt64")]
        # Schema unchanged after up — verification failure
        mock_schema.side_effect = [pre_schema, pre_schema]
        mock_up.return_value = True

        cluster = MagicMock()
        result = run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        self.assertFalse(result)
        # Down should NOT be called since up was a no-op
        mock_down.assert_not_called()


if __name__ == "__main__":
    unittest.main()
