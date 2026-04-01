from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1081_alter_scheduledchange_failure_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="schema_validation_disabled",
            field=models.BooleanField(blank=True, default=False, null=True),
        ),
    ]
