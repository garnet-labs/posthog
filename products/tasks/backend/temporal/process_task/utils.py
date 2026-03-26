from dataclasses import dataclass, field
from typing import Any, Optional

from django.conf import settings

from posthog.models.integration import GitHubIntegration, Integration
from posthog.temporal.oauth import PosthogMcpScopes, has_write_scopes


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
    if settings.DEBUG:
        # In local dev, sandboxes run in Docker and can't reach localhost.
        # Use host.docker.internal on port 8000 (Django) instead of 8010 (webpack proxy).
        return "http://host.docker.internal:8000"
    return settings.SITE_URL


def get_sandbox_mcp_configs(
    token: str,
    project_id: int,
    *,
    scopes: PosthogMcpScopes = "read_only",
) -> list[McpServerConfig]:
    """Return MCP server configurations for sandbox agents.

    When SANDBOX_MCP_AUTH_TOKEN and SANDBOX_MCP_PROJECT_ID are set, a prod MCP
    is added (using those credentials) and the local MCP is filtered to
    action_prediction_models only. Otherwise a single MCP is returned with
    full access.
    """
    read_only = not has_write_scopes(scopes)
    configs: list[McpServerConfig] = []

    prod_auth_token = settings.SANDBOX_MCP_AUTH_TOKEN or ""
    prod_project_id = settings.SANDBOX_MCP_PROJECT_ID or ""
    has_prod = bool(prod_auth_token and prod_project_id)

    # Local MCP (from SANDBOX_MCP_URL or derived from SITE_URL)
    local_url = _resolve_local_mcp_url()
    if local_url:
        if has_prod:
            local_url = _append_query_param(local_url, "features", "action_prediction_models")
        # Prevent recursive sandbox creation — sandboxed agents must not spawn new tasks.
        local_url = _append_query_param(local_url, "exclude_tools", "action-prediction-model-predict")
        configs.append(
            McpServerConfig(
                type="http",
                name="posthog-local" if has_prod else "posthog",
                url=local_url,
                headers=[
                    {"name": "Authorization", "value": f"Bearer {token}"},
                    {"name": "x-posthog-project-id", "value": str(project_id)},
                    {"name": "x-posthog-mcp-version", "value": "2"},
                    {"name": "x-posthog-read-only", "value": str(read_only).lower()},
                ],
            )
        )

    # Prod MCP (when env credentials are provided)
    if has_prod:
        prod_url = _resolve_prod_mcp_url()
        if prod_url:
            configs.append(
                McpServerConfig(
                    type="http",
                    name="posthog",
                    url=prod_url,
                    headers=[
                        {"name": "Authorization", "value": f"Bearer {prod_auth_token}"},
                        {"name": "x-posthog-project-id", "value": prod_project_id},
                        {"name": "x-posthog-mcp-version", "value": "2"},
                        {"name": "x-posthog-read-only", "value": str(read_only).lower()},
                    ],
                )
            )

    return configs


def _append_query_param(url: str, key: str, value: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{key}={value}"


def _resolve_local_mcp_url() -> str | None:
    if settings.SANDBOX_MCP_URL:
        return settings.SANDBOX_MCP_URL
    return None


def _resolve_prod_mcp_url() -> str | None:
    return "https://mcp.posthog.com/mcp"


def get_github_token(github_integration_id: int) -> Optional[str]:
    integration = Integration.objects.get(id=github_integration_id)
    github_integration = GitHubIntegration(integration)

    if github_integration.access_token_expired():
        github_integration.refresh_access_token()

    return github_integration.integration.access_token or None


def get_sandbox_name_for_task(task_id: str) -> str:
    return f"task-sandbox-{task_id}"
