from rest_framework import serializers, viewsets
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.models.event_filter_config import (
    DEFAULT_FILTER_TREE,
    EventFilterConfig,
    validate_filter_tree,
    validate_test_cases,
)


class EventFilterConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventFilterConfig
        fields = [
            "id",
            "enabled",
            "filter_tree",
            "test_cases",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_filter_tree(self, value: object) -> object:
        if value:
            validate_filter_tree(value)
        return value

    def validate_test_cases(self, value: object) -> object:
        if value:
            validate_test_cases(value)
        return value


class EventFilterConfigViewSet(TeamAndOrgViewSetMixin, viewsets.GenericViewSet):
    """
    Single event filter per team. Auto-creates on first access.
    GET  /event_filters/ — returns the config
    POST /event_filters/ — updates the config (upsert)
    """

    scope_object = "INTERNAL"
    serializer_class = EventFilterConfigSerializer
    queryset = EventFilterConfig.objects.all()

    def _get_or_create(self) -> EventFilterConfig:
        config, _ = EventFilterConfig.objects.get_or_create(
            team_id=self.team_id,
            defaults={"filter_tree": DEFAULT_FILTER_TREE, "enabled": False, "test_cases": []},
        )
        return config

    def list(self, request, **kwargs):
        config = self._get_or_create()
        serializer = self.get_serializer(config)
        return Response(serializer.data)

    def create(self, request, **kwargs):
        config = self._get_or_create()
        serializer = self.get_serializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
