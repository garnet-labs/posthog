import dataclasses
from typing import Any


@dataclasses.dataclass
class DiscoverInsightsActivityInputs:
    recently_viewed_days: int = 30
    max_candidates: int = 500


@dataclasses.dataclass
class EligibleInsight:
    insight_id: int
    team_id: int
    interval: str  # hour, day, week, month


# -- Training types --


@dataclasses.dataclass
class ScheduleTrainingInputs:
    batch_size: int = 50
    max_concurrent: int = 5  # max child workflows running in parallel


@dataclasses.dataclass
class TrainInsightActivityInputs:
    insight_id: int
    team_id: int
    detector_config: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class TrainInsightWorkflowInputs:
    insight_id: int
    team_id: int
    detector_config: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class TrainInsightResult:
    insight_id: int
    trained: bool = False
    model_version: int = 0
    error: str | None = None


# -- Scoring types --


@dataclasses.dataclass
class ScheduleScoringInputs:
    batch_size: int = 50
    max_concurrent: int = 10  # scoring is lighter, can run more in parallel


@dataclasses.dataclass
class ScoreInsightActivityInputs:
    insight_id: int
    team_id: int
    model_storage_key: str = ""
    detector_config: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ScoreInsightWorkflowInputs:
    insight_id: int
    team_id: int
    model_storage_key: str = ""
    detector_config: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ScoreInsightResult:
    insight_id: int
    scored: bool = False
    error: str | None = None


# -- Cleanup types --


@dataclasses.dataclass
class CleanupScoresActivityInputs:
    retention_days: int = 30
