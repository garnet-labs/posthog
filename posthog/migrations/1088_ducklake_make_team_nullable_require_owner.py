import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1087_alertconfiguration_schedule_restriction"),
    ]

    operations = [
        migrations.AlterField(
            model_name="duckgresserver",
            name="team",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="duckgres_server",
                to="posthog.team",
            ),
        ),
        migrations.AlterField(
            model_name="ducklakecatalog",
            name="team",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ducklake_catalog",
                to="posthog.team",
            ),
        ),
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
