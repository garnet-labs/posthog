from django.db.models import QuerySet

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets

from posthog.schema import ProductKey

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.api.shared import UserBasicSerializer

from ..models import ActionPredictionModel


class ActionPredictionModelSerializer(serializers.ModelSerializer):
    created_by = UserBasicSerializer(
        read_only=True,
        allow_null=True,
        help_text="User who created this model.",
    )

    class Meta:
        model = ActionPredictionModel
        fields = [
            "id",
            "config",
            "experiment_id",
            "model_url",
            "metrics",
            "feature_importance",
            "artifact_scripts",
            "notes",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


@extend_schema(tags=[ProductKey.MAX])
class ActionPredictionModelViewSet(TeamAndOrgViewSetMixin, viewsets.ModelViewSet):
    scope_object = "action_prediction_model"
    queryset = ActionPredictionModel.objects.all()
    serializer_class = ActionPredictionModelSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def safely_get_queryset(self, queryset: QuerySet) -> QuerySet:
        qs = queryset.filter(team_id=self.team_id).select_related("created_by").order_by("-created_at")

        config = self.request.query_params.get("config")
        if config:
            qs = qs.filter(config_id=config)

        experiment_id = self.request.query_params.get("experiment_id")
        if experiment_id:
            qs = qs.filter(experiment_id=experiment_id)

        return qs

    def perform_create(self, serializer: ActionPredictionModelSerializer) -> None:
        serializer.save(team_id=self.team_id, created_by=self.request.user)
