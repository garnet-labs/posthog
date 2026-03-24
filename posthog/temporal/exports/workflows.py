import json
import traceback
import dataclasses
from datetime import timedelta
from typing import Optional

import temporalio.workflow as wf
from temporalio.exceptions import ActivityError, ApplicationError

from posthog.event_usage import EventSource
from posthog.slo.types import SloConfig
from posthog.temporal.common.base import PostHogWorkflow
from posthog.temporal.exports.activities import export_asset_activity
from posthog.temporal.exports.retry_policy import EXPORT_RETRY_POLICY
from posthog.temporal.exports.types import ExportAssetActivityInputs


@dataclasses.dataclass
class ExportAssetWorkflowInputs:
    exported_asset_id: int
    team_id: int
    distinct_id: str = ""
    export_format: Optional[str] = None
    slo: SloConfig | None = None


@wf.defn(name="export-asset")
class ExportAssetWorkflow(PostHogWorkflow):
    """One-off export workflow: export a single asset with durable retry."""

    @staticmethod
    def parse_inputs(inputs: list[str]) -> ExportAssetWorkflowInputs:
        loaded = json.loads(inputs[0])
        return ExportAssetWorkflowInputs(**loaded)

    @wf.run
    async def run(self, inputs: ExportAssetWorkflowInputs) -> None:
        if inputs.slo:
            inputs.slo.completion_properties["export_format"] = inputs.export_format or ""

        try:
            await wf.execute_activity(
                export_asset_activity,
                ExportAssetActivityInputs(
                    exported_asset_id=inputs.exported_asset_id,
                    source=EventSource.EXPORT,
                ),
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=EXPORT_RETRY_POLICY,
            )
        except Exception as e:
            if inputs.slo:
                cause = e.cause if isinstance(e, ActivityError) and isinstance(e.cause, ApplicationError) else None
                if isinstance(cause, ApplicationError) and cause.details:
                    inputs.slo.completion_properties["error"] = {
                        "exception_class": cause.details[0] if len(cause.details) >= 1 else type(e).__name__,
                        "error_trace": cause.details[4] if len(cause.details) >= 5 else "",
                    }
                else:
                    inputs.slo.completion_properties["error"] = {
                        "exception_class": type(e).__name__,
                        "error_trace": "\n".join(traceback.format_exception(e)[:5]),
                    }
            raise
