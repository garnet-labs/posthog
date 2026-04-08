from posthog.test.base import BaseTest
from unittest.mock import patch

from django.test import TestCase

from parameterized import parameterized

from posthog.models import Organization, Team, User

from products.mcp_store.backend.models import MCPServer, MCPServerInstallation
from products.tasks.backend.temporal.process_task.utils import (
    McpServerConfig,
    fetch_user_mcp_server_configs,
    get_sandbox_ph_mcp_configs,
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


class TestFetchUserMcpServerConfigs(BaseTest):
    TOKEN = "phx_test_token"
    API_BASE = "https://us.posthog.com"

    def _create_installation(self, **kwargs) -> MCPServerInstallation:
        defaults: dict = {
            "team": self.team,
            "user": self.user,
            "display_name": "Linear",
            "url": "https://mcp.linear.app/mcp",
            "auth_type": "api_key",
            "is_enabled": True,
        }
        defaults.update(kwargs)
        return MCPServerInstallation.objects.create(**defaults)

    def _fetch(self, **kwargs) -> list[McpServerConfig]:
        defaults: dict = {
            "token": self.TOKEN,
            "team_id": self.team.id,
            "user_id": self.user.id,
        }
        defaults.update(kwargs)
        return fetch_user_mcp_server_configs(**defaults)

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_returns_configs_for_enabled_installations(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._create_installation()

        configs = self._fetch()

        expected_proxy = (
            f"{self.API_BASE}/api/environments/{self.team.id}/mcp_server_installations/{installation.id}/proxy/"
        )
        assert configs == [
            McpServerConfig(
                type="http",
                name="Linear",
                url=expected_proxy,
                headers=[{"name": "Authorization", "value": f"Bearer {self.TOKEN}"}],
            )
        ]

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_skips_disabled_installations(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        self._create_installation(is_enabled=False)

        assert self._fetch() == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_skips_installations_needing_reauth(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        self._create_installation(
            auth_type="oauth",
            sensitive_configuration={"needs_reauth": True, "access_token": "tok"},
        )

        assert self._fetch() == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_skips_installations_with_pending_oauth(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        self._create_installation(auth_type="oauth", sensitive_configuration={})

        assert self._fetch() == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_returns_empty_when_no_installations(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE

        assert self._fetch() == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_uses_display_name(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        self._create_installation(display_name="My Custom Server")

        configs = self._fetch()

        assert configs[0].name == "My Custom Server"

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_name_falls_back_to_server_name(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        server = MCPServer.objects.create(
            name="Linear", url="https://linear.app/.well-known/oauth", created_by=self.user
        )
        self._create_installation(display_name="", server=server)

        configs = self._fetch()

        assert configs[0].name == "Linear"

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_name_falls_back_to_url(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        self._create_installation(display_name="", url="https://mcp.notion.com/mcp")

        configs = self._fetch()

        assert configs[0].name == "https://mcp.notion.com/mcp"

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_strips_trailing_slash_from_api_url(self, mock_api_url) -> None:
        mock_api_url.return_value = "https://us.posthog.com/"
        self._create_installation()

        configs = self._fetch()

        assert configs[0].url.startswith("https://us.posthog.com/api/")

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_api_key_not_filtered_by_oauth_checks(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        self._create_installation(auth_type="api_key", sensitive_configuration={})

        configs = self._fetch()

        assert len(configs) == 1

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_only_returns_for_given_user(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        other_user = User.objects.create_and_join(self.organization, "other@posthog.com", "password")
        self._create_installation(user=other_user)
        self._create_installation(url="https://mcp.other.com/mcp")

        configs = self._fetch()

        assert len(configs) == 1
        assert configs[0].name == "Linear"

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_only_returns_for_given_team(self, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        other_org = Organization.objects.create(name="Other Org")
        other_team = Team.objects.create(organization=other_org, name="Other Team")
        self._create_installation(team=other_team)
        self._create_installation(url="https://mcp.other.com/mcp")

        configs = self._fetch()

        assert len(configs) == 1

    @parameterized.expand(
        [
            ("enabled_api_key", True, "api_key", {}, True),
            ("disabled_api_key", False, "api_key", {}, False),
            ("oauth_with_token", True, "oauth", {"access_token": "tok"}, True),
            ("oauth_needs_reauth", True, "oauth", {"needs_reauth": True, "access_token": "tok"}, False),
            ("oauth_pending", True, "oauth", {}, False),
        ]
    )
    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    def test_filtering_matrix(
        self, _name, is_enabled, auth_type, sensitive_configuration, expected_included, mock_api_url
    ) -> None:
        mock_api_url.return_value = self.API_BASE
        self._create_installation(
            is_enabled=is_enabled,
            auth_type=auth_type,
            sensitive_configuration=sensitive_configuration,
        )

        configs = self._fetch()

        assert (len(configs) == 1) == expected_included
