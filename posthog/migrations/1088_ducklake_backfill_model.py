import django.db.models.deletion
from django.db import migrations, models

import posthog.models.utils


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1087_alertconfiguration_schedule_restriction"),
    ]

    operations = [
        migrations.CreateModel(
            name="DuckLakeBackfill",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=posthog.models.utils.UUIDT,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "team",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ducklake_backfill",
                        to="posthog.team",
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Whether warehouse backfills are enabled for this team",
                    ),
                ),
            ],
            options={
                "db_table": "posthog_ducklakebackfill",
                "verbose_name": "DuckLake backfill",
                "verbose_name_plural": "DuckLake backfills",
            },
        ),
    ]
