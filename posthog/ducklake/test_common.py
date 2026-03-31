import pytest
from unittest.mock import MagicMock, patch

import duckdb

from posthog.ducklake.common import _drop_and_recreate_catalog, initialize_ducklake

TEST_CONFIG = {
    "DUCKLAKE_RDS_HOST": "localhost",
    "DUCKLAKE_RDS_PORT": "5432",
    "DUCKLAKE_RDS_DATABASE": "ducklake",
    "DUCKLAKE_RDS_USERNAME": "posthog",
    "DUCKLAKE_RDS_PASSWORD": "posthog",
    "DUCKLAKE_BUCKET": "ducklake-dev",
    "DUCKLAKE_BUCKET_REGION": "us-east-1",
    "DUCKLAKE_S3_ACCESS_KEY": "",
    "DUCKLAKE_S3_SECRET_KEY": "",
}


@patch.dict("os.environ", {}, clear=True)
@patch("posthog.ducklake.common.psycopg")
@patch("posthog.ducklake.common.is_dev_mode", return_value=True)
def test_drop_and_recreate_catalog_fails_closed_without_env_flag(
    _mock_dev: MagicMock,
    mock_psycopg: MagicMock,
) -> None:
    with pytest.raises(RuntimeError, match="POSTHOG_ALLOW_DUCKLAKE_CATALOG_RESET=1"):
        _drop_and_recreate_catalog(TEST_CONFIG)

    mock_psycopg.connect.assert_not_called()


@patch.dict("os.environ", {"POSTHOG_ALLOW_DUCKLAKE_CATALOG_RESET": "1"}, clear=True)
@patch("posthog.ducklake.common._read_catalog_version", return_value="0.3")
@patch("posthog.ducklake.common._drop_and_recreate_catalog")
@patch("posthog.ducklake.common.run_smoke_check")
@patch("posthog.ducklake.common.ensure_ducklake_catalog")
@patch("posthog.ducklake.common.duckdb")
@patch("posthog.ducklake.common.is_dev_mode", return_value=True)
def test_initialize_ducklake_resets_only_when_env_flag_is_enabled(
    _mock_dev: MagicMock,
    mock_duckdb: MagicMock,
    mock_ensure_catalog: MagicMock,
    mock_smoke_check: MagicMock,
    mock_drop_and_recreate: MagicMock,
    _mock_read_catalog_version: MagicMock,
) -> None:
    initial_conn = MagicMock()
    recreated_conn = MagicMock()
    mock_duckdb.connect.side_effect = [initial_conn, recreated_conn]
    mock_duckdb.NotImplementedException = duckdb.NotImplementedException
    mock_duckdb.CatalogException = duckdb.CatalogException

    def attach_side_effect(conn: MagicMock, config: dict[str, str], alias: str = "ducklake") -> None:
        if conn is initial_conn:
            raise duckdb.NotImplementedException("catalog version mismatch")

    with patch("posthog.ducklake.common.attach_catalog", side_effect=attach_side_effect):
        assert initialize_ducklake(TEST_CONFIG) is True

    mock_drop_and_recreate.assert_called_once_with(TEST_CONFIG)
    assert mock_ensure_catalog.call_count == 2
    mock_smoke_check.assert_called_once_with(recreated_conn, alias="ducklake")
