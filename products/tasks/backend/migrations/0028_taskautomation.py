import uuid

import django.utils.timezone
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1066_alter_insight_saved"),
        ("tasks", "0027_task_signal_report_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskAutomation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("prompt", models.TextField()),
                ("repository", models.CharField(max_length=255)),
                ("schedule_hour", models.PositiveSmallIntegerField()),
                ("schedule_minute", models.PositiveSmallIntegerField(default=0)),
                ("timezone", models.CharField(default="UTC", max_length=128)),
                ("template_id", models.CharField(blank=True, max_length=255, null=True)),
                ("enabled", models.BooleanField(default=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_run_status",
                    models.CharField(
                        blank=True,
                        choices=[("success", "Success"), ("failed", "Failed"), ("running", "Running")],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("last_error", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="posthog.user"
                    ),
                ),
                (
                    "github_integration",
                    models.ForeignKey(
                        blank=True,
                        help_text="GitHub integration for this automation",
                        limit_choices_to={"kind": "github"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="posthog.integration",
                    ),
                ),
                (
                    "last_task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="tasks.task",
                    ),
                ),
                (
                    "last_task_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="tasks.taskrun",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="task_automations", to="posthog.team"
                    ),
                ),
            ],
            options={
                "db_table": "posthog_task_automation",
                "ordering": ["name", "-created_at"],
            },
        ),
        migrations.AlterField(
            model_name="task",
            name="origin_product",
            field=models.CharField(
                choices=[
                    ("error_tracking", "Error Tracking"),
                    ("eval_clusters", "Eval Clusters"),
                    ("user_created", "User Created"),
                    ("automation", "Automation"),
                    ("slack", "Slack"),
                    ("support_queue", "Support Queue"),
                    ("session_summaries", "Session Summaries"),
                    ("signal_report", "Signal Report"),
                ],
                max_length=20,
            ),
        ),
    ]
