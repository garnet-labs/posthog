import logging

from django.contrib.postgres.fields import ArrayField
from django.db import models

from posthog.models.team import Team
from posthog.models.team.extensions import register_team_extension_signal

logger = logging.getLogger(__name__)


class TeamCodeConfig(models.Model):
    team = models.OneToOneField(Team, on_delete=models.CASCADE, primary_key=True)

    relevant_repositories = ArrayField(
        models.CharField(max_length=255),
        default=list,
        blank=True,
        help_text="List of relevant repository full names in org/repo format, e.g. posthog/posthog",
    )

    class Meta:
        app_label = "tasks"
        db_table = "posthog_team_code_config"


register_team_extension_signal(TeamCodeConfig, logger=logger)
