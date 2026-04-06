"""Product bootstrapping — scaffold new products and register them in config files."""

from __future__ import annotations

import re
import json
from collections.abc import Callable
from pathlib import Path

import click

from .paths import (
    DB_ROUTING_YAML,
    DJANGO_SETTINGS,
    FEATURE_FLAGS_CONSTANTS,
    FRONTEND_PACKAGE_JSON,
    PRODUCTS_DIR,
    TACH_TOML,
    load_structure,
)


def flatten_structure(files: dict, prefix: str = "", result: dict | None = None) -> dict[str, dict]:
    """
    Flatten nested structure dict into flat paths.
    e.g., {"facade/": {"api.py": {...}}} -> {"facade/api.py": {...}}
    """
    if result is None:
        result = {}
    for name, config in files.items():
        if name.endswith("/"):
            flatten_structure(config, prefix + name, result)
        else:
            result[prefix + name] = config if isinstance(config, dict) else {}
    return result


def _render_template(template: str, product_name: str) -> str:
    pascal_name = "".join(word.capitalize() for word in product_name.split("_"))
    upper_name = product_name.upper()
    hyphen_name = product_name.replace("_", "-")
    return template.format(product=product_name, Product=pascal_name, PRODUCT=upper_name, product_hyphen=hyphen_name)


def _register_in_file(
    file_path: Path, label: str, needle: str, write_fn: Callable[[str], str | None], *, dry_run: bool
) -> None:
    """Register a product entry in a config file. Skips if needle already present."""
    if not file_path.exists():
        return
    content = file_path.read_text()
    if needle in content:
        click.echo(f"\n  Already in {label}: {needle}")
        return
    if dry_run:
        click.echo(f"\n  Would add to {label}: {needle}")
        return
    result = write_fn(content)
    if result is not None:
        file_path.write_text(result)
        click.echo(f"\n  Added to {label}: {needle}")


def _add_to_tach_toml(product_name: str, *, dry_run: bool) -> None:
    module_path = f"products.{product_name}"
    block = (
        f"\n[[modules]]\n"
        f'path = "{module_path}"\n'
        f'depends_on = ["posthog"]\n'
        f'layer = "products"\n'
        f"interfaces = [\n"
        f'    "{module_path}.backend.facade",\n'
        f'    "{module_path}.backend.presentation.views",\n'
        f"]\n"
    )
    _register_in_file(
        TACH_TOML,
        "tach.toml",
        f'path = "{module_path}"',
        lambda content: content.rstrip() + "\n" + block,
        dry_run=dry_run,
    )


def _add_to_frontend_package_json(product_name: str, *, dry_run: bool) -> None:
    pkg_name = f"@posthog/products-{product_name.replace('_', '-')}"

    def write(content: str) -> str:
        data = json.loads(content)
        deps = data.get("dependencies", {})
        deps[pkg_name] = "workspace:*"
        data["dependencies"] = dict(sorted(deps.items()))
        return json.dumps(data, indent=4) + "\n"

    _register_in_file(FRONTEND_PACKAGE_JSON, "frontend/package.json", pkg_name, write, dry_run=dry_run)


def _add_to_django_settings(product_name: str, *, dry_run: bool) -> None:
    pascal_name = "".join(word.capitalize() for word in product_name.split("_"))
    app_config = f"products.{product_name}.backend.apps.{pascal_name}Config"

    def write(content: str) -> str | None:
        pattern = r'(    "products\.[^"]+",\n)(?!    "products\.)'
        match = list(re.finditer(pattern, content))
        if not match:
            click.echo(f"\n  Could not find INSTALLED_APPS products section — add manually: {app_config}")
            return None
        insert_pos = match[-1].end()
        return content[:insert_pos] + f'    "{app_config}",\n' + content[insert_pos:]

    _register_in_file(DJANGO_SETTINGS, "Django settings", app_config, write, dry_run=dry_run)


def _add_to_feature_flags(product_name: str, *, dry_run: bool) -> None:
    flag_key = product_name.upper()
    flag_value = product_name.replace("_", "-")
    entry = f"    {flag_key}: '{flag_value}', // owner: #team-CHANGEME\n"

    def write(content: str) -> str | None:
        lines = content.split("\n")

        marker_idx = None
        for i, line in enumerate(lines):
            if "// PLEASE KEEP THIS ALPHABETICALLY ORDERED" in line:
                marker_idx = i
                break

        if marker_idx is None:
            click.echo(f"\n  Could not find FEATURE_FLAGS insertion point — add manually: {flag_key}")
            return None

        # Walk backward from marker to find the last section comment.
        # constants.tsx has curated sub-sections (Eternal, Holidays, UX, etc.)
        # before the general "Temporary feature flags" section — we only want
        # to insert into that last section.
        section_start = None
        for i in range(marker_idx - 1, -1, -1):
            stripped = lines[i].strip()
            if stripped.startswith("//") and not stripped.startswith("// owner"):
                section_start = i + 1
                break

        # Walk forward to find the alphabetical insertion point
        insert_idx = marker_idx
        if section_start is not None:
            for i in range(section_start, marker_idx):
                stripped = lines[i].strip()
                if not stripped or stripped.startswith("//"):
                    continue
                existing_key = stripped.split(":")[0].strip().rstrip(",")
                if existing_key > flag_key:
                    insert_idx = i
                    break

        lines.insert(insert_idx, entry.rstrip("\n"))
        return "\n".join(lines)

    _register_in_file(FEATURE_FLAGS_CONSTANTS, "FEATURE_FLAGS constants", flag_key, write, dry_run=dry_run)


def _get_existing_databases() -> list[str]:
    """Read unique database names from db_routing.yaml."""
    if not DB_ROUTING_YAML.exists():
        return []
    import yaml

    config = yaml.safe_load(DB_ROUTING_YAML.read_text()) or {}
    return sorted({r["database"] for r in config.get("routes", []) if r.get("database")})


def _add_to_db_routing(product_name: str, database_name: str, *, dry_run: bool) -> None:
    route_entry = f"    - app_label: {product_name}\n      database: {database_name}\n"

    def write(content: str) -> str:
        return content.rstrip() + "\n" + route_entry

    _register_in_file(
        DB_ROUTING_YAML,
        "products/db_routing.yaml",
        f"app_label: {product_name}",
        write,
        dry_run=dry_run,
    )


_VALID_PRODUCT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def bootstrap_product(name: str, dry_run: bool, force: bool) -> None:
    if not _VALID_PRODUCT_NAME_RE.match(name):
        raise click.ClickException(
            f"Invalid product name '{name}' — must be lowercase, start with a letter, and contain only [a-z0-9_]."
        )
    product_dir = PRODUCTS_DIR / name

    if product_dir.exists() and not force:
        raise click.ClickException(f"Product '{name}' already exists at {product_dir}. Use --force to overwrite.")

    structure = load_structure()
    created: list[str] = []
    skipped: list[str] = []

    for path, config in flatten_structure(structure.get("root_files", {})).items():
        file_path = product_dir / path
        if dry_run:
            (skipped if (file_path.exists() and not force) else created).append(path)
            continue
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists() and not force:
            skipped.append(path)
            continue
        file_path.write_text(_render_template(config.get("template", ""), name))
        created.append(path)

    for path, config in flatten_structure(structure.get("backend_files", {})).items():
        file_path = product_dir / "backend" / path
        label = f"backend/{path}"
        if dry_run:
            (skipped if (file_path.exists() and not force) else created).append(label)
            continue
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists() and not force:
            skipped.append(label)
            continue
        file_path.write_text(_render_template(config.get("template", ""), name))
        created.append(label)

    for folder_name in structure.get("frontend_files", {}).keys():
        folder_path = product_dir / "frontend" / folder_name.rstrip("/")
        label = f"frontend/{folder_name}"
        if dry_run:
            created.append(label)
        else:
            folder_path.mkdir(parents=True, exist_ok=True)
            created.append(label)

    click.echo(f"{'Would create' if dry_run else 'Created'} product '{name}' at {product_dir}")
    if created:
        click.echo(f"\n  Created {len(created)} files/folders:")
        for path in created:
            click.echo(f"    {path}")
    if skipped:
        click.echo(f"\n  Skipped {len(skipped)} existing files:")
        for path in skipped:
            click.echo(f"    {path}")

    _add_to_tach_toml(name, dry_run=dry_run)
    _add_to_frontend_package_json(name, dry_run=dry_run)
    _add_to_django_settings(name, dry_run=dry_run)
    _add_to_feature_flags(name, dry_run=dry_run)

    if dry_run:
        _add_to_db_routing(name, name, dry_run=True)
    else:
        click.echo(
            "\n  Products get their own database by default — this isolates locks, "
            "connections, and migrations so one product can't bring down the app. "
            "This is new but fully working. Reach out in #team-devex with questions."
        )
        click.secho(
            "  ⚠ Adding a route here is only the Django side. The database must also "
            "be provisioned by #team-infrastructure (Terraform + charts).",
            fg="yellow",
        )
        existing_dbs = _get_existing_databases()
        if existing_dbs:
            click.echo(f"  Existing databases: {', '.join(existing_dbs)}")
            click.echo("  You can share a database with another product from the same team.")

        if click.confirm("  Skip separate database?", default=False):
            click.echo("  Skipped. You can add it later in products/db_routing.yaml.")
        else:
            db_name = click.prompt(
                "  Database name",
                default=name,
                show_default=True,
            )
            _add_to_db_routing(name, db_name, dry_run=False)

    if not dry_run:
        click.echo("")
        click.secho("  📦 Installing dependencies", bold=True)
        import subprocess

        click.echo("  Running pnpm install...")
        result = subprocess.run(["pnpm", "install"], capture_output=True, text=True)
        if result.returncode == 0:
            click.secho("  ✓ pnpm install", fg="green")
        else:
            click.secho("  ✗ pnpm install failed — run it manually", fg="red")
            output = (result.stderr or result.stdout or "").strip()
            if output:
                click.echo(f"    {output.splitlines()[-1]}")

        click.echo("  Running pnpm build:products...")
        result = subprocess.run(
            ["pnpm", "--filter=@posthog/frontend", "build:products"], capture_output=True, text=True
        )
        if result.returncode == 0:
            click.secho("  ✓ build:products", fg="green")
        else:
            click.secho("  ✗ build:products failed — run it manually", fg="red")
            output = (result.stderr or result.stdout or "").strip()
            if output:
                click.echo(f"    {output.splitlines()[-1]}")

    flag_value = name.replace("_", "-")
    click.echo("")
    click.secho("  🚩 Feature flag", bold=True)
    click.echo(f"  Your product is gated behind '{flag_value}' (category: Unreleased, tags: alpha).")
    click.secho(
        "  Enable the flag in PostHog to see it in the nav!",
        fg="green",
    )
    click.echo("")
    click.secho("  📋 Next steps", bold=True)
    click.echo(f"  See TODO.md in products/{name}/ for the full setup checklist.")
