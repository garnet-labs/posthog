from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1082_oauth_cimd_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="company_size",
            field=models.CharField(
                blank=True,
                choices=[
                    ("1", "Only me"),
                    ("2-10", "2-10"),
                    ("11-50", "11-50"),
                    ("51-200", "51-200"),
                    ("201-1000", "201-1,000"),
                    ("1001-5000", "1,001-5,000"),
                    ("5001+", "5,001+"),
                ],
                help_text="Self-reported company size collected during signup.",
                max_length=20,
                null=True,
            ),
        ),
    ]
