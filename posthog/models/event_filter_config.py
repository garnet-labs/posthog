from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from posthog.models.utils import UUIDTModel

ALLOWED_FIELDS = {"event_name", "distinct_id"}
ALLOWED_OPERATORS = {"exact", "contains"}
NODE_TYPES = {"and", "or", "not", "condition"}
EXPECTED_RESULTS = {"drop", "ingest"}
MAX_TREE_DEPTH = 5

DEFAULT_FILTER_TREE = {"type": "or", "children": []}


class EventFilterConfig(UUIDTModel):
    """
    Per-team event filter configuration evaluated at ingestion time.
    One filter per team. Uses a boolean expression tree with AND, OR, NOT
    and condition nodes. If the tree evaluates to true, the event is dropped.
    """

    team = models.OneToOneField("posthog.Team", on_delete=models.CASCADE, related_name="event_filter")
    enabled = models.BooleanField(default=False)
    filter_tree = models.JSONField(
        default=None,
        null=True,
        blank=True,
        help_text=(
            "Boolean expression tree. Nodes: "
            '{"type": "and"|"or", "children": [...]}, '
            '{"type": "not", "child": {...}}, '
            '{"type": "condition", "field": "event_name"|"distinct_id"|"session_id", '
            '"operator": "exact"|"contains", "value": "<string>"}'
        ),
    )
    test_cases = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Test events to validate the filter. Each: "
            '{"event_name": "...", "distinct_id": "...", "session_id": "...", '
            '"expected_result": "drop"|"ingest"}'
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return f"EventFilterConfig(team={self.team_id}, enabled={self.enabled})"

    def clean(self) -> None:
        if self.filter_tree:
            validate_filter_tree(self.filter_tree)
        if self.test_cases:
            validate_test_cases(self.test_cases)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


def validate_filter_tree(node: object, depth: int = 0, path: str = "root") -> None:
    if depth > MAX_TREE_DEPTH:
        raise ValidationError({"filter_tree": f"Tree exceeds maximum depth of {MAX_TREE_DEPTH} at {path}."})

    if not isinstance(node, dict):
        raise ValidationError({"filter_tree": f"Node at {path} must be an object."})

    node_type = node.get("type")
    if node_type not in NODE_TYPES:
        raise ValidationError(
            {"filter_tree": f"Node at {path}: type must be one of {sorted(NODE_TYPES)}, got '{node_type}'."}
        )

    if node_type == "condition":
        _validate_condition(node, path)
    elif node_type == "not":
        if "child" not in node:
            raise ValidationError({"filter_tree": f"Node at {path}: 'not' node must have a 'child'."})
        validate_filter_tree(node["child"], depth + 1, f"{path}.child")
    elif node_type in ("and", "or"):
        children = node.get("children")
        if not isinstance(children, list):
            raise ValidationError({"filter_tree": f"Node at {path}: '{node_type}' node must have a 'children' list."})
        for i, child in enumerate(children):
            validate_filter_tree(child, depth + 1, f"{path}.children[{i}]")


def _validate_condition(node: dict, path: str) -> None:
    for key in ("field", "operator", "value"):
        if key not in node:
            raise ValidationError({"filter_tree": f"Condition at {path} missing required key '{key}'."})

    if node["field"] not in ALLOWED_FIELDS:
        raise ValidationError(
            {
                "filter_tree": f"Condition at {path}: field must be one of {sorted(ALLOWED_FIELDS)}, got '{node['field']}'."
            }
        )

    if node["operator"] not in ALLOWED_OPERATORS:
        raise ValidationError(
            {
                "filter_tree": f"Condition at {path}: operator must be one of {sorted(ALLOWED_OPERATORS)}, got '{node['operator']}'."
            }
        )

    if not isinstance(node["value"], str) or len(node["value"]) == 0:
        raise ValidationError({"filter_tree": f"Condition at {path}: value must be a non-empty string."})


def validate_test_cases(test_cases: object) -> None:
    if not isinstance(test_cases, list):
        raise ValidationError({"test_cases": "Must be a list."})

    for i, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            raise ValidationError({"test_cases": f"Test case {i} must be an object."})

        if "expected_result" not in tc:
            raise ValidationError({"test_cases": f"Test case {i} missing 'expected_result'."})

        if tc["expected_result"] not in EXPECTED_RESULTS:
            raise ValidationError({"test_cases": f"Test case {i}: expected_result must be 'drop' or 'ingest'."})

        for field in ("event_name", "distinct_id"):
            if field in tc and not isinstance(tc[field], str):
                raise ValidationError({"test_cases": f"Test case {i}: {field} must be a string."})


def evaluate_filter_tree(node: dict, event: dict) -> bool:
    """Evaluate a filter tree against an event dict. Returns True if the event should be dropped."""
    node_type = node.get("type")

    if node_type == "condition":
        field_value = event.get(node["field"])
        if field_value is None:
            return False
        operator = node["operator"]
        target = node["value"]
        if operator == "exact":
            return field_value == target
        elif operator == "contains":
            return target in field_value
        return False

    elif node_type == "and":
        return all(evaluate_filter_tree(child, event) for child in node["children"])

    elif node_type == "or":
        return any(evaluate_filter_tree(child, event) for child in node["children"])

    elif node_type == "not":
        return not evaluate_filter_tree(node["child"], event)

    return False
