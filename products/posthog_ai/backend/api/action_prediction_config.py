import uuid

from django.conf import settings

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from posthog.schema import ProductKey

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.api.shared import UserBasicSerializer
from posthog.storage import object_storage

from ..models import ActionPredictionConfig

PREDICTION_MODEL_MAX_ARTIFACT_BYTES = 500 * 1024 * 1024  # 500 MB
PRESIGNED_URL_EXPIRATION_SECONDS = 3600  # 1 hour


def _artifact_storage_path(team_id: int, model_id: str, filename: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    return f"{settings.OBJECT_STORAGE_TASKS_FOLDER}/prediction_models/{team_id}/{model_id}/{suffix}_{filename}"


class _ActionPredictionConfigFieldsMixin(serializers.ModelSerializer):
    created_by = UserBasicSerializer(read_only=True)
    training_status = serializers.SerializerMethodField(
        help_text="Current training status: not_started, queued, in_progress, completed, failed, cancelled, or null if no training run.",
    )
    lookback_days = serializers.IntegerField(
        min_value=1,
        help_text="Number of days to look back for prediction data.",
    )
    name = serializers.CharField(
        max_length=400,
        required=False,
        allow_blank=True,
        help_text="Human-readable name for the prediction config.",
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Longer description of the prediction config's purpose.",
    )
    event_name = serializers.CharField(
        max_length=400,
        required=False,
        allow_null=True,
        help_text="Name of the raw event to predict. Mutually exclusive with action.",
    )

    def get_training_status(self, obj: ActionPredictionConfig) -> str | None:
        if obj.task_run_id is None:
            return None
        return obj.task_run.status

    def get_fields(self):
        fields = super().get_fields()
        # Scope the action queryset to the current team
        if "action" in fields and hasattr(fields["action"], "queryset"):
            from posthog.models.action import Action

            try:
                team = self.context["get_team"]()
                fields["action"].queryset = Action.objects.filter(team=team, deleted=False)
            except KeyError:
                fields["action"].queryset = Action.objects.none()
        return fields


class ActionPredictionConfigListSerializer(_ActionPredictionConfigFieldsMixin):
    class Meta:
        model = ActionPredictionConfig
        fields = [
            "id",
            "name",
            "action",
            "event_name",
            "lookback_days",
            "task_run",
            "winning_model",
            "training_status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "task_run", "training_status", "created_by", "created_at", "updated_at"]
        extra_kwargs = {
            "action": {
                "required": False,
                "allow_null": True,
                "help_text": "ID of the PostHog action to predict. Mutually exclusive with event_name.",
            },
        }


class ActionPredictionConfigSerializer(_ActionPredictionConfigFieldsMixin):
    class Meta:
        model = ActionPredictionConfig
        fields = [
            "id",
            "name",
            "description",
            "action",
            "event_name",
            "lookback_days",
            "task_run",
            "winning_model",
            "training_status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "task_run", "training_status", "created_by", "created_at", "updated_at"]
        extra_kwargs = {
            "action": {
                "required": False,
                "allow_null": True,
                "help_text": "ID of the PostHog action to predict. Mutually exclusive with event_name.",
            },
        }

    def validate(self, attrs):
        action = attrs.get("action", self.instance.action if self.instance else None)
        event_name = attrs.get("event_name", self.instance.event_name if self.instance else None)

        # Handle explicit null assignments
        if "action" in attrs and attrs["action"] is None:
            action = None
        if "event_name" in attrs and attrs["event_name"] is None:
            event_name = None

        has_action = action is not None
        has_event = event_name is not None

        if has_action and has_event:
            raise serializers.ValidationError("Specify either 'action' or 'event_name', not both.")
        if not has_action and not has_event:
            raise serializers.ValidationError("One of 'action' or 'event_name' must be provided.")

        return attrs

    def create(self, validated_data):
        return super().create(validated_data)


class UploadURLResponseSerializer(serializers.Serializer):
    url = serializers.URLField(help_text="Presigned S3 POST URL to upload the file to.")
    fields = serializers.DictField(
        child=serializers.CharField(),
        help_text="Form fields to include with the POST request.",
    )
    storage_path = serializers.CharField(help_text="S3 storage path to use as model_url when creating a model.")


@extend_schema(tags=[ProductKey.MAX])
class ActionPredictionConfigViewSet(TeamAndOrgViewSetMixin, viewsets.ModelViewSet):
    scope_object = "action_prediction_model"
    scope_object_write_actions = ["create", "update", "partial_update", "patch", "destroy", "upload_url"]
    queryset = ActionPredictionConfig.objects.select_related("action", "created_by", "task_run").all()
    serializer_class = ActionPredictionConfigSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return ActionPredictionConfigListSerializer
        return ActionPredictionConfigSerializer

    def safely_get_queryset(self, queryset):
        return queryset.filter(team_id=self.team.id)

    def perform_create(self, serializer):
        from products.tasks.backend.models import Task

        instance = serializer.save(team_id=self.team_id, created_by=self.request.user)

        task = Task.create_and_run(
            team=self.team,
            title=f"Train prediction model: {instance.name or instance.event_name or 'unnamed'}",
            description=f"/training-action-predictions Train the model for the existing configuration {serializer.validated_data} (the ID is provided). You must read the query-examples skill to retrieve the data schema and query examples before doing any SQL queries.",
            origin_product=Task.OriginProduct.USER_CREATED,
            user_id=self.request.user.id,
            repository=None,
            create_pr=False,
            mode="background",
            posthog_mcp_scopes="full",
        )

        task_run = task.latest_run
        if task_run:
            instance.task_run = task_run
            instance.save(update_fields=["task_run"])

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(response=UploadURLResponseSerializer, description="Presigned upload URL"),
            400: OpenApiResponse(description="Object storage unavailable or invalid request"),
        },
        summary="Generate a presigned S3 upload URL for a model artifact",
        description="Returns a presigned POST URL that can be used to upload a model artifact "
        "directly to S3. Use the returned storage_path as model_url when creating an "
        "ActionPredictionModel.",
    )
    @action(detail=True, methods=["post"], url_path="upload_url")
    def upload_url(self, request, pk=None, **kwargs):
        config = self.get_object()
        storage_path = _artifact_storage_path(self.team_id, str(config.id), "model.pkl")

        presigned = object_storage.get_presigned_post(
            file_key=storage_path,
            conditions=[["content-length-range", 0, PREDICTION_MODEL_MAX_ARTIFACT_BYTES]],
            expiration=PRESIGNED_URL_EXPIRATION_SECONDS,
        )
        if not presigned:
            return Response(
                {"detail": "Object storage is not available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            UploadURLResponseSerializer(
                {
                    "url": presigned["url"],
                    "fields": presigned["fields"],
                    "storage_path": storage_path,
                }
            ).data
        )
