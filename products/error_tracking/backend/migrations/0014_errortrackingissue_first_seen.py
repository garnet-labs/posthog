from django.db import migrations, models


def backfill_first_seen(apps, schema_editor):
    ErrorTrackingIssue = apps.get_model("error_tracking", "ErrorTrackingIssue")
    ErrorTrackingIssueFingerprintV2 = apps.get_model("error_tracking", "ErrorTrackingIssueFingerprintV2")

    # Batch update issues with MIN(first_seen) from their fingerprints
    issues_to_update = []
    for issue in ErrorTrackingIssue.objects.filter(first_seen__isnull=True).iterator(chunk_size=1000):
        min_first_seen = (
            ErrorTrackingIssueFingerprintV2.objects.filter(issue_id=issue.id)
            .aggregate(min_first_seen=models.Min("first_seen"))
            .get("min_first_seen")
        )
        if min_first_seen:
            issue.first_seen = min_first_seen
            issues_to_update.append(issue)

        if len(issues_to_update) >= 1000:
            ErrorTrackingIssue.objects.bulk_update(issues_to_update, ["first_seen"])
            issues_to_update = []

    if issues_to_update:
        ErrorTrackingIssue.objects.bulk_update(issues_to_update, ["first_seen"])


class Migration(migrations.Migration):
    dependencies = [
        ("error_tracking", "0013_spike_events"),
    ]

    operations = [
        migrations.AddField(
            model_name="errortrackingissue",
            name="first_seen",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_first_seen, reverse_code=migrations.RunPython.noop),
    ]
