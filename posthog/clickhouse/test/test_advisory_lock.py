"""Unit tests for advisory locking in tracking.py.

Tests acquire_apply_lock and release_apply_lock with mocked ClickHouse
client — no Django or ClickHouse connection required.
"""

from __future__ import annotations

from datetime import UTC, datetime

import unittest
from unittest.mock import MagicMock

import posthog.clickhouse.test._stubs  # noqa: F401
from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock, release_apply_lock


class TestAdvisoryLock(unittest.TestCase):
    """Tests for the advisory lock mechanism."""

    def test_advisory_lock_prevents_concurrent_apply(self) -> None:
        """An active lock from another host prevents acquisition."""
        client = MagicMock()
        now = datetime.now(tz=UTC)
        # Simulate existing lock from a different host
        client.execute.side_effect = [
            # First call: check for existing lock — returns a row
            [("other-pod", now)],
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertFalse(acquired)
        self.assertIn("other-pod", reason)
        self.assertIn("--force", reason)

    def test_advisory_lock_expired_allows_apply(self) -> None:
        """No active lock (expired or absent) allows acquisition."""
        client = MagicMock()
        # First call: check for existing lock — returns empty (no active lock)
        # Second call: INSERT lock row
        client.execute.side_effect = [
            [],  # No active lock
            None,  # INSERT succeeds
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")
        # Should have called execute twice: SELECT check + INSERT lock
        self.assertEqual(client.execute.call_count, 2)

    def test_advisory_lock_same_host_allows_reacquire(self) -> None:
        """A lock from the same host allows re-acquisition (idempotent)."""
        client = MagicMock()
        now = datetime.now(tz=UTC)
        # Lock exists but from same host
        client.execute.side_effect = [
            [("my-pod", now)],  # Existing lock from same host
            None,  # INSERT lock row
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")

    def test_advisory_lock_force_overrides_other_host(self) -> None:
        """force=True acquires even when another host holds the lock."""
        client = MagicMock()
        # No SELECT should happen — force skips the check entirely.
        client.execute.side_effect = [
            None,  # INSERT lock row
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod", force=True)

        self.assertTrue(acquired)
        self.assertEqual(reason, "")
        # Only one call: the INSERT. No SELECT check.
        self.assertEqual(client.execute.call_count, 1)

    def test_release_apply_lock_inserts_shadow_row(self) -> None:
        """Release inserts a success=False row to shadow the lock."""
        client = MagicMock()
        client.execute.return_value = None

        release_apply_lock(client, "default", "my-pod")

        # Should have inserted a row (via record_step which calls client.execute)
        client.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
