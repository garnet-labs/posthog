from datetime import UTC, datetime, timedelta

from posthog.test.base import APIBaseTest

from parameterized import parameterized
from rest_framework import status

from posthog.models.anomaly import AnomalyScore, InsightAnomalyConfig
from posthog.models.team import Team

ANOMALIES_URL = "/api/environments/{team_id}/anomalies/"
EXCLUDE_URL = "/api/environments/{team_id}/anomalies/exclude/"
INCLUDE_URL = "/api/environments/{team_id}/anomalies/include/"


def _make_score(
    team,
    insight,
    *,
    score: float = 0.9,
    is_anomalous: bool = True,
    series_index: int = 0,
    series_label: str = "",
    interval: str = "day",
    scored_at: datetime | None = None,
) -> AnomalyScore:
    """Helper that creates an AnomalyScore with sensible defaults."""
    obj = AnomalyScore.objects.create(
        team=team,
        insight=insight,
        series_index=series_index,
        series_label=series_label,
        timestamp=datetime.now(UTC),
        score=score,
        is_anomalous=is_anomalous,
        interval=interval,
    )
    if scored_at is not None:
        AnomalyScore.objects.filter(pk=obj.pk).update(scored_at=scored_at)
        obj.refresh_from_db()
    return obj


class TestAnomalyViewSet(APIBaseTest):
    def setUp(self):
        super().setUp()
        self.insight_a = self.client.post(
            f"/api/projects/{self.team.id}/insights",
            data={
                "name": "Pageview trends",
                "query": {
                    "kind": "TrendsQuery",
                    "series": [{"kind": "EventsNode", "event": "$pageview"}],
                },
            },
        ).json()
        self.insight_b = self.client.post(
            f"/api/projects/{self.team.id}/insights",
            data={
                "name": "Signup funnel",
                "query": {
                    "kind": "TrendsQuery",
                    "series": [{"kind": "EventsNode", "event": "$signup"}],
                },
            },
        ).json()
        self.base_url = ANOMALIES_URL.format(team_id=self.team.id)
        self.exclude_url = EXCLUDE_URL.format(team_id=self.team.id)
        self.include_url = INCLUDE_URL.format(team_id=self.team.id)

    # ------------------------------------------------------------------
    # List — happy path
    # ------------------------------------------------------------------

    def test_list_returns_anomaly_scores_for_team(self):
        score = _make_score(self.team, self._insight_obj(self.insight_a))
        response = self.client.get(self.base_url)

        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.json()["results"]]
        assert str(score.id) in ids

    def test_list_response_shape_contains_required_fields(self):
        _make_score(self.team, self._insight_obj(self.insight_a))
        response = self.client.get(self.base_url)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()["results"][0]
        for field in (
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
        ):
            assert field in result, f"Missing field: {field}"

    def test_list_insight_name_uses_insight_name_field(self):
        _make_score(self.team, self._insight_obj(self.insight_a))
        response = self.client.get(self.base_url)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()["results"][0]
        assert result["insight_name"] == "Pageview trends"

    def test_list_insight_short_id_matches_insight(self):
        _make_score(self.team, self._insight_obj(self.insight_a))
        response = self.client.get(self.base_url)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()["results"][0]
        assert result["insight_short_id"] == self.insight_a["short_id"]

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    def test_list_ordered_by_score_descending(self):
        insight_obj = self._insight_obj(self.insight_a)
        _make_score(self.team, insight_obj, score=0.5, series_index=0)
        _make_score(self.team, insight_obj, score=0.95, series_index=1)
        _make_score(self.team, insight_obj, score=0.7, series_index=2)

        response = self.client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        scores = [r["score"] for r in response.json()["results"]]
        assert scores == sorted(scores, reverse=True)

    # ------------------------------------------------------------------
    # Window filter
    # ------------------------------------------------------------------

    @parameterized.expand(
        [
            ("24h", timedelta(hours=24), timedelta(hours=25)),
            ("7d", timedelta(days=7), timedelta(days=8)),
            ("30d", timedelta(days=30), timedelta(days=31)),
        ]
    )
    def test_window_filter_excludes_scores_outside_window(self, window, inside_delta, outside_delta):
        now = datetime.now(UTC)
        insight_obj = self._insight_obj(self.insight_a)
        recent = _make_score(
            self.team, insight_obj, score=0.9, series_index=0, scored_at=now - inside_delta + timedelta(hours=1)
        )
        old = _make_score(self.team, insight_obj, score=0.8, series_index=1, scored_at=now - outside_delta)

        response = self.client.get(self.base_url, {"window": window})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(recent.id) in result_ids
        assert str(old.id) not in result_ids

    def test_window_filter_defaults_to_7d(self):
        now = datetime.now(UTC)
        insight_obj = self._insight_obj(self.insight_a)
        within = _make_score(self.team, insight_obj, score=0.9, series_index=0, scored_at=now - timedelta(days=6))
        outside = _make_score(self.team, insight_obj, score=0.8, series_index=1, scored_at=now - timedelta(days=8))

        response = self.client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(within.id) in result_ids
        assert str(outside.id) not in result_ids

    def test_unknown_window_defaults_to_7d(self):
        now = datetime.now(UTC)
        insight_obj = self._insight_obj(self.insight_a)
        within = _make_score(self.team, insight_obj, score=0.9, series_index=0, scored_at=now - timedelta(days=6))
        outside = _make_score(self.team, insight_obj, score=0.8, series_index=1, scored_at=now - timedelta(days=8))

        response = self.client.get(self.base_url, {"window": "bogus"})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(within.id) in result_ids
        assert str(outside.id) not in result_ids

    # ------------------------------------------------------------------
    # min_score filter
    # ------------------------------------------------------------------

    def test_min_score_filter_excludes_lower_scores(self):
        insight_obj = self._insight_obj(self.insight_a)
        high = _make_score(self.team, insight_obj, score=0.9, series_index=0)
        low = _make_score(self.team, insight_obj, score=0.3, series_index=1)

        response = self.client.get(self.base_url, {"min_score": "0.5"})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(high.id) in result_ids
        assert str(low.id) not in result_ids

    def test_min_score_filter_includes_exact_boundary(self):
        insight_obj = self._insight_obj(self.insight_a)
        at_boundary = _make_score(self.team, insight_obj, score=0.5, series_index=0)

        response = self.client.get(self.base_url, {"min_score": "0.5"})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(at_boundary.id) in result_ids

    def test_min_score_invalid_value_is_ignored(self):
        _make_score(self.team, self._insight_obj(self.insight_a))
        response = self.client.get(self.base_url, {"min_score": "not_a_number"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["results"]) >= 1

    # ------------------------------------------------------------------
    # anomalous_only filter
    # ------------------------------------------------------------------

    def test_anomalous_only_true_by_default_excludes_non_anomalous(self):
        insight_obj = self._insight_obj(self.insight_a)
        anomalous = _make_score(self.team, insight_obj, is_anomalous=True, series_index=0)
        normal = _make_score(self.team, insight_obj, is_anomalous=False, series_index=1)

        response = self.client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(anomalous.id) in result_ids
        assert str(normal.id) not in result_ids

    @parameterized.expand([("false", "false"), ("zero", "0"), ("no", "no")])
    def test_anomalous_only_false_includes_non_anomalous(self, _name, param_value):
        insight_obj = self._insight_obj(self.insight_a)
        anomalous = _make_score(self.team, insight_obj, is_anomalous=True, series_index=0)
        normal = _make_score(self.team, insight_obj, is_anomalous=False, series_index=1)

        response = self.client.get(self.base_url, {"anomalous_only": param_value})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(anomalous.id) in result_ids
        assert str(normal.id) in result_ids

    # ------------------------------------------------------------------
    # Search filter
    # ------------------------------------------------------------------

    def test_search_matches_insight_name(self):
        score_a = _make_score(self.team, self._insight_obj(self.insight_a))
        score_b = _make_score(self.team, self._insight_obj(self.insight_b))

        response = self.client.get(self.base_url, {"search": "Pageview"})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(score_a.id) in result_ids
        assert str(score_b.id) not in result_ids

    def test_search_is_case_insensitive(self):
        score = _make_score(self.team, self._insight_obj(self.insight_a))
        response = self.client.get(self.base_url, {"search": "pageview"})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(score.id) in result_ids

    def test_search_matches_series_label(self):
        insight_obj = self._insight_obj(self.insight_a)
        score = _make_score(self.team, insight_obj, series_label="revenue metric")
        unmatched = _make_score(self.team, insight_obj, series_label="unrelated", series_index=1)

        response = self.client.get(self.base_url, {"search": "revenue"})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(score.id) in result_ids
        assert str(unmatched.id) not in result_ids

    def test_search_with_no_match_returns_empty_results(self):
        _make_score(self.team, self._insight_obj(self.insight_a))
        response = self.client.get(self.base_url, {"search": "zzznomatch"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["results"] == []

    # ------------------------------------------------------------------
    # Interval filter
    # ------------------------------------------------------------------

    @parameterized.expand(
        [
            ("hour", "hour", "day"),
            ("day", "day", "week"),
            ("week", "week", "month"),
            ("month", "month", "hour"),
        ]
    )
    def test_interval_filter_returns_only_matching_interval(self, _name, matching_interval, other_interval):
        insight_obj = self._insight_obj(self.insight_a)
        matched = _make_score(self.team, insight_obj, interval=matching_interval, series_index=0)
        unmatched = _make_score(self.team, insight_obj, interval=other_interval, series_index=1)

        response = self.client.get(self.base_url, {"interval": matching_interval})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(matched.id) in result_ids
        assert str(unmatched.id) not in result_ids

    def test_interval_filter_invalid_value_is_ignored(self):
        _make_score(self.team, self._insight_obj(self.insight_a))
        response = self.client.get(self.base_url, {"interval": "bogus"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["results"]) >= 1

    # ------------------------------------------------------------------
    # Multi-team isolation
    # ------------------------------------------------------------------

    def test_list_does_not_return_scores_from_other_teams(self):
        other_team = Team.objects.create(
            organization=self.organization,
            api_token=self.CONFIG_API_TOKEN + "_other",
        )
        other_insight = self.client.post(
            f"/api/projects/{other_team.id}/insights",
            data={
                "query": {
                    "kind": "TrendsQuery",
                    "series": [{"kind": "EventsNode", "event": "$pageview"}],
                },
            },
        ).json()

        from posthog.models.insight import Insight

        other_insight_obj = Insight.objects.get(id=other_insight["id"])
        other_score = _make_score(other_team, other_insight_obj)
        own_score = _make_score(self.team, self._insight_obj(self.insight_a))

        response = self.client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(own_score.id) in result_ids
        assert str(other_score.id) not in result_ids

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def test_list_is_paginated(self):
        insight_obj = self._insight_obj(self.insight_a)
        for i in range(5):
            _make_score(self.team, insight_obj, series_index=i)

        response = self.client.get(self.base_url, {"limit": 2})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "next" in data
        assert len(data["results"]) == 2

    def test_pagination_next_page_returns_remaining_results(self):
        insight_obj = self._insight_obj(self.insight_a)
        for i in range(4):
            _make_score(self.team, insight_obj, series_index=i)

        first_page = self.client.get(self.base_url, {"limit": 2}).json()
        assert first_page["next"] is not None
        second_page = self.client.get(first_page["next"]).json()
        assert len(second_page["results"]) == 2

    # ------------------------------------------------------------------
    # Exclude action
    # ------------------------------------------------------------------

    def test_exclude_marks_insight_as_excluded(self):
        insight_id = self.insight_a["id"]
        InsightAnomalyConfig.objects.create(
            team=self.team,
            insight_id=insight_id,
            excluded=False,
        )

        response = self.client.post(self.exclude_url, {"insight_id": insight_id})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "excluded"
        assert response.json()["insight_id"] == insight_id

        config = InsightAnomalyConfig.objects.get(team=self.team, insight_id=insight_id)
        assert config.excluded is True

    def test_exclude_creates_config_if_not_exists(self):
        insight_id = self.insight_a["id"]
        assert not InsightAnomalyConfig.objects.filter(team=self.team, insight_id=insight_id).exists()

        response = self.client.post(self.exclude_url, {"insight_id": insight_id})
        assert response.status_code == status.HTTP_200_OK

        config = InsightAnomalyConfig.objects.get(team=self.team, insight_id=insight_id)
        assert config.excluded is True

    def test_exclude_without_insight_id_returns_400(self):
        response = self.client.post(self.exclude_url, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "insight_id" in response.json()["detail"].lower()

    def test_exclude_does_not_affect_other_teams(self):
        other_team = Team.objects.create(
            organization=self.organization,
            api_token=self.CONFIG_API_TOKEN + "_other2",
        )
        insight_id = self.insight_a["id"]
        InsightAnomalyConfig.objects.create(team=other_team, insight_id=insight_id, excluded=False)

        self.client.post(self.exclude_url, {"insight_id": insight_id})

        other_config = InsightAnomalyConfig.objects.get(team=other_team, insight_id=insight_id)
        assert other_config.excluded is False

    # ------------------------------------------------------------------
    # Include action
    # ------------------------------------------------------------------

    def test_include_re_enables_previously_excluded_insight(self):
        insight_id = self.insight_a["id"]
        InsightAnomalyConfig.objects.create(
            team=self.team,
            insight_id=insight_id,
            excluded=True,
        )

        response = self.client.post(self.include_url, {"insight_id": insight_id})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "included"
        assert response.json()["insight_id"] == insight_id

        config = InsightAnomalyConfig.objects.get(team=self.team, insight_id=insight_id)
        assert config.excluded is False

    def test_include_clears_next_score_due_at(self):
        insight_id = self.insight_a["id"]
        InsightAnomalyConfig.objects.create(
            team=self.team,
            insight_id=insight_id,
            excluded=True,
            next_score_due_at=datetime.now(UTC) + timedelta(days=1),
        )

        self.client.post(self.include_url, {"insight_id": insight_id})

        config = InsightAnomalyConfig.objects.get(team=self.team, insight_id=insight_id)
        assert config.next_score_due_at is None

    def test_include_returns_404_when_no_config_exists(self):
        insight_id = self.insight_a["id"]
        assert not InsightAnomalyConfig.objects.filter(team=self.team, insight_id=insight_id).exists()

        response = self.client.post(self.include_url, {"insight_id": insight_id})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_include_without_insight_id_returns_400(self):
        response = self.client.post(self.include_url, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "insight_id" in response.json()["detail"].lower()

    # ------------------------------------------------------------------
    # Combined filter scenarios
    # ------------------------------------------------------------------

    def test_search_and_anomalous_only_combined(self):
        insight_obj_a = self._insight_obj(self.insight_a)
        anomalous_pageview = _make_score(self.team, insight_obj_a, is_anomalous=True, series_index=0)
        normal_pageview = _make_score(self.team, insight_obj_a, is_anomalous=False, series_index=1)
        anomalous_signup = _make_score(self.team, self._insight_obj(self.insight_b), is_anomalous=True, series_index=0)

        response = self.client.get(self.base_url, {"search": "Pageview", "anomalous_only": "true"})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(anomalous_pageview.id) in result_ids
        assert str(normal_pageview.id) not in result_ids
        assert str(anomalous_signup.id) not in result_ids

    def test_min_score_and_interval_combined(self):
        insight_obj = self._insight_obj(self.insight_a)
        high_day = _make_score(self.team, insight_obj, score=0.9, interval="day", series_index=0)
        low_day = _make_score(self.team, insight_obj, score=0.2, interval="day", series_index=1)
        high_week = _make_score(self.team, insight_obj, score=0.9, interval="week", series_index=2)

        response = self.client.get(self.base_url, {"min_score": "0.5", "interval": "day"})
        assert response.status_code == status.HTTP_200_OK
        result_ids = [r["id"] for r in response.json()["results"]]
        assert str(high_day.id) in result_ids
        assert str(low_day.id) not in result_ids
        assert str(high_week.id) not in result_ids

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _insight_obj(self, insight_response: dict):
        from posthog.models.insight import Insight

        return Insight.objects.get(id=insight_response["id"])
