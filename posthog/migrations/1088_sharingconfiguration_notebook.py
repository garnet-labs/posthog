# Generated manually for SharingConfiguration.notebook

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notebooks", "0003_add_kernel_timeouts"),
        ("posthog", "1087_alertconfiguration_schedule_restriction"),
    ]

    operations = [
        migrations.AddField(
            model_name="sharingconfiguration",
            name="notebook",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="notebooks.notebook",
            ),
        ),
    ]
