from types import SimpleNamespace

from unittest.mock import Mock, patch

from asgiref.sync import async_to_sync
from temporalio.testing import ActivityEnvironment

from products.hogbot.backend.temporal.activities.create_hogbot_sandbox import (
    CreateHogbotSandboxInput,
    create_hogbot_sandbox,
)


def _execution_result(*, exit_code: int = 0, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(exit_code=exit_code, stdout=stdout, stderr=stderr)


def _sandbox() -> Mock:
    sandbox = Mock()
    sandbox.id = "sb-1"
    sandbox.get_connect_credentials.return_value = SimpleNamespace(url="http://sandbox", token="token")
    sandbox.clone_repository.return_value = _execution_result()
    sandbox.execute.return_value = _execution_result()
    return sandbox


class TestCreateHogbotSandboxActivity:
    def test_create_hogbot_sandbox_uses_runtime_snapshot_without_recloning_repository(self) -> None:
        sandbox = _sandbox()
        runtime = SimpleNamespace(latest_snapshot_external_id="snap-1")

        with (
            patch(
                "products.hogbot.backend.temporal.activities.create_hogbot_sandbox.HogbotRuntime.objects.get_or_create",
                return_value=(runtime, False),
            ),
            patch(
                "products.hogbot.backend.temporal.activities.create_hogbot_sandbox.Sandbox.create",
                return_value=sandbox,
            ) as mock_create,
            patch(
                "products.hogbot.backend.temporal.activities.create_hogbot_sandbox._get_github_token",
                return_value="github-token",
            ),
        ):
            result = async_to_sync(ActivityEnvironment().run)(
                create_hogbot_sandbox,
                CreateHogbotSandboxInput(
                    team_id=1,
                    repository="PostHog/PostHog",
                    github_integration_id=7,
                ),
            )

        config = mock_create.call_args.args[0]
        assert config.snapshot_external_id == "snap-1"
        assert config.environment_variables == {"GITHUB_TOKEN": "github-token"}
        sandbox.clone_repository.assert_not_called()
        sandbox.execute.assert_not_called()
        assert result.sandbox_id == "sb-1"
        assert result.sandbox_url == "http://sandbox"
        assert result.connect_token == "token"

    def test_create_hogbot_sandbox_clones_repository_when_snapshot_is_unavailable(self) -> None:
        sandbox = _sandbox()
        runtime = SimpleNamespace(latest_snapshot_external_id=None)

        with (
            patch(
                "products.hogbot.backend.temporal.activities.create_hogbot_sandbox.HogbotRuntime.objects.get_or_create",
                return_value=(runtime, False),
            ),
            patch(
                "products.hogbot.backend.temporal.activities.create_hogbot_sandbox.Sandbox.create",
                return_value=sandbox,
            ) as mock_create,
            patch(
                "products.hogbot.backend.temporal.activities.create_hogbot_sandbox._get_github_token",
                return_value="github-token",
            ),
        ):
            result = async_to_sync(ActivityEnvironment().run)(
                create_hogbot_sandbox,
                CreateHogbotSandboxInput(
                    team_id=1,
                    repository="PostHog/PostHog",
                    github_integration_id=7,
                ),
            )

        config = mock_create.call_args.args[0]
        assert config.snapshot_external_id is None
        sandbox.clone_repository.assert_called_once_with("PostHog/PostHog", github_token="github-token")
        assert result.sandbox_id == "sb-1"
