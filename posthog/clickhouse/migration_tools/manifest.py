"""Shared data types for ClickHouse migration steps."""

from __future__ import annotations

from dataclasses import dataclass

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
    "OPS": "ops",
    "AI_EVENTS": "ai_events",
    "AUX": "aux",
}

VALID_NODE_ROLES = frozenset(ROLE_MAP.keys())

# Engine tier determines creation order: Kafka(0) → MergeTree(1) → Distributed(2) → MV/Dict(3)
ENGINE_TIER: dict[str, int] = {
    "kafka": 0,
    "mergetree": 1,
    "replacingmergetree": 1,
    "replicatedmergetree": 1,
    "replicatedreplacingmergetree": 1,
    "collapsingmergetree": 1,
    "replicatedcollapsingmergetree": 1,
    "versionedcollapsingmergetree": 1,
    "replicatedversionedcollapsingmergetree": 1,
    "summingmergetree": 1,
    "replicatedsummingmergetree": 1,
    "aggregatingmergetree": 1,
    "replicatedaggregatingmergetree": 1,
    "distributed": 2,
    "materializedview": 3,
    "dictionary": 3,
}


def engine_tier(engine: str) -> int:
    return ENGINE_TIER.get(engine.lower(), 1)


def is_mergetree(engine: str) -> bool:
    return "mergetree" in engine.lower()


def is_distributed(engine: str) -> bool:
    return engine.lower() == "distributed"


def is_mv(engine: str) -> bool:
    return engine.lower() == "materializedview"


def is_kafka(engine: str) -> bool:
    return engine.lower() == "kafka"


@dataclass
class ManifestStep:
    sql: str
    node_roles: list[str]
    comment: str = ""
    sharded: bool = False
    is_alter_on_replicated_table: bool = False
    clusters: list[str] | None = None
    affected_table: str | None = None
