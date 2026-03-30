import uuid
from datetime import UTC, datetime

import pytest
from unittest.mock import MagicMock, patch

from posthog.temporal.data_imports.cdc.activities import (
    CDCExtractInput,
    _flush_deferred_runs,
    _get_pg_connection_params,
    cdc_extract_activity,
)
from posthog.temporal.data_imports.cdc.types import ChangeEvent


def _make_event(
    op: str = "I",
    table: str = "users",
    position: str = "0/100",
    columns: dict | None = None,
) -> ChangeEvent:
    return ChangeEvent(
        operation=op,
        table_name=table,
        position_serialized=position,
        timestamp=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        columns=columns or {"id": 1, "name": "Alice"},
    )


def _make_source(source_id=None, job_inputs=None):
    source = MagicMock()
    source.id = source_id or uuid.uuid4()
    source.team_id = 1
    source.job_inputs = (
        job_inputs
        if job_inputs is not None
        else {
            "host": "localhost",
            "port": 5432,
            "database": "testdb",
            "user": "test",
            "password": "test",
            "cdc_slot_name": "posthog_slot",
            "cdc_publication_name": "posthog_pub",
        }
    )
    return source


def _make_schema(name, cdc_mode="streaming", source=None, schema_id=None):
    schema = MagicMock()
    schema.id = schema_id or uuid.uuid4()
    schema.name = name
    schema.team_id = 1
    schema.source = source
    schema.sync_type = "cdc"
    schema.sync_type_config = {"cdc_mode": cdc_mode}
    schema.is_cdc = True
    schema.cdc_mode = cdc_mode
    schema.should_sync = True
    schema.deleted = False
    schema.save = MagicMock()
    return schema


class TestGetPgConnectionParams:
    def test_extracts_params_from_job_inputs(self):
        source = _make_source()
        params = _get_pg_connection_params(source)

        assert params.host == "localhost"
        assert params.port == 5432
        assert params.database == "testdb"
        assert params.user == "test"
        assert params.password == "test"
        assert params.slot_name == "posthog_slot"
        assert params.publication_name == "posthog_pub"

    def test_defaults_when_missing(self):
        source = _make_source(job_inputs={})
        params = _get_pg_connection_params(source)

        assert params.host == ""
        assert params.port == 5432
        assert params.sslmode == "prefer"
        assert params.slot_name == ""


class TestFlushDeferredRuns:
    @patch("posthog.temporal.data_imports.cdc.activities.KafkaBatchProducer")
    def test_sends_kafka_messages_for_deferred_runs(self, MockProducer):
        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer

        source = _make_source()
        schema = _make_schema("users", cdc_mode="streaming", source=source)
        schema.sync_type_config["cdc_deferred_runs"] = [
            {
                "job_id": "job-1",
                "run_uuid": "run-1",
                "data_folder": "s3://bucket/data/",
                "schema_path": "s3://bucket/schema.json",
                "total_batches": 1,
                "total_rows": 10,
                "batch_results": [
                    {
                        "s3_path": "s3://bucket/data/part-0000.parquet",
                        "row_count": 10,
                        "byte_size": 1024,
                        "batch_index": 0,
                        "timestamp_ns": 123456789,
                    }
                ],
            }
        ]

        log = MagicMock()
        _flush_deferred_runs(schema, source, log)

        mock_producer.send_batch_notification.assert_called_once()
        mock_producer.flush.assert_called_once()

        assert schema.sync_type_config["cdc_deferred_runs"] == []
        schema.save.assert_called()

    @patch("posthog.temporal.data_imports.cdc.activities.KafkaBatchProducer")
    def test_no_op_when_no_deferred_runs(self, MockProducer):
        source = _make_source()
        schema = _make_schema("users", cdc_mode="streaming", source=source)
        schema.sync_type_config = {"cdc_mode": "streaming"}

        log = MagicMock()
        _flush_deferred_runs(schema, source, log)

        MockProducer.assert_not_called()
        schema.save.assert_not_called()

    @patch("posthog.temporal.data_imports.cdc.activities.KafkaBatchProducer")
    def test_multiple_deferred_runs(self, MockProducer):
        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer

        source = _make_source()
        schema = _make_schema("users", cdc_mode="streaming", source=source)
        schema.sync_type_config["cdc_deferred_runs"] = [
            {
                "job_id": f"job-{i}",
                "run_uuid": f"run-{i}",
                "data_folder": f"s3://bucket/data-{i}/",
                "schema_path": f"s3://bucket/schema-{i}.json",
                "total_batches": 1,
                "total_rows": 5,
                "batch_results": [
                    {
                        "s3_path": f"s3://bucket/data-{i}/part-0000.parquet",
                        "row_count": 5,
                        "byte_size": 512,
                        "batch_index": 0,
                    }
                ],
            }
            for i in range(3)
        ]

        log = MagicMock()
        _flush_deferred_runs(schema, source, log)

        # 3 deferred runs, each with 1 batch → 3 send calls, 3 flush calls (one per producer)
        assert mock_producer.send_batch_notification.call_count == 3
        assert mock_producer.flush.call_count == 3
        assert schema.sync_type_config["cdc_deferred_runs"] == []


class TestCDCExtractActivity:
    """Integration tests for cdc_extract_activity with mocked external deps."""

    @patch("posthog.temporal.data_imports.cdc.activities.activity")
    @patch("posthog.temporal.data_imports.cdc.activities.KafkaBatchProducer")
    @patch("posthog.temporal.data_imports.cdc.activities.S3BatchWriter")
    @patch("posthog.temporal.data_imports.cdc.activities.PgCDCStreamReader")
    @patch("posthog.temporal.data_imports.cdc.activities._get_cdc_schemas")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataSource")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataJob")
    @patch("posthog.temporal.data_imports.cdc.activities.close_old_connections")
    def test_streaming_schema_writes_s3_and_sends_kafka(
        self,
        mock_close_conns,
        MockJob,
        MockSourceModel,
        mock_get_schemas,
        MockReader,
        MockS3Writer,
        MockProducer,
        mock_activity,
    ):
        source = _make_source()
        MockSourceModel.objects.get.return_value = source

        schema = _make_schema("users", cdc_mode="streaming", source=source)
        mock_get_schemas.return_value = [schema]

        events = [
            _make_event(op="I", table="users", position="0/100", columns={"id": 1, "name": "Alice"}),
            _make_event(op="U", table="users", position="0/200", columns={"id": 1, "name": "Bob"}),
        ]

        mock_reader = MagicMock()
        mock_reader.read_changes.return_value = iter(events)
        mock_reader.truncated_tables = []
        MockReader.return_value = mock_reader

        mock_s3 = MagicMock()
        mock_batch_result = MagicMock()
        mock_batch_result.s3_path = "s3://bucket/data/part-0000.parquet"
        mock_batch_result.row_count = 2
        mock_batch_result.byte_size = 512
        mock_batch_result.batch_index = 0
        mock_batch_result.timestamp_ns = 123456
        mock_s3.write_batch.return_value = mock_batch_result
        mock_s3.write_schema.return_value = "s3://bucket/schema.json"
        mock_s3.get_data_folder.return_value = "s3://bucket/data/"
        MockS3Writer.return_value = mock_s3

        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer

        mock_job = MagicMock()
        mock_job.id = uuid.uuid4()
        MockJob.objects.create.return_value = mock_job
        MockJob.PipelineVersion.V2 = "v2-non-dlt"
        MockJob.Status.RUNNING = "Running"

        mock_activity.heartbeat = MagicMock()
        mock_activity.info.return_value = MagicMock(workflow_id="wf-1", workflow_run_id="run-1")

        inputs = CDCExtractInput(team_id=1, source_id=source.id)
        cdc_extract_activity(inputs)

        mock_reader.connect.assert_called_once()
        mock_s3.write_batch.assert_called_once()
        mock_producer.send_batch_notification.assert_called_once()
        mock_producer.flush.assert_called_once()
        mock_reader.confirm_position.assert_called_once_with("0/200")
        mock_reader.close.assert_called_once()

    @patch("posthog.temporal.data_imports.cdc.activities.activity")
    @patch("posthog.temporal.data_imports.cdc.activities.KafkaBatchProducer")
    @patch("posthog.temporal.data_imports.cdc.activities.S3BatchWriter")
    @patch("posthog.temporal.data_imports.cdc.activities.PgCDCStreamReader")
    @patch("posthog.temporal.data_imports.cdc.activities._get_cdc_schemas")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataSource")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataJob")
    @patch("posthog.temporal.data_imports.cdc.activities.close_old_connections")
    def test_snapshot_schema_writes_s3_but_defers_kafka(
        self,
        mock_close_conns,
        MockJob,
        MockSourceModel,
        mock_get_schemas,
        MockReader,
        MockS3Writer,
        MockProducer,
        mock_activity,
    ):
        source = _make_source()
        MockSourceModel.objects.get.return_value = source

        schema = _make_schema("users", cdc_mode="snapshot", source=source)
        mock_get_schemas.return_value = [schema]

        events = [_make_event(op="I", table="users", position="0/100")]
        mock_reader = MagicMock()
        mock_reader.read_changes.return_value = iter(events)
        mock_reader.truncated_tables = []
        MockReader.return_value = mock_reader

        mock_s3 = MagicMock()
        mock_batch_result = MagicMock()
        mock_batch_result.s3_path = "s3://bucket/data/part-0000.parquet"
        mock_batch_result.row_count = 1
        mock_batch_result.byte_size = 256
        mock_batch_result.batch_index = 0
        mock_batch_result.timestamp_ns = 123456
        mock_s3.write_batch.return_value = mock_batch_result
        mock_s3.write_schema.return_value = "s3://bucket/schema.json"
        mock_s3.get_data_folder.return_value = "s3://bucket/data/"
        MockS3Writer.return_value = mock_s3

        mock_job = MagicMock()
        mock_job.id = uuid.uuid4()
        MockJob.objects.create.return_value = mock_job
        MockJob.PipelineVersion.V2 = "v2-non-dlt"
        MockJob.Status.RUNNING = "Running"

        mock_activity.heartbeat = MagicMock()
        mock_activity.info.return_value = MagicMock(workflow_id="wf-1", workflow_run_id="run-1")

        inputs = CDCExtractInput(team_id=1, source_id=source.id)
        cdc_extract_activity(inputs)

        # S3 write happened
        mock_s3.write_batch.assert_called_once()

        # NO Kafka message
        MockProducer.assert_not_called()

        # Deferred run stored
        deferred = schema.sync_type_config.get("cdc_deferred_runs", [])
        assert len(deferred) == 1
        assert deferred[0]["run_uuid"] is not None
        assert deferred[0]["total_rows"] == 1

        # Slot still advanced
        mock_reader.confirm_position.assert_called_once_with("0/100")

    @patch("posthog.temporal.data_imports.cdc.activities.activity")
    @patch("posthog.temporal.data_imports.cdc.activities.PgCDCStreamReader")
    @patch("posthog.temporal.data_imports.cdc.activities._get_cdc_schemas")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataSource")
    @patch("posthog.temporal.data_imports.cdc.activities.close_old_connections")
    def test_no_changes_no_writes(
        self,
        mock_close_conns,
        MockSourceModel,
        mock_get_schemas,
        MockReader,
        mock_activity,
    ):
        source = _make_source()
        MockSourceModel.objects.get.return_value = source

        schema = _make_schema("users", cdc_mode="streaming", source=source)
        mock_get_schemas.return_value = [schema]

        mock_reader = MagicMock()
        mock_reader.read_changes.return_value = iter([])
        mock_reader.truncated_tables = []
        MockReader.return_value = mock_reader

        inputs = CDCExtractInput(team_id=1, source_id=source.id)
        cdc_extract_activity(inputs)

        # No S3 writes, no Kafka, no slot advance
        mock_reader.confirm_position.assert_not_called()
        mock_reader.close.assert_called_once()

    @patch("posthog.temporal.data_imports.cdc.activities.activity")
    @patch("posthog.temporal.data_imports.cdc.activities.PgCDCStreamReader")
    @patch("posthog.temporal.data_imports.cdc.activities._get_cdc_schemas")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataSource")
    @patch("posthog.temporal.data_imports.cdc.activities.close_old_connections")
    def test_no_cdc_schemas_returns_early(
        self,
        mock_close_conns,
        MockSourceModel,
        mock_get_schemas,
        MockReader,
        mock_activity,
    ):
        source = _make_source()
        MockSourceModel.objects.get.return_value = source
        mock_get_schemas.return_value = []

        inputs = CDCExtractInput(team_id=1, source_id=source.id)
        cdc_extract_activity(inputs)

        MockReader.assert_not_called()

    @patch("posthog.temporal.data_imports.cdc.activities.activity")
    @patch("posthog.temporal.data_imports.cdc.activities.KafkaBatchProducer")
    @patch("posthog.temporal.data_imports.cdc.activities.S3BatchWriter")
    @patch("posthog.temporal.data_imports.cdc.activities.PgCDCStreamReader")
    @patch("posthog.temporal.data_imports.cdc.activities._get_cdc_schemas")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataSource")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataJob")
    @patch("posthog.temporal.data_imports.cdc.activities.close_old_connections")
    def test_events_for_unknown_tables_are_filtered(
        self,
        mock_close_conns,
        MockJob,
        MockSourceModel,
        mock_get_schemas,
        MockReader,
        MockS3Writer,
        MockProducer,
        mock_activity,
    ):
        source = _make_source()
        MockSourceModel.objects.get.return_value = source

        schema = _make_schema("users", cdc_mode="streaming", source=source)
        mock_get_schemas.return_value = [schema]

        events = [
            _make_event(op="I", table="users", position="0/100"),
            _make_event(op="I", table="other_table", position="0/200"),
        ]
        mock_reader = MagicMock()
        mock_reader.read_changes.return_value = iter(events)
        mock_reader.truncated_tables = []
        MockReader.return_value = mock_reader

        mock_s3 = MagicMock()
        mock_batch_result = MagicMock()
        mock_batch_result.s3_path = "s3://path"
        mock_batch_result.row_count = 1
        mock_batch_result.byte_size = 100
        mock_batch_result.batch_index = 0
        mock_batch_result.timestamp_ns = 0
        mock_s3.write_batch.return_value = mock_batch_result
        mock_s3.write_schema.return_value = None
        mock_s3.get_data_folder.return_value = "s3://data/"
        MockS3Writer.return_value = mock_s3

        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer

        mock_job = MagicMock()
        mock_job.id = uuid.uuid4()
        MockJob.objects.create.return_value = mock_job
        MockJob.PipelineVersion.V2 = "v2-non-dlt"
        MockJob.Status.RUNNING = "Running"

        mock_activity.heartbeat = MagicMock()
        mock_activity.info.return_value = MagicMock(workflow_id="wf-1", workflow_run_id="run-1")

        inputs = CDCExtractInput(team_id=1, source_id=source.id)
        cdc_extract_activity(inputs)

        # Only 1 S3 write (for "users"), not for "other_table"
        mock_s3.write_batch.assert_called_once()
        call_args = mock_s3.write_batch.call_args
        pa_table = call_args[0][0]
        assert pa_table.num_rows == 1

    @patch("posthog.temporal.data_imports.cdc.activities.activity")
    @patch("posthog.temporal.data_imports.cdc.activities.PgCDCStreamReader")
    @patch("posthog.temporal.data_imports.cdc.activities._get_cdc_schemas")
    @patch("posthog.temporal.data_imports.cdc.activities.ExternalDataSource")
    @patch("posthog.temporal.data_imports.cdc.activities.close_old_connections")
    def test_reader_closed_on_error(
        self,
        mock_close_conns,
        MockSourceModel,
        mock_get_schemas,
        MockReader,
        mock_activity,
    ):
        source = _make_source()
        MockSourceModel.objects.get.return_value = source

        schema = _make_schema("users", cdc_mode="streaming", source=source)
        mock_get_schemas.return_value = [schema]

        mock_reader = MagicMock()
        mock_reader.read_changes.side_effect = RuntimeError("connection lost")
        mock_reader.truncated_tables = []
        MockReader.return_value = mock_reader

        inputs = CDCExtractInput(team_id=1, source_id=source.id)

        with pytest.raises(RuntimeError, match="connection lost"):
            cdc_extract_activity(inputs)

        mock_reader.close.assert_called_once()
