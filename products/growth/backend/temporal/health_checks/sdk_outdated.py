import json
from collections import defaultdict
from typing import Any

import structlog

from posthog.dags.common.owners import JobOwners
from posthog.models.health_issue import HealthIssue
from posthog.redis import get_client
from posthog.temporal.health_checks.detectors import CLICKHOUSE_BATCH_EXECUTION_POLICY
from posthog.temporal.health_checks.framework import HealthCheck
from posthog.temporal.health_checks.models import HealthCheckResult
from posthog.temporal.health_checks.query import execute_clickhouse_health_team_query

from products.growth.backend.constants import (
    TEAM_SDK_VERSIONS_CACHE_EXPIRY,
    github_sdk_versions_key,
    team_sdk_versions_key,
)
from products.growth.dags.github_sdk_versions import SDK_TYPES

logger = structlog.get_logger(__name__)

SDK_VERSIONS_LOOKBACK_DAYS = 7

SDK_VERSIONS_SQL = """
SELECT
    team_id,
    JSONExtractString(properties, '$lib') AS lib,
    JSONExtractString(properties, '$lib_version') AS lib_version,
    max(timestamp) AS max_timestamp,
    count() AS event_count
FROM events
WHERE team_id IN %(team_ids)s
  AND timestamp >= now() - INTERVAL %(lookback_days)s DAY
  AND JSONExtractString(properties, '$lib') != ''
  AND JSONExtractString(properties, '$lib_version') != ''
GROUP BY team_id, lib, lib_version
ORDER BY team_id, lib,
  arrayMap(x -> toInt64OrZero(x), splitByChar('.', extract(assumeNotNull(lib_version), '(\\d+(\\.\\d+)+)'))) DESC,
  event_count DESC
"""

SDK_TYPES_SET = frozenset(SDK_TYPES)


def _decode_redis_json(raw: bytes | str) -> Any:
    return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)


def _load_github_sdk_data() -> dict[str, dict]:
    """Load latest SDK versions from Redis for all known SDK types."""
    redis_client = get_client()
    keys = [github_sdk_versions_key(sdk_type) for sdk_type in SDK_TYPES]
    values = redis_client.mget(keys)

    data: dict[str, dict] = {}
    for sdk_type, raw in zip(SDK_TYPES, values):
        if not raw:
            continue
        parsed = _decode_redis_json(raw)
        if "latestVersion" in parsed:
            data[sdk_type] = parsed
    return data


def _group_by_team(
    rows: list[tuple[Any, ...]],
) -> dict[int, dict[str, list[dict[str, Any]]]]:
    """Group ClickHouse rows into per-team SDK version dicts, filtering to known SDK types."""
    teams: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for team_id, lib, lib_version, max_timestamp, event_count in rows:
        if lib in SDK_TYPES_SET:
            teams[team_id][lib].append(
                {
                    "lib_version": lib_version,
                    "max_timestamp": str(max_timestamp),
                    "count": event_count,
                }
            )
    return dict(teams)


def _cache_team_sdk_data(
    teams_data: dict[int, dict[str, list[dict[str, Any]]]],
    team_ids: list[int],
) -> None:
    """Cache SDK version data in Redis for each team. Teams with no data get an empty dict cached."""
    redis_client = get_client()
    pipe = redis_client.pipeline(transaction=False)
    for team_id in team_ids:
        data = teams_data.get(team_id, {})
        cache_key = team_sdk_versions_key(team_id)
        pipe.setex(cache_key, TEAM_SDK_VERSIONS_CACHE_EXPIRY, json.dumps(data))
    pipe.execute()


class SdkOutdatedCheck(HealthCheck):
    name = "sdk_outdated"
    kind = "sdk_outdated"
    owner = JobOwners.TEAM_GROWTH
    policy = CLICKHOUSE_BATCH_EXECUTION_POLICY

    def detect(self, team_ids: list[int]) -> dict[int, list[HealthCheckResult]]:
        github_data = _load_github_sdk_data()
        if not github_data:
            logger.warning("GitHub SDK version data unavailable in Redis; skipping sdk_outdated check")
            return {}

        rows = execute_clickhouse_health_team_query(
            SDK_VERSIONS_SQL,
            team_ids=team_ids,
            lookback_days=SDK_VERSIONS_LOOKBACK_DAYS,
            settings={"max_execution_time": 120},
        )

        teams_data = _group_by_team(rows)

        _cache_team_sdk_data(teams_data, team_ids)

        issues: defaultdict[int, list[HealthCheckResult]] = defaultdict(list)
        for team_id, team_sdks in teams_data.items():
            for lib_name, entries in team_sdks.items():
                if lib_name not in github_data or not entries:
                    continue
                sdk_github_data = github_data[lib_name]
                latest_version = sdk_github_data["latestVersion"]
                release_dates = sdk_github_data.get("releaseDates", {})

                current_version = entries[0].get("lib_version")

                if current_version and current_version != latest_version:
                    issues[team_id].append(
                        HealthCheckResult(
                            severity=HealthIssue.Severity.WARNING,
                            payload={
                                "sdk_name": lib_name,
                                "latest_version": latest_version,
                                "usage": [
                                    {
                                        "lib_version": entry["lib_version"],
                                        "count": entry.get("count", 0),
                                        "max_timestamp": entry["max_timestamp"],
                                        "release_date": release_dates.get(entry["lib_version"]),
                                        "is_latest": entry["lib_version"] == latest_version,
                                    }
                                    for entry in entries
                                ],
                            },
                            hash_keys=["sdk_name"],
                        )
                    )

        return issues
