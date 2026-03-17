from __future__ import annotations

import typing
import dataclasses

VALID_DATA_TYPES = ("events", "persons")


@dataclasses.dataclass
class DucklingDiscoveryInputs:
    """Inputs for the discovery workflow that finds teams needing backfill.

    partition_key is derived from Temporal's TemporalScheduledStartTime by the
    workflow. When triggering manually, set it explicitly.
    """

    data_type: str  # "events" or "persons"
    partition_key: str = ""  # "2024-01-15", derived from scheduled time if empty

    @property
    def properties_to_log(self) -> dict[str, typing.Any]:
        return {
            "data_type": self.data_type,
            "partition_key": self.partition_key,
        }


@dataclasses.dataclass
class DucklingBackfillInputs:
    """Inputs for a single team/partition backfill workflow."""

    team_id: int
    data_type: str  # "events" or "persons"
    partition_key: str  # "2024-01-15" or "2024-01"

    @property
    def properties_to_log(self) -> dict[str, typing.Any]:
        return {
            "team_id": self.team_id,
            "data_type": self.data_type,
            "partition_key": self.partition_key,
        }


@dataclasses.dataclass
class DucklingResolveConfigInputs:
    """Inputs for resolving duckling configuration."""

    team_id: int
    data_type: str

    @property
    def properties_to_log(self) -> dict[str, typing.Any]:
        return {
            "team_id": self.team_id,
            "data_type": self.data_type,
        }


@dataclasses.dataclass
class DucklingResolveConfigResult:
    """Result from resolving duckling configuration."""

    bucket: str
    region: str
    role_arn: str
    external_id: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_session_token: str


@dataclasses.dataclass
class DucklingCopyFilesInputs:
    """Inputs for the S3 copy activity (shared DuckLake catalog → customer S3)."""

    team_id: int
    data_type: str
    partition_key: str  # "2024-01-15"
    dest_bucket: str
    dest_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_session_token: str

    @property
    def properties_to_log(self) -> dict[str, typing.Any]:
        return {
            "team_id": self.team_id,
            "data_type": self.data_type,
            "partition_key": self.partition_key,
            "dest_bucket": self.dest_bucket,
        }


@dataclasses.dataclass
class DucklingCopyFilesResult:
    """Result from the S3 copy activity."""

    dest_s3_paths: list[str]
    total_records: int
    total_bytes: int


@dataclasses.dataclass
class DucklingRegisterInputs:
    """Inputs for registering files with DuckLake."""

    team_id: int
    data_type: str
    s3_paths: list[str]

    @property
    def properties_to_log(self) -> dict[str, typing.Any]:
        return {
            "team_id": self.team_id,
            "data_type": self.data_type,
            "s3_paths_count": len(self.s3_paths),
        }


@dataclasses.dataclass
class DucklingUpdateStatusInputs:
    """Inputs for updating backfill run status."""

    team_id: int
    data_type: str
    partition_key: str
    status: str  # "running", "completed", "failed"
    workflow_id: str = ""
    error_message: str = ""
    records_exported: int = 0
    bytes_exported: int = 0


@dataclasses.dataclass
class DucklingDiscoveryResult:
    """A single team/partition to backfill."""

    team_id: int
    partition_key: str
