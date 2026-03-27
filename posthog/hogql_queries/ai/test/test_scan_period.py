from posthog.test.base import BaseTest

from parameterized import parameterized

from posthog.hogql_queries.ai.scan_period import (
    EVENT_CARDINALITY_THRESHOLD,
    PROPERTY_CARDINALITY_THRESHOLD,
    SCAN_PERIOD_DAYS,
    TaxonomyVolumeTier,
    get_scan_period_days,
    get_taxonomy_volume_tier,
    should_use_postgres_for_events,
)

from products.event_definitions.backend.models.event_definition import EventDefinition
from products.event_definitions.backend.models.property_definition import PropertyDefinition


class TestTaxonomyVolumeTier(BaseTest):
    def _set_org_usage(self, event_usage: int | None = None, usage: dict | None = None):
        if usage is not None:
            self.organization.usage = usage
        elif event_usage is not None:
            self.organization.usage = {"events": {"usage": event_usage, "limit": 1_000_000, "todays_usage": 0}}
        else:
            self.organization.usage = None
        self.organization.save(update_fields=["usage"])

    @parameterized.expand(
        [
            ("no_usage_data", None, None, TaxonomyVolumeTier.MEDIUM),
            ("empty_usage", {}, None, TaxonomyVolumeTier.MEDIUM),
            ("missing_events_key", {"recordings": {"usage": 100}}, None, TaxonomyVolumeTier.MEDIUM),
            ("none_event_usage", {"events": {"usage": None, "limit": 100}}, None, TaxonomyVolumeTier.LOW),
            ("zero_events", None, 0, TaxonomyVolumeTier.LOW),
            ("low_volume", None, 50_000, TaxonomyVolumeTier.LOW),
            ("low_volume_boundary", None, 99_999, TaxonomyVolumeTier.LOW),
            ("medium_lower_boundary", None, 100_000, TaxonomyVolumeTier.MEDIUM),
            ("medium_volume", None, 1_000_000, TaxonomyVolumeTier.MEDIUM),
            ("medium_upper_boundary", None, 5_000_000, TaxonomyVolumeTier.MEDIUM),
            ("high_lower_boundary", None, 5_000_001, TaxonomyVolumeTier.HIGH),
            ("high_volume", None, 20_000_000, TaxonomyVolumeTier.HIGH),
            ("high_upper_boundary", None, 50_000_000, TaxonomyVolumeTier.HIGH),
            ("extra_high", None, 50_000_001, TaxonomyVolumeTier.EXTRA_HIGH),
            ("very_high", None, 500_000_000, TaxonomyVolumeTier.EXTRA_HIGH),
        ]
    )
    def test_volume_tier(self, _name, usage_dict, event_usage, expected_tier):
        if usage_dict is not None:
            self._set_org_usage(usage=usage_dict)
        else:
            self._set_org_usage(event_usage=event_usage)
        self.assertEqual(get_taxonomy_volume_tier(self.team), expected_tier)

    def test_low_volume_with_high_event_cardinality_bumps_to_medium(self):
        self._set_org_usage(event_usage=50_000)
        for i in range(EVENT_CARDINALITY_THRESHOLD + 1):
            EventDefinition.objects.create(team=self.team, name=f"event_{i}")
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_low_volume_with_high_event_property_cardinality_bumps_to_medium(self):
        self._set_org_usage(event_usage=50_000)
        for i in range(PROPERTY_CARDINALITY_THRESHOLD + 1):
            PropertyDefinition.objects.create(team=self.team, name=f"prop_{i}", type=PropertyDefinition.Type.EVENT)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_low_volume_with_high_person_property_cardinality_stays_low(self):
        self._set_org_usage(event_usage=50_000)
        for i in range(PROPERTY_CARDINALITY_THRESHOLD + 1):
            PropertyDefinition.objects.create(team=self.team, name=f"prop_{i}", type=PropertyDefinition.Type.PERSON)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.LOW)

    def test_low_volume_with_low_cardinality_stays_low(self):
        self._set_org_usage(event_usage=50_000)
        for i in range(10):
            EventDefinition.objects.create(team=self.team, name=f"event_{i}")
        for i in range(20):
            PropertyDefinition.objects.create(team=self.team, name=f"prop_{i}", type=PropertyDefinition.Type.EVENT)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.LOW)

    def test_high_volume_ignores_cardinality(self):
        self._set_org_usage(event_usage=20_000_000)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.HIGH)


class TestGetScanPeriodDays(BaseTest):
    def _set_org_usage(self, event_usage: int):
        self.organization.usage = {"events": {"usage": event_usage, "limit": 1_000_000, "todays_usage": 0}}
        self.organization.save(update_fields=["usage"])

    @parameterized.expand(
        [
            ("low_volume", 50_000, 7),
            ("medium_volume", 1_000_000, 30),
            ("high_volume", 20_000_000, 7),
            ("extra_high_volume", 100_000_000, 3),
        ]
    )
    def test_scan_period_days(self, _name, event_usage, expected_days):
        self._set_org_usage(event_usage=event_usage)
        self.assertEqual(get_scan_period_days(self.team), expected_days)

    def test_all_tiers_have_scan_periods(self):
        for tier in TaxonomyVolumeTier:
            self.assertIn(tier, SCAN_PERIOD_DAYS)


class TestShouldUsePostgresForEvents(BaseTest):
    def _set_org_usage(self, event_usage: int | None = None):
        if event_usage is not None:
            self.organization.usage = {"events": {"usage": event_usage, "limit": 1_000_000, "todays_usage": 0}}
        else:
            self.organization.usage = None
        self.organization.save(update_fields=["usage"])

    @parameterized.expand(
        [
            ("low_volume", 50_000, True),
            ("medium_volume", 1_000_000, False),
            ("high_volume", 20_000_000, False),
        ]
    )
    def test_should_use_postgres(self, _name, event_usage, expected):
        self._set_org_usage(event_usage=event_usage)
        self.assertEqual(should_use_postgres_for_events(self.team), expected)

    def test_no_usage_data_uses_clickhouse(self):
        self._set_org_usage(event_usage=None)
        self.assertFalse(should_use_postgres_for_events(self.team))

    def test_low_volume_high_cardinality_uses_clickhouse(self):
        self._set_org_usage(event_usage=50_000)
        for i in range(EVENT_CARDINALITY_THRESHOLD + 1):
            EventDefinition.objects.create(team=self.team, name=f"event_{i}")
        self.assertFalse(should_use_postgres_for_events(self.team))
