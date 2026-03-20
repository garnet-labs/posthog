from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("posthog", "1059_add_button_tile"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS "posthog_buttontile_created_by_id_bf09d147"
                            ON "posthog_buttontile" ("created_by_id");
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS "posthog_buttontile_last_modified_by_id_a5860b7a"
                            ON "posthog_buttontile" ("last_modified_by_id");
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS "posthog_buttontile_team_id_a76a940c"
                            ON "posthog_buttontile" ("team_id");
                        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "unique_dashboard_button_tile"
                            ON "posthog_dashboardtile" ("dashboard_id", "button_tile_id")
                            WHERE "button_tile_id" IS NOT NULL; -- not-null-ignore
                        ALTER TABLE "posthog_dashboardtile"
                            VALIDATE CONSTRAINT "dash_tile_exactly_one_related_object";
                    """,
                    reverse_sql="""
                        DROP INDEX IF EXISTS "unique_dashboard_button_tile";
                        DROP INDEX IF EXISTS "posthog_buttontile_team_id_a76a940c";
                        DROP INDEX IF EXISTS "posthog_buttontile_last_modified_by_id_a5860b7a";
                        DROP INDEX IF EXISTS "posthog_buttontile_created_by_id_bf09d147";
                    """,
                ),
            ],
        ),
    ]
