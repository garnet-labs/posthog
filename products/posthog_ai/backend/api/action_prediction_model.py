from django.conf import settings
from django.db.models import QuerySet

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from posthog.schema import ProductKey

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.api.shared import UserBasicSerializer
from posthog.storage import object_storage

from ..models import ActionPredictionModel

PRESIGNED_URL_EXPIRATION_SECONDS = 3600  # 1 hour


class _ActionPredictionModelFieldsMixin(serializers.ModelSerializer):
    created_by = UserBasicSerializer(
        read_only=True,
        allow_null=True,
        help_text="User who created this model.",
    )
    model_url = serializers.CharField(
        max_length=2000,
        help_text="S3 storage path to the serialized model artifact. Must be a storage path "
        "(e.g. from action-prediction-config-upload-url's storage_path field), not a presigned URL.",
    )
    prediction_status = serializers.SerializerMethodField(
        help_text="Current prediction status: not_started, queued, in_progress, completed, failed, cancelled, or null if no prediction run.",
    )
    model_download_url = serializers.SerializerMethodField(
        help_text="Presigned download URL for the model artifact. Docker-accessible in local dev.",
    )

    def validate_model_url(self, value: str) -> str:
        if value.startswith(("http://", "https://")):
            raise serializers.ValidationError(
                "model_url must be an S3 storage path, not a full URL. "
                "Use the storage_path returned by action-prediction-config-upload-url."
            )
        return value

    def get_prediction_status(self, obj: ActionPredictionModel) -> str | None:
        if obj.task_run_id is None:
            return None
        return obj.task_run.status

    def get_model_download_url(self, obj: ActionPredictionModel) -> str | None:
        if not obj.model_url:
            return None
        url = object_storage.get_presigned_url(
            file_key=obj.model_url,
            expiration=PRESIGNED_URL_EXPIRATION_SECONDS,
        )
        if url and settings.DEBUG:
            url = url.replace("://localhost:", "://host.docker.internal:")
        return url


class ActionPredictionModelListSerializer(_ActionPredictionModelFieldsMixin):
    class Meta:
        model = ActionPredictionModel
        fields = [
            "id",
            "config",
            "experiment_id",
            "model_url",
            "model_download_url",
            "metrics",
            "task_run",
            "prediction_status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "model_download_url",
            "task_run",
            "prediction_status",
            "created_by",
            "created_at",
            "updated_at",
        ]


class ActionPredictionModelSerializer(_ActionPredictionModelFieldsMixin):
    class Meta:
        model = ActionPredictionModel
        fields = [
            "id",
            "config",
            "experiment_id",
            "model_url",
            "model_download_url",
            "metrics",
            "feature_importance",
            "artifact_scripts",
            "notes",
            "task_run",
            "prediction_status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "model_download_url",
            "task_run",
            "prediction_status",
            "created_by",
            "created_at",
            "updated_at",
        ]


class PredictRequestSerializer(serializers.Serializer):
    prompt = serializers.CharField(
        help_text="Instructions for the prediction agent describing what to do with the model, "
        "e.g. 'score all users and write person properties', 'run a simulation for the next 30 days', "
        "'predict which users will churn this week'.",
    )


@extend_schema(tags=[ProductKey.MAX])
class ActionPredictionModelViewSet(TeamAndOrgViewSetMixin, viewsets.ModelViewSet):
    scope_object = "action_prediction_model"
    scope_object_write_actions = ["create", "update", "partial_update", "patch", "predict"]
    queryset = ActionPredictionModel.objects.all()
    serializer_class = ActionPredictionModelSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "list":
            return ActionPredictionModelListSerializer
        return ActionPredictionModelSerializer

    def safely_get_queryset(self, queryset: QuerySet) -> QuerySet:
        qs = queryset.filter(team_id=self.team_id).select_related("created_by", "task_run").order_by("-created_at")

        config = self.request.query_params.get("config")
        if config:
            qs = qs.filter(config_id=config)

        experiment_id = self.request.query_params.get("experiment_id")
        if experiment_id:
            qs = qs.filter(experiment_id=experiment_id)

        return qs

    def perform_create(self, serializer: ActionPredictionModelSerializer) -> None:
        serializer.save(team_id=self.team_id, created_by=self.request.user)

    @extend_schema(
        request=PredictRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=ActionPredictionModelSerializer, description="Model with prediction task started"
            ),
            400: OpenApiResponse(description="Model has no model_url or artifact_scripts"),
        },
        summary="Run a prediction task using this trained model",
        description="Creates a sandboxed agent task that uses the trained model to execute "
        "the instructions in the prompt. The agent has access to the model's artifact_scripts "
        "(predict script, utils, query) and can score users, run simulations, or perform "
        "other prediction tasks.",
    )
    @action(detail=True, methods=["post"], url_path="predict")
    def predict(self, request, pk=None, **kwargs):
        from products.tasks.backend.models import Task

        request_serializer = PredictRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        prompt = request_serializer.validated_data["prompt"]

        instance = self.get_object()

        if not instance.model_url:
            return Response(
                {"detail": "Model has no model_url. Train the model first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not instance.artifact_scripts or "predict" not in instance.artifact_scripts:
            return Response(
                {"detail": "Model has no predict script in artifact_scripts. Train the model first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config = instance.config
        model_name = config.name or config.event_name or "unnamed"

        description = (
            f"/predicting-user-actions Score users using the trained model {instance.id} "
            f"for config {config.id}. The model's artifact_scripts contain the predict script, "
            f"utils, and query needed for scoring. Load the winning model, adapt the training "
            f"query for scoring (T=now(), no label column), run the prediction, and write "
            f"results as person properties and $ai_prediction events. Before running the prediction, you must use query-examples skill to get the query examples. Optionally, read the training-action-predictions skill to get the training scripts examples."
            f" To download the model artifact, retrieve the model via action-prediction-model-retrieve"
            f" and use the model_download_url field (a fresh presigned URL)."
            f"\n\nAdditional instructions: {prompt}"
        )

        task = Task.create_and_run(
            team=self.team,
            title=f"Predict: {model_name}",
            description=description,
            origin_product=Task.OriginProduct.USER_CREATED,
            user_id=request.user.id,
            repository=None,
            create_pr=False,
            mode="background",
            posthog_mcp_scopes="full",
        )

        task_run = task.latest_run
        if task_run:
            instance.task_id = task.id
            instance.task_run_id = task_run.id
            instance.save(update_fields=["task_id", "task_run_id"])

        serializer = self.get_serializer(instance)
        return Response(serializer.data)
