import shlex
import logging
from dataclasses import dataclass

from temporalio import activity

from posthog.models.integration import GitHubIntegration, Integration
from posthog.temporal.common.utils import asyncify

from products.hogbot.backend.models import HogbotRuntime
from products.tasks.backend.services.sandbox import Sandbox, SandboxConfig, SandboxTemplate

HOGBOT_SANDBOX_TTL_SECONDS = 60 * 60 * 24 * 7

logger = logging.getLogger(__name__)


@dataclass
class CreateHogbotSandboxInput:
    team_id: int
    repository: str | None = None
    github_integration_id: int | None = None
    branch: str | None = None


@dataclass
class CreateHogbotSandboxOutput:
    sandbox_id: str
    sandbox_url: str
    connect_token: str | None = None


def _get_github_token(github_integration_id: int | None) -> str:
    if github_integration_id is None:
        return ""

    integration = Integration.objects.get(id=github_integration_id)
    github_integration = GitHubIntegration(integration)
    if github_integration.access_token_expired():
        github_integration.refresh_access_token()

    return github_integration.integration.access_token or ""


def _get_repository_path(repository: str) -> str:
    org, repo = repository.lower().split("/")
    return f"/tmp/workspace/repos/{org}/{repo}"


def _checkout_branch(
    sandbox: Sandbox,
    repository: str,
    branch: str,
    *,
    github_token: str,
    update_remote: bool,
) -> None:
    org, repo = repository.lower().split("/")
    repo_slug = f"{org}/{repo}"
    repo_path = _get_repository_path(repository)

    if update_remote and github_token:
        remote_url = f"https://x-access-token:{github_token}@github.com/{repo_slug}.git"
        update_remote_result = sandbox.execute(
            f"cd {shlex.quote(repo_path)} && git remote set-url origin {shlex.quote(remote_url)}",
            timeout_seconds=30,
        )
        if update_remote_result.exit_code != 0:
            logger.warning(
                "Failed to update remote URL for hogbot sandbox",
                extra={"repository": repository, "branch": branch, "stderr": update_remote_result.stderr},
            )

    fetch_and_checkout = (
        f"cd {shlex.quote(repo_path)} && "
        f"git fetch --depth 1 origin -- {shlex.quote(branch)} && "
        f"git checkout -B {shlex.quote(branch)} FETCH_HEAD"
    )
    result = sandbox.execute(fetch_and_checkout, timeout_seconds=5 * 60)
    if result.exit_code != 0:
        raise RuntimeError(f"Failed to checkout branch {branch}: {result.stderr}")


@activity.defn
@asyncify
def create_hogbot_sandbox(input: CreateHogbotSandboxInput) -> CreateHogbotSandboxOutput:
    runtime, _ = HogbotRuntime.objects.get_or_create(team_id=input.team_id)
    snapshot_external_id = runtime.latest_snapshot_external_id
    has_snapshot = bool(snapshot_external_id)
    github_token = _get_github_token(input.github_integration_id)

    environment_variables = {"GITHUB_TOKEN": github_token} if github_token else None
    config = SandboxConfig(
        name=f"hogbot-team-{input.team_id}",
        template=SandboxTemplate.DEFAULT_BASE,
        environment_variables=environment_variables,
        snapshot_external_id=snapshot_external_id,
        ttl_seconds=HOGBOT_SANDBOX_TTL_SECONDS,
        metadata={"team_id": str(input.team_id)},
    )

    sandbox = Sandbox.create(config)

    try:
        if input.repository and not has_snapshot:
            clone_result = sandbox.clone_repository(input.repository, github_token=github_token)
            if clone_result.exit_code != 0:
                raise RuntimeError(f"Failed to clone repository {input.repository}: {clone_result.stderr}")

            if input.branch:
                _checkout_branch(
                    sandbox,
                    input.repository,
                    input.branch,
                    github_token=github_token,
                    update_remote=False,
                )

        credentials = sandbox.get_connect_credentials()
    except Exception:
        try:
            sandbox.destroy()
        except Exception:
            logger.warning("Failed to destroy hogbot sandbox during startup cleanup", exc_info=True)
        raise

    return CreateHogbotSandboxOutput(
        sandbox_id=sandbox.id,
        sandbox_url=credentials.url,
        connect_token=credentials.token,
    )
