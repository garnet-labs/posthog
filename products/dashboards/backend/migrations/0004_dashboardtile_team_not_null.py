import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0003_dashboardtile_team_backfill"),
    ]

    operations = [
        # 1. Add NOT NULL check without validating existing rows (instant)
        migrations.RunSQL(
            sql="""
                ALTER TABLE posthog_dashboardtile
                ADD CONSTRAINT dashboardtile_team_id_not_null
                CHECK (team_id IS NOT NULL) NOT VALID
            """,
            reverse_sql="ALTER TABLE posthog_dashboardtile DROP CONSTRAINT IF EXISTS dashboardtile_team_id_not_null",
        ),
        # 2. Validate existing rows (SHARE UPDATE EXCLUSIVE lock — allows reads/writes)
        migrations.RunSQL(
            sql="ALTER TABLE posthog_dashboardtile VALIDATE CONSTRAINT dashboardtile_team_id_not_null",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # 3. Add real NOT NULL (instant — Postgres skips the scan thanks to the validated CHECK)
        #    then drop the now-redundant CHECK constraint.
        #    SeparateDatabaseAndState keeps Django state in sync.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="dashboardtile",
                    name="team",
                    field=models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="posthog.team",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE posthog_dashboardtile ALTER COLUMN team_id SET NOT NULL;
                        ALTER TABLE posthog_dashboardtile DROP CONSTRAINT IF EXISTS dashboardtile_team_id_not_null;
                    """,
                    reverse_sql="ALTER TABLE posthog_dashboardtile ALTER COLUMN team_id DROP NOT NULL",
                ),
            ],
        ),
    ]
