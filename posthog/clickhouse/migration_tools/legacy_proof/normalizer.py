"""Normalize migration representations for comparison.

Produces comparison-friendly representations of both legacy and generated
migrations by normalizing SQL formatting, role targeting, and step ordering
without changing semantic intent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class NormalizedStep:
    """A normalized migration step for comparison."""

    index: int
    sql: str
    node_roles: frozenset[str]
    sharded: bool
    is_alter_on_replicated_table: bool


@dataclass
class NormalizedMigration:
    """A normalized migration for comparison."""

    migration_number: int
    migration_name: str
    steps: list[NormalizedStep] = field(default_factory=list)
    source: str = ""  # "legacy" or "generated"


def normalize_sql(sql: str) -> str:
    """Normalize SQL for comparison purposes.

    Normalizes only non-semantic differences:
    - Whitespace compression
    - Consistent newlines
    - Comment removal
    - Trailing semicolons
    - Case normalization for SQL keywords

    Does NOT normalize:
    - Statement order
    - Table names
    - Engine types
    - Column types
    """
    # Remove SQL comments (-- and /* */)
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)

    # Collapse whitespace
    sql = re.sub(r"\s+", " ", sql).strip()

    # Remove trailing semicolons
    sql = sql.rstrip(";").strip()

    # Protect Jinja2 template variables from keyword normalization
    import uuid as _uuid

    _templates: dict[str, str] = {}

    def _protect_template(m):
        key = f"__TMPL_{_uuid.uuid4().hex[:8]}__"
        _templates[key] = m.group(0)
        return key

    sql = re.sub(r"\{\{.*?\}\}", _protect_template, sql)

    # Normalize SQL keywords to uppercase
    keywords = [
        "SELECT",
        "FROM",
        "WHERE",
        "AND",
        "OR",
        "NOT",
        "IN",
        "IS",
        "CREATE",
        "TABLE",
        "IF",
        "EXISTS",
        "DROP",
        "ALTER",
        "ADD",
        "COLUMN",
        "ENGINE",
        "ORDER",
        "BY",
        "PARTITION",
        "SETTINGS",
        "INSERT",
        "INTO",
        "VALUES",
        "UPDATE",
        "DELETE",
        "SET",
        "DATABASE",
        "ON",
        "CLUSTER",
        "AS",
        "MATERIALIZED",
        "VIEW",
        "TO",
        "DISTRIBUTED",
        "NULL",
        "DEFAULT",
        "COMMENT",
        "TTL",
        "SYNC",
        "ATTACH",
        "DETACH",
        "RENAME",
        "MODIFY",
        "REPLACE",
    ]
    for kw in keywords:
        sql = re.sub(rf"\b{kw}\b", kw, sql, flags=re.IGNORECASE)

    # Restore templates
    for key, val in _templates.items():
        sql = sql.replace(key, val)

    return sql


def normalize_node_roles(roles: list[str]) -> frozenset[str]:
    """Normalize node role lists to a comparable frozenset.

    Converts all role representations to uppercase canonical form.
    """
    canonical: set[str] = set()
    for role in roles:
        val = role.upper().strip()
        # Map NodeRole enum values to canonical names
        role_map = {
            "DATA": "DATA",
            "COORDINATOR": "COORDINATOR",
            "EVENTS": "INGESTION_EVENTS",
            "SMALL": "INGESTION_SMALL",
            "MEDIUM": "INGESTION_MEDIUM",
            "SHUFFLEHOG": "SHUFFLEHOG",
            "ENDPOINTS": "ENDPOINTS",
            "LOGS": "LOGS",
            "ALL": "ALL",
            # Also accept the manifest form directly
            "INGESTION_EVENTS": "INGESTION_EVENTS",
            "INGESTION_SMALL": "INGESTION_SMALL",
            "INGESTION_MEDIUM": "INGESTION_MEDIUM",
        }
        canonical.add(role_map.get(val, val))
    return frozenset(canonical)
