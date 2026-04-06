from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from django.conf import settings

import requests as http_requests
import structlog

from posthog.models.integration import GitHubIntegration, Integration
from posthog.temporal.oauth import PosthogMcpScopes, has_write_scopes

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class McpServerConfig:
    """Configuration for a remote MCP server matching the ACP McpServer schema.

    Matches the CLI --mcpServers JSON format:
    - type: "http" (streamable HTTP) or "sse"
    - name: server identifier
    - url: server endpoint
    - headers: list of {name, value} pairs
    """

    type: str
    name: str
    url: str
    headers: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "url": self.url,
            "headers": self.headers,
        }


def get_sandbox_api_url() -> str:
    return settings.SANDBOX_API_URL or settings.SITE_URL


def fetch_user_mcp_server_configs(
    token: str,
    project_id: int,
) -> list[McpServerConfig]:
    """Fetch the user's MCP Store installations via the PostHog API and return configs.

    Calls GET /api/environments/{project_id}/mcp_server_installations/ to discover
    installations, then builds McpServerConfig entries using each installation's
    proxy URL. The proxy handles upstream auth (OAuth token refresh, API key injection).

    Returns an empty list on API errors (non-fatal).
    """
    api_base = get_sandbox_api_url().rstrip("/")
    url = f"{api_base}/api/environments/{project_id}/mcp_server_installations/"

    try:
        response = http_requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
    except Exception as e:
        logger.warning("Error fetching MCP installations", error=str(e), project_id=project_id)
        return []

    if not response.ok:
        logger.warning(
            "Failed to fetch MCP installations",
            status_code=response.status_code,
            response_body=response.text[:500],
            project_id=project_id,
        )
        return []

    try:
        data = response.json()
    except Exception as e:
        logger.warning(
            "Failed to parse MCP installations response",
            error=str(e),
            response_body=response.text[:500],
            project_id=project_id,
        )
        return []

    installations = data.get("results", [])

    configs: list[McpServerConfig] = []
    for installation in installations:
        if not installation.get("is_enabled", True):
            logger.debug("Skipping disabled MCP installation", name=installation.get("name"))
            continue
        if installation.get("needs_reauth"):
            logger.debug("Skipping MCP installation needing reauth", name=installation.get("name"))
            continue
        if installation.get("pending_oauth"):
            logger.debug("Skipping MCP installation with pending OAuth", name=installation.get("name"))
            continue

        name = installation.get("name") or installation.get("url", "")
        proxy_url = f"{api_base}/api/environments/{project_id}/mcp_server_installations/{installation['id']}/proxy/"

        configs.append(
            McpServerConfig(
                type="http",
                name=name,
                url=proxy_url,
                headers=[{"name": "Authorization", "value": f"Bearer {token}"}],
            )
        )

    logger.info("Built user MCP server configs", count=len(configs), project_id=project_id)
    return configs


def get_sandbox_ph_mcp_configs(
    token: str,
    project_id: int,
    *,
    scopes: PosthogMcpScopes = "read_only",
) -> list[McpServerConfig]:
    """Return PostHog MCP server configurations for sandbox agents.

    Uses SANDBOX_MCP_URL if explicitly set, otherwise derives it from SITE_URL:
    - app.posthog.com / us.posthog.com → https://mcp.posthog.com/mcp
    - eu.posthog.com → https://mcp-eu.posthog.com/mcp
    - Other hosts → empty list (MCP not available)
    """
    url = _resolve_mcp_url()
    if not url:
        return []
    read_only = not has_write_scopes(scopes)
    headers = [
        {"name": "Authorization", "value": f"Bearer {token}"},
        {"name": "x-posthog-project-id", "value": str(project_id)},
        {"name": "x-posthog-mcp-version", "value": "2"},
        {"name": "x-posthog-read-only", "value": str(read_only).lower()},
    ]
    return [McpServerConfig(type="http", name="posthog", url=url, headers=headers)]


def _resolve_mcp_url() -> str | None:
    if settings.SANDBOX_MCP_URL:
        return settings.SANDBOX_MCP_URL

    site_url = settings.SITE_URL
    if not site_url:
        return None

    hostname = urlparse(site_url).hostname or ""
    if hostname in ("app.posthog.com", "us.posthog.com"):
        return "https://mcp.posthog.com/mcp"
    if hostname == "eu.posthog.com":
        return "https://mcp-eu.posthog.com/mcp"

    return None


def get_github_token(github_integration_id: int) -> Optional[str]:
    integration = Integration.objects.get(id=github_integration_id)
    github_integration = GitHubIntegration(integration)

    if github_integration.access_token_expired():
        github_integration.refresh_access_token()

    return github_integration.integration.access_token or None


def format_allowed_domains_for_log(domains: list[str], limit: int = 5) -> str:
    preview = ", ".join(domains[:limit])
    remaining = len(domains) - limit
    if remaining > 0:
        return f"{preview}, +{remaining} more"
    return preview


def get_sandbox_name_for_task(task_id: str) -> str:
    return f"task-sandbox-{task_id}"


def build_sandbox_environment_variables(
    github_token: str | None,
    access_token: str,
    team_id: int,
    sandbox_environment: Optional[Any] = None,
) -> dict[str, str]:
    """Build the environment variables dict for a sandbox, merging user env vars from SandboxEnvironment.

    User-provided env vars are applied first so system vars always take precedence,
    preventing a malicious SandboxEnvironment from overriding security-critical values.
    """
    from products.tasks.backend.services.connection_token import get_sandbox_jwt_public_key

    env_vars: dict[str, str] = {}

    # Apply user-provided vars first so system vars always take precedence
    if sandbox_environment and sandbox_environment.environment_variables:
        env_vars.update(sandbox_environment.environment_variables)

    if github_token:
        env_vars["GITHUB_TOKEN"] = github_token

    env_vars.update(
        {
            "POSTHOG_PERSONAL_API_KEY": access_token,
            "POSTHOG_API_URL": get_sandbox_api_url(),
            "POSTHOG_PROJECT_ID": str(team_id),
            "JWT_PUBLIC_KEY": get_sandbox_jwt_public_key(),
        }
    )

    if settings.SANDBOX_LLM_GATEWAY_URL:
        env_vars["LLM_GATEWAY_URL"] = settings.SANDBOX_LLM_GATEWAY_URL

    return env_vars
