from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("dashboards", "0004_dashboardtile_team_not_null"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="dashboardtile",
            index=models.Index(fields=["team_id"], name="posthog_dashboardtile_team_idx"),
        ),
    ]
