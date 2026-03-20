from django.db import transaction

from dateutil.parser import isoparse

from posthog.models.hog_flow.hog_flow import HogFlow

from products.workflows.backend.models.hog_flow_scheduled_run import HogFlowScheduledRun
from products.workflows.backend.utils.rrule_utils import compute_next_occurrences


def sync_schedule(hog_flow: HogFlow, team_id: int) -> None:
    """
    Manage the next pending HogFlowScheduledRun based on schedule_config.
    Deletes any existing pending run and creates a new one if the workflow is active.
    Called from the HogFlow post_save signal.
    """
    with transaction.atomic():
        # Lock existing pending runs to prevent concurrent duplicates
        pending = HogFlowScheduledRun.objects.select_for_update().filter(
            hog_flow=hog_flow, status=HogFlowScheduledRun.Status.PENDING
        )
        pending.delete()

        schedule_config = hog_flow.schedule_config
        if not schedule_config or hog_flow.status != HogFlow.State.ACTIVE:
            return

        rrule_str = schedule_config.get("rrule")
        starts_at_str = schedule_config.get("starts_at")
        tz = schedule_config.get("timezone", "UTC")

        if not rrule_str or not starts_at_str:
            return

        starts_at = isoparse(starts_at_str)
        occurrences = compute_next_occurrences(
            rrule_string=rrule_str,
            starts_at=starts_at,
            timezone_str=tz,
            count=1,
        )
        if occurrences:
            HogFlowScheduledRun.objects.create(
                team_id=team_id,
                hog_flow=hog_flow,
                run_at=occurrences[0],
                status=HogFlowScheduledRun.Status.PENDING,
            )
