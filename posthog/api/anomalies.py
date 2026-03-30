from datetime import UTC, datetime, timedelta

from django.db.models import Q, QuerySet

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.models.anomaly import AnomalyScore, InsightAnomalyConfig


class AnomalyScoreSerializer(serializers.ModelSerializer):
    insight_name = serializers.SerializerMethodField(help_text="Name of the insight this anomaly belongs to.")
    insight_short_id = serializers.SerializerMethodField(help_text="Short ID for building insight URLs.")

    class Meta:
        model = AnomalyScore
        fields = [
            "id",
            "insight_id",
            "insight_name",
            "insight_short_id",
            "series_index",
            "series_label",
            "timestamp",
            "score",
            "is_anomalous",
            "interval",
            "data_snapshot",
            "scored_at",
        ]
        read_only_fields = fields

    def get_insight_name(self, obj: AnomalyScore) -> str:
        insight = obj.insight
        return insight.name or insight.derived_name or f"Insight {insight.short_id}"

    def get_insight_short_id(self, obj: AnomalyScore) -> str:
        return obj.insight.short_id


WINDOW_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


class AnomalyViewSet(TeamAndOrgViewSetMixin, viewsets.GenericViewSet):
    """Anomaly detection scores for time-series insights."""

    scope_object = "INTERNAL"
    serializer_class = AnomalyScoreSerializer

    def safely_get_queryset(self, queryset: QuerySet | None = None) -> QuerySet:
        return (
            AnomalyScore.objects.filter(team_id=self.team_id).select_related("insight").order_by("-score", "-scored_at")
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="window",
                type=str,
                required=False,
                description="Time window for anomaly scores: 24h, 7d, 30d. Default: 7d.",
            ),
            OpenApiParameter(
                name="min_score",
                type=float,
                required=False,
                description="Minimum anomaly score (0-1). Default: 0 (show all).",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                required=False,
                description="Search insight name or series label.",
            ),
            OpenApiParameter(
                name="interval",
                type=str,
                required=False,
                description="Filter by insight interval: hour, day, week, month.",
            ),
            OpenApiParameter(
                name="anomalous_only",
                type=bool,
                required=False,
                description="Only return anomalous scores. Default: true.",
            ),
        ],
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        queryset = self.safely_get_queryset()

        # Window filter
        window = request.query_params.get("window", "7d")
        delta = WINDOW_DELTAS.get(window, timedelta(days=7))
        cutoff = datetime.now(UTC) - delta
        queryset = queryset.filter(scored_at__gte=cutoff)

        # Min score filter
        min_score = request.query_params.get("min_score")
        if min_score:
            try:
                queryset = queryset.filter(score__gte=float(min_score))
            except (ValueError, TypeError):
                pass

        # Anomalous only (default true)
        anomalous_only = request.query_params.get("anomalous_only", "true").lower()
        if anomalous_only in ("true", "1", "yes"):
            queryset = queryset.filter(is_anomalous=True)

        # Search
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(insight__name__icontains=search) | Q(series_label__icontains=search))

        # Interval filter
        interval = request.query_params.get("interval")
        if interval and interval in ("hour", "day", "week", "month"):
            queryset = queryset.filter(interval=interval)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset[:100], many=True)
        return Response(serializer.data)

    @action(methods=["POST"], detail=False, url_path="exclude")
    def exclude(self, request: Request, *args, **kwargs) -> Response:
        """Exclude an insight from anomaly scoring."""
        insight_id = request.data.get("insight_id")
        if not insight_id:
            return Response({"detail": "insight_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        config, _ = InsightAnomalyConfig.objects.update_or_create(
            team_id=self.team_id,
            insight_id=insight_id,
            defaults={"excluded": True},
        )
        return Response({"status": "excluded", "insight_id": insight_id})

    @action(methods=["POST"], detail=False, url_path="include")
    def include(self, request: Request, *args, **kwargs) -> Response:
        """Re-include a previously excluded insight in anomaly scoring."""
        insight_id = request.data.get("insight_id")
        if not insight_id:
            return Response({"detail": "insight_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        updated = InsightAnomalyConfig.objects.filter(
            team_id=self.team_id,
            insight_id=insight_id,
        ).update(excluded=False, next_score_due_at=None)

        if not updated:
            return Response({"detail": "No config found for this insight"}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "included", "insight_id": insight_id})
