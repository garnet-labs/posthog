from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("hogbot", "0001_initial")]

    operations = [
        migrations.RemoveField(model_name="hogbotruntime", name="active_workflow_id"),
        migrations.RemoveField(model_name="hogbotruntime", name="active_run_id"),
        migrations.RemoveField(model_name="hogbotruntime", name="sandbox_id"),
        migrations.RemoveField(model_name="hogbotruntime", name="server_url"),
        migrations.RemoveField(model_name="hogbotruntime", name="status"),
        migrations.RemoveField(model_name="hogbotruntime", name="last_error"),
    ]
