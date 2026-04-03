from django.db import migrations


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
        ("tasks", "0028_taskrepository"),
    ]

    operations = [
        migrations.RunPython(forwards_func, migrations.RunPython.noop, elidable=True),
    ]
