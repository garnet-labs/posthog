from enum import StrEnum
from functools import lru_cache

from django.utils import timezone

from posthog.models import Team

from products.event_definitions.backend.models.event_definition import EventDefinition
from products.event_definitions.backend.models.property_definition import PropertyDefinition

# Cardinality thresholds for the Postgres fallback. If a low-volume org
# exceeds these, we use ClickHouse instead so we get count-based ordering.
EVENT_CARDINALITY_THRESHOLD = 50
PROPERTY_CARDINALITY_THRESHOLD = 100

# How long to cache the volume tier result (seconds).
_CACHE_TTL_SECONDS = 300


class TaxonomyVolumeTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTRA_HIGH = "extra_high"


SCAN_PERIOD_DAYS: dict[TaxonomyVolumeTier, int] = {
    TaxonomyVolumeTier.LOW: 7,
    TaxonomyVolumeTier.MEDIUM: 30,
    TaxonomyVolumeTier.HIGH: 7,
    TaxonomyVolumeTier.EXTRA_HIGH: 3,
}


class TaxonomyScanConfig:
    """
    Resolves and caches the taxonomy scan configuration for a team.

    Caches the volume tier per team_id for up to 5 minutes to avoid
    redundant DB queries (cardinality checks) when multiple taxonomy
    tools are called in the same conversation turn.
    """

    def __init__(self, team: Team):
        self._team = team
        self._tier: TaxonomyVolumeTier | None = None

    @property
    def volume_tier(self) -> TaxonomyVolumeTier:
        if self._tier is None:
            self._tier = _get_cached_volume_tier(self._team.pk)
        return self._tier

    @property
    def scan_period_days(self) -> int:
        return SCAN_PERIOD_DAYS[self.volume_tier]

    @property
    def use_postgres_for_events(self) -> bool:
        return self.volume_tier == TaxonomyVolumeTier.LOW


@lru_cache(maxsize=128)
def _get_cached_volume_tier_inner(team_pk: int, cache_bucket: int) -> TaxonomyVolumeTier:
    """
    Cached computation of volume tier. The `cache_bucket` parameter
    is derived from the current time divided by the TTL, so entries
    expire naturally as the bucket rolls over.
    """
    team = Team.objects.select_related("organization").get(pk=team_pk)
    return _compute_volume_tier(team)


def _get_cached_volume_tier(team_pk: int) -> TaxonomyVolumeTier:
    bucket = int(timezone.now().timestamp()) // _CACHE_TTL_SECONDS
    return _get_cached_volume_tier_inner(team_pk, bucket)


def _has_high_cardinality(team: Team) -> bool:
    event_count = EventDefinition.objects.filter(team=team).count()
    if event_count > EVENT_CARDINALITY_THRESHOLD:
        return True

    property_count = PropertyDefinition.objects.filter(team=team, type=PropertyDefinition.Type.EVENT).count()
    return property_count > PROPERTY_CARDINALITY_THRESHOLD


def _compute_volume_tier(team: Team) -> TaxonomyVolumeTier:
    usage = team.organization.usage
    if not usage or not usage.get("events"):
        return TaxonomyVolumeTier.MEDIUM

    event_usage = usage["events"].get("usage") or 0
    if event_usage < 100_000:
        if _has_high_cardinality(team):
            return TaxonomyVolumeTier.MEDIUM
        return TaxonomyVolumeTier.LOW
    elif event_usage <= 5_000_000:
        return TaxonomyVolumeTier.MEDIUM
    elif event_usage <= 50_000_000:
        return TaxonomyVolumeTier.HIGH
    return TaxonomyVolumeTier.EXTRA_HIGH


# Module-level convenience functions for callers that don't need the full config object.
def get_taxonomy_volume_tier(team: Team) -> TaxonomyVolumeTier:
    return TaxonomyScanConfig(team).volume_tier


def get_scan_period_days(team: Team) -> int:
    return TaxonomyScanConfig(team).scan_period_days


def should_use_postgres_for_events(team: Team) -> bool:
    return TaxonomyScanConfig(team).use_postgres_for_events
