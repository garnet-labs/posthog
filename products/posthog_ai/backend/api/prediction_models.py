from django.db.models import QuerySet

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets

from posthog.schema import ProductKey

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.api.shared import UserBasicSerializer

from ..models import ActionPredictionModelRun


class ActionPredictionModelRunSerializer(serializers.ModelSerializer):
    created_by = UserBasicSerializer(
        read_only=True,
        allow_null=True,
        help_text="User who created this run.",
    )

    class Meta:
        model = ActionPredictionModelRun
        fields = [
            "id",
            "prediction_model",
            "experiment_id",
            "model_url",
            "metrics",
            "feature_importance",
            "artifact_scripts",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


@extend_schema(tags=[ProductKey.MAX])
class ActionPredictionModelRunViewSet(TeamAndOrgViewSetMixin, viewsets.ModelViewSet):
    scope_object = "action_prediction_model"
    queryset = ActionPredictionModelRun.objects.all()
    serializer_class = ActionPredictionModelRunSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def safely_get_queryset(self, queryset: QuerySet) -> QuerySet:
        qs = queryset.filter(team_id=self.team_id).select_related("created_by").order_by("-created_at")

        # Filter by prediction model
        prediction_model = self.request.query_params.get("prediction_model")
        if prediction_model:
            qs = qs.filter(prediction_model_id=prediction_model)

        # Filter by experiment_id
        experiment_id = self.request.query_params.get("experiment_id")
        if experiment_id:
            qs = qs.filter(experiment_id=experiment_id)

        return qs

    def perform_create(self, serializer: ActionPredictionModelRunSerializer) -> None:
        serializer.save(team_id=self.team_id, created_by=self.request.user)
