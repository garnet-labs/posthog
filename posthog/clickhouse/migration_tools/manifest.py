from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROLE_MAP: dict[str, str] = {
    "DATA": "data",
    "COORDINATOR": "coordinator",
    "INGESTION_EVENTS": "events",
    "INGESTION_SMALL": "small",
    "INGESTION_MEDIUM": "medium",
    "SHUFFLEHOG": "shufflehog",
    "ENDPOINTS": "endpoints",
    "LOGS": "logs",
    "ALL": "all",
}

VALID_NODE_ROLES = frozenset(ROLE_MAP.keys())


@dataclass
class ManifestStep:
    sql: str  # "up.sql#section_name" or "up.sql"
    node_roles: list[str]  # ["DATA", "COORDINATOR"]
    comment: str = ""
    sharded: bool = False
    is_alter_on_replicated_table: bool = False
    clusters: list[str] | None = None
    affected_table: str | None = None  # table name for mutation checks


@dataclass
class MigrationManifest:
    description: str
    steps: list[ManifestStep]
    rollback: list[ManifestStep]
    clusters: list[str] | None = None
    ecosystem: str | None = None
    template: str | None = None
    template_config: dict[str, Any] | None = None


def _parse_step(raw: dict[str, Any]) -> ManifestStep:
    if "sql" not in raw:
        raise ValueError("Each step must have a 'sql' field")
    if "node_roles" not in raw:
        raise ValueError("Each step must have a 'node_roles' field")

    node_roles = raw["node_roles"]
    for role in node_roles:
        if role not in VALID_NODE_ROLES:
            raise ValueError(f"Invalid node_role '{role}'. Must be one of: {sorted(VALID_NODE_ROLES)}")

    return ManifestStep(
        sql=raw["sql"],
        node_roles=node_roles,
        comment=raw.get("comment", ""),
        sharded=raw.get("sharded", False),
        is_alter_on_replicated_table=raw.get("is_alter_on_replicated_table", False),
        clusters=raw.get("clusters", None),
        affected_table=raw.get("affected_table", None),
    )


def parse_manifest(manifest_path: Path) -> MigrationManifest:
    with open(manifest_path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Manifest must be a YAML mapping, got {type(data).__name__}")

    if "description" not in data:
        raise ValueError("Manifest must have a 'description' field")

    clusters = data.get("clusters") or ([data["cluster"]] if "cluster" in data else None)

    # Template-based manifest: template + config instead of steps
    if "template" in data:
        if "config" not in data:
            raise ValueError("Template-based manifest must have a 'config' field")
        return MigrationManifest(
            description=data["description"],
            steps=[],
            rollback=[],
            clusters=clusters,
            ecosystem=data.get("ecosystem", None),
            template=data["template"],
            template_config=data["config"],
        )

    # Step-based manifest (original format)
    if "steps" not in data:
        raise ValueError("Manifest must have a 'steps' or 'template' field")

    raw_steps = data["steps"]
    if not isinstance(raw_steps, list):
        raise ValueError(f"Manifest 'steps' must be a list, got {type(raw_steps).__name__}")
    raw_rollback = data.get("rollback", [])
    if not isinstance(raw_rollback, list):
        raise ValueError(f"Manifest 'rollback' must be a list, got {type(raw_rollback).__name__}")

    steps = [_parse_step(s) for s in raw_steps]
    rollback = [_parse_step(s) for s in raw_rollback]

    return MigrationManifest(
        description=data["description"],
        steps=steps,
        rollback=rollback,
        clusters=clusters,
        ecosystem=data.get("ecosystem", None),
    )
