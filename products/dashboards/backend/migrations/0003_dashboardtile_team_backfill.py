from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0002_dashboardtile_team_add"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                -- migration-analyzer: safe reason=single-pass join update, only row-level locks, no table lock
                UPDATE posthog_dashboardtile dt
                SET team_id = d.team_id
                FROM posthog_dashboard d
                WHERE dt.dashboard_id = d.id
                  AND dt.team_id IS NULL
            """,
            reverse_sql=migrations.RunSQL.noop,
            elidable=True,
        ),
    ]
