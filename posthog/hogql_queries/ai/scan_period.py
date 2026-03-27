from enum import StrEnum

from posthog.models import Team


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


def get_taxonomy_volume_tier(team: Team) -> TaxonomyVolumeTier:
    """
    Determine the taxonomy volume tier based on the org's billing usage data.

    Uses organization.usage['events']['usage'] (billing-period event count)
    cached from the billing service. Falls back to MEDIUM for self-hosted
    instances without billing data.
    """
    usage = team.organization.usage
    if not usage or not usage.get("events"):
        return TaxonomyVolumeTier.MEDIUM

    event_usage = usage["events"].get("usage") or 0
    if event_usage < 100_000:
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
