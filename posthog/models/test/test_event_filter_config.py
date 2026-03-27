from django.test import SimpleTestCase

from posthog.models.event_filter_config import evaluate_filter_tree, prune_filter_tree, tree_has_conditions


class TestEvaluateFilterTree(SimpleTestCase):
    def _event(self, event_name="$pageview", distinct_id="user-1"):
        return {"event_name": event_name, "distinct_id": distinct_id}

    def test_empty_and_returns_false(self):
        """Empty AND must NOT drop (conservative). all([]) is True in Python but we guard against it."""
        node = {"type": "and", "children": []}
        self.assertFalse(evaluate_filter_tree(node, self._event()))

    def test_empty_or_returns_false(self):
        node = {"type": "or", "children": []}
        self.assertFalse(evaluate_filter_tree(node, self._event()))

    def test_not_wrapping_empty_and_returns_true(self):
        node = {"type": "not", "child": {"type": "and", "children": []}}
        self.assertTrue(evaluate_filter_tree(node, self._event()))

    def test_not_wrapping_empty_or_returns_true(self):
        node = {"type": "not", "child": {"type": "or", "children": []}}
        self.assertTrue(evaluate_filter_tree(node, self._event()))

    def test_and_with_only_empty_children_returns_false(self):
        node = {"type": "and", "children": [{"type": "or", "children": []}, {"type": "or", "children": []}]}
        self.assertFalse(evaluate_filter_tree(node, self._event()))

    def test_exact_match(self):
        node = {"type": "condition", "field": "event_name", "operator": "exact", "value": "$pageview"}
        self.assertTrue(evaluate_filter_tree(node, self._event("$pageview")))
        self.assertFalse(evaluate_filter_tree(node, self._event("$click")))

    def test_contains_match(self):
        node = {"type": "condition", "field": "distinct_id", "operator": "contains", "value": "bot-"}
        self.assertTrue(evaluate_filter_tree(node, self._event(distinct_id="bot-crawler")))
        self.assertFalse(evaluate_filter_tree(node, self._event(distinct_id="real-user")))

    def test_missing_field_returns_false(self):
        node = {"type": "condition", "field": "distinct_id", "operator": "exact", "value": "test"}
        self.assertFalse(evaluate_filter_tree(node, {"event_name": "$pageview"}))

    def test_and_logic(self):
        node = {
            "type": "and",
            "children": [
                {"type": "condition", "field": "event_name", "operator": "exact", "value": "$internal"},
                {"type": "condition", "field": "distinct_id", "operator": "contains", "value": "bot-"},
            ],
        }
        self.assertTrue(evaluate_filter_tree(node, self._event("$internal", "bot-crawler")))
        self.assertFalse(evaluate_filter_tree(node, self._event("$internal", "real-user")))
        self.assertFalse(evaluate_filter_tree(node, self._event("$click", "bot-crawler")))

    def test_or_logic(self):
        node = {
            "type": "or",
            "children": [
                {"type": "condition", "field": "event_name", "operator": "exact", "value": "$drop_me"},
                {"type": "condition", "field": "event_name", "operator": "exact", "value": "$also_drop"},
            ],
        }
        self.assertTrue(evaluate_filter_tree(node, self._event("$drop_me")))
        self.assertTrue(evaluate_filter_tree(node, self._event("$also_drop")))
        self.assertFalse(evaluate_filter_tree(node, self._event("$keep_me")))

    def test_not_logic(self):
        node = {
            "type": "not",
            "child": {"type": "condition", "field": "event_name", "operator": "exact", "value": "$keep"},
        }
        self.assertFalse(evaluate_filter_tree(node, self._event("$keep")))
        self.assertTrue(evaluate_filter_tree(node, self._event("$other")))

    def test_complex_or_of_and_groups(self):
        node = {
            "type": "or",
            "children": [
                {"type": "condition", "field": "event_name", "operator": "exact", "value": "$drop_me"},
                {
                    "type": "and",
                    "children": [
                        {"type": "condition", "field": "event_name", "operator": "exact", "value": "$internal"},
                        {"type": "condition", "field": "distinct_id", "operator": "contains", "value": "bot-"},
                    ],
                },
            ],
        }
        self.assertTrue(evaluate_filter_tree(node, self._event("$drop_me", "anyone")))
        self.assertTrue(evaluate_filter_tree(node, self._event("$internal", "bot-crawler")))
        self.assertFalse(evaluate_filter_tree(node, self._event("$internal", "real-user")))
        self.assertFalse(evaluate_filter_tree(node, self._event("$pageview", "bot-crawler")))

    def test_not_wrapping_or_allowlist(self):
        node = {
            "type": "not",
            "child": {
                "type": "or",
                "children": [
                    {"type": "condition", "field": "event_name", "operator": "exact", "value": "allowed_1"},
                    {"type": "condition", "field": "event_name", "operator": "exact", "value": "allowed_2"},
                ],
            },
        }
        self.assertFalse(evaluate_filter_tree(node, self._event("allowed_1")))
        self.assertFalse(evaluate_filter_tree(node, self._event("allowed_2")))
        self.assertTrue(evaluate_filter_tree(node, self._event("other_event")))


class TestPruneFilterTree(SimpleTestCase):
    def test_prunes_empty_or(self):
        self.assertIsNone(prune_filter_tree({"type": "or", "children": []}))

    def test_prunes_empty_and(self):
        self.assertIsNone(prune_filter_tree({"type": "and", "children": []}))

    def test_collapses_single_child_group(self):
        node = {
            "type": "or",
            "children": [{"type": "condition", "field": "event_name", "operator": "exact", "value": "test"}],
        }
        result = prune_filter_tree(node)
        self.assertEqual(result["type"], "condition")
        self.assertEqual(result["value"], "test")

    def test_removes_empty_children_from_group(self):
        node = {
            "type": "or",
            "children": [
                {"type": "and", "children": []},
                {"type": "condition", "field": "event_name", "operator": "exact", "value": "test"},
                {"type": "or", "children": []},
            ],
        }
        result = prune_filter_tree(node)
        self.assertEqual(result["type"], "condition")
        self.assertEqual(result["value"], "test")

    def test_prunes_not_wrapping_empty(self):
        node = {"type": "not", "child": {"type": "or", "children": []}}
        self.assertIsNone(prune_filter_tree(node))

    def test_preserves_valid_tree(self):
        node = {
            "type": "or",
            "children": [
                {"type": "condition", "field": "event_name", "operator": "exact", "value": "a"},
                {"type": "condition", "field": "event_name", "operator": "exact", "value": "b"},
            ],
        }
        result = prune_filter_tree(node)
        self.assertEqual(result["type"], "or")
        self.assertEqual(len(result["children"]), 2)

    def test_deep_prune(self):
        node = {
            "type": "or",
            "children": [
                {
                    "type": "and",
                    "children": [
                        {"type": "or", "children": []},
                    ],
                },
                {"type": "condition", "field": "event_name", "operator": "exact", "value": "keep"},
            ],
        }
        result = prune_filter_tree(node)
        self.assertEqual(result["type"], "condition")
        self.assertEqual(result["value"], "keep")


class TestTreeHasConditions(SimpleTestCase):
    def test_empty_or(self):
        self.assertFalse(tree_has_conditions({"type": "or", "children": []}))

    def test_empty_and(self):
        self.assertFalse(tree_has_conditions({"type": "and", "children": []}))

    def test_condition(self):
        self.assertTrue(
            tree_has_conditions({"type": "condition", "field": "event_name", "operator": "exact", "value": "x"})
        )

    def test_nested_condition(self):
        node = {
            "type": "or",
            "children": [
                {
                    "type": "and",
                    "children": [{"type": "condition", "field": "event_name", "operator": "exact", "value": "x"}],
                }
            ],
        }
        self.assertTrue(tree_has_conditions(node))

    def test_nested_empty_groups(self):
        node = {"type": "or", "children": [{"type": "and", "children": [{"type": "or", "children": []}]}]}
        self.assertFalse(tree_has_conditions(node))

    def test_not_wrapping_condition(self):
        node = {"type": "not", "child": {"type": "condition", "field": "event_name", "operator": "exact", "value": "x"}}
        self.assertTrue(tree_has_conditions(node))

    def test_not_wrapping_empty(self):
        node = {"type": "not", "child": {"type": "or", "children": []}}
        self.assertFalse(tree_has_conditions(node))
