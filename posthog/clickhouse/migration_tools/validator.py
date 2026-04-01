"""Validate desired-state YAML schemas for ecosystem completeness and targeting."""

from __future__ import annotations

from posthog.clickhouse.migration_tools.desired_state import DesiredState
from posthog.clickhouse.migration_tools.schema_graph import lookup_ecosystem

# Expected node roles by engine type
_EXPECTED_ROLES: dict[str, set[str]] = {
    "distributed": {"COORDINATOR", "ALL"},
    "kafka": {"INGESTION_EVENTS", "INGESTION_SMALL", "INGESTION_MEDIUM", "ALL"},
    "materializedview": {"INGESTION_EVENTS", "INGESTION_SMALL", "INGESTION_MEDIUM", "ALL"},
}


def validate_desired_states(desired_states: list[DesiredState]) -> list[str]:
    """Validate a list of desired states. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    for state in desired_states:
        errors.extend(_check_ecosystem_completeness(state))
        errors.extend(_check_cross_cluster_targeting(state))

    return errors


def _check_ecosystem_completeness(state: DesiredState) -> list[str]:
    """Warn if a known ecosystem is partially declared (e.g. sharded without distributed)."""
    errors: list[str] = []

    for table_name in state.tables:
        eco = lookup_ecosystem(table_name)
        if eco is None:
            continue

        expected_tables = eco.all_tables()
        declared_tables = set(state.tables.keys())
        missing = expected_tables - declared_tables

        if missing:
            errors.append(
                f"[{state.ecosystem}] Table '{table_name}' belongs to ecosystem "
                f"'{eco.base_name}' but companion tables are missing: {sorted(missing)}"
            )
            break  # one warning per ecosystem is enough

    return errors


def _check_cross_cluster_targeting(state: DesiredState) -> list[str]:
    """Check that engine types target appropriate node roles."""
    errors: list[str] = []

    for table_name, table in state.tables.items():
        engine_lower = table.engine.lower()
        expected = None
        for engine_key, roles in _EXPECTED_ROLES.items():
            if engine_key in engine_lower:
                expected = roles
                break

        if expected is None:
            continue

        on_nodes_set = set(table.on_nodes)
        if not on_nodes_set & expected:
            errors.append(
                f"[{state.ecosystem}] Table '{table_name}' (engine={table.engine}) "
                f"targets {table.on_nodes} but expected one of {sorted(expected)}"
            )

    return errors
