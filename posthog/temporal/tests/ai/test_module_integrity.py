from posthog.temporal import ai
from posthog.temporal.session_replay import session_summary


class TestAITemporalModuleIntegrity:
    def test_workflows_remain_unchanged(self):
        """Ensure all expected workflows are present in the module."""
        expected_workflows = [
            "SyncVectorsWorkflow",
            "AssistantConversationRunnerWorkflow",
            "ChatAgentWorkflow",
            "ResearchAgentWorkflow",
            "SummarizeLLMTracesWorkflow",
            "SlackConversationRunnerWorkflow",
            "PostHogCodeSlackMentionWorkflow",
            "PostHogCodeSlackTerminateTaskWorkflow",
        ]
        actual_workflow_names = [workflow.__name__ for workflow in ai.AI_WORKFLOWS]
        assert len(actual_workflow_names) == len(expected_workflows), (
            f"Workflow count mismatch. Expected {len(expected_workflows)}, got {len(actual_workflow_names)}. "
            "If you're adding/removing workflows, update this test accordingly."
        )
        for expected in expected_workflows:
            assert expected in actual_workflow_names, (
                f"Workflow '{expected}' is missing from ai.AI_WORKFLOWS. If this was intentional, update the test."
            )
        for actual in actual_workflow_names:
            assert actual in expected_workflows, (
                f"Unexpected workflow '{actual}' found in ai.AI_WORKFLOWS. If this was intentional, update the test."
            )

    def test_activities_remain_unchanged(self):
        """Ensure all expected activities are present in the module."""
        expected_activities = [
            "get_approximate_actions_count",
            "batch_summarize_actions",
            "batch_embed_and_sync_actions",
            "process_conversation_activity",
            "process_chat_agent_activity",
            "process_research_agent_activity",
            "summarize_llm_traces_activity",
            "process_slack_conversation_activity",
            "resolve_posthog_code_slack_user_activity",
            "handle_posthog_code_rules_command_activity",
            "collect_posthog_code_thread_messages_activity",
            "create_posthog_code_routing_rule_activity",
            "select_posthog_code_repository_activity",
            "classify_posthog_code_task_needs_repo_activity",
            "post_posthog_code_no_repos_activity",
            "post_posthog_code_repo_picker_activity",
            "create_posthog_code_task_for_repo_activity",
            "forward_posthog_code_followup_activity",
            "post_posthog_code_picker_timeout_activity",
            "post_posthog_code_internal_error_activity",
            "process_posthog_code_terminate_task_activity",
        ]
        actual_activity_names = [activity.__name__ for activity in ai.AI_ACTIVITIES]
        assert len(actual_activity_names) == len(expected_activities), (
            f"Activity count mismatch. Expected {len(expected_activities)}, got {len(actual_activity_names)}. "
            "If you're adding/removing activities, update this test accordingly."
        )
        for expected in expected_activities:
            assert expected in actual_activity_names, (
                f"Activity '{expected}' is missing from ai.AI_ACTIVITIES. If this was intentional, update the test."
            )
        for actual in actual_activity_names:
            assert actual in expected_activities, (
                f"Unexpected activity '{actual}' found in ai.AI_ACTIVITIES. If this was intentional, update the test."
            )

    def test_all_exports_remain_unchanged(self):
        """Ensure __all__ exports remain unchanged."""
        expected_exports = [
            "SyncVectorsInputs",
            "SummarizeLLMTracesInputs",
            "SlackConversationRunnerWorkflowInputs",
        ]
        actual_exports = ai.__all__
        assert len(actual_exports) == len(expected_exports), (
            f"Export count mismatch. Expected {len(expected_exports)}, got {len(actual_exports)}. "
            "If you're adding/removing exports, update this test accordingly."
        )
        for expected in expected_exports:
            assert expected in actual_exports, (
                f"Export '{expected}' is missing from __all__. If this was intentional, update the test."
            )
        for actual in actual_exports:
            assert actual in expected_exports, (
                f"Unexpected export '{actual}' found in __all__. If this was intentional, update the test."
            )


class TestSessionSummaryTemporalModuleIntegrity:
    def test_session_summary_workflows(self):
        """Ensure all expected session summary workflows are present."""
        expected_workflows = [
            "SummarizeSingleSessionStreamWorkflow",
            "SummarizeSingleSessionWorkflow",
            "SummarizeSessionGroupWorkflow",
        ]
        actual_workflow_names = [w.__name__ for w in session_summary.SESSION_SUMMARY_WORKFLOWS]
        assert len(actual_workflow_names) == len(expected_workflows), (
            f"Workflow count mismatch. Expected {len(expected_workflows)}, got {len(actual_workflow_names)}. "
            "If you're adding/removing workflows, update this test accordingly."
        )
        for expected in expected_workflows:
            assert expected in actual_workflow_names, (
                f"Workflow '{expected}' is missing from SESSION_SUMMARY_WORKFLOWS."
            )

    def test_session_summary_activities(self):
        """Ensure all expected session summary activities are present."""
        expected_activities = [
            "stream_llm_single_session_summary_activity",
            "get_llm_single_session_summary_activity",
            "fetch_session_batch_events_activity",
            "extract_session_group_patterns_activity",
            "assign_events_to_patterns_activity",
            "fetch_session_data_activity",
            "combine_patterns_from_chunks_activity",
            "split_session_summaries_into_chunks_for_patterns_extraction_activity",
            "validate_llm_single_session_summary_with_videos_activity",
            "prep_session_video_asset_activity",
            "upload_video_to_gemini_activity",
            "analyze_video_segment_activity",
            "embed_and_store_segments_activity",
            "store_video_session_summary_activity",
            "cleanup_gemini_file_activity",
            "consolidate_video_segments_activity",
            "capture_timing_activity",
        ]
        actual_activity_names = [a.__name__ for a in session_summary.SESSION_SUMMARY_ACTIVITIES]
        assert len(actual_activity_names) == len(expected_activities), (
            f"Activity count mismatch. Expected {len(expected_activities)}, got {len(actual_activity_names)}. "
            "If you're adding/removing activities, update this test accordingly."
        )
        for expected in expected_activities:
            assert expected in actual_activity_names, (
                f"Activity '{expected}' is missing from SESSION_SUMMARY_ACTIVITIES."
            )
