from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("ee", "0041_migrate_dashboards_models"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="conversation",
            index=models.Index(fields=["team", "user", "-updated_at"], name="ee_conv_team_user_upd_idx"),
        ),
    ]
