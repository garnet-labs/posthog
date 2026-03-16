import django.db.models.deletion
import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1047_dashboard_quick_filter_ids"),
        ("tasks", "0024_task_title_manually_set"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeamCodeConfig",
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
                (
                    "relevant_repositories",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        blank=True,
                        default=list,
                        help_text="List of relevant repository full names in org/repo format, e.g. posthog/posthog",
                        size=None,
                    ),
                ),
            ],
            options={
                "db_table": "posthog_team_code_config",
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
                    ("slack", "Slack"),
                    ("support_queue", "Support Queue"),
                    ("session_summaries", "Session Summaries"),
                    ("data_management", "Data Management"),
                ],
                max_length=20,
            ),
        ),
    ]
