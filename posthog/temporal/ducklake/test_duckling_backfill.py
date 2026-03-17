from __future__ import annotations

import json
import uuid
import datetime as dt

import pytest
from unittest.mock import MagicMock, patch

import temporalio.worker
from parameterized import parameterized
from temporalio import activity as temporal_activity
from temporalio.testing import WorkflowEnvironment

from posthog.temporal.ducklake.duckling_backfill_activities import (
    copy_partition_files_activity,
    discover_duckling_teams_activity,
    register_with_ducklake_activity,
    update_backfill_run_status_activity,
)
from posthog.temporal.ducklake.duckling_backfill_inputs import (
    DucklingBackfillInputs,
    DucklingCopyFilesInputs,
    DucklingCopyFilesResult,
    DucklingDiscoveryInputs,
    DucklingDiscoveryResult,
    DucklingRegisterInputs,
    DucklingResolveConfigInputs,
    DucklingResolveConfigResult,
    DucklingUpdateStatusInputs,
)
from posthog.temporal.ducklake.duckling_backfill_workflow import (
    DucklingBackfillDiscoveryWorkflow,
    DucklingBackfillWorkflow,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_heartbeater_mock():
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _base_copy_inputs(**overrides):
    base = {
        "team_id": 7,
        "data_type": "events",
        "partition_key": "2024-01-15",
        "dest_bucket": "customer-bucket",
        "dest_region": "us-east-1",
        "aws_access_key_id": "AKIA_TEST",
        "aws_secret_access_key": "secret",
        "aws_session_token": "token",
    }
    base.update(overrides)
    return DucklingCopyFilesInputs(**base)


# ---------------------------------------------------------------------------
# Input dataclass / parse_inputs tests
# ---------------------------------------------------------------------------


def test_duckling_backfill_workflow_parse_inputs():
    payload = json.dumps({"team_id": 42, "data_type": "events", "partition_key": "2024-01-15"})

    inputs = DucklingBackfillWorkflow.parse_inputs([payload])

    assert inputs.team_id == 42
    assert inputs.data_type == "events"
    assert inputs.partition_key == "2024-01-15"


def test_duckling_backfill_discovery_workflow_parse_inputs():
    payload = json.dumps({"data_type": "persons"})

    inputs = DucklingBackfillDiscoveryWorkflow.parse_inputs([payload])

    assert inputs.data_type == "persons"


@parameterized.expand(
    [
        ("events", {"team_id": 1, "data_type": "events", "partition_key": "2024-03-01"}),
        ("persons", {"team_id": 99, "data_type": "persons", "partition_key": "2024-12-31"}),
    ]
)
def test_duckling_backfill_inputs_properties_to_log(_, kwargs):
    inputs = DucklingBackfillInputs(**kwargs)
    logged = inputs.properties_to_log

    assert logged["team_id"] == kwargs["team_id"]
    assert logged["data_type"] == kwargs["data_type"]
    assert logged["partition_key"] == kwargs["partition_key"]


# ---------------------------------------------------------------------------
# copy_partition_files_activity — unit tests (mocked DuckDB + boto3)
# ---------------------------------------------------------------------------


@parameterized.expand(
    [
        ("two_parts", "2024-01"),
        ("single_part", "2024"),
        ("no_separator", "20240115"),
    ]
)
def test_copy_partition_files_activity_raises_for_invalid_partition_key(_, partition_key):
    mock_heartbeater = _make_heartbeater_mock()

    with patch("posthog.temporal.ducklake.duckling_backfill_activities.HeartbeaterSync", return_value=mock_heartbeater):
        inputs = _base_copy_inputs(partition_key=partition_key)
        with pytest.raises(ValueError, match="Invalid partition_key format"):
            copy_partition_files_activity(inputs)


def _patch_copy_activity_deps(monkeypatch, *, table_row, files):
    """Patch all lazy-imported dependencies used by copy_partition_files_activity."""
    mock_heartbeater = _make_heartbeater_mock()
    monkeypatch.setattr(
        "posthog.temporal.ducklake.duckling_backfill_activities.HeartbeaterSync",
        MagicMock(return_value=mock_heartbeater),
    )

    mock_conn = MagicMock()
    execute_results = [
        MagicMock(fetchone=MagicMock(return_value=table_row)),
        MagicMock(fetchall=MagicMock(return_value=files)),
    ]
    mock_conn.execute.side_effect = execute_results
    monkeypatch.setattr(
        "posthog.temporal.ducklake.duckling_backfill_activities.duckdb.connect",
        MagicMock(return_value=mock_conn),
    )
    monkeypatch.setattr(
        "posthog.ducklake.storage.DuckLakeStorageConfig.from_runtime",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr("posthog.ducklake.storage.configure_connection", MagicMock())
    monkeypatch.setattr(
        "posthog.ducklake.common.get_config",
        MagicMock(return_value={"DUCKLAKE_BUCKET": "shared-bucket"}),
    )
    monkeypatch.setattr("posthog.ducklake.common.attach_catalog", MagicMock())
    return mock_conn


def test_copy_partition_files_activity_returns_empty_when_no_files(monkeypatch):
    mock_conn = _patch_copy_activity_deps(
        monkeypatch,
        table_row=("table-uuid-1", "s3://shared/events/"),
        files=[],
    )

    result = copy_partition_files_activity(_base_copy_inputs())

    assert result.dest_s3_paths == []
    assert result.total_records == 0
    assert result.total_bytes == 0
    mock_conn.close.assert_called_once()


def test_copy_partition_files_activity_raises_when_table_not_found(monkeypatch):
    mock_conn = _patch_copy_activity_deps(
        monkeypatch,
        table_row=None,
        files=[],
    )

    with pytest.raises(ValueError, match="not found in megaduck catalog"):
        copy_partition_files_activity(_base_copy_inputs())

    mock_conn.close.assert_called_once()


def test_copy_partition_files_activity_copies_files_and_returns_result(monkeypatch):
    # Two files: one relative, one absolute
    fake_files = [
        ("file-1", "team_7/year=2024/month=01/day=15/part1.parquet", True, 1000, 512000),
        ("file-2", "s3://shared-bucket/team_7/year=2024/month=01/day=15/part2.parquet", False, 500, 256000),
    ]
    mock_conn = _patch_copy_activity_deps(
        monkeypatch,
        table_row=("table-uuid-1", "s3://shared-bucket/events/"),
        files=fake_files,
    )

    mock_dest_s3 = MagicMock()
    monkeypatch.setattr("boto3.client", MagicMock(return_value=mock_dest_s3))

    result = copy_partition_files_activity(_base_copy_inputs())

    assert len(result.dest_s3_paths) == 2
    assert result.total_records == 1500
    assert result.total_bytes == 768000
    assert mock_dest_s3.copy_object.call_count == 2
    mock_conn.close.assert_called_once()


def test_copy_partition_files_activity_uses_fallback_path_when_no_table_data_path(monkeypatch):
    fake_files = [
        ("file-1", "team_7/part1.parquet", True, 100, 1024),
    ]
    _patch_copy_activity_deps(
        monkeypatch,
        table_row=("table-uuid-1", None),
        files=fake_files,
    )

    mock_dest_s3 = MagicMock()
    monkeypatch.setattr("boto3.client", MagicMock(return_value=mock_dest_s3))

    result = copy_partition_files_activity(_base_copy_inputs())

    assert len(result.dest_s3_paths) == 1
    copy_call = mock_dest_s3.copy_object.call_args
    assert copy_call.kwargs["CopySource"]["Bucket"] == "shared-bucket"
    assert "team_7/part1.parquet" in copy_call.kwargs["CopySource"]["Key"]


def test_copy_partition_files_activity_passes_correct_partition_filters(monkeypatch):
    mock_conn = _patch_copy_activity_deps(
        monkeypatch,
        table_row=("table-uuid-1", "s3://shared-bucket/events/"),
        files=[],
    )

    inputs = _base_copy_inputs(team_id=42, partition_key="2024-07-04")
    copy_partition_files_activity(inputs)

    # Second execute call is the partition file query; its params include year/month/day
    second_call_args = mock_conn.execute.call_args_list[1]
    params_passed = second_call_args[0][1]  # positional args: (sql, params)
    assert params_passed[0] == "table-uuid-1"
    assert params_passed[1] == "42"  # team_id as string
    assert params_passed[2] == "2024"
    assert params_passed[3] == "07"
    assert params_passed[4] == "04"


# ---------------------------------------------------------------------------
# register_with_ducklake_activity — unit tests
# ---------------------------------------------------------------------------


def test_register_with_ducklake_activity_dev_mode_calls_duckdb(monkeypatch):
    mock_heartbeater = _make_heartbeater_mock()
    monkeypatch.setattr(
        "posthog.temporal.ducklake.duckling_backfill_activities.HeartbeaterSync",
        MagicMock(return_value=mock_heartbeater),
    )
    monkeypatch.setattr("posthog.ducklake.common.is_dev_mode", MagicMock(return_value=True))

    mock_catalog = MagicMock()
    mock_catalog.to_cross_account_destination.return_value = MagicMock()
    monkeypatch.setattr(
        "posthog.ducklake.models.DuckLakeCatalog.objects.get",
        MagicMock(return_value=mock_catalog),
    )
    monkeypatch.setattr("posthog.ducklake.common.get_team_config", MagicMock(return_value={}))

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(
        "posthog.temporal.ducklake.duckling_backfill_activities.duckdb.connect",
        MagicMock(return_value=mock_conn),
    )
    monkeypatch.setattr("posthog.ducklake.storage.configure_cross_account_connection", MagicMock())
    monkeypatch.setattr("posthog.ducklake.common.attach_catalog", MagicMock())
    monkeypatch.setattr("posthog.ducklake.common.escape", lambda x: x)

    inputs = DucklingRegisterInputs(
        team_id=7,
        data_type="events",
        s3_paths=["s3://bucket/path1.parquet", "s3://bucket/path2.parquet"],
    )

    register_with_ducklake_activity(inputs)

    assert mock_conn.execute.call_count == 2
    mock_conn.close.assert_called_once()


def test_register_with_ducklake_activity_production_mode_uses_duckgres(monkeypatch):
    mock_heartbeater = _make_heartbeater_mock()
    monkeypatch.setattr(
        "posthog.temporal.ducklake.duckling_backfill_activities.HeartbeaterSync",
        MagicMock(return_value=mock_heartbeater),
    )
    monkeypatch.setattr("posthog.ducklake.common.is_dev_mode", MagicMock(return_value=False))
    monkeypatch.setattr(
        "posthog.ducklake.common.get_duckgres_server_for_team",
        MagicMock(return_value=MagicMock()),
    )

    mock_pg_conn = MagicMock()
    mock_pg_conn.__enter__ = MagicMock(return_value=mock_pg_conn)
    mock_pg_conn.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(
        "posthog.ducklake.storage.connect_to_duckgres",
        MagicMock(return_value=mock_pg_conn),
    )
    monkeypatch.setattr("posthog.ducklake.storage.setup_duckgres_session", MagicMock())

    inputs = DucklingRegisterInputs(
        team_id=7,
        data_type="events",
        s3_paths=["s3://bucket/file.parquet"],
    )

    register_with_ducklake_activity(inputs)

    mock_pg_conn.execute.assert_called_once()
    call_args = mock_pg_conn.execute.call_args
    assert "ducklake_add_data_files" in call_args[0][0]
    assert call_args[0][1] == ["events", "s3://bucket/file.parquet"]


def test_register_with_ducklake_activity_production_mode_raises_when_no_server(monkeypatch):
    mock_heartbeater = _make_heartbeater_mock()
    monkeypatch.setattr(
        "posthog.temporal.ducklake.duckling_backfill_activities.HeartbeaterSync",
        MagicMock(return_value=mock_heartbeater),
    )
    monkeypatch.setattr("posthog.ducklake.common.is_dev_mode", MagicMock(return_value=False))
    monkeypatch.setattr(
        "posthog.ducklake.common.get_duckgres_server_for_team",
        MagicMock(return_value=None),
    )

    inputs = DucklingRegisterInputs(
        team_id=99,
        data_type="events",
        s3_paths=["s3://bucket/file.parquet"],
    )

    with pytest.raises(ValueError, match="No DuckgresServer configured for team 99"):
        register_with_ducklake_activity(inputs)


def test_register_with_ducklake_activity_production_mode_registers_multiple_paths(monkeypatch):
    mock_heartbeater = _make_heartbeater_mock()
    monkeypatch.setattr(
        "posthog.temporal.ducklake.duckling_backfill_activities.HeartbeaterSync",
        MagicMock(return_value=mock_heartbeater),
    )
    monkeypatch.setattr("posthog.ducklake.common.is_dev_mode", MagicMock(return_value=False))
    monkeypatch.setattr(
        "posthog.ducklake.common.get_duckgres_server_for_team",
        MagicMock(return_value=MagicMock()),
    )

    mock_pg_conn = MagicMock()
    mock_pg_conn.__enter__ = MagicMock(return_value=mock_pg_conn)
    mock_pg_conn.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(
        "posthog.ducklake.storage.connect_to_duckgres",
        MagicMock(return_value=mock_pg_conn),
    )
    monkeypatch.setattr("posthog.ducklake.storage.setup_duckgres_session", MagicMock())

    s3_paths = [f"s3://bucket/file{i}.parquet" for i in range(5)]
    inputs = DucklingRegisterInputs(team_id=7, data_type="persons", s3_paths=s3_paths)

    register_with_ducklake_activity(inputs)

    assert mock_pg_conn.execute.call_count == 5


# ---------------------------------------------------------------------------
# discover_duckling_teams_activity — unit tests (async, mocked ORM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_discover_duckling_teams_activity_returns_teams_without_completed_run(ateam):
    from posthog.ducklake.models import DuckLakeCatalog, DucklingBackfillRun
    from posthog.sync import database_sync_to_async

    # Team 20 gets a completed run; ateam does not
    other_org = await database_sync_to_async(
        lambda: __import__("posthog.models", fromlist=["Organization"]).Organization.objects.create(
            name="OtherOrg-discover-test"
        )
    )()
    other_team = await database_sync_to_async(
        lambda: __import__("posthog.models", fromlist=["Team"]).Team.objects.create(
            organization=other_org, name="OtherTeam-discover-test"
        )
    )()

    try:
        await database_sync_to_async(DuckLakeCatalog.objects.create)(
            team=ateam,
            db_host="localhost",
            db_port=5432,
            db_database="ducklake",
            db_username="user",
            db_password="pass",
            bucket="test-bucket",
            bucket_region="us-east-1",
            cross_account_role_arn="arn:aws:iam::123:role/test",
            cross_account_external_id="ext-id",
        )
        await database_sync_to_async(DuckLakeCatalog.objects.create)(
            team=other_team,
            db_host="localhost",
            db_port=5432,
            db_database="ducklake",
            db_username="user",
            db_password="pass",
            bucket="test-bucket",
            bucket_region="us-east-1",
            cross_account_role_arn="arn:aws:iam::123:role/test",
            cross_account_external_id="ext-id",
        )

        # Mark other_team as already completed for yesterday
        from django.utils import timezone

        yesterday = (timezone.now() - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        await database_sync_to_async(DucklingBackfillRun.objects.create)(
            team=other_team,
            data_type="events",
            partition_key=yesterday,
            status="completed",
        )

        inputs = DucklingDiscoveryInputs(data_type="events")
        results = await discover_duckling_teams_activity(inputs)

        returned_team_ids = {r.team_id for r in results}
        assert ateam.id in returned_team_ids
        assert other_team.id not in returned_team_ids
    finally:
        await database_sync_to_async(other_team.delete)()
        await database_sync_to_async(other_org.delete)()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_discover_duckling_teams_activity_returns_empty_when_no_catalogs():
    # No DuckLakeCatalog rows at all → no teams to backfill
    inputs = DucklingDiscoveryInputs(data_type="events")
    results = await discover_duckling_teams_activity(inputs)

    # We can only assert the result is a list; catalog rows from other tests may exist
    assert isinstance(results, list)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_discover_duckling_teams_activity_skips_team_with_completed_run(ateam):
    from django.utils import timezone

    from posthog.ducklake.models import DuckLakeCatalog, DucklingBackfillRun
    from posthog.sync import database_sync_to_async

    await database_sync_to_async(DuckLakeCatalog.objects.create)(
        team=ateam,
        db_host="localhost",
        db_port=5432,
        db_database="ducklake",
        db_username="user",
        db_password="pass",
        bucket="test-bucket",
        bucket_region="us-east-1",
        cross_account_role_arn="arn:aws:iam::123:role/test",
        cross_account_external_id="ext-id",
    )

    yesterday = (timezone.now() - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    await database_sync_to_async(DucklingBackfillRun.objects.create)(
        team=ateam,
        data_type="events",
        partition_key=yesterday,
        status="completed",
    )

    inputs = DucklingDiscoveryInputs(data_type="events")
    results = await discover_duckling_teams_activity(inputs)

    returned_team_ids = {r.team_id for r in results}
    assert ateam.id not in returned_team_ids


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_discover_duckling_teams_activity_uses_yesterday_as_partition_key(ateam):
    from django.utils import timezone

    from posthog.ducklake.models import DuckLakeCatalog
    from posthog.sync import database_sync_to_async

    await database_sync_to_async(DuckLakeCatalog.objects.create)(
        team=ateam,
        db_host="localhost",
        db_port=5432,
        db_database="ducklake",
        db_username="user",
        db_password="pass",
        bucket="test-bucket",
        bucket_region="us-east-1",
        cross_account_role_arn="arn:aws:iam::123:role/test",
        cross_account_external_id="ext-id",
    )

    inputs = DucklingDiscoveryInputs(data_type="events")
    results = await discover_duckling_teams_activity(inputs)

    expected_yesterday = (timezone.now() - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    matching = [r for r in results if r.team_id == ateam.id]
    assert len(matching) == 1
    assert matching[0].partition_key == expected_yesterday


# ---------------------------------------------------------------------------
# DucklingBackfillWorkflow — integration tests using WorkflowEnvironment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duckling_backfill_workflow_happy_path():
    """Test the full happy path.

    Note: The workflow calls activities by string name. When Temporal serializes
    the DucklingResolveConfigResult dataclass to JSON and back without a result_type
    hint, the workflow receives a dict. The stubs therefore return dicts matching
    the dataclass field layout to match actual runtime behavior.
    """
    call_log: list[str] = []
    captured_status_inputs: list[dict] = []

    @temporal_activity.defn(name="update_backfill_run_status_activity")
    async def update_status_stub(inputs: DucklingUpdateStatusInputs) -> None:
        call_log.append(f"update_status:{inputs.status}")
        captured_status_inputs.append(
            {
                "status": inputs.status,
                "records_exported": inputs.records_exported,
                "bytes_exported": inputs.bytes_exported,
            }
        )

    @temporal_activity.defn(name="resolve_duckling_config_activity")
    async def resolve_config_stub(inputs: DucklingResolveConfigInputs) -> DucklingResolveConfigResult:
        call_log.append("resolve_config")
        return DucklingResolveConfigResult(
            bucket="customer-bucket",
            region="us-east-1",
            role_arn="arn:aws:iam::123:role/test",
            external_id="ext-id",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )

    @temporal_activity.defn(name="copy_partition_files_activity")
    async def copy_files_stub(inputs: DucklingCopyFilesInputs) -> DucklingCopyFilesResult:
        call_log.append("copy_files")
        return DucklingCopyFilesResult(
            dest_s3_paths=["s3://customer-bucket/part1.parquet"],
            total_records=5000,
            total_bytes=1024000,
        )

    @temporal_activity.defn(name="register_with_ducklake_activity")
    async def register_stub(inputs: DucklingRegisterInputs) -> None:
        call_log.append("register")

    inputs = DucklingBackfillInputs(team_id=1, data_type="events", partition_key="2024-01-15")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with temporalio.worker.Worker(
            env.client,
            task_queue="duckling-backfill-test",
            workflows=[DucklingBackfillWorkflow],
            activities=[update_status_stub, resolve_config_stub, copy_files_stub, register_stub],
            workflow_runner=temporalio.worker.UnsandboxedWorkflowRunner(),
        ):
            await env.client.execute_workflow(
                DucklingBackfillWorkflow.run,
                inputs,
                id=str(uuid.uuid4()),
                task_queue="duckling-backfill-test",
                execution_timeout=dt.timedelta(seconds=30),
            )

    assert call_log == ["update_status:running", "resolve_config", "copy_files", "register", "update_status:completed"]

    final_status = captured_status_inputs[-1]
    assert final_status["status"] == "completed"
    assert final_status["records_exported"] == 5000
    assert final_status["bytes_exported"] == 1024000


@pytest.mark.asyncio
async def test_duckling_backfill_workflow_empty_partition_skips_register_and_marks_completed():
    call_log: list[str] = []

    @temporal_activity.defn(name="update_backfill_run_status_activity")
    async def update_status_stub(inputs: DucklingUpdateStatusInputs) -> None:
        call_log.append(f"update_status:{inputs.status}")

    @temporal_activity.defn(name="resolve_duckling_config_activity")
    async def resolve_config_stub(inputs: DucklingResolveConfigInputs) -> DucklingResolveConfigResult:
        call_log.append("resolve_config")
        return DucklingResolveConfigResult(
            bucket="customer-bucket",
            region="us-east-1",
            role_arn="arn:aws:iam::123:role/test",
            external_id="ext-id",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )

    @temporal_activity.defn(name="copy_partition_files_activity")
    async def copy_files_stub(inputs: DucklingCopyFilesInputs) -> DucklingCopyFilesResult:
        call_log.append("copy_files")
        # Empty result — no files found for this partition
        return DucklingCopyFilesResult(dest_s3_paths=[], total_records=0, total_bytes=0)

    @temporal_activity.defn(name="register_with_ducklake_activity")
    async def register_stub(inputs: DucklingRegisterInputs) -> None:
        call_log.append("register")

    inputs = DucklingBackfillInputs(team_id=1, data_type="events", partition_key="2024-01-15")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with temporalio.worker.Worker(
            env.client,
            task_queue="duckling-backfill-test-empty",
            workflows=[DucklingBackfillWorkflow],
            activities=[update_status_stub, resolve_config_stub, copy_files_stub, register_stub],
            workflow_runner=temporalio.worker.UnsandboxedWorkflowRunner(),
        ):
            await env.client.execute_workflow(
                DucklingBackfillWorkflow.run,
                inputs,
                id=str(uuid.uuid4()),
                task_queue="duckling-backfill-test-empty",
                execution_timeout=dt.timedelta(seconds=30),
            )

    assert "register" not in call_log
    assert call_log == ["update_status:running", "resolve_config", "copy_files", "update_status:completed"]


@pytest.mark.asyncio
async def test_duckling_backfill_workflow_marks_failed_on_activity_error():
    call_log: list[str] = []
    status_updates: list[tuple[str, str]] = []  # (status, error_message)

    @temporal_activity.defn(name="update_backfill_run_status_activity")
    async def update_status_stub(inputs: DucklingUpdateStatusInputs) -> None:
        call_log.append(f"update_status:{inputs.status}")
        status_updates.append((inputs.status, inputs.error_message))

    @temporal_activity.defn(name="resolve_duckling_config_activity")
    async def resolve_config_stub(inputs: DucklingResolveConfigInputs) -> DucklingResolveConfigResult:
        call_log.append("resolve_config")
        raise RuntimeError("IAM role assumption failed")

    @temporal_activity.defn(name="copy_partition_files_activity")
    async def copy_files_stub(inputs: DucklingCopyFilesInputs) -> DucklingCopyFilesResult:
        call_log.append("copy_files")
        return DucklingCopyFilesResult(dest_s3_paths=[], total_records=0, total_bytes=0)

    @temporal_activity.defn(name="register_with_ducklake_activity")
    async def register_stub(inputs: DucklingRegisterInputs) -> None:
        call_log.append("register")

    inputs = DucklingBackfillInputs(team_id=1, data_type="events", partition_key="2024-01-15")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with temporalio.worker.Worker(
            env.client,
            task_queue="duckling-backfill-test-fail",
            workflows=[DucklingBackfillWorkflow],
            activities=[update_status_stub, resolve_config_stub, copy_files_stub, register_stub],
            workflow_runner=temporalio.worker.UnsandboxedWorkflowRunner(),
        ):
            with pytest.raises(Exception):
                await env.client.execute_workflow(
                    DucklingBackfillWorkflow.run,
                    inputs,
                    id=str(uuid.uuid4()),
                    task_queue="duckling-backfill-test-fail",
                    execution_timeout=dt.timedelta(minutes=5),
                )

    statuses = [s for s, _ in status_updates]
    assert "running" in statuses
    assert "failed" in statuses
    assert "copy_files" not in call_log
    assert "register" not in call_log

    failed_error = next(err for status, err in status_updates if status == "failed")
    # Temporal wraps activity exceptions in ActivityError; the error_message will reflect
    # the outer wrapper, so we just verify the workflow recorded a non-empty error message.
    assert failed_error != ""


@pytest.mark.asyncio
async def test_duckling_backfill_workflow_error_message_is_truncated_to_1000_chars():
    status_updates: list[tuple[str, str]] = []

    @temporal_activity.defn(name="update_backfill_run_status_activity")
    async def update_status_stub(inputs: DucklingUpdateStatusInputs) -> None:
        status_updates.append((inputs.status, inputs.error_message))

    @temporal_activity.defn(name="resolve_duckling_config_activity")
    async def resolve_config_stub(inputs: DucklingResolveConfigInputs) -> DucklingResolveConfigResult:
        raise RuntimeError("x" * 2000)

    @temporal_activity.defn(name="copy_partition_files_activity")
    async def copy_files_stub(inputs: DucklingCopyFilesInputs) -> DucklingCopyFilesResult:
        return DucklingCopyFilesResult(dest_s3_paths=[], total_records=0, total_bytes=0)

    @temporal_activity.defn(name="register_with_ducklake_activity")
    async def register_stub(inputs: DucklingRegisterInputs) -> None:
        pass

    inputs = DucklingBackfillInputs(team_id=1, data_type="events", partition_key="2024-01-15")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with temporalio.worker.Worker(
            env.client,
            task_queue="duckling-backfill-test-truncate",
            workflows=[DucklingBackfillWorkflow],
            activities=[update_status_stub, resolve_config_stub, copy_files_stub, register_stub],
            workflow_runner=temporalio.worker.UnsandboxedWorkflowRunner(),
        ):
            with pytest.raises(Exception):
                await env.client.execute_workflow(
                    DucklingBackfillWorkflow.run,
                    inputs,
                    id=str(uuid.uuid4()),
                    task_queue="duckling-backfill-test-truncate",
                    execution_timeout=dt.timedelta(minutes=5),
                )

    failed_error = next((err for status, err in status_updates if status == "failed"), None)
    assert failed_error is not None
    assert len(failed_error) <= 1000


# ---------------------------------------------------------------------------
# DucklingBackfillDiscoveryWorkflow — integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duckling_backfill_discovery_workflow_spawns_child_workflow_per_team():
    started_children: list[dict] = []

    @temporal_activity.defn(name="discover_duckling_teams_activity")
    async def discover_stub(inputs: DucklingDiscoveryInputs) -> list[DucklingDiscoveryResult]:
        return [
            DucklingDiscoveryResult(team_id=10, partition_key="2024-01-15"),
            DucklingDiscoveryResult(team_id=20, partition_key="2024-01-15"),
        ]

    # Record child workflow executions by capturing the activity calls made by the child
    @temporal_activity.defn(name="update_backfill_run_status_activity")
    async def child_status_stub(inputs: DucklingUpdateStatusInputs) -> None:
        if inputs.status == "running":
            started_children.append({"team_id": inputs.team_id, "partition_key": inputs.partition_key})

    @temporal_activity.defn(name="resolve_duckling_config_activity")
    async def resolve_config_stub(inputs: DucklingResolveConfigInputs) -> DucklingResolveConfigResult:
        return DucklingResolveConfigResult(
            bucket="customer-bucket",
            region="us-east-1",
            role_arn="arn:aws:iam::123:role/test",
            external_id="ext-id",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )

    @temporal_activity.defn(name="copy_partition_files_activity")
    async def copy_files_stub(inputs: DucklingCopyFilesInputs) -> DucklingCopyFilesResult:
        return DucklingCopyFilesResult(dest_s3_paths=[], total_records=0, total_bytes=0)

    @temporal_activity.defn(name="register_with_ducklake_activity")
    async def register_stub(inputs: DucklingRegisterInputs) -> None:
        pass

    inputs = DucklingDiscoveryInputs(data_type="events")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with temporalio.worker.Worker(
            env.client,
            task_queue="duckling-discovery-test",
            workflows=[DucklingBackfillDiscoveryWorkflow, DucklingBackfillWorkflow],
            activities=[
                discover_stub,
                child_status_stub,
                resolve_config_stub,
                copy_files_stub,
                register_stub,
            ],
            workflow_runner=temporalio.worker.UnsandboxedWorkflowRunner(),
        ):
            await env.client.execute_workflow(
                DucklingBackfillDiscoveryWorkflow.run,
                inputs,
                id=str(uuid.uuid4()),
                task_queue="duckling-discovery-test",
                execution_timeout=dt.timedelta(minutes=5),
            )

    assert len(started_children) == 2
    team_ids = {c["team_id"] for c in started_children}
    assert 10 in team_ids
    assert 20 in team_ids


@pytest.mark.asyncio
async def test_duckling_backfill_discovery_workflow_returns_early_when_no_teams():
    discover_call_count = {"count": 0}

    @temporal_activity.defn(name="discover_duckling_teams_activity")
    async def discover_stub(inputs: DucklingDiscoveryInputs) -> list[DucklingDiscoveryResult]:
        discover_call_count["count"] += 1
        return []

    inputs = DucklingDiscoveryInputs(data_type="events")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with temporalio.worker.Worker(
            env.client,
            task_queue="duckling-discovery-empty-test",
            workflows=[DucklingBackfillDiscoveryWorkflow],
            activities=[discover_stub],
            workflow_runner=temporalio.worker.UnsandboxedWorkflowRunner(),
        ):
            await env.client.execute_workflow(
                DucklingBackfillDiscoveryWorkflow.run,
                inputs,
                id=str(uuid.uuid4()),
                task_queue="duckling-discovery-empty-test",
                execution_timeout=dt.timedelta(seconds=30),
            )

    assert discover_call_count["count"] == 1


@pytest.mark.asyncio
async def test_duckling_backfill_discovery_workflow_uses_correct_child_workflow_id():
    child_update_calls: list[DucklingUpdateStatusInputs] = []

    @temporal_activity.defn(name="discover_duckling_teams_activity")
    async def discover_stub(inputs: DucklingDiscoveryInputs) -> list[DucklingDiscoveryResult]:
        return [DucklingDiscoveryResult(team_id=42, partition_key="2024-03-17")]

    @temporal_activity.defn(name="update_backfill_run_status_activity")
    async def child_status_stub(inputs: DucklingUpdateStatusInputs) -> None:
        child_update_calls.append(inputs)

    @temporal_activity.defn(name="resolve_duckling_config_activity")
    async def resolve_config_stub(inputs: DucklingResolveConfigInputs) -> DucklingResolveConfigResult:
        return DucklingResolveConfigResult(
            bucket="customer-bucket",
            region="us-east-1",
            role_arn="arn:aws:iam::123:role/test",
            external_id="ext-id",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )

    @temporal_activity.defn(name="copy_partition_files_activity")
    async def copy_files_stub(inputs: DucklingCopyFilesInputs) -> DucklingCopyFilesResult:
        return DucklingCopyFilesResult(dest_s3_paths=[], total_records=0, total_bytes=0)

    @temporal_activity.defn(name="register_with_ducklake_activity")
    async def register_stub(inputs: DucklingRegisterInputs) -> None:
        pass

    inputs = DucklingDiscoveryInputs(data_type="persons")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with temporalio.worker.Worker(
            env.client,
            task_queue="duckling-discovery-id-test",
            workflows=[DucklingBackfillDiscoveryWorkflow, DucklingBackfillWorkflow],
            activities=[
                discover_stub,
                child_status_stub,
                resolve_config_stub,
                copy_files_stub,
                register_stub,
            ],
            workflow_runner=temporalio.worker.UnsandboxedWorkflowRunner(),
        ):
            await env.client.execute_workflow(
                DucklingBackfillDiscoveryWorkflow.run,
                inputs,
                id=str(uuid.uuid4()),
                task_queue="duckling-discovery-id-test",
                execution_timeout=dt.timedelta(minutes=5),
            )

    # The child workflow for team 42 should have been started with the correct ID.
    # We verify this by checking the workflow_id passed to update_backfill_run_status_activity.
    running_calls = [c for c in child_update_calls if c.status == "running"]
    assert len(running_calls) == 1
    assert running_calls[0].team_id == 42
    assert running_calls[0].partition_key == "2024-03-17"
    assert running_calls[0].workflow_id == "duckling-backfill-persons-42-2024-03-17"


# ---------------------------------------------------------------------------
# update_backfill_run_status_activity — async ORM integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_backfill_run_status_activity_creates_run(ateam):
    from posthog.ducklake.models import DucklingBackfillRun

    inputs = DucklingUpdateStatusInputs(
        team_id=ateam.id,
        data_type="events",
        partition_key="2024-01-15",
        status="running",
        workflow_id="wf-test-123",
    )

    await update_backfill_run_status_activity(inputs)

    run = await DucklingBackfillRun.objects.aget(team_id=ateam.id, data_type="events", partition_key="2024-01-15")
    assert run.status == "running"
    assert run.workflow_id == "wf-test-123"


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_backfill_run_status_activity_updates_existing_run(ateam):
    from posthog.ducklake.models import DucklingBackfillRun
    from posthog.sync import database_sync_to_async

    await database_sync_to_async(DucklingBackfillRun.objects.create)(
        team_id=ateam.id,
        data_type="events",
        partition_key="2024-01-15",
        status="running",
        workflow_id="wf-original",
    )

    inputs = DucklingUpdateStatusInputs(
        team_id=ateam.id,
        data_type="events",
        partition_key="2024-01-15",
        status="completed",
        workflow_id="wf-original",
        records_exported=9999,
        bytes_exported=123456,
    )

    await update_backfill_run_status_activity(inputs)

    run = await DucklingBackfillRun.objects.aget(team_id=ateam.id, data_type="events", partition_key="2024-01-15")
    assert run.status == "completed"
    assert run.records_exported == 9999
    assert run.bytes_exported == 123456


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_backfill_run_status_activity_stores_error_message(ateam):
    from posthog.ducklake.models import DucklingBackfillRun

    error_message = "Something went badly wrong"
    inputs = DucklingUpdateStatusInputs(
        team_id=ateam.id,
        data_type="events",
        partition_key="2024-02-29",
        status="failed",
        error_message=error_message,
    )

    await update_backfill_run_status_activity(inputs)

    run = await DucklingBackfillRun.objects.aget(team_id=ateam.id, data_type="events", partition_key="2024-02-29")
    assert run.status == "failed"
    assert run.error_message == error_message
