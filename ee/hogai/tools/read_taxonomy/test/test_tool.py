from posthog.test.base import NonAtomicBaseTest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.runnables import RunnableConfig

from ee.hogai.tools.read_taxonomy.core import (
    ReadEvents,
    ReadEventSamplePropertyValues,
    _is_excluded_ai_property,
    execute_taxonomy_query,
)
from ee.hogai.tools.read_taxonomy.tool import ReadTaxonomyTool
from ee.hogai.utils.types import AssistantState
from ee.hogai.utils.types.base import NodePath
from ee.models import Conversation


class TestReadTaxonomyTool(NonAtomicBaseTest):
    CLASS_DATA_LEVEL_SETUP = False

    def setUp(self):
        super().setUp()
        self.tool_call_id = "test_tool_call_id"
        self.conversation = Conversation.objects.create(user=self.user, team=self.team)

    @patch("ee.hogai.tools.read_taxonomy.tool.AssistantContextManager")
    async def test_tool_has_correct_name(self, mock_context_manager_class):
        mock_context_manager = MagicMock()
        mock_context_manager.get_group_names = AsyncMock(return_value=["organization", "project"])
        mock_context_manager_class.return_value = mock_context_manager

        config = RunnableConfig(configurable={"thread_id": str(self.conversation.id)})
        tool = await ReadTaxonomyTool.create_tool_class(
            team=self.team,
            user=self.user,
            state=AssistantState(messages=[]),
            config=config,
            node_path=(NodePath(name="test_node", tool_call_id=self.tool_call_id, message_id="test"),),
        )

        self.assertEqual(tool.name, "read_taxonomy")

    @patch("ee.hogai.tools.read_taxonomy.tool.AssistantContextManager")
    async def test_create_tool_class_includes_groups_in_schema(self, mock_context_manager_class):
        mock_context_manager = MagicMock()
        mock_context_manager.get_group_names = AsyncMock(return_value=["organization", "project"])
        mock_context_manager_class.return_value = mock_context_manager

        config = RunnableConfig(configurable={"thread_id": str(self.conversation.id)})
        tool = await ReadTaxonomyTool.create_tool_class(
            team=self.team,
            user=self.user,
            state=AssistantState(messages=[]),
            config=config,
            node_path=(NodePath(name="test_node", tool_call_id=self.tool_call_id, message_id="test"),),
        )

        assert tool.args_schema is not None and isinstance(tool.args_schema, type)
        schema = tool.args_schema.model_json_schema()
        entity_properties_schema = schema["$defs"]["ReadEntityProperties"]["properties"]["entity"]

        self.assertIn("organization", entity_properties_schema["enum"])
        self.assertIn("project", entity_properties_schema["enum"])
        self.assertIn("person", entity_properties_schema["enum"])
        self.assertIn("session", entity_properties_schema["enum"])

    @patch("ee.hogai.tools.read_taxonomy.core.TaxonomyAgentToolkit")
    @patch("ee.hogai.tools.read_taxonomy.core.format_events_yaml")
    def test_execute_taxonomy_query_read_events(self, mock_format_events, mock_toolkit_class):
        mock_format_events.return_value = "events:\n  - $pageview\n  - $autocapture"

        result = execute_taxonomy_query(ReadEvents(), mock_toolkit_class.return_value, self.team)

        self.assertIn("events:", result)
        mock_format_events.assert_called_once_with([], self.team, limit=500, offset=0)

    def test_is_excluded_ai_property_per_event_scoping(self):
        self.assertTrue(_is_excluded_ai_property("$ai_span", "$ai_input_state"))
        self.assertTrue(_is_excluded_ai_property("$ai_span", "$ai_output_state"))
        self.assertFalse(_is_excluded_ai_property("$ai_span", "$ai_input"))
        self.assertFalse(_is_excluded_ai_property("$ai_span", "$ai_output_choices"))

        self.assertTrue(_is_excluded_ai_property("$ai_generation", "$ai_input"))
        self.assertTrue(_is_excluded_ai_property("$ai_generation", "$ai_output_choices"))
        self.assertFalse(_is_excluded_ai_property("$ai_generation", "$ai_input_state"))
        self.assertFalse(_is_excluded_ai_property("$ai_generation", "$ai_output_state"))

        self.assertTrue(_is_excluded_ai_property("$ai_embedding", "$ai_input"))
        self.assertTrue(_is_excluded_ai_property("$ai_embedding", "$ai_output_choices"))
        self.assertFalse(_is_excluded_ai_property("$ai_embedding", "$ai_input_state"))

        self.assertFalse(_is_excluded_ai_property("$pageview", "$ai_input"))
        self.assertFalse(_is_excluded_ai_property("custom_event", "$ai_input_state"))

    @patch("ee.hogai.tools.read_taxonomy.core.TaxonomyAgentToolkit")
    def test_execute_taxonomy_query_returns_warning_for_excluded_ai_properties(self, mock_toolkit_class):
        query = ReadEventSamplePropertyValues(event_name="$ai_generation", property_name="$ai_input")
        result = execute_taxonomy_query(query, mock_toolkit_class.return_value, self.team)

        self.assertIn("too large", result)
        self.assertIn("$ai_input", result)
        mock_toolkit_class.return_value.retrieve_event_or_action_property_values.assert_not_called()

    @patch("ee.hogai.tools.read_taxonomy.core.TaxonomyAgentToolkit")
    def test_execute_taxonomy_query_delegates_for_non_excluded_properties(self, mock_toolkit_class):
        mock_toolkit_class.return_value.retrieve_event_or_action_property_values.return_value = "gpt-4, claude-3"

        query = ReadEventSamplePropertyValues(event_name="$ai_generation", property_name="$ai_model")
        result = execute_taxonomy_query(query, mock_toolkit_class.return_value, self.team)

        self.assertEqual(result, "gpt-4, claude-3")
        mock_toolkit_class.return_value.retrieve_event_or_action_property_values.assert_called_once_with(
            "$ai_generation", "$ai_model"
        )
