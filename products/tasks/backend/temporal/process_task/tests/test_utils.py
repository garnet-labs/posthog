from unittest.mock import patch

from django.test import TestCase

from parameterized import parameterized

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


class TestFetchUserMcpServerConfigs(TestCase):
    TOKEN = "phx_test_token"
    PROJECT_ID = 42
    API_BASE = "https://us.posthog.com"

    def _mock_response(
        self,
        *,
        results: list[dict] | None = None,
        status_code: int = 200,
        ok: bool = True,
        text: str = "",
    ):
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.ok = ok
        resp.status_code = status_code
        resp.text = text or '{"results": []}'
        resp.json.return_value = {"results": results or []}
        return resp

    def _make_installation_data(
        self,
        *,
        installation_id: str = "inst-1",
        name: str = "Linear",
        url: str = "https://mcp.linear.app/mcp",
        is_enabled: bool = True,
        needs_reauth: bool = False,
        pending_oauth: bool = False,
    ) -> dict:
        return {
            "id": installation_id,
            "name": name,
            "url": url,
            "is_enabled": is_enabled,
            "needs_reauth": needs_reauth,
            "pending_oauth": pending_oauth,
        }

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_returns_configs_for_enabled_installations(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._make_installation_data()
        mock_get.return_value = self._mock_response(results=[installation])

        configs = fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID)

        expected_proxy = f"{self.API_BASE}/api/environments/{self.PROJECT_ID}/mcp_server_installations/inst-1/proxy/"
        assert configs == [
            McpServerConfig(
                type="http",
                name="Linear",
                url=expected_proxy,
                headers=[{"name": "Authorization", "value": f"Bearer {self.TOKEN}"}],
            )
        ]
        mock_get.assert_called_once_with(
            f"{self.API_BASE}/api/environments/{self.PROJECT_ID}/mcp_server_installations/",
            headers={
                "Authorization": f"Bearer {self.TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_skips_disabled_installations(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._make_installation_data(is_enabled=False)
        mock_get.return_value = self._mock_response(results=[installation])

        assert fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID) == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_skips_installations_needing_reauth(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._make_installation_data(needs_reauth=True)
        mock_get.return_value = self._mock_response(results=[installation])

        assert fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID) == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_skips_installations_with_pending_oauth(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._make_installation_data(pending_oauth=True)
        mock_get.return_value = self._mock_response(results=[installation])

        assert fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID) == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_returns_empty_on_api_error(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        mock_get.return_value = self._mock_response(status_code=500, ok=False)

        assert fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID) == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_returns_empty_on_request_exception(self, mock_get, mock_api_url) -> None:
        import requests

        mock_api_url.return_value = self.API_BASE
        mock_get.side_effect = requests.ConnectionError("connection refused")

        assert fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID) == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_returns_empty_on_json_decode_error(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        resp = self._mock_response(text="<html>ngrok warning page</html>")
        resp.json.side_effect = ValueError("No JSON object could be decoded")
        mock_get.return_value = resp

        assert fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID) == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_returns_empty_when_no_installations(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        mock_get.return_value = self._mock_response(results=[])

        assert fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID) == []

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_uses_name_from_response(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._make_installation_data(name="My Custom Server")
        mock_get.return_value = self._mock_response(results=[installation])

        configs = fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID)

        assert configs[0].name == "My Custom Server"

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_falls_back_to_url_when_name_empty(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._make_installation_data(name="", url="https://mcp.notion.com/mcp")
        mock_get.return_value = self._mock_response(results=[installation])

        configs = fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID)

        assert configs[0].name == "https://mcp.notion.com/mcp"

    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_strips_trailing_slash_from_api_url(self, mock_get, mock_api_url) -> None:
        mock_api_url.return_value = "https://us.posthog.com/"
        installation = self._make_installation_data(installation_id="inst-1")
        mock_get.return_value = self._mock_response(results=[installation])

        configs = fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID)

        assert configs[0].url.startswith("https://us.posthog.com/api/")

    @parameterized.expand(
        [
            (True, False, False, True),
            (False, False, False, False),
            (True, True, False, False),
            (True, False, True, False),
        ]
    )
    @patch("products.tasks.backend.temporal.process_task.utils.get_sandbox_api_url")
    @patch("products.tasks.backend.temporal.process_task.utils.http_requests.get")
    def test_filtering_matrix(
        self, is_enabled, needs_reauth, pending_oauth, expected_included, mock_get, mock_api_url
    ) -> None:
        mock_api_url.return_value = self.API_BASE
        installation = self._make_installation_data(
            is_enabled=is_enabled,
            needs_reauth=needs_reauth,
            pending_oauth=pending_oauth,
        )
        mock_get.return_value = self._mock_response(results=[installation])

        configs = fetch_user_mcp_server_configs(self.TOKEN, self.PROJECT_ID)

        assert (len(configs) == 1) == expected_included
