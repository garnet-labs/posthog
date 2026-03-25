from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1067_add_dashboardtemplate_is_featured"),
    ]

    operations = [
        migrations.RunSQL(
            """
            UPDATE posthog_featureflag
            SET filters = jsonb_set(filters, '{feature_enrollment}', 'true')
            WHERE
                deleted = false
                AND filters ? 'super_groups'
                AND filters->>'super_groups' IS NOT NULL
                AND filters->>'super_groups' != 'null'
                AND jsonb_typeof(filters->'super_groups') = 'array'
                AND jsonb_array_length(filters->'super_groups') > 0
                AND (
                    NOT filters ? 'feature_enrollment'
                    OR filters->>'feature_enrollment' != 'true'
                );
            """,
            reverse_sql=migrations.RunSQL.noop,
            elidable=True,
        ),
    ]
