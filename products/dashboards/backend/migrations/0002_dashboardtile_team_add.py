import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0001_migrate_dashboards_models"),
        ("posthog", "1079_event_filter_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboardtile",
            name="team",
            field=models.ForeignKey(
                null=True,
                db_index=False,
                on_delete=django.db.models.deletion.CASCADE,
                to="posthog.team",
            ),
        ),
    ]
