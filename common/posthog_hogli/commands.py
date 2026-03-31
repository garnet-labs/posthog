"""Developer Click commands for PostHog workflows.

This is the extension point for adding new Click commands to hogli.
Add your @cli.command() decorated functions here as an alternative to shell scripts.

They auto-register with hogli and appear in `hogli --help` automatically.

Example:
    ```python
    import click
    from hogli.cli import cli

    @cli.command(name="my:command", help="Does something useful")
    @click.argument('path', type=click.Path())
    @click.option('--flag', is_flag=True, help='Enable feature')
    def my_command(path, flag):
        '''Command implementation.'''
        # Your Python logic here
        click.echo(f"Processing {path}")
    ```

Guidelines:
- Use Click decorators for arguments and options
- Import cli group from hogli.cli (the framework in tools/hogli/)
- Name commands with colons for grouping (e.g., 'test:python', 'db:migrate')
- Add helpful docstrings - they become the command help text
- Prefer Python Click commands over shell scripts for better type safety

For simple shell commands or bin script delegation, use hogli.yaml instead.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import click
from hogli.hooks import register_precheck, register_telemetry_properties
from hogli.manifest import REPO_ROOT

# Side-effect imports: these modules use @cli.command() decorators that register
# commands with the CLI group when imported. The imports appear unused but are required.
from . import doctor, migrations, product, telemetry_commands  # noqa: F401
from .devenv import cli as devenv_cli  # noqa: F401
from .migrations import _compute_migration_diff, _get_cached_migration

# ---------------------------------------------------------------------------
# Precheck handlers -- registered with the hogli framework
# ---------------------------------------------------------------------------


def _migrations_precheck(check: dict, yes: bool) -> bool | None:
    """Check for orphaned migrations before starting services."""
    try:
        diff = _compute_migration_diff()

        if diff.orphaned:
            click.echo()
            click.secho("\u26a0\ufe0f  Orphaned migrations detected!", fg="yellow", bold=True)
            click.echo("These migrations are applied in the DB but don't exist in code.")
            click.echo("They were likely applied on another branch.\n")

            for m in diff.orphaned:
                cached = "cached" if _get_cached_migration(m.app, m.name) else "not cached"
                click.echo(f"    {m.app}: {m.name} ({cached})")
            click.echo()

            click.echo("Run 'hogli migrations:sync' to roll them back.\n")

            if not yes:
                if not click.confirm("Continue anyway?", default=False):
                    click.echo("Aborted. Run 'hogli migrations:sync' first.")
                    return False

    except Exception as e:
        # Don't block start if migration check fails (e.g., DB not running)
        click.secho(f"\u26a0\ufe0f  Could not check migrations: {e}", fg="yellow", err=True)

    return None


register_precheck("migrations", _migrations_precheck)


# ---------------------------------------------------------------------------
# Telemetry property hooks -- PostHog-specific environment properties
# ---------------------------------------------------------------------------


def _infer_process_manager(command: str | None) -> str | None:
    pm = os.environ.get("HOGLI_PROCESS_MANAGER")
    if pm:
        return os.path.basename(pm)
    if command == "start":
        return "mprocs" if "--mprocs" in sys.argv[2:] else "phrocs"
    return None


def _posthog_telemetry_properties(command: str | None = None) -> dict[str, Any]:
    return {
        "has_devenv_config": (REPO_ROOT / ".posthog" / ".generated" / "mprocs.yaml").exists(),
        "in_flox": os.environ.get("FLOX_ENV") is not None,
        "is_worktree": (REPO_ROOT / ".git").is_file(),
        "process_manager": _infer_process_manager(command),
    }


register_telemetry_properties(_posthog_telemetry_properties)
