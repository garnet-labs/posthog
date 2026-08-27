#!/usr/bin/env python3
"""Isolated Django-ORM replay for PostHog PR 71294's dual selection paths.

This intentionally does not import PostHog. It uses Django 5.2 QuerySets with the
same filters, `.first()` shape, metadata iteration/overwrite rule, and prefetch
query as the source at the requested revisions. Representative final SQL is a
model of PropertySwapper's documented String/Float choice, not real HogQL output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from django.conf import settings


if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="local-replay-only",
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        INSTALLED_APPS=[],
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
    )

import django

django.setup()

from django.db import connection, models
from django.db.models.functions import Coalesce
from django.test.utils import CaptureQueriesContext


EVENT = 1
TYPED_TYPES = {"Numeric", "Boolean", "DateTime"}
REPO = Path(__file__).resolve().parents[3]
REVISIONS = {
    "base": "507f13ecc15a2e4ed314ba73612b302da6f2d3b8",
    "head": "88eb5feb56242ff2eb7f6a3d907bb38f62966e93",
}


class PropertyDefinition(models.Model):
    id = models.UUIDField(primary_key=True)
    team_id = models.BigIntegerField()
    project_id = models.BigIntegerField(null=True)
    name = models.CharField(max_length=400)
    type = models.PositiveSmallIntegerField(null=True)
    property_type = models.CharField(max_length=50, null=True)

    class Meta:
        app_label = "replay"
        db_table = "posthog_propertydefinition"


class MaterializedColumnSlot(models.Model):
    property_definition = models.ForeignKey(
        PropertyDefinition, related_name="materialized_column_slots", on_delete=models.CASCADE
    )
    team_id = models.BigIntegerField()
    state = models.CharField(max_length=20)

    class Meta:
        app_label = "replay"
        db_table = "posthog_materializedcolumnslot"


@dataclass
class ReplayResult:
    revision_label: str
    revision: str
    insertion_order: str
    inserted_rows: list[dict[str, Any]]
    coercion_selected: dict[str, Any] | None
    metadata_visit_order: list[dict[str, Any]]
    swapper_selected: dict[str, Any]
    rhs_kind: str
    lhs_kind: str
    modeled_final_sql: str
    compatible: bool
    observed_query_count: int
    observed_queries: list[str]


def git_show(revision: str, path: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO), "show", f"{revision}:{path}"], text=True)


def validate_source(revision_label: str, revision: str) -> dict[str, Any]:
    property_source = git_show(revision, "posthog/hogql/property.py")
    metadata_source = git_show(revision, "posthog/hogql/property_metadata.py")
    swapper_source = git_show(revision, "posthog/hogql/transforms/property_types.py")
    model_source = git_show(revision, "products/event_definitions/backend/models/property_definition.py")

    has_coercion = "def _coerce_numeric_value_for_string_property" in property_source
    expected = revision_label == "head"
    assert has_coercion is expected, (revision_label, has_coercion)
    if expected:
        for marker in (
            'type_filters = {"type__in": [None, PropertyDefinition.Type.EVENT]}',
            '.values_list("property_type", flat=True)',
            ".first()",
        ):
            assert marker in property_source, marker

    for marker in (
        "type__in=[None, PropertyDefinition.Type.EVENT]",
        "for prop_def in event_property_definitions:",
        "event_properties[prop_def.name] = prop_info",
    ):
        assert marker in metadata_source, marker
    assert 'field_type = "Float" if prop_info.get("type") == "Numeric"' in swapper_source
    assert "class UUIDTModel" in git_show(revision, "posthog/models/utils.py")
    assert "UUID (mostly) sortable by generation time." in git_show(revision, "posthog/uuidt.py")
    assert "UniqueConstraintByExpression(" in model_source

    return {
        "has_numeric_coercion_helper": has_coercion,
        "metadata_last_write_wins": True,
        "swapper_numeric_maps_to_float": True,
        "property_definition_pk": "UUIDT (mostly generation-time sortable)",
    }


def row_dict(row: PropertyDefinition) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "type": row.type,
        "type_label": "legacy_NULL" if row.type is None else "EVENT",
        "property_type": row.property_type,
    }


def reset_tables() -> None:
    MaterializedColumnSlot.objects.all().delete()
    PropertyDefinition.objects.all().delete()


def insert_fixture(order: str) -> list[PropertyDefinition]:
    # Ordered UUIDs mimic UUIDT's normal generation ordering while remaining deterministic.
    ids = [
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
        uuid.UUID("00000000-0000-0000-0000-000000000002"),
    ]
    specs = {
        "legacy": {"type": None, "property_type": "String"},
        "event": {"type": EVENT, "property_type": "Numeric"},
    }
    labels = ["legacy", "event"] if order == "legacy_then_event" else ["event", "legacy"]
    rows = []
    for pk, label in zip(ids, labels):
        rows.append(
            PropertyDefinition.objects.create(
                id=pk,
                team_id=1,
                project_id=1,
                name="conflict",
                **specs[label],
            )
        )
    return rows


def candidates():
    return PropertyDefinition.objects.alias(
        effective_project_id=Coalesce("project_id", "team_id", output_field=models.BigIntegerField())
    ).filter(effective_project_id=1, name="conflict", type__in=[None, EVENT])


def run_case(revision_label: str, revision: str, order: str) -> ReplayResult:
    reset_tables()
    inserted = insert_fixture(order)

    with CaptureQueriesContext(connection) as captured:
        coercion_selected = None
        if revision_label == "head":
            selected_type = (
                candidates()
                .exclude(property_type__isnull=True)
                .exclude(property_type="")
                .values_list("property_type", flat=True)
                .first()
            )
            selected_row = candidates().filter(property_type=selected_type).order_by("id").first()
            assert selected_row is not None
            coercion_selected = row_dict(selected_row)
            rhs_kind = "number" if selected_type in TYPED_TYPES else "string"
        else:
            rhs_kind = "number"

        event_property_definitions = candidates().prefetch_related(
            models.Prefetch(
                "materialized_column_slots",
                queryset=MaterializedColumnSlot.objects.filter(team_id=1, state="READY"),
            )
        )
        visited = []
        swapper_row = None
        for prop_def in event_property_definitions:
            visited.append(row_dict(prop_def))
            if not prop_def.property_type:
                continue
            # Mirrors event_properties[prop_def.name] = prop_info.
            swapper_row = prop_def
            prop_def.materialized_column_slots.first()

    assert swapper_row is not None
    lhs_kind = "number" if swapper_row.property_type == "Numeric" else "string"
    compatible = lhs_kind == rhs_kind
    lhs = (
        "toFloat(JSONExtractRaw(events.properties, 'conflict'))"
        if lhs_kind == "number"
        else "JSONExtractRaw(events.properties, 'conflict')"
    )
    rhs = "5" if rhs_kind == "number" else "'5'"

    return ReplayResult(
        revision_label=revision_label,
        revision=revision,
        insertion_order=order,
        inserted_rows=[row_dict(row) for row in inserted],
        coercion_selected=coercion_selected,
        metadata_visit_order=visited,
        swapper_selected=row_dict(swapper_row),
        rhs_kind=rhs_kind,
        lhs_kind=lhs_kind,
        modeled_final_sql=f"equals({lhs}, {rhs})",
        compatible=compatible,
        observed_query_count=len(captured),
        observed_queries=[query["sql"] for query in captured.captured_queries],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", choices=["base", "head", "both"], default="both")
    args = parser.parse_args()

    with connection.schema_editor() as editor:
        editor.create_model(PropertyDefinition)
        editor.create_model(MaterializedColumnSlot)

    labels = ["base", "head"] if args.revision == "both" else [args.revision]
    source_validation = {label: validate_source(label, REVISIONS[label]) for label in labels}
    results = [
        run_case(label, REVISIONS[label], order)
        for label in labels
        for order in ("legacy_then_event", "event_then_legacy")
    ]

    payload = {
        "probe": "isolated Django 5.2 ORM replay; modeled final SQL, not the full PostHog printer",
        "django_version": django.get_version(),
        "database": "SQLite in-memory (deterministic local harness, not PostgreSQL)",
        "source_validation": source_validation,
        "results": [asdict(result) for result in results],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
