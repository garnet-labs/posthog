from dataclasses import dataclass

import structlog
import temporalio

from posthog.models.integration import Integration
from posthog.models.organization import OrganizationMembership
from posthog.models.team.team import Team
from posthog.sync import database_sync_to_async

from products.signals.backend.report_generation.select_repo import RepoSelectionResult, select_repository_for_report
from products.signals.backend.temporal.types import SignalData

logger = structlog.get_logger(__name__)


@dataclass
class SelectRepositoryInput:
    team_id: int
    signals: list[SignalData]


@dataclass
class _TeamRepoContext:
    team_id: int
    user_id: int


def _resolve_team_repo_context(team_id: int) -> _TeamRepoContext:
    """Resolve team and user context for repository selection."""
    team = Team.objects.select_related("organization").get(id=team_id)
    membership = (
        OrganizationMembership.objects.select_related("user")
        .filter(organization=team.organization)
        .order_by("id")
        .first()
    )
    if not membership:
        raise RuntimeError(f"No users in organization '{team.organization.name}' (team {team.id})")
    github_integration = Integration.objects.filter(team=team, kind="github").first()
    if not github_integration:
        raise RuntimeError(
            f"No GitHub integration found for team {team.id}. "
            "Signals agentic report generation requires a connected GitHub integration."
        )
    return _TeamRepoContext(
        team_id=team.id,
        user_id=membership.user_id,
    )


@temporalio.activity.defn
async def select_repository_activity(input: SelectRepositoryInput) -> RepoSelectionResult:
    """Select the most relevant repository for a report's signals."""
    team_ctx = await database_sync_to_async(_resolve_team_repo_context, thread_sensitive=False)(input.team_id)
    result = await select_repository_for_report(
        team_id=team_ctx.team_id,
        user_id=team_ctx.user_id,
        signals=input.signals,
    )
    logger.info(
        "signals repo selection completed",
        repository=result.repository,
        reason=result.reason,
    )
    return result
