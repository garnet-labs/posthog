import asyncio
import tempfile

import pytest
from unittest import mock

import pyarrow as pa
import deltalake
import structlog

from posthog.temporal.data_imports.pipelines.pipeline.consts import PARTITION_KEY
from posthog.temporal.data_imports.pipelines.pipeline.delta_table_helper import DeltaTableHelper


def _make_helper(table_uri: str, is_first_sync: bool = False) -> DeltaTableHelper:
    job = mock.MagicMock()
    job.folder_path.return_value = "test_folder"
    logger = structlog.get_logger()

    helper = DeltaTableHelper(resource_name="test_resource", job=job, logger=logger, is_first_sync=is_first_sync)
    # Override internals so the helper uses a local directory instead of S3
    helper._get_delta_table_uri = mock.AsyncMock(return_value=table_uri)  # type: ignore[method-assign]
    helper._get_credentials = mock.MagicMock(return_value={})  # type: ignore[method-assign]
    return helper


def _create_partitioned_table(uri: str, data: pa.Table) -> deltalake.DeltaTable:
    deltalake.write_deltalake(uri, data, partition_by=PARTITION_KEY, mode="overwrite")
    return deltalake.DeltaTable(uri)


def _pa_table_with_partitions(ids: list[int], names: list[str], partitions: list[str]) -> pa.Table:
    return pa.table(
        {
            "id": pa.array(ids, type=pa.int64()),
            "name": pa.array(names),
            PARTITION_KEY: pa.array(partitions),
        }
    )


class TestPartitionOverwrite:
    def test_partition_overwrite_deletes_and_appends(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uri = f"{tmpdir}/delta_table"

            initial_data = _pa_table_with_partitions(
                ids=[1, 2, 3],
                names=["old_a", "old_b", "old_c"],
                partitions=["2024-01-01", "2024-01-01", "2024-01-02"],
            )
            _create_partitioned_table(uri, initial_data)

            helper = _make_helper(uri)
            # Pre-populate the cache so get_delta_table returns the existing table
            helper.get_delta_table.cache_clear()

            new_data = _pa_table_with_partitions(
                ids=[1, 2],
                names=["new_a", "new_b"],
                partitions=["2024-01-01", "2024-01-01"],
            )

            asyncio.get_event_loop().run_until_complete(
                helper.write_to_deltalake(
                    data=new_data,
                    write_type="incremental",
                    should_overwrite_table=False,
                    primary_keys=["id"],
                    partition_overwrite=True,
                )
            )

            dt = deltalake.DeltaTable(uri)
            result = dt.to_pyarrow_table()

            # Partition 2024-01-01 should have the new data only
            p1 = result.filter(pa.compute.equal(result[PARTITION_KEY], "2024-01-01")).sort_by("id")
            assert p1.column("name").to_pylist() == ["new_a", "new_b"]
            assert p1.column("id").to_pylist() == [1, 2]

            # Partition 2024-01-02 should be untouched
            p2 = result.filter(pa.compute.equal(result[PARTITION_KEY], "2024-01-02"))
            assert p2.column("name").to_pylist() == ["old_c"]
            assert p2.column("id").to_pylist() == [3]

    def test_partition_overwrite_does_not_double_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uri = f"{tmpdir}/delta_table"

            initial_data = _pa_table_with_partitions(
                ids=[1, 2],
                names=["a", "b"],
                partitions=["2024-01-01", "2024-01-01"],
            )
            _create_partitioned_table(uri, initial_data)

            helper = _make_helper(uri)
            helper.get_delta_table.cache_clear()

            # First write: should delete partition then append
            batch1 = _pa_table_with_partitions(
                ids=[1],
                names=["batch1"],
                partitions=["2024-01-01"],
            )
            asyncio.get_event_loop().run_until_complete(
                helper.write_to_deltalake(
                    data=batch1,
                    write_type="incremental",
                    should_overwrite_table=False,
                    primary_keys=["id"],
                    partition_overwrite=True,
                )
            )

            # Second write to the same partition: should NOT delete again, just append
            batch2 = _pa_table_with_partitions(
                ids=[2],
                names=["batch2"],
                partitions=["2024-01-01"],
            )
            asyncio.get_event_loop().run_until_complete(
                helper.write_to_deltalake(
                    data=batch2,
                    write_type="incremental",
                    should_overwrite_table=False,
                    primary_keys=["id"],
                    partition_overwrite=True,
                )
            )

            dt = deltalake.DeltaTable(uri)
            result = dt.to_pyarrow_table().sort_by("id")

            # Both batch1 and batch2 rows should be present
            assert result.column("id").to_pylist() == [1, 2]
            assert result.column("name").to_pylist() == ["batch1", "batch2"]

    def test_partition_overwrite_data_integrity_across_partitions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uri = f"{tmpdir}/delta_table"

            initial_data = _pa_table_with_partitions(
                ids=[1, 2, 3, 4],
                names=["a", "b", "c", "d"],
                partitions=["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03"],
            )
            _create_partitioned_table(uri, initial_data)

            helper = _make_helper(uri)
            helper.get_delta_table.cache_clear()

            # Overwrite partitions 2024-01-01 and 2024-01-02 in one batch
            new_data = _pa_table_with_partitions(
                ids=[10, 20, 30],
                names=["new_a", "new_b", "new_c"],
                partitions=["2024-01-01", "2024-01-01", "2024-01-02"],
            )

            asyncio.get_event_loop().run_until_complete(
                helper.write_to_deltalake(
                    data=new_data,
                    write_type="incremental",
                    should_overwrite_table=False,
                    primary_keys=["id"],
                    partition_overwrite=True,
                )
            )

            dt = deltalake.DeltaTable(uri)
            result = dt.to_pyarrow_table()

            # 2024-01-01: replaced
            p1 = result.filter(pa.compute.equal(result[PARTITION_KEY], "2024-01-01")).sort_by("id")
            assert p1.column("id").to_pylist() == [10, 20]
            assert p1.column("name").to_pylist() == ["new_a", "new_b"]

            # 2024-01-02: replaced
            p2 = result.filter(pa.compute.equal(result[PARTITION_KEY], "2024-01-02"))
            assert p2.column("id").to_pylist() == [30]
            assert p2.column("name").to_pylist() == ["new_c"]

            # 2024-01-03: untouched
            p3 = result.filter(pa.compute.equal(result[PARTITION_KEY], "2024-01-03"))
            assert p3.column("id").to_pylist() == [4]
            assert p3.column("name").to_pylist() == ["d"]


class TestIncrementalMergeUnaffected:
    """Verify that the standard incremental merge paths (partition_overwrite=False)
    are not affected by the partition_overwrite changes."""

    def test_partitioned_incremental_merge_upserts_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uri = f"{tmpdir}/delta_table"

            initial_data = _pa_table_with_partitions(
                ids=[1, 2, 3],
                names=["a", "b", "c"],
                partitions=["2024-01-01", "2024-01-01", "2024-01-02"],
            )
            _create_partitioned_table(uri, initial_data)

            helper = _make_helper(uri)
            helper.get_delta_table.cache_clear()

            # Update id=1 and insert id=4, both in partition 2024-01-01
            update_data = _pa_table_with_partitions(
                ids=[1, 4],
                names=["updated_a", "new_d"],
                partitions=["2024-01-01", "2024-01-01"],
            )

            asyncio.get_event_loop().run_until_complete(
                helper.write_to_deltalake(
                    data=update_data,
                    write_type="incremental",
                    should_overwrite_table=False,
                    primary_keys=["id"],
                    partition_overwrite=False,
                )
            )

            dt = deltalake.DeltaTable(uri)
            result = dt.to_pyarrow_table()

            p1 = result.filter(pa.compute.equal(result[PARTITION_KEY], "2024-01-01")).sort_by("id")
            # id=1 updated, id=2 untouched, id=4 inserted
            assert p1.column("id").to_pylist() == [1, 2, 4]
            assert p1.column("name").to_pylist() == ["updated_a", "b", "new_d"]

            # Partition 2024-01-02 untouched
            p2 = result.filter(pa.compute.equal(result[PARTITION_KEY], "2024-01-02"))
            assert p2.column("id").to_pylist() == [3]
            assert p2.column("name").to_pylist() == ["c"]

    def test_unpartitioned_incremental_merge_upserts_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uri = f"{tmpdir}/delta_table"

            # No partition key column — unpartitioned table
            initial_data = pa.table(
                {
                    "id": pa.array([1, 2, 3], type=pa.int64()),
                    "name": pa.array(["a", "b", "c"]),
                }
            )
            deltalake.write_deltalake(uri, initial_data, mode="overwrite")

            helper = _make_helper(uri)
            helper.get_delta_table.cache_clear()

            update_data = pa.table(
                {
                    "id": pa.array([2, 4], type=pa.int64()),
                    "name": pa.array(["updated_b", "new_d"]),
                }
            )

            asyncio.get_event_loop().run_until_complete(
                helper.write_to_deltalake(
                    data=update_data,
                    write_type="incremental",
                    should_overwrite_table=False,
                    primary_keys=["id"],
                    partition_overwrite=False,
                )
            )

            dt = deltalake.DeltaTable(uri)
            result = dt.to_pyarrow_table().sort_by("id")

            assert result.column("id").to_pylist() == [1, 2, 3, 4]
            assert result.column("name").to_pylist() == ["a", "updated_b", "c", "new_d"]

    def test_partition_overwrite_false_does_not_delete_partition(self):
        """Explicitly confirm that partition_overwrite=False uses merge, not delete+append."""
        with tempfile.TemporaryDirectory() as tmpdir:
            uri = f"{tmpdir}/delta_table"

            initial_data = _pa_table_with_partitions(
                ids=[1, 2],
                names=["a", "b"],
                partitions=["2024-01-01", "2024-01-01"],
            )
            _create_partitioned_table(uri, initial_data)

            helper = _make_helper(uri)
            helper.get_delta_table.cache_clear()

            # Write only id=1 with partition_overwrite=False — id=2 must survive
            update_data = _pa_table_with_partitions(
                ids=[1],
                names=["updated_a"],
                partitions=["2024-01-01"],
            )

            asyncio.get_event_loop().run_until_complete(
                helper.write_to_deltalake(
                    data=update_data,
                    write_type="incremental",
                    should_overwrite_table=False,
                    primary_keys=["id"],
                    partition_overwrite=False,
                )
            )

            dt = deltalake.DeltaTable(uri)
            result = dt.to_pyarrow_table().sort_by("id")

            # Both rows present — id=2 was NOT deleted (merge, not delete+append)
            assert result.column("id").to_pylist() == [1, 2]
            assert result.column("name").to_pylist() == ["updated_a", "b"]


class TestPartitionOverwriteResumableGuard:
    def test_partition_overwrite_with_resumable_source_raises(self):
        from posthog.temporal.data_imports.pipelines.pipeline.pipeline import PipelineNonDLT
        from posthog.temporal.data_imports.pipelines.pipeline.typings import SourceResponse

        source_response = SourceResponse(
            name="test",
            items=lambda: iter([]),
            primary_keys=["id"],
            partition_overwrite=True,
        )

        with pytest.raises(ValueError, match="partition_overwrite is incompatible with resumable sources"):
            PipelineNonDLT(
                source_response=source_response,
                logger=structlog.get_logger(),
                job_id="test-job",
                reset_pipeline=False,
                shutdown_monitor=mock.MagicMock(),
                job=mock.MagicMock(),
                schema=mock.MagicMock(
                    is_incremental=True,
                    is_append=False,
                    incremental_field_earliest_value=None,
                    incremental_field_type=None,
                ),
                source=mock.MagicMock(),
                table=None,
                resumable_source_manager=mock.MagicMock(),  # non-None = resumable
            )
