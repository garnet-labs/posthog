from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets

from posthog.schema import ProductKey

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.api.shared import UserBasicSerializer

from ..models import ActionPredictionModel


class ActionPredictionModelSerializer(serializers.ModelSerializer):
    created_by = UserBasicSerializer(read_only=True)
    lookback_days = serializers.IntegerField(
        min_value=1,
        help_text="Number of days to look back for prediction data.",
    )
    name = serializers.CharField(
        max_length=400,
        required=False,
        allow_blank=True,
        help_text="Human-readable name for the prediction model.",
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Longer description of the prediction model's purpose.",
    )
    event_name = serializers.CharField(
        max_length=400,
        required=False,
        allow_null=True,
        help_text="Name of the raw event to predict. Mutually exclusive with action.",
    )

    class Meta:
        model = ActionPredictionModel
        fields = [
            "id",
            "name",
            "description",
            "action",
            "event_name",
            "lookback_days",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]
        extra_kwargs = {
            "action": {
                "required": False,
                "allow_null": True,
                "help_text": "ID of the PostHog action to predict. Mutually exclusive with event_name.",
            },
        }

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
        validated_data["team_id"] = self.context["team_id"]
        request = self.context["request"]
        validated_data["created_by"] = request.user
        return super().create(validated_data)


@extend_schema(tags=[ProductKey.MAX])
class ActionPredictionModelViewSet(TeamAndOrgViewSetMixin, viewsets.ModelViewSet):
    scope_object = "action_prediction_model"
    queryset = ActionPredictionModel.objects.select_related("action", "created_by").all()
    serializer_class = ActionPredictionModelSerializer

    def safely_get_queryset(self, queryset):
        return queryset.filter(team_id=self.team.id)
