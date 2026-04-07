import django.db.models.deletion
from django.db import migrations, models

import posthog.models.utils


def backfill_from_catalogs(apps, schema_editor):
    """Create DuckLakeBackfill rows for existing DuckLakeCatalog entries."""
    DuckLakeCatalog = apps.get_model("posthog", "DuckLakeCatalog")
    DuckLakeBackfill = apps.get_model("posthog", "DuckLakeBackfill")

    backfills = [DuckLakeBackfill(team_id=catalog.team_id, enabled=True) for catalog in DuckLakeCatalog.objects.all()]
    if backfills:
        DuckLakeBackfill.objects.bulk_create(backfills, ignore_conflicts=True)


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
        migrations.RunPython(backfill_from_catalogs, migrations.RunPython.noop),
    ]
