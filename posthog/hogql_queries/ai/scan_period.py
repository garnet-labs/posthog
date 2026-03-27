from enum import StrEnum

from posthog.models import Team

# Cardinality thresholds: if a low-volume org has more distinct events or
# properties than these, we bump them to MEDIUM (use ClickHouse with 30d scan)
# so we get proper count-based ordering.
EVENT_DEFINITION_HIGH_CARDINALITY_THRESHOLD = 500
PROPERTY_DEFINITION_HIGH_CARDINALITY_THRESHOLD = 2000


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


def _has_high_cardinality(team: Team) -> bool:
    """
    Check if the team has high cardinality of event/property definitions in Postgres.

    Even with low event volume, high cardinality means the Postgres fallback
    (ordered by last_seen_at) won't give useful results — ClickHouse count-based
    ordering is needed.
    """
    from products.event_definitions.backend.models.event_definition import EventDefinition
    from products.event_definitions.backend.models.property_definition import PropertyDefinition

    event_count = EventDefinition.objects.filter(team=team).count()
    if event_count > EVENT_DEFINITION_HIGH_CARDINALITY_THRESHOLD:
        return True

    property_count = PropertyDefinition.objects.filter(team=team).count()
    return property_count > PROPERTY_DEFINITION_HIGH_CARDINALITY_THRESHOLD


def get_taxonomy_volume_tier(team: Team) -> TaxonomyVolumeTier:
    """
    Determine the taxonomy volume tier based on the org's billing usage data
    and the cardinality of stored event/property definitions.

    Uses organization.usage['events']['usage'] (billing-period event count)
    cached from the billing service. Falls back to MEDIUM for self-hosted
    instances without billing data.

    For orgs that would be LOW by volume but have high cardinality of stored
    definitions, we bump to MEDIUM so ClickHouse count-based ordering is used.
    """
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


def get_scan_period_days(team: Team) -> int:
    """Return the ClickHouse scan period in days for the team's volume tier."""
    return SCAN_PERIOD_DAYS[get_taxonomy_volume_tier(team)]


def should_use_postgres_for_events(team: Team) -> bool:
    """Whether to use Postgres EventDefinition instead of ClickHouse for event listing."""
    return get_taxonomy_volume_tier(team) == TaxonomyVolumeTier.LOW
