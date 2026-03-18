from dataclasses import dataclass

from django.db import transaction

import structlog
import temporalio
import posthoganalytics

from posthog.models.organization import OrganizationMembership
from posthog.models.team.team import Team
from posthog.sync import database_sync_to_async

from products.signals.backend.models import SignalReportArtefact
from products.signals.backend.report_generation.research import ReportResearchOutput, run_multi_turn_research
from products.signals.backend.report_generation.select_repo import RepoSelectionResult
from products.signals.backend.temporal.actionability_judge import ActionabilityChoice, Priority
from products.signals.backend.temporal.types import SignalData
from products.tasks.backend.services.custom_prompt_runner import CustomPromptSandboxContext

logger = structlog.get_logger(__name__)

SIGNALS_AGENTIC_REPORT_GENERATION_FF = "signals-agentic-report-generation"


@dataclass
class SignalsAgenticReportGateInput:
    team_id: int


@temporalio.activity.defn
async def signals_agentic_report_gate_activity(input: SignalsAgenticReportGateInput) -> bool:
    """Evaluate whether Signals should use the agentic report path for a team."""
    try:
        team = await Team.objects.only("id", "uuid", "organization_id").aget(id=input.team_id)
    except Team.DoesNotExist:
        logger.warning("signals agentic report gate: team does not exist", team_id=input.team_id)
        return False

    try:
        return posthoganalytics.feature_enabled(
            SIGNALS_AGENTIC_REPORT_GENERATION_FF,
            str(team.uuid),
            groups={
                "organization": str(team.organization_id),
                "project": str(team.id),
            },
            group_properties={
                "organization": {
                    "id": str(team.organization_id),
                },
                "project": {
                    "id": str(team.id),
                },
            },
            only_evaluate_locally=True,
            send_feature_flag_events=False,
        )
    except Exception:
        logger.exception(
            "signals agentic report gate: failed to evaluate feature flag",
            team_id=input.team_id,
            flag=SIGNALS_AGENTIC_REPORT_GENERATION_FF,
        )
        return False


@dataclass
class RunAgenticReportInput:
    team_id: int
    report_id: str
    signals: list[SignalData]
    repo_selection: RepoSelectionResult


@dataclass
class RunAgenticReportOutput:
    title: str
    summary: str
    choice: ActionabilityChoice
    priority: Priority | None
    explanation: str
    already_addressed: bool
    repository: str


def _resolve_user_id(team_id: int) -> int:
    """Resolve the first org member's user ID for sandbox context."""
    # TODO: Decide if it's a safe approach
    team = Team.objects.select_related("organization").get(id=team_id)
    membership = (
        OrganizationMembership.objects.select_related("user")
        .filter(organization=team.organization)
        .order_by("id")
        .first()
    )
    if not membership:
        raise RuntimeError(f"No users in organization '{team.organization.name}' (team {team.id})")
    return membership.user_id


def _persist_agentic_report_artefacts(
    team_id: int, report_id: str, result: ReportResearchOutput, repo_selection: RepoSelectionResult
) -> None:
    artefacts = [
        SignalReportArtefact(
            team_id=team_id,
            report_id=report_id,
            type=SignalReportArtefact.ArtefactType.REPO_SELECTION,
            content=repo_selection.model_dump_json(),
        ),
    ]
    artefacts.extend(
        SignalReportArtefact(
            team_id=team_id,
            report_id=report_id,
            type=SignalReportArtefact.ArtefactType.SIGNAL_FINDING,
            content=finding.model_dump_json(),
        )
        for finding in result.findings
    )
    artefacts.append(
        SignalReportArtefact(
            team_id=team_id,
            report_id=report_id,
            type=SignalReportArtefact.ArtefactType.ACTIONABILITY_JUDGMENT,
            content=result.actionability.model_dump_json(),
        )
    )
    if result.priority:
        artefacts.append(
            SignalReportArtefact(
                team_id=team_id,
                report_id=report_id,
                type=SignalReportArtefact.ArtefactType.PRIORITY_JUDGMENT,
                content=result.priority.model_dump_json(),
            )
        )
    with transaction.atomic():
        SignalReportArtefact.objects.bulk_create(artefacts)


@temporalio.activity.defn
async def run_agentic_report_activity(input: RunAgenticReportInput) -> RunAgenticReportOutput:
    """Run the sandbox-backed report research and persist its artefacts after full success."""
    try:
        # The workflow only calls this activity when repo_selection.repository is not None.
        assert input.repo_selection.repository is not None, "run_agentic_report_activity called without a repository"
        repository = input.repo_selection.repository

        # 1. Get context for the sandbox
        user_id = await database_sync_to_async(_resolve_user_id, thread_sensitive=False)(input.team_id)
        context = CustomPromptSandboxContext(
            team_id=input.team_id,
            user_id=user_id,
            repository=repository,
        )
        # 2. Run the agentic research in the sandbox
        result = await run_multi_turn_research(
            input.signals,
            context,
            branch="master",
        )
        # 3. Persist artefacts, avoid partial data from failed runs
        await database_sync_to_async(_persist_agentic_report_artefacts, thread_sensitive=False)(
            input.team_id,
            input.report_id,
            result,
            input.repo_selection,
        )
        logger.info(
            "signals agentic report completed",
            report_id=input.report_id,
            signal_count=len(input.signals),
            choice=result.actionability.actionability.value,
            repository=repository,
        )
        return RunAgenticReportOutput(
            title=result.title,
            summary=result.summary,
            choice=result.actionability.actionability,
            priority=result.priority.priority if result.priority else None,
            explanation=result.actionability.explanation,
            already_addressed=result.actionability.already_addressed,
            repository=repository,
        )
    except Exception as error:
        logger.exception(
            "signals agentic report failed",
            report_id=input.report_id,
            team_id=input.team_id,
            error=str(error),
        )
        raise
