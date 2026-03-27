from posthog.test.base import BaseTest

from posthog.hogql_queries.ai.scan_period import (
    EVENT_DEFINITION_HIGH_CARDINALITY_THRESHOLD,
    PROPERTY_DEFINITION_HIGH_CARDINALITY_THRESHOLD,
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

    def test_no_usage_data_returns_medium(self):
        self._set_org_usage(usage=None)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_empty_usage_returns_medium(self):
        self._set_org_usage(usage={})
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_missing_events_key_returns_medium(self):
        self._set_org_usage(usage={"recordings": {"usage": 100}})
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_none_event_usage_returns_low(self):
        self._set_org_usage(usage={"events": {"usage": None, "limit": 100}})
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.LOW)

    def test_zero_events_returns_low(self):
        self._set_org_usage(event_usage=0)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.LOW)

    def test_low_volume(self):
        self._set_org_usage(event_usage=50_000)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.LOW)

    def test_low_volume_boundary(self):
        self._set_org_usage(event_usage=99_999)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.LOW)

    def test_medium_volume_lower_boundary(self):
        self._set_org_usage(event_usage=100_000)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_medium_volume(self):
        self._set_org_usage(event_usage=1_000_000)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_medium_volume_upper_boundary(self):
        self._set_org_usage(event_usage=5_000_000)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_high_volume_lower_boundary(self):
        self._set_org_usage(event_usage=5_000_001)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.HIGH)

    def test_high_volume(self):
        self._set_org_usage(event_usage=20_000_000)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.HIGH)

    def test_high_volume_upper_boundary(self):
        self._set_org_usage(event_usage=50_000_000)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.HIGH)

    def test_extra_high_volume(self):
        self._set_org_usage(event_usage=50_000_001)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.EXTRA_HIGH)

    def test_very_high_volume(self):
        self._set_org_usage(event_usage=500_000_000)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.EXTRA_HIGH)

    def test_low_volume_with_high_event_cardinality_bumps_to_medium(self):
        self._set_org_usage(event_usage=50_000)
        for i in range(EVENT_DEFINITION_HIGH_CARDINALITY_THRESHOLD + 1):
            EventDefinition.objects.create(team=self.team, name=f"event_{i}")
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

    def test_low_volume_with_high_property_cardinality_bumps_to_medium(self):
        self._set_org_usage(event_usage=50_000)
        for i in range(PROPERTY_DEFINITION_HIGH_CARDINALITY_THRESHOLD + 1):
            PropertyDefinition.objects.create(team=self.team, name=f"prop_{i}", type=PropertyDefinition.Type.EVENT)
        self.assertEqual(get_taxonomy_volume_tier(self.team), TaxonomyVolumeTier.MEDIUM)

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

    def test_low_volume_returns_7_days(self):
        self._set_org_usage(event_usage=50_000)
        self.assertEqual(get_scan_period_days(self.team), 7)

    def test_medium_volume_returns_30_days(self):
        self._set_org_usage(event_usage=1_000_000)
        self.assertEqual(get_scan_period_days(self.team), 30)

    def test_high_volume_returns_7_days(self):
        self._set_org_usage(event_usage=20_000_000)
        self.assertEqual(get_scan_period_days(self.team), 7)

    def test_extra_high_volume_returns_3_days(self):
        self._set_org_usage(event_usage=100_000_000)
        self.assertEqual(get_scan_period_days(self.team), 3)

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

    def test_low_volume_uses_postgres(self):
        self._set_org_usage(event_usage=50_000)
        self.assertTrue(should_use_postgres_for_events(self.team))

    def test_medium_volume_uses_clickhouse(self):
        self._set_org_usage(event_usage=1_000_000)
        self.assertFalse(should_use_postgres_for_events(self.team))

    def test_high_volume_uses_clickhouse(self):
        self._set_org_usage(event_usage=20_000_000)
        self.assertFalse(should_use_postgres_for_events(self.team))

    def test_no_usage_data_uses_clickhouse(self):
        self._set_org_usage(event_usage=None)
        self.assertFalse(should_use_postgres_for_events(self.team))

    def test_low_volume_high_cardinality_uses_clickhouse(self):
        self._set_org_usage(event_usage=50_000)
        for i in range(EVENT_DEFINITION_HIGH_CARDINALITY_THRESHOLD + 1):
            EventDefinition.objects.create(team=self.team, name=f"event_{i}")
        self.assertFalse(should_use_postgres_for_events(self.team))
