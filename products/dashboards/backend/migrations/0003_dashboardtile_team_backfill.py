from django.db import migrations


def backfill_team_id(apps, schema_editor):
    DashboardTile = apps.get_model("dashboards", "DashboardTile")
    batch_size = 1000
    to_update = []
    for tile in (
        DashboardTile.objects.filter(team_id__isnull=True).select_related("dashboard").iterator(chunk_size=batch_size)
    ):
        tile.team_id = tile.dashboard.team_id
        to_update.append(tile)
        if len(to_update) >= batch_size:
            DashboardTile.objects.bulk_update(to_update, ["team_id"])
            to_update = []
    if to_update:
        DashboardTile.objects.bulk_update(to_update, ["team_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0002_dashboardtile_team_add"),
    ]

    operations = [
        migrations.RunPython(backfill_team_id, migrations.RunPython.noop, elidable=True),
    ]
