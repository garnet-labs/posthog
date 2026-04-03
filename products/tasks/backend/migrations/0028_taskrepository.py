import django.db.models.deletion
from django.db import migrations, models


def forwards_func(apps, schema_editor):
    """Migrate existing Task.repository data into TaskRepository rows."""
    Task = apps.get_model("tasks", "Task")
    TaskRepository = apps.get_model("tasks", "TaskRepository")

    tasks_with_repo = Task.objects.filter(repository__isnull=False).exclude(repository="")
    batch = []
    for task in tasks_with_repo.iterator(chunk_size=1000):
        batch.append(
            TaskRepository(
                task=task,
                repository=task.repository,
                github_integration_id=task.github_integration_id,
            )
        )
        if len(batch) >= 1000:
            TaskRepository.objects.bulk_create(batch, ignore_conflicts=True)
            batch = []
    if batch:
        TaskRepository.objects.bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "0901_add_object_property_type"),
        ("tasks", "0027_task_signal_report_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskRepository",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
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
        migrations.RunPython(forwards_func, migrations.RunPython.noop, elidable=True),
    ]
