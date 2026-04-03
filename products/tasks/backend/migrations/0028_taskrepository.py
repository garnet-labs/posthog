import django.db.models.deletion
from django.db import migrations, models

import posthog.models.utils


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "0901_add_object_property_type"),
        ("tasks", "0027_task_signal_report_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskRepository",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=posthog.models.utils.uuid7, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("repository", models.CharField(max_length=400)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "github_integration",
                    models.ForeignKey(
                        blank=True,
                        limit_choices_to={"kind": "github"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="posthog.integration",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="task_repositories",
                        to="tasks.task",
                    ),
                ),
            ],
            options={
                "db_table": "posthog_task_repository",
            },
        ),
    ]
