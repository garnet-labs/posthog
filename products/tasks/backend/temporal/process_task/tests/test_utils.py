from unittest.mock import patch

from django.test import TestCase

from parameterized import parameterized

from products.mcp_store.backend.facade.contracts import ActiveInstallationInfo
from products.tasks.backend.temporal.process_task.utils import (
    McpServerConfig,
    get_sandbox_ph_mcp_configs,
    get_user_mcp_server_configs,
)


class TestGetSandboxMcpConfigs(TestCase):
    TOKEN = "phx_test_token"
    PROJECT_ID = 42

    def _expected_headers(self, *, read_only: bool = True) -> list[dict[str, str]]:
        return [
            {"name": "Authorization", "value": f"Bearer {self.TOKEN}"},
            {"name": "x-posthog-project-id", "value": str(self.PROJECT_ID)},
            {"name": "x-posthog-mcp-version", "value": "2"},
            {"name": "x-posthog-read-only", "value": str(read_only).lower()},
        ]

    @parameterized.expand(
        [
            ("https://app.posthog.com", "https://mcp.posthog.com/mcp"),
            ("https://us.posthog.com", "https://mcp.posthog.com/mcp"),
            ("https://eu.posthog.com", "https://mcp-eu.posthog.com/mcp"),
        ]
    )
    def test_derives_mcp_config_from_site_url(self, site_url: str, expected_mcp_url: str) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            mock_settings.SANDBOX_MCP_URL = None
            mock_settings.SITE_URL = site_url
            configs = get_sandbox_ph_mcp_configs(self.TOKEN, self.PROJECT_ID)
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
            mock_settings.SANDBOX_MCP_URL = "https://custom-mcp.example.com/mcp"
            mock_settings.SITE_URL = "https://app.posthog.com"
            configs = get_sandbox_ph_mcp_configs(self.TOKEN, self.PROJECT_ID)
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
            mock_settings.SANDBOX_MCP_URL = None
            mock_settings.SITE_URL = "https://app.posthog.com"
            configs = get_sandbox_ph_mcp_configs(self.TOKEN, self.PROJECT_ID, scopes="full")
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
            mock_settings.SANDBOX_MCP_URL = None
            mock_settings.SITE_URL = "https://app.posthog.com"
            configs = get_sandbox_ph_mcp_configs(
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
            mock_settings.SANDBOX_MCP_URL = None
            mock_settings.SITE_URL = "https://app.posthog.com"
            configs = get_sandbox_ph_mcp_configs(
                self.TOKEN, self.PROJECT_ID, scopes=["feature_flag:read", "insight:read"]
            )
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
            mock_settings.SANDBOX_MCP_URL = None
            mock_settings.SITE_URL = site_url
            assert get_sandbox_ph_mcp_configs(self.TOKEN, self.PROJECT_ID) == []

    def test_returns_empty_list_when_no_site_url(self) -> None:
        with patch("products.tasks.backend.temporal.process_task.utils.settings") as mock_settings:
            mock_settings.SANDBOX_MCP_URL = None
            mock_settings.SITE_URL = ""
            assert get_sandbox_ph_mcp_configs(self.TOKEN, self.PROJECT_ID) == []


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


class TestFetchUserMcpServerConfigs(TestCase):
    TOKEN = "phx_test_token"
    TEAM_ID = 42
    USER_ID = 7
    API_BASE = "https://us.posthog.com"

    MOCK_FACADE = "products.tasks.backend.temporal.process_task.utils.get_active_installations"
    MOCK_API_URL = "products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url"

    def _make_installation(self, **kwargs) -> ActiveInstallationInfo:
        defaults = {
            "id": "abc-123",
            "name": "Linear",
            "proxy_path": f"/api/environments/{self.TEAM_ID}/mcp_server_installations/abc-123/proxy/",
        }
        defaults.update(kwargs)
        return ActiveInstallationInfo(**defaults)

    @patch(MOCK_API_URL)
    @patch(MOCK_FACADE)
    def test_builds_configs_from_facade_results(self, mock_facade, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._make_installation()
        mock_facade.return_value = [installation]

        configs = get_user_mcp_server_configs(self.TOKEN, self.TEAM_ID, self.USER_ID)

        mock_facade.assert_called_once_with(self.TEAM_ID, self.USER_ID)
        assert configs == [
            McpServerConfig(
                type="http",
                name="Linear",
                url=f"{self.API_BASE}/api/environments/{self.TEAM_ID}/mcp_server_installations/abc-123/proxy/",
                headers=[{"name": "Authorization", "value": f"Bearer {self.TOKEN}"}],
            )
        ]

    @patch(MOCK_API_URL)
    @patch(MOCK_FACADE)
    def test_returns_empty_when_no_installations(self, mock_facade, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        mock_facade.return_value = []

        assert get_user_mcp_server_configs(self.TOKEN, self.TEAM_ID, self.USER_ID) == []

    @patch(MOCK_API_URL)
    @patch(MOCK_FACADE)
    def test_strips_trailing_slash_from_api_url(self, mock_facade, mock_api_url) -> None:
        mock_api_url.return_value = "https://us.posthog.com/"
        mock_facade.return_value = [self._make_installation()]

        configs = get_user_mcp_server_configs(self.TOKEN, self.TEAM_ID, self.USER_ID)

        assert configs[0].url.startswith("https://us.posthog.com/api/")

    @patch(MOCK_API_URL)
    @patch(MOCK_FACADE)
    def test_multiple_installations(self, mock_facade, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        mock_facade.return_value = [
            self._make_installation(
                id="abc-1", name="Linear", proxy_path="/api/environments/42/mcp_server_installations/abc-1/proxy/"
            ),
            self._make_installation(
                id="abc-2", name="Notion", proxy_path="/api/environments/42/mcp_server_installations/abc-2/proxy/"
            ),
        ]

        configs = get_user_mcp_server_configs(self.TOKEN, self.TEAM_ID, self.USER_ID)

        assert len(configs) == 2
        assert configs[0].name == "Linear"
        assert configs[1].name == "Notion"
