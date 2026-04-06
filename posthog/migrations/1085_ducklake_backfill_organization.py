from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1084_ducklake_add_organization_fk"),
    ]

    operations = [
        # Backfill organization_id from team.organization_id for existing rows.
        # These are tiny tables (single-digit rows) so a simple UPDATE is safe.
        migrations.RunSQL(
            sql="""
                UPDATE posthog_ducklakecatalog
                SET organization_id = t.organization_id
                FROM posthog_team t
                WHERE posthog_ducklakecatalog.team_id = t.id
                  AND posthog_ducklakecatalog.organization_id IS NULL
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                UPDATE posthog_duckgresserver
                SET organization_id = t.organization_id
                FROM posthog_team t
                WHERE posthog_duckgresserver.team_id = t.id
                  AND posthog_duckgresserver.organization_id IS NULL
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
