import json
from datetime import UTC, datetime, timedelta
from typing import Optional

import temporalio
from asgiref.sync import sync_to_async
from django.conf import settings
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.service import RPCError, RPCStatusCode

from posthog.storage import object_storage
from posthog.temporal.common.client import async_connect

from products.signals.backend.temporal.grouping import (
    TYPE_EXAMPLES_CACHE_TTL,
    FetchSignalTypeExamplesOutput,
    _process_signal_batch,
)
from products.signals.backend.temporal.types import (
    EmitSignalInputs,
    ReadSignalsFromS3Input,
    ReadSignalsFromS3Output,
    TeamSignalGroupingV2Input,
)

PAUSE_SLEEP_SECONDS = 30
PAUSE_MAX_CONTINUE_AS_NEW_MINUTES = 30


@activity.defn
async def read_signals_from_s3_activity(input: ReadSignalsFromS3Input) -> ReadSignalsFromS3Output:
    raw = await sync_to_async(object_storage.read, thread_sensitive=False)(input.object_key)
    if raw is None:
        raise ValueError(f"Signal batch not found in S3: {input.object_key}")

    data = json.loads(raw)
    signals = [EmitSignalInputs(**item) for item in data]

    return ReadSignalsFromS3Output(signals=signals)


@temporalio.workflow.defn(name="team-signal-grouping-v2")
class TeamSignalGroupingV2Workflow:
    """
    V2 grouping workflow that receives S3 object keys (from BufferSignalsWorkflow)
    instead of raw signals. Downloads each batch from S3 and processes it via
    _process_signal_batch. S3 objects are cleaned up by lifecycle policies.

    Buffers pending object keys in memory. Calls continue_as_new after processing
    each batch, carrying over any remaining keys.

    One instance per team (workflow ID: team-signal-grouping-v2-{team_id}).
    """

    def __init__(self) -> None:
        self._batch_key_buffer: list[str] = []
        self._cached_type_examples: Optional[FetchSignalTypeExamplesOutput] = None
        self._type_examples_fetched_at: Optional[datetime] = None
        self._paused_until: Optional[datetime] = None

    @staticmethod
    def workflow_id_for(team_id: int) -> str:
        return f"team-signal-grouping-v2-{team_id}"

    @temporalio.workflow.signal
    async def submit_batch(self, object_key: str) -> None:
        """Receive an S3 object key containing a batch of signals."""
        self._batch_key_buffer.append(object_key)

    @temporalio.workflow.signal
    async def set_paused_until(self, timestamp: datetime) -> None:
        self._paused_until = timestamp

    @temporalio.workflow.signal
    async def clear_paused(self) -> None:
        self._paused_until = None

    @temporalio.workflow.query
    def get_paused_state(self) -> Optional[datetime]:
        return self._paused_until

    def _is_paused(self) -> bool:
        return self._paused_until is not None and workflow.now() < self._paused_until

    @temporalio.workflow.run
    async def run(self, input: TeamSignalGroupingV2Input) -> None:
        # Restore any keys carried over from continue_as_new
        self._batch_key_buffer.extend(input.pending_batch_keys)
        self._paused_until = input.paused_until
        pause_started_at = workflow.now() if self._is_paused() else None

        while True:
            # While paused, sleep in short intervals
            if self._is_paused():
                if pause_started_at is None:
                    pause_started_at = workflow.now()

                # continue_as_new if paused for too long to keep history bounded
                if (workflow.now() - pause_started_at) > timedelta(minutes=PAUSE_MAX_CONTINUE_AS_NEW_MINUTES):
                    workflow.continue_as_new(
                        TeamSignalGroupingV2Input(
                            team_id=input.team_id,
                            pending_batch_keys=list(self._batch_key_buffer),
                            paused_until=self._paused_until,
                        )
                    )

                await workflow.wait_condition(lambda: not self._is_paused(), timeout=timedelta(seconds=PAUSE_SLEEP_SECONDS))
                continue

            pause_started_at = None

            # Wait for at least one batch key
            await workflow.wait_condition(lambda: len(self._batch_key_buffer) > 0 or self._is_paused())

            # Re-check pause after waking
            if self._is_paused():
                continue

            # Pop the next key
            object_key = self._batch_key_buffer.pop(0)

            # Download the batch from S3
            read_result: ReadSignalsFromS3Output = await workflow.execute_activity(
                read_signals_from_s3_activity,
                ReadSignalsFromS3Input(object_key=object_key),
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            signals: list[EmitSignalInputs] = read_result.signals

            # Invalidate type examples cache if stale
            now = workflow.now()
            cached = self._cached_type_examples
            if (
                self._type_examples_fetched_at is not None
                and (now - self._type_examples_fetched_at) > TYPE_EXAMPLES_CACHE_TTL
            ):
                cached = None

            try:
                dropped, type_examples = await _process_signal_batch(signals, cached_type_examples=cached)
                self._cached_type_examples = type_examples
                self._type_examples_fetched_at = self._type_examples_fetched_at if cached is not None else now
            except Exception:
                workflow.logger.exception(
                    "Failed to process signal batch",
                    team_id=input.team_id,
                    batch_size=len(signals),
                    object_key=object_key,
                )

            # continue_as_new after each batch to keep history bounded.
            # Carry over any pending keys that arrived while we were processing.
            workflow.continue_as_new(
                TeamSignalGroupingV2Input(
                    team_id=input.team_id,
                    pending_batch_keys=list(self._batch_key_buffer),
                    paused_until=self._paused_until,
                )
            )

    @classmethod
    async def pause_until(cls, team_id: int, timestamp: datetime) -> None:
        client = await async_connect()
        await client.start_workflow(
            cls.run,
            TeamSignalGroupingV2Input(team_id=team_id),
            id=cls.workflow_id_for(team_id),
            task_queue=settings.VIDEO_EXPORT_TASK_QUEUE,
            run_timeout=timedelta(hours=3),
            start_signal="set_paused_until",
            start_signal_args=[timestamp],
        )

    @classmethod
    async def unpause(cls, team_id: int) -> bool:
        client = await async_connect()
        # Query current state to determine if it was actually paused
        was_paused = False
        try:
            handle = client.get_workflow_handle(cls.workflow_id_for(team_id))
            state = await handle.query(cls.get_paused_state)
            was_paused = state is not None and state > datetime.now(tz=UTC)
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND:
                return False
            raise

        await client.start_workflow(
            cls.run,
            TeamSignalGroupingV2Input(team_id=team_id),
            id=cls.workflow_id_for(team_id),
            task_queue=settings.VIDEO_EXPORT_TASK_QUEUE,
            run_timeout=timedelta(hours=3),
            start_signal="clear_paused",
            start_signal_args=[],
        )
        return was_paused

    @classmethod
    async def paused_state(cls, team_id: int) -> Optional[datetime]:
        client = await async_connect()
        try:
            handle = client.get_workflow_handle(cls.workflow_id_for(team_id))
            return await handle.query(cls.get_paused_state)
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND:
                return None
            raise
