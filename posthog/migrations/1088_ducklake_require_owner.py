from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1087_alertconfiguration_schedule_restriction"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="ducklakecatalog",
            constraint=models.CheckConstraint(
                check=models.Q(team__isnull=False) | models.Q(organization__isnull=False),
                name="ducklakecatalog_has_owner",
            ),
        ),
        migrations.AddConstraint(
            model_name="duckgresserver",
            constraint=models.CheckConstraint(
                check=models.Q(team__isnull=False) | models.Q(organization__isnull=False),
                name="duckgresserver_has_owner",
            ),
        ),
    ]
