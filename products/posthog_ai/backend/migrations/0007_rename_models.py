import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0024_task_title_manually_set"),
        ("posthog", "1066_alter_insight_saved"),
        ("posthog_ai", "0006_actionpredictionmodel_task_run"),
    ]

    operations = [
        # 1. Rename ActionPredictionModel → ActionPredictionConfig
        migrations.RenameModel(
            old_name="ActionPredictionModel",
            new_name="ActionPredictionConfig",
        ),
        # 2. Rename ActionPredictionModelRun → ActionPredictionModel
        migrations.RenameModel(
            old_name="ActionPredictionModelRun",
            new_name="ActionPredictionModel",
        ),
        # 3. Rename FK field prediction_model → config
        migrations.RenameField(
            model_name="ActionPredictionModel",
            old_name="prediction_model",
            new_name="config",
        ),
        # 4. Update related_names on ActionPredictionConfig
        migrations.AlterField(
            model_name="ActionPredictionConfig",
            name="team",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="action_prediction_configs",
                to="posthog.team",
            ),
        ),
        migrations.AlterField(
            model_name="ActionPredictionConfig",
            name="task_run",
            field=models.ForeignKey(
                blank=True,
                help_text="Sandbox task run that trains this prediction config.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="action_prediction_configs",
                to="tasks.taskrun",
            ),
        ),
        # 5. Update related_names on ActionPredictionModel
        migrations.AlterField(
            model_name="ActionPredictionModel",
            name="team",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="action_prediction_models",
                to="posthog.team",
            ),
        ),
        migrations.AlterField(
            model_name="ActionPredictionModel",
            name="task_run",
            field=models.ForeignKey(
                blank=True,
                help_text="Specific task run that produced this model.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="action_prediction_models",
                to="tasks.taskrun",
            ),
        ),
        migrations.AlterField(
            model_name="ActionPredictionModel",
            name="config",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="models",
                to="posthog_ai.actionpredictionconfig",
            ),
        ),
        migrations.AlterField(
            model_name="ActionPredictionModel",
            name="is_winning",
            field=models.BooleanField(
                default=False,
                help_text="Whether this is the winning prediction model.",
            ),
        ),
        # 6. Fix indexes for renamed models/fields
        migrations.RemoveIndex(
            model_name="ActionPredictionModel",
            name="posthog_ai__predict_b99ec6_idx",
        ),
        migrations.AddIndex(
            model_name="ActionPredictionModel",
            index=models.Index(fields=["config", "-created_at"], name="posthog_ai__config__00c0cb_idx"),
        ),
        migrations.RenameIndex(
            model_name="actionpredictionconfig",
            new_name="posthog_ai__team_id_76fc68_idx",
            old_name="posthog_ai__team_id_07fd1e_idx",
        ),
        migrations.RenameIndex(
            model_name="actionpredictionmodel",
            new_name="posthog_ai__team_id_07fd1e_idx",
            old_name="posthog_ai__team_id_9f64e3_idx",
        ),
        # 7. Add task FK
        migrations.AddField(
            model_name="ActionPredictionModel",
            name="task",
            field=models.ForeignKey(
                blank=True,
                help_text="Task containing all training runs and snapshots for this model.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="action_prediction_models",
                to="tasks.task",
            ),
        ),
    ]
