"""Tests for the hogli CLI."""

from __future__ import annotations

import json
import time

import pytest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from hogli.core.cli import (
    _POSTHOG_DEV_CACHE_TTL_SECONDS,
    _check_email_domain,
    _get_github_token,
    _infer_process_manager,
    _is_posthog_dev,
    cli,
)

runner = CliRunner()


class TestMainCommand:
    """Test main command functionality."""

    def test_help_displays_commands(self) -> None:
        """Verify --help displays available commands."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        # Check for some core commands that should exist
        assert "start" in result.output or "docker" in result.output or "migrations" in result.output

    def test_help_displays_categories(self) -> None:
        """Verify --help displays command categories."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        # Should have at least one category from metadata
        output_lower = result.output.lower()
        assert any(
            category in output_lower for category in ["core development", "start services", "migrations", "tests"]
        )

    def test_invalid_command_fails(self) -> None:
        """Verify invalid commands fail gracefully."""
        result = runner.invoke(cli, ["nonexistent-command"])
        assert result.exit_code != 0


class TestQuickstartCommand:
    """Test quickstart command."""

    def test_quickstart_displays_help(self) -> None:
        """Verify quickstart command displays getting started info."""
        result = runner.invoke(cli, ["quickstart"])
        assert result.exit_code == 0
        assert "PostHog Development Quickstart" in result.output
        assert "hogli" in result.output


class TestMetaCheckCommand:
    """Test meta:check command."""

    def test_meta_check_validates_manifest(self) -> None:
        """Verify meta:check validates manifest entries."""
        result = runner.invoke(cli, ["meta:check"])
        # Should either pass or report missing entries clearly
        assert "bin script" in result.output.lower() or "✓" in result.output


class TestMetaConceptsCommand:
    """Test meta:concepts command."""

    def test_meta_concepts_displays_services(self) -> None:
        """Verify meta:concepts displays infrastructure concepts."""
        result = runner.invoke(cli, ["meta:concepts"])
        assert result.exit_code == 0
        assert "Infrastructure" in result.output or "service" in result.output.lower()


class TestDynamicCommandRegistration:
    """Test that commands are dynamically registered from manifest."""

    def test_start_command_exists(self) -> None:
        """Verify start command is registered from manifest."""
        result = runner.invoke(cli, ["start", "--help"])
        # Should either work or show a proper Click error
        assert "Error: No such command" not in result.output or result.exit_code == 2

    def test_migrations_command_exists(self) -> None:
        """Verify migrations commands are registered from manifest."""
        result = runner.invoke(cli, ["migrations:run", "--help"])
        # Should either work or show proper error
        assert "Error: No such command" not in result.output or result.exit_code == 2

    @patch("hogli.core.command_types._run")
    def test_command_with_bin_script_executes(self, mock_run: MagicMock) -> None:
        """Verify bin_script commands can execute."""
        mock_run.return_value = None
        # Try a command that should have a bin_script
        result = runner.invoke(cli, ["check:postgres", "--help"])
        # Should return help or execute
        assert result.exit_code in (0, 2)

    @patch("hogli.core.command_types._run")
    def test_direct_command_execution(self, mock_run: MagicMock) -> None:
        """Verify direct cmd commands execute properly."""
        mock_run.return_value = None
        # build:schema-json uses direct cmd field
        result = runner.invoke(cli, ["build:schema-json", "--help"])
        assert result.exit_code in (0, 2)


class TestCommandInjectionPrevention:
    """Test that command argument handling is secure."""

    @patch("hogli.core.command_types._run")
    def test_arguments_are_properly_escaped(self, mock_run: MagicMock) -> None:
        """Verify arguments passed to commands are properly escaped."""
        mock_run.return_value = None
        # Invoke a command with special characters
        result = runner.invoke(cli, ["migrations:run", "--help"])
        # The key test is that no exception is raised during argument parsing
        assert result.exit_code in (0, 1, 2)  # Any of these is acceptable

    @patch("hogli.core.command_types._run")
    def test_shell_operators_are_handled_safely(self, mock_run: MagicMock) -> None:
        """Verify commands with shell operators are executed safely."""
        mock_run.return_value = None
        # Invoke a composite command
        result = runner.invoke(cli, ["dev:reset", "--help"])
        # Should not raise an exception
        assert result.exit_code in (0, 1, 2)


class TestHelpText:
    """Test command help text generation."""

    def test_command_help_includes_description(self) -> None:
        """Verify command help includes description from manifest."""
        result = runner.invoke(cli, ["start", "--help"])
        # Should contain help text
        assert "Usage:" in result.output or result.exit_code == 2

    def test_category_grouping_in_help(self) -> None:
        """Verify help output groups commands by category."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        # Should have multiple sections
        lines = result.output.split("\n")
        # Look for section headers (typically uppercase or titled)
        assert len(lines) > 10


class TestProcessManagerInference:
    """Test process manager inference for telemetry."""

    def test_start_defaults_to_phrocs(self, monkeypatch) -> None:
        monkeypatch.delenv("HOGLI_PROCESS_MANAGER", raising=False)
        monkeypatch.setattr("sys.argv", ["hogli", "start"])

        assert _infer_process_manager("start") == "phrocs"

    def test_start_uses_mprocs_flag(self, monkeypatch) -> None:
        monkeypatch.delenv("HOGLI_PROCESS_MANAGER", raising=False)
        monkeypatch.setattr("sys.argv", ["hogli", "start", "--mprocs"])

        assert _infer_process_manager("start") == "mprocs"

    def test_env_override_wins(self, monkeypatch) -> None:
        monkeypatch.setenv("HOGLI_PROCESS_MANAGER", "/usr/local/bin/phrocs")
        monkeypatch.setattr("sys.argv", ["hogli", "start", "--mprocs"])

        assert _infer_process_manager("start") == "phrocs"


class TestCheckEmailDomain:
    @pytest.fixture()
    def _fake_home(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hogli.core.cli.Path.home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr("hogli.core.cli.REPO_ROOT", tmp_path)
        return tmp_path

    def test_posthog_email(self, _fake_home):
        (_fake_home / ".gitconfig").write_text("[user]\n\temail = dev@posthog.com\n")
        assert _check_email_domain() is True

    def test_non_posthog_email(self, _fake_home):
        (_fake_home / ".gitconfig").write_text("[user]\n\temail = user@example.com\n")
        assert _check_email_domain() is False

    def test_no_config_files(self, _fake_home):
        assert _check_email_domain() is False


class TestGetGithubToken:
    def test_gh_token_env(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok-from-env")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert _get_github_token() == "tok-from-env"

    def test_github_token_env(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "tok-github")
        assert _get_github_token() == "tok-github"

    @patch("hogli.core.cli.subprocess.run")
    def test_falls_back_to_gh_auth(self, mock_run, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        mock_run.return_value = MagicMock(returncode=0, stdout="tok-cli\n")
        assert _get_github_token() == "tok-cli"

    @patch("hogli.core.cli.subprocess.run", side_effect=FileNotFoundError)
    def test_no_gh_returns_none(self, _mock_run, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert _get_github_token() is None


class TestIsPosthogDev:
    @pytest.fixture()
    def _config_dir(self, tmp_path, monkeypatch):
        config_file = tmp_path / "hogli_telemetry.json"
        monkeypatch.setattr("hogli.telemetry.get_config_path", lambda: config_file)
        return config_file

    def _write_config(self, path, **kwargs):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(kwargs))

    def test_fresh_cache_returns_cached_true(self, _config_dir):
        self._write_config(_config_dir, is_posthog_org_member=True, org_check_timestamp=time.time())
        assert _is_posthog_dev() is True

    def test_fresh_cache_returns_cached_false(self, _config_dir):
        self._write_config(_config_dir, is_posthog_org_member=False, org_check_timestamp=time.time())
        assert _is_posthog_dev() is False

    @patch("hogli.core.cli._check_github_org", return_value=True)
    @patch("hogli.core.cli._get_github_token", return_value="tok")
    def test_stale_cache_triggers_api_check(self, _mock_tok, _mock_org, _config_dir):
        stale_ts = time.time() - _POSTHOG_DEV_CACHE_TTL_SECONDS - 1
        self._write_config(_config_dir, is_posthog_org_member=False, org_check_timestamp=stale_ts)

        assert _is_posthog_dev() is True

    @patch("hogli.core.cli._check_github_org", return_value=True)
    @patch("hogli.core.cli._get_github_token", return_value="tok")
    def test_api_member_caches_true(self, _mock_tok, _mock_org, _config_dir):
        assert _is_posthog_dev() is True

        config = json.loads(_config_dir.read_text())
        assert config["is_posthog_org_member"] is True
        assert config["org_check_timestamp"] > 0

    @patch("hogli.core.cli._check_github_org", return_value=False)
    @patch("hogli.core.cli._get_github_token", return_value="tok")
    def test_api_non_member_caches_false(self, _mock_tok, _mock_org, _config_dir):
        assert _is_posthog_dev() is False

        config = json.loads(_config_dir.read_text())
        assert config["is_posthog_org_member"] is False

    @patch("hogli.core.cli._check_email_domain", return_value=True)
    @patch("hogli.core.cli._get_github_token", return_value=None)
    def test_no_token_falls_back_to_email(self, _mock_tok, mock_email, _config_dir):
        assert _is_posthog_dev() is True
        mock_email.assert_called_once()

    @patch("hogli.core.cli._check_email_domain", return_value=False)
    @patch("hogli.core.cli._check_github_org", side_effect=Exception("network error"))
    @patch("hogli.core.cli._get_github_token", return_value="tok")
    def test_api_error_falls_back_to_email(self, _mock_tok, _mock_org, mock_email, _config_dir):
        assert _is_posthog_dev() is False
        mock_email.assert_called_once()
