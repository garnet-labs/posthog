"""Tests for advisory locking. No Django or ClickHouse required."""

from __future__ import annotations

from datetime import UTC, datetime

import unittest
from unittest.mock import MagicMock

import posthog.clickhouse.test._stubs  # noqa: F401
from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock, release_apply_lock


class TestAdvisoryLock(unittest.TestCase):
    def test_advisory_lock_prevents_concurrent_apply(self) -> None:
        """An active lock from another host prevents acquisition."""
        client = MagicMock()
        now = datetime.now(tz=UTC)
        # Atomic pattern: ensure table, INSERT...SELECT WHERE NOT EXISTS, verify SELECT
        client.execute.side_effect = [
            None,  # CREATE TABLE IF NOT EXISTS (ensure tracking table)
            None,  # INSERT...SELECT WHERE NOT EXISTS (atomic — no rows inserted due to existing lock)
            [("other-pod", now)],  # Verify SELECT — another host holds the lock
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertFalse(acquired)
        self.assertIn("other-pod", reason)
        self.assertIn("--force", reason)

    def test_advisory_lock_expired_allows_apply(self) -> None:
        """No active lock (expired or absent) allows acquisition."""
        client = MagicMock()
        now = datetime.now(tz=UTC)
        client.execute.side_effect = [
            None,  # CREATE TABLE IF NOT EXISTS (ensure tracking table)
            None,  # INSERT...SELECT WHERE NOT EXISTS (atomic — row inserted)
            [("my-pod", now)],  # Verify SELECT — our lock is latest
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")
        # Three calls: CREATE IF NOT EXISTS + INSERT...SELECT + verify SELECT
        self.assertEqual(client.execute.call_count, 3)

    def test_advisory_lock_same_host_allows_reacquire(self) -> None:
        """A lock from the same host allows re-acquisition (idempotent)."""
        client = MagicMock()
        now = datetime.now(tz=UTC)
        client.execute.side_effect = [
            None,  # CREATE TABLE IF NOT EXISTS (ensure tracking table)
            None,  # INSERT...SELECT WHERE NOT EXISTS (atomic)
            [("my-pod", now)],  # Verify SELECT — our own host holds the lock
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")

    def test_advisory_lock_force_overrides_other_host(self) -> None:
        """force=True acquires even when another host holds the lock."""
        client = MagicMock()
        client.execute.side_effect = [
            None,  # CREATE TABLE IF NOT EXISTS (ensure tracking table)
            None,  # INSERT lock row directly (no atomic check with force=True)
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod", force=True)

        self.assertTrue(acquired)
        self.assertEqual(reason, "")
        # Two calls: CREATE IF NOT EXISTS + INSERT (via record_step). No verify needed.
        self.assertEqual(client.execute.call_count, 2)

    def test_release_apply_lock_inserts_shadow_row(self) -> None:
        """Release inserts a success=False row to shadow the lock."""
        client = MagicMock()
        client.execute.return_value = None

        release_apply_lock(client, "default", "my-pod")

        # Should have inserted a row (via record_step which calls client.execute)
        client.execute.assert_called_once()

    def test_after_release_another_host_can_acquire(self) -> None:
        """After the lock holder releases, a different host must be able to acquire."""
        # After host-A releases, the acquire query excludes host-A from the blocking check
        # because host-A now has a success=0,direction='down' release row.
        # Simulate: host-B acquires, finds NO active lock (verify SELECT returns host-B's own row).
        client = MagicMock()
        now = datetime.now(tz=UTC)
        client.execute.side_effect = [
            None,  # CREATE TABLE IF NOT EXISTS
            None,  # INSERT...SELECT WHERE NOT EXISTS (row inserted — no active un-released lock)
            [("host-b", now)],  # Verify SELECT — host-B holds the lock
        ]

        acquired, reason = acquire_apply_lock(client, "default", "host-b")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")
        # Verify the acquire SQL contains the NOT IN subquery that checks for releases
        acquire_call = client.execute.call_args_list[1]
        sql_arg = acquire_call[0][0]
        self.assertIn("host NOT IN", sql_arg)
        self.assertIn("direction = 'down'", sql_arg)


if __name__ == "__main__":
    unittest.main()
