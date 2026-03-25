import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("posthog", "1066_alter_insight_saved"),
    ]

    operations = [
        migrations.CreateModel(
            name="HogbotRuntime",
            fields=[
                (
                    "team",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to="posthog.team",
                    ),
                ),
                ("latest_snapshot_external_id", models.CharField(blank=True, max_length=255, null=True)),
                ("active_workflow_id", models.CharField(blank=True, max_length=255, null=True)),
                ("active_run_id", models.CharField(blank=True, max_length=255, null=True)),
                ("sandbox_id", models.CharField(blank=True, max_length=255, null=True)),
                ("server_url", models.CharField(blank=True, max_length=1000, null=True)),
                ("status", models.CharField(default="idle", max_length=32)),
                ("last_error", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "posthog_hogbotruntime",
            },
        ),
    ]
