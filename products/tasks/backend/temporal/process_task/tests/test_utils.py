from unittest.mock import patch

from django.test import TestCase

from parameterized import parameterized

from products.tasks.backend.temporal.process_task.utils import McpServerConfig, get_sandbox_mcp_configs


class TestGetSandboxMcpConfigs(TestCase):
    TOKEN = "phx_test_token"
    PROJECT_ID = 42

    def _expected_headers(
        self, *, read_only: bool = True, token: str | None = None, project_id: str | None = None
    ) -> list[dict[str, str]]:
        return [
            {"name": "Authorization", "value": f"Bearer {token or self.TOKEN}"},
            {"name": "x-posthog-project-id", "value": project_id or str(self.PROJECT_ID)},
            {"name": "x-posthog-mcp-version", "value": "2"},
            {"name": "x-posthog-read-only", "value": str(read_only).lower()},
        ]

    def _mock_settings(self, mock: object, **overrides: object) -> None:
        defaults = {
            "SANDBOX_MCP_URL": None,
            "SANDBOX_MCP_AUTH_TOKEN": None,
            "SANDBOX_MCP_PROJECT_ID": None,
            "SITE_URL": "",
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            setattr(mock, k, v)

    @parameterized.expand(
        [
            ("https://app.posthog.com", "https://mcp.posthog.com/mcp"),
            ("https://us.posthog.com", "https://mcp.posthog.com/mcp"),
            ("https://eu.posthog.com", "https://mcp-eu.posthog.com/mcp"),
        ]
    )
    def test_derives_mcp_config_from_site_url(self, site_url: str, expected_mcp_url: str) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(mock_settings, SITE_URL=site_url)
            configs = get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID)
            assert configs == [
                McpServerConfig(
                    type="http",
                    name="posthog",
                    url=expected_mcp_url,
                    headers=self._expected_headers(),
                )
            ]

    def test_explicit_sandbox_mcp_url_takes_precedence(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(
                mock_settings,
                SANDBOX_MCP_URL="https://custom-mcp.example.com/mcp",
                SITE_URL="https://app.posthog.com",
            )
            configs = get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID)
            assert configs == [
                McpServerConfig(
                    type="http",
                    name="posthog",
                    url="https://custom-mcp.example.com/mcp",
                    headers=self._expected_headers(),
                )
            ]

    def test_full_scopes_preset(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(mock_settings, SITE_URL="https://app.posthog.com")
            configs = get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID, scopes="full")
            assert configs == [
                McpServerConfig(
                    type="http",
                    name="posthog",
                    url="https://mcp.posthog.com/mcp",
                    headers=self._expected_headers(read_only=False),
                )
            ]

    def test_custom_scopes_with_write(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(mock_settings, SITE_URL="https://app.posthog.com")
            configs = get_sandbox_mcp_configs(
                self.TOKEN, self.PROJECT_ID, scopes=["feature_flag:read", "feature_flag:write"]
            )
            assert configs == [
                McpServerConfig(
                    type="http",
                    name="posthog",
                    url="https://mcp.posthog.com/mcp",
                    headers=self._expected_headers(read_only=False),
                )
            ]

    def test_custom_scopes_read_only(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(mock_settings, SITE_URL="https://app.posthog.com")
            configs = get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID, scopes=["feature_flag:read", "insight:read"])
            assert configs == [
                McpServerConfig(
                    type="http",
                    name="posthog",
                    url="https://mcp.posthog.com/mcp",
                    headers=self._expected_headers(read_only=True),
                )
            ]

    @parameterized.expand(
        [
            ("http://localhost:8000",),
            ("https://custom.example.com",),
        ]
    )
    def test_returns_empty_list_for_unknown_hosts(self, site_url: str) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(mock_settings, SITE_URL=site_url)
            assert get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID) == []

    def test_returns_empty_list_when_no_site_url(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(mock_settings)
            assert get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID) == []

    def test_dual_mcp_when_prod_settings_set(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(
                mock_settings,
                SANDBOX_MCP_URL="http://host.docker.internal:8787/mcp",
                SANDBOX_MCP_AUTH_TOKEN="prod_token_123",
                SANDBOX_MCP_PROJECT_ID="99",
                SITE_URL="https://us.posthog.com",
            )
            configs = get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID)
            assert configs == [
                McpServerConfig(
                    type="http",
                    name="posthog-local",
                    url="http://host.docker.internal:8787/mcp?features=action_prediction_models",
                    headers=self._expected_headers(),
                ),
                McpServerConfig(
                    type="http",
                    name="posthog",
                    url="https://mcp.posthog.com/mcp",
                    headers=self._expected_headers(token="prod_token_123", project_id="99"),
                ),
            ]

    def test_dual_mcp_local_url_with_existing_query_params(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(
                mock_settings,
                SANDBOX_MCP_URL="http://host.docker.internal:8787/mcp?v=2",
                SANDBOX_MCP_AUTH_TOKEN="prod_token",
                SANDBOX_MCP_PROJECT_ID="5",
                SITE_URL="https://us.posthog.com",
            )
            configs = get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID)
            assert configs[0].url == "http://host.docker.internal:8787/mcp?v=2&features=action_prediction_models"

    def test_prod_env_without_local_mcp_url_uses_site_url_derivation(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            self._mock_settings(
                mock_settings,
                SANDBOX_MCP_AUTH_TOKEN="prod_token",
                SANDBOX_MCP_PROJECT_ID="5",
                SITE_URL="https://us.posthog.com",
            )
            configs = get_sandbox_mcp_configs(self.TOKEN, self.PROJECT_ID)
            # Local derived from SITE_URL, filtered
            assert configs[0].name == "posthog-local"
            assert configs[0].url == "https://mcp.posthog.com/mcp?features=action_prediction_models"
            # Prod uses same derived URL, unfiltered
            assert configs[1].name == "posthog"
            assert configs[1].url == "https://mcp.posthog.com/mcp"


class TestMcpServerConfigToDict(TestCase):
    def test_minimal_config(self) -> None:
        config = McpServerConfig(type="http", name="posthog", url="https://mcp.posthog.com/mcp")
        assert config.to_dict() == {
            "type": "http",
            "name": "posthog",
            "url": "https://mcp.posthog.com/mcp",
            "headers": [],
        }

    def test_config_with_headers(self) -> None:
        config = McpServerConfig(
            type="http",
            name="posthog",
            url="https://mcp.example.com/mcp",
            headers=[{"name": "Authorization", "value": "Bearer token"}],
        )
        assert config.to_dict() == {
            "type": "http",
            "name": "posthog",
            "url": "https://mcp.example.com/mcp",
            "headers": [{"name": "Authorization", "value": "Bearer token"}],
        }
