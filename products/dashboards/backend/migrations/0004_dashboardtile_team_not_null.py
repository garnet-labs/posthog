import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0003_dashboardtile_team_backfill"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dashboardtile",
            name="team",
            field=models.ForeignKey(
                db_index=False,
                on_delete=django.db.models.deletion.CASCADE,
                to="posthog.team",
            ),
        ),
    ]
