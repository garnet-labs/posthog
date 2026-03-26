"""Django models for hogbot."""

from django.db import models

from posthog.models import Team
from posthog.models.utils import UUIDModel


class HogbotRuntime(UUIDModel):
    team = models.OneToOneField(Team, on_delete=models.CASCADE)

    latest_snapshot_external_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "posthog_hogbotruntime"
