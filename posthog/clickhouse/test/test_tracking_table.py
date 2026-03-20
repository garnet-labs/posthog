import re
import hashlib

import pytest
from unittest.mock import MagicMock

from posthog.clickhouse.migrations.tracking import (
    TRACKING_TABLE_DDL,
    TRACKING_TABLE_NAME,
    get_applied_migrations,
    get_tracking_ddl,
    record_step,
)

try:
    from posthog.clickhouse.cluster import Query  # noqa: F401

    HAS_CLUSTER = True
except ImportError:
    HAS_CLUSTER = False

if HAS_CLUSTER:
    from posthog.clickhouse.migrations.tracking import get_migration_status_all_hosts

try:
    from posthog.management.commands.ch_migrate import Command as ChMigrateCommand

    HAS_DJANGO = True
except ImportError:
    HAS_DJANGO = False


class TestTrackingDDL:
    def test_tracking_ddl_is_valid_sql(self) -> None:
        ddl = get_tracking_ddl("test_db")
        assert len(ddl) > 0
        assert ddl.strip().startswith("CREATE TABLE IF NOT EXISTS")

    def test_tracking_ddl_uses_mergetree(self) -> None:
        assert "MergeTree()" in TRACKING_TABLE_DDL
        assert "ReplicatedMergeTree" not in TRACKING_TABLE_DDL

    def test_tracking_ddl_has_required_columns(self) -> None:
        required_columns = [
            "migration_number",
            "step_index",
            "host",
            "node_role",
            "direction",
            "checksum",
            "applied_at",
            "success",
        ]
        for col in required_columns:
            assert col in TRACKING_TABLE_DDL, f"Missing column: {col}"

    def test_get_tracking_ddl_substitutes_database(self) -> None:
        ddl = get_tracking_ddl("my_database")
        assert "my_database.clickhouse_schema_migrations" in ddl
        assert "{database}" not in ddl


class TestRecordStep:
    def test_record_step_inserts_row(self) -> None:
        client = MagicMock()
        record_step(
            client=client,
            migration_number=1,
            migration_name="0001_initial",
            step_index=0,
            host="localhost",
            node_role="data",
            direction="up",
            checksum="abc123",
            success=True,
        )
        client.execute.assert_called_once()
        sql = client.execute.call_args[0][0]
        assert "INSERT INTO" in sql
        assert TRACKING_TABLE_NAME in sql

    def test_record_step_checksum_is_sha256(self) -> None:
        sha256_pattern = re.compile(r"^[a-f0-9]{64}$")
        checksum = hashlib.sha256(b"test data").hexdigest()
        assert sha256_pattern.match(checksum)

        client = MagicMock()
        record_step(
            client=client,
            migration_number=1,
            migration_name="0001_initial",
            step_index=0,
            host="localhost",
            node_role="data",
            direction="up",
            checksum=checksum,
            success=True,
        )
        client.execute.assert_called_once()
        params = client.execute.call_args[0][1]
        assert any(checksum in str(v) for v in (params if isinstance(params, (list, tuple, dict)) else [params]))


class TestGetAppliedMigrations:
    def test_get_applied_migrations_query(self) -> None:
        client = MagicMock()
        client.execute.return_value = []
        get_applied_migrations(client, "test_db")
        client.execute.assert_called_once()
        sql = client.execute.call_args[0][0]
        assert "SELECT" in sql
        assert TRACKING_TABLE_NAME in sql


@pytest.mark.skipif(not HAS_CLUSTER, reason="Requires dagster/cluster imports")
class TestGetMigrationStatusAllHosts:
    def test_get_migration_status_all_hosts_returns_dict(self) -> None:
        cluster = MagicMock()
        mock_futures_map = MagicMock()
        mock_futures_map.result.return_value = {}
        cluster.map_all_hosts.return_value = mock_futures_map
        result = get_migration_status_all_hosts(cluster, "test_db")
        assert isinstance(result, dict)


@pytest.mark.skipif(not HAS_DJANGO, reason="Requires Django")
class TestBootstrapCommand:
    def test_bootstrap_command_exists(self) -> None:
        cmd = ChMigrateCommand()
        assert cmd is not None

    def test_bootstrap_command_help(self) -> None:
        cmd = ChMigrateCommand()
        assert "ClickHouse" in cmd.help or "clickhouse" in cmd.help.lower()
