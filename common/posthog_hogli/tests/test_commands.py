"""Tests for PostHog-specific hogli commands and hooks."""

from __future__ import annotations

from posthog_hogli.commands import _infer_process_manager


class TestProcessManagerInference:
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
