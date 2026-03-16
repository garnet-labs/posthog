import pytest
from unittest.mock import AsyncMock, Mock, patch

from posthog.temporal.messaging.backfill_precalculated_person_properties_coordinator_workflow import (
    generate_uuid_ranges,
)
from posthog.temporal.messaging.backfill_precalculated_person_properties_workflow import (
    BackfillPrecalculatedPersonPropertiesInputs,
    PersonPropertyFilter,
    backfill_precalculated_person_properties_activity,
    flush_kafka_batch,
)


class TestFlushKafkaBatch:
    """Tests for the flush_kafka_batch helper function."""

    @pytest.mark.asyncio
    async def test_empty_messages_returns_zero(self):
        """When pending_messages is empty, should return 0 without flushing."""
        kafka_producer = Mock()
        heartbeater = Mock()
        logger = Mock()

        result = await flush_kafka_batch(
            kafka_producer=kafka_producer,
            pending_messages=[],
            team_id=1,
            current_offset=0,
            heartbeater=heartbeater,
            logger=logger,
        )

        assert result == 0
        kafka_producer.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_batch_flush(self):
        """Should flush messages and return batch size on success."""
        kafka_producer = Mock()
        kafka_producer.flush = Mock()

        # Mock successful send results
        mock_results = [Mock() for _ in range(100)]
        for mock_result in mock_results:
            mock_result.get = Mock(return_value=None)

        heartbeater = Mock()
        logger = Mock()

        with patch(
            "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread"
        ) as mock_thread:
            mock_thread.return_value = None

            result = await flush_kafka_batch(
                kafka_producer=kafka_producer,
                pending_messages=mock_results,
                team_id=1,
                current_offset=1000,
                heartbeater=heartbeater,
                logger=logger,
            )

        assert result == 100
        mock_thread.assert_called_once_with(kafka_producer.flush)
        logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_final_batch_includes_final_in_messages(self):
        """When is_final=True, should include 'final' in heartbeat and log messages."""
        kafka_producer = Mock()
        mock_result = Mock()
        mock_result.get = Mock(return_value=None)

        heartbeater = Mock()
        logger = Mock()

        with patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread"):
            await flush_kafka_batch(
                kafka_producer=kafka_producer,
                pending_messages=[mock_result],
                team_id=1,
                current_offset=5000,
                heartbeater=heartbeater,
                logger=logger,
                is_final=True,
            )

        # Check heartbeat details includes "final"
        assert heartbeater.details[0].startswith("Flushing final ")

        # Check logger includes "final"
        log_call_args = logger.info.call_args[0][0]
        assert "final" in log_call_args.lower()

    @pytest.mark.asyncio
    async def test_non_final_batch_excludes_final_from_messages(self):
        """When is_final=False, should not include 'final' in messages."""
        kafka_producer = Mock()
        mock_result = Mock()
        mock_result.get = Mock(return_value=None)

        heartbeater = Mock()
        logger = Mock()

        with patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread"):
            await flush_kafka_batch(
                kafka_producer=kafka_producer,
                pending_messages=[mock_result],
                team_id=1,
                current_offset=2000,
                heartbeater=heartbeater,
                logger=logger,
                is_final=False,
            )

        # Check heartbeat details does not include "final"
        heartbeat_msg = heartbeater.details[0]
        assert "final" not in heartbeat_msg.lower()

        # Check logger does not include "final"
        log_call_args = logger.info.call_args[0][0]
        assert "final" not in log_call_args.lower()

    @pytest.mark.asyncio
    async def test_batch_flush_with_partial_failures(self):
        """Should raise exception when some messages fail to send."""
        kafka_producer = Mock()

        # Create mix of successful and failed results
        successful_result = Mock()
        successful_result.get = Mock(return_value=None)

        failed_result = Mock()
        failed_result.get = Mock(side_effect=Exception("Send failed"))

        mock_results = [successful_result, failed_result, successful_result]

        heartbeater = Mock()
        logger = Mock()

        with patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread"):
            with pytest.raises(Exception, match="Failed to send 1/3 Kafka messages"):
                await flush_kafka_batch(
                    kafka_producer=kafka_producer,
                    pending_messages=mock_results,
                    team_id=1,
                    current_offset=3000,
                    heartbeater=heartbeater,
                    logger=logger,
                )

        # Should log warnings for failed messages
        assert logger.warning.call_count == 1
        # Should log error summary
        assert logger.error.call_count == 1

    @pytest.mark.asyncio
    async def test_batch_flush_with_all_failures(self):
        """Should raise exception when all messages fail to send."""
        kafka_producer = Mock()

        # All results fail
        mock_results = []
        for _ in range(5):
            failed_result = Mock()
            failed_result.get = Mock(side_effect=Exception("Send failed"))
            mock_results.append(failed_result)

        heartbeater = Mock()
        logger = Mock()

        with patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread"):
            with pytest.raises(Exception, match="Failed to send 5/5 Kafka messages"):
                await flush_kafka_batch(
                    kafka_producer=kafka_producer,
                    pending_messages=mock_results,
                    team_id=1,
                    current_offset=4000,
                    heartbeater=heartbeater,
                    logger=logger,
                )

        assert logger.warning.call_count == 5
        assert logger.error.call_count == 1

    @pytest.mark.asyncio
    async def test_heartbeat_details_format(self):
        """Should format heartbeat details with offset information."""
        kafka_producer = Mock()
        mock_result = Mock()
        mock_result.get = Mock(return_value=None)

        heartbeater = Mock()
        logger = Mock()

        with patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread"):
            await flush_kafka_batch(
                kafka_producer=kafka_producer,
                pending_messages=[mock_result] * 10000,
                team_id=1,
                current_offset=50000,
                heartbeater=heartbeater,
                logger=logger,
            )

        heartbeat_msg = heartbeater.details[0]
        assert "10000 messages" in heartbeat_msg
        assert "offset 50000" in heartbeat_msg

    @pytest.mark.asyncio
    async def test_logger_includes_metadata(self):
        """Should include team_id, offset, and batch_size in logger metadata."""
        kafka_producer = Mock()
        mock_result = Mock()
        mock_result.get = Mock(return_value=None)

        heartbeater = Mock()
        logger = Mock()

        with patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread"):
            await flush_kafka_batch(
                kafka_producer=kafka_producer,
                pending_messages=[mock_result] * 5000,
                team_id=42,
                current_offset=25000,
                heartbeater=heartbeater,
                logger=logger,
            )

        # Check logger.info was called with metadata
        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args[1]
        assert call_kwargs["team_id"] == 42
        assert call_kwargs["offset"] == 25000
        assert call_kwargs["batch_size"] == 5000


class TestBatchFlushingBehavior:
    """Tests for batch flushing logic and integration."""

    @pytest.mark.asyncio
    async def test_multiple_batches_handled_correctly(self):
        """Should handle multiple batch flushes correctly."""
        kafka_producer = Mock()

        # Simulate 3 batches: 10k, 10k, 5k
        heartbeater = Mock()
        logger = Mock()

        mock_results_batch1 = [Mock() for _ in range(10000)]
        mock_results_batch2 = [Mock() for _ in range(10000)]
        mock_results_batch3 = [Mock() for _ in range(5000)]

        for result in mock_results_batch1 + mock_results_batch2 + mock_results_batch3:
            result.get = Mock(return_value=None)

        with patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread"):
            # Batch 1
            result1 = await flush_kafka_batch(kafka_producer, mock_results_batch1, 1, 0, heartbeater, logger)
            # Batch 2
            result2 = await flush_kafka_batch(kafka_producer, mock_results_batch2, 1, 10000, heartbeater, logger)
            # Batch 3 (final)
            result3 = await flush_kafka_batch(
                kafka_producer, mock_results_batch3, 1, 20000, heartbeater, logger, is_final=True
            )

        assert result1 == 10000
        assert result2 == 10000
        assert result3 == 5000
        assert result1 + result2 + result3 == 25000


class TestBackfillPrecalculatedPersonPropertiesActivity:
    """Tests for the main backfill activity function."""

    @pytest.mark.asyncio
    async def test_multi_cohort_processing_with_correct_source_attribution(self):
        """Should process multiple cohorts and attribute events to correct cohort sources."""
        # Set up test data
        person_data = [
            {
                "person_id": "person_1",
                "properties": '{"age": 25, "country": "US"}',
                "distinct_ids": ["user_1a", "user_1b"],
            },
            {
                "person_id": "person_2",
                "properties": '{"age": 35, "country": "UK"}',
                "distinct_ids": ["user_2a"],
            },
        ]

        # Create filters structure
        # Cohort 100: age_filter_25, country_filter_us
        # Cohort 200: age_filter_35
        filters = [
            PersonPropertyFilter(
                condition_hash="age_filter_25",
                bytecode=["mock_bytecode_age_25"],
                cohort_ids=[100],
            ),
            PersonPropertyFilter(
                condition_hash="country_filter_us",
                bytecode=["mock_bytecode_country_us"],
                cohort_ids=[100],
            ),
            PersonPropertyFilter(
                condition_hash="age_filter_35",
                bytecode=["mock_bytecode_age_35"],
                cohort_ids=[200],
            ),
        ]

        inputs = BackfillPrecalculatedPersonPropertiesInputs(
            team_id=1,
            filters=filters,
            cohort_ids=[100, 200],
            batch_size=100,
            start_uuid="00000000-0000-0000-0000-000000000000",
            end_uuid="ffffffff-ffff-ffff-ffff-ffffffffffff",
        )

        # Mock dependencies
        mock_kafka_producer = Mock()
        mock_send_results = []

        def mock_produce(**kwargs):
            result = Mock()
            result.get = Mock(return_value=None)
            mock_send_results.append((result, kwargs))
            return result

        mock_kafka_producer.produce = Mock(side_effect=mock_produce)
        mock_kafka_producer.flush = Mock()

        mock_client = AsyncMock()

        # Create an async generator for the mock
        async def mock_stream_query(*args, **kwargs):
            for person in person_data:
                yield person

        mock_client.stream_query_as_jsonl = mock_stream_query

        # Mock HogQL execution to return different results for different filters
        def mock_execute_bytecode(bytecode, globals_dict, timeout=None):
            result = Mock()
            person_age = globals_dict["person"]["properties"].get("age")
            person_country = globals_dict["person"]["properties"].get("country")

            # Match filters based on bytecode
            if bytecode == ["mock_bytecode_age_25"]:
                result.result = person_age == 25
            elif bytecode == ["mock_bytecode_age_35"]:
                result.result = person_age == 35
            elif bytecode == ["mock_bytecode_country_us"]:
                result.result = person_country == "US"
            else:
                result.result = False
            return result

        # Mock asyncio.to_thread to handle both flush and execute_bytecode calls
        async def mock_to_thread(func, *args, **kwargs):
            if hasattr(func, "_mock_name") and "flush" in func._mock_name:
                # This is the kafka flush call - just return None
                return None
            else:
                # This is the execute_bytecode call
                return mock_execute_bytecode(*args, **kwargs)

        with (
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.KafkaProducer",
                return_value=mock_kafka_producer,
            ),
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.get_client"
            ) as mock_get_client,
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.Heartbeater"
            ) as mock_heartbeater,
            patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.bind_contextvars"),
            patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.LOGGER"),
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.get_person_properties_backfill_success_metric"
            ) as mock_metric,
            patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.tags_context"),
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread",
                side_effect=mock_to_thread,
            ),
        ):
            mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_heartbeater_instance = Mock()
            mock_heartbeater_instance.__aenter__ = AsyncMock(return_value=mock_heartbeater_instance)
            mock_heartbeater_instance.__aexit__ = AsyncMock(return_value=None)
            mock_heartbeater.return_value = mock_heartbeater_instance

            mock_metric.return_value.add = Mock()

            # Execute the activity
            await backfill_precalculated_person_properties_activity(inputs)

        # Verify Kafka messages were produced
        assert len(mock_send_results) > 0

        # Extract all events from mock calls
        produced_events = []
        for _result, call_kwargs in mock_send_results:
            produced_events.append(call_kwargs["data"])

        # Expected events:
        # Person 1 (age=25, country=US) should match:
        #   - cohort 100: age_filter_25 (matches), country_filter_us (matches)
        # Person 2 (age=35, country=UK) should match:
        #   - cohort 100: age_filter_25 (doesn't match), country_filter_us (doesn't match)
        #   - cohort 200: age_filter_35 (matches)

        # Group events by cohort source
        cohort_100_events = [e for e in produced_events if e["source"] == "cohort_backfill_100"]
        cohort_200_events = [e for e in produced_events if e["source"] == "cohort_backfill_200"]

        # Should have events for both cohorts
        assert len(cohort_100_events) > 0, "Should have events for cohort 100"
        assert len(cohort_200_events) > 0, "Should have events for cohort 200"

        # Verify cohort 100 events have correct source and conditions
        cohort_100_conditions = {e["condition"] for e in cohort_100_events}
        assert "age_filter_25" in cohort_100_conditions
        assert "country_filter_us" in cohort_100_conditions

        # Verify cohort 200 events have correct source and conditions
        cohort_200_conditions = {e["condition"] for e in cohort_200_events}
        assert "age_filter_35" in cohort_200_conditions

        # Verify person 1 matches are correct for cohort 100
        person_1_cohort_100_events = [e for e in cohort_100_events if e["person_id"] == "person_1"]

        # Person 1 should have matching events for both filters in cohort 100
        person_1_matches = {e["condition"]: e["matches"] for e in person_1_cohort_100_events}
        assert person_1_matches.get("age_filter_25") is True  # age=25 matches
        assert person_1_matches.get("country_filter_us") is True  # country=US matches

        # Verify person 2 matches are correct for cohort 200
        person_2_cohort_200_events = [e for e in cohort_200_events if e["person_id"] == "person_2"]

        person_2_matches = {e["condition"]: e["matches"] for e in person_2_cohort_200_events}
        assert person_2_matches.get("age_filter_35") is True  # age=35 matches

        # Verify all events have the correct team_id
        for event in produced_events:
            assert event["team_id"] == 1

        # Verify distinct_ids are properly handled - each person should generate events for each distinct_id
        person_1_distinct_ids = {e["distinct_id"] for e in produced_events if e["person_id"] == "person_1"}
        assert person_1_distinct_ids == {"user_1a", "user_1b"}

        person_2_distinct_ids = {e["distinct_id"] for e in produced_events if e["person_id"] == "person_2"}
        assert person_2_distinct_ids == {"user_2a"}

    @pytest.mark.asyncio
    async def test_shared_condition_across_multiple_cohorts(self):
        """Should evaluate a shared condition once and emit results to multiple cohorts."""
        # Set up test data
        person_data = [
            {
                "person_id": "person_1",
                "properties": '{"age": 25}',
                "distinct_ids": ["user_1"],
            },
        ]

        # Create a shared condition that is used by both cohorts 100 and 200
        filters = [
            PersonPropertyFilter(
                condition_hash="age_filter_25",
                bytecode=["mock_bytecode_age_25"],
                cohort_ids=[100, 200],  # This condition is shared between both cohorts
            ),
        ]

        inputs = BackfillPrecalculatedPersonPropertiesInputs(
            team_id=1,
            filters=filters,
            cohort_ids=[100, 200],
            batch_size=100,
            start_uuid="00000000-0000-0000-0000-000000000000",
            end_uuid="ffffffff-ffff-ffff-ffff-ffffffffffff",
        )

        # Track how many times execute_bytecode is called
        execute_bytecode_call_count = 0

        # Mock dependencies
        mock_kafka_producer = Mock()
        mock_send_results = []

        def mock_produce(**kwargs):
            result = Mock()
            result.get = Mock(return_value=None)
            mock_send_results.append((result, kwargs))
            return result

        mock_kafka_producer.produce = Mock(side_effect=mock_produce)
        mock_kafka_producer.flush = Mock()

        mock_client = AsyncMock()

        # Create an async generator for the mock
        async def mock_stream_query(*args, **kwargs):
            for person in person_data:
                yield person

        mock_client.stream_query_as_jsonl = mock_stream_query

        # Mock HogQL execution to track calls
        def mock_execute_bytecode(bytecode, globals_dict, timeout=None):
            nonlocal execute_bytecode_call_count
            execute_bytecode_call_count += 1

            result = Mock()
            person_age = globals_dict["person"]["properties"].get("age")

            # Match filters based on bytecode
            if bytecode == ["mock_bytecode_age_25"]:
                result.result = person_age == 25
            else:
                result.result = False
            return result

        # Mock asyncio.to_thread
        async def mock_to_thread(func, *args, **kwargs):
            if hasattr(func, "_mock_name") and "flush" in func._mock_name:
                # This is the kafka flush call
                return None
            else:
                # This is the execute_bytecode call
                return mock_execute_bytecode(*args, **kwargs)

        with (
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.KafkaProducer",
                return_value=mock_kafka_producer,
            ),
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.get_client"
            ) as mock_get_client,
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.Heartbeater"
            ) as mock_heartbeater,
            patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.bind_contextvars"),
            patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.LOGGER"),
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.get_person_properties_backfill_success_metric"
            ) as mock_metric,
            patch("posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.tags_context"),
            patch(
                "posthog.temporal.messaging.backfill_precalculated_person_properties_workflow.asyncio.to_thread",
                side_effect=mock_to_thread,
            ),
        ):
            mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_heartbeater_instance = Mock()
            mock_heartbeater_instance.__aenter__ = AsyncMock(return_value=mock_heartbeater_instance)
            mock_heartbeater_instance.__aexit__ = AsyncMock(return_value=None)
            mock_heartbeater.return_value = mock_heartbeater_instance

            mock_metric.return_value.add = Mock()

            # Execute the activity
            await backfill_precalculated_person_properties_activity(inputs)

        # CRITICAL ASSERTION: The condition should be evaluated only ONCE
        assert execute_bytecode_call_count == 1, f"Expected 1 bytecode execution, got {execute_bytecode_call_count}"

        # Extract all events from mock calls
        produced_events = []
        for _result, call_kwargs in mock_send_results:
            produced_events.append(call_kwargs["data"])

        # Should have events for BOTH cohorts from the SAME evaluation
        cohort_100_events = [e for e in produced_events if e["source"] == "cohort_backfill_100"]
        cohort_200_events = [e for e in produced_events if e["source"] == "cohort_backfill_200"]

        # Both cohorts should have events
        assert len(cohort_100_events) == 1, f"Expected 1 event for cohort 100, got {len(cohort_100_events)}"
        assert len(cohort_200_events) == 1, f"Expected 1 event for cohort 200, got {len(cohort_200_events)}"

        # Both events should have the same condition hash
        assert cohort_100_events[0]["condition"] == "age_filter_25"
        assert cohort_200_events[0]["condition"] == "age_filter_25"

        # Both events should have the same evaluation result (matches=True since age=25)
        assert cohort_100_events[0]["matches"] is True
        assert cohort_200_events[0]["matches"] is True

        # Both events should be for the same person
        assert cohort_100_events[0]["person_id"] == "person_1"
        assert cohort_200_events[0]["person_id"] == "person_1"

        # Verify distinct IDs are correct for both
        assert cohort_100_events[0]["distinct_id"] == "user_1"
        assert cohort_200_events[0]["distinct_id"] == "user_1"

        # Verify sources are different
        assert cohort_100_events[0]["source"] == "cohort_backfill_100"
        assert cohort_200_events[0]["source"] == "cohort_backfill_200"


class TestGenerateUuidRanges:
    """Tests for the generate_uuid_ranges function."""

    @pytest.mark.parametrize(
        "min_uuid,max_uuid,num_ranges,expected_count",
        [
            # Single range case
            ("00000000-0000-0000-0000-000000000001", "ffffffff-ffff-ffff-ffff-ffffffffffff", 1, 1),
            # Normal case
            ("00000000-0000-0000-0000-000000000001", "ffffffff-ffff-ffff-ffff-ffffffffffff", 4, 4),
            # Edge cases
            ("", "", 1, 0),
            ("00000000-0000-0000-0000-000000000001", "", 1, 0),
            ("", "ffffffff-ffff-ffff-ffff-ffffffffffff", 1, 0),
            ("00000000-0000-0000-0000-000000000001", "ffffffff-ffff-ffff-ffff-ffffffffffff", 0, 0),
            ("00000000-0000-0000-0000-000000000001", "ffffffff-ffff-ffff-ffff-ffffffffffff", -1, 0),
        ],
    )
    def test_basic_range_generation(self, min_uuid, max_uuid, num_ranges, expected_count):
        """Test basic range generation with various inputs."""
        result = generate_uuid_ranges(min_uuid, max_uuid, num_ranges)
        assert len(result) == expected_count

    def test_single_range_returns_full_span(self):
        """Test that num_ranges=1 returns a single tuple spanning the full range."""
        min_uuid = "00000000-0000-0000-0000-000000000001"
        max_uuid = "ffffffff-ffff-ffff-ffff-ffffffffffff"

        result = generate_uuid_ranges(min_uuid, max_uuid, 1)

        assert len(result) == 1
        assert result[0] == (min_uuid, max_uuid)

    def test_identical_uuids_edge_case(self):
        """Test min_int >= max_int fallback when UUIDs are identical."""
        same_uuid = "12345678-1234-1234-1234-123456789abc"

        result = generate_uuid_ranges(same_uuid, same_uuid, 3)

        assert len(result) == 1
        assert result[0] == (same_uuid, same_uuid)

    def test_very_small_range_fallback(self):
        """Test that very small ranges trigger the single range fallback."""
        min_uuid = "00000000-0000-0000-0000-000000000000"
        max_uuid = "00000000-0000-0000-0000-000000000002"

        # Request many ranges but the total range is only 2
        result = generate_uuid_ranges(min_uuid, max_uuid, 10)

        assert len(result) == 1
        assert result[0] == (min_uuid, max_uuid)

    def test_range_contiguity_and_coverage(self):
        """Test that ranges are contiguous and cover the full span."""
        min_uuid = "10000000-0000-0000-0000-000000000000"
        max_uuid = "20000000-0000-0000-0000-000000000000"

        result = generate_uuid_ranges(min_uuid, max_uuid, 4)

        assert len(result) == 4

        # Check that ranges are contiguous
        for i in range(len(result) - 1):
            current_end = result[i][1]
            next_start = result[i + 1][0]

            # Convert to integers for comparison
            current_end_int = int(current_end.replace("-", ""), 16)
            next_start_int = int(next_start.replace("-", ""), 16)

            # Next range should start exactly where current ends + 1
            assert next_start_int == current_end_int + 1

        # Check coverage spans full range
        assert result[0][0] == min_uuid
        assert result[-1][1] == max_uuid

    def test_uuid_format_preservation(self):
        """Test that generated UUIDs maintain proper format (8-4-4-4-12)."""
        min_uuid = "00000000-0000-0000-0000-000000000000"
        max_uuid = "ffffffff-ffff-ffff-ffff-ffffffffffff"

        result = generate_uuid_ranges(min_uuid, max_uuid, 3)

        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        import re

        for start_uuid, end_uuid in result:
            assert re.match(uuid_pattern, start_uuid), f"Invalid start UUID format: {start_uuid}"
            assert re.match(uuid_pattern, end_uuid), f"Invalid end UUID format: {end_uuid}"

    def test_load_balancing_distribution(self):
        """Test that ranges are distributed evenly to balance load."""
        min_uuid = "00000000-0000-0000-0000-000000000000"
        max_uuid = "00000000-0000-0000-0000-000000000063"  # Hex 63 = decimal 99

        # Total range is 99, split into 4 ranges
        result = generate_uuid_ranges(min_uuid, max_uuid, 4)

        assert len(result) == 4

        # Calculate actual range sizes
        range_sizes = []
        for start_uuid, end_uuid in result:
            start_int = int(start_uuid.replace("-", ""), 16)
            end_int = int(end_uuid.replace("-", ""), 16)
            range_sizes.append(end_int - start_int + 1)

        # All ranges should be reasonably balanced (difference <= 2 for small ranges)
        # For a range of 99 split 4 ways, some ranges will be slightly larger
        min_size = min(range_sizes)
        max_size = max(range_sizes)
        assert max_size - min_size <= 2, f"Unbalanced ranges: {range_sizes}"

        # Verify total coverage
        total_covered = sum(range_sizes)
        expected_total = 99 + 1  # 0 to 99 inclusive = 100 elements
        assert total_covered == expected_total

    def test_invalid_uuid_fallback(self):
        """Test fallback behavior when UUIDs cannot be parsed as hex."""
        invalid_uuid = "invalid-uuid-format"
        valid_uuid = "ffffffff-ffff-ffff-ffff-ffffffffffff"

        result = generate_uuid_ranges(invalid_uuid, valid_uuid, 3)

        # Should fall back to simple partitioning (single range)
        assert len(result) == 1
        assert result[0] == (invalid_uuid, valid_uuid)
