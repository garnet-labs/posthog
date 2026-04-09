from unittest.mock import patch

from django.test import TestCase

from posthog.models import Organization, Team, User

from products.tasks.backend.automation_service import run_task_automation
from products.tasks.backend.models import Task, TaskAutomation, TaskRun


class TestAutomationService(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Test Org")
        self.team = Team.objects.create(organization=self.organization, name="Test Team")
        self.user = User.objects.create_user(email="test@example.com", first_name="Test", password="password")

    def create_automation(self) -> TaskAutomation:
        return TaskAutomation.objects.create(
            team=self.team,
            created_by=self.user,
            name="Daily PRs",
            prompt="Check my GitHub PRs",
            repository="posthog/posthog",
            cron_expression="0 9 * * *",
            timezone="Europe/London",
            enabled=True,
        )

    @patch("products.tasks.backend.automation_service.execute_task_processing_workflow_for_automation")
    def test_run_task_automation_is_idempotent_per_trigger_workflow(self, mock_execute_workflow):
        automation = self.create_automation()

        with self.captureOnCommitCallbacks(execute=True):
            first_task, first_run = run_task_automation(
                str(automation.id), trigger_workflow_id="automation-workflow-123"
            )
        with self.captureOnCommitCallbacks(execute=True):
            second_task, second_run = run_task_automation(
                str(automation.id), trigger_workflow_id="automation-workflow-123"
            )

        self.assertEqual(first_task.id, second_task.id)
        self.assertEqual(first_run.id, second_run.id)
        self.assertEqual(Task.objects.filter(origin_product=Task.OriginProduct.AUTOMATION).count(), 1)
        self.assertEqual(TaskRun.objects.filter(task__origin_product=Task.OriginProduct.AUTOMATION).count(), 1)
        self.assertEqual(first_run.state["automation_id"], str(automation.id))
        self.assertEqual(first_run.state["automation_trigger_workflow_id"], "automation-workflow-123")
        self.assertEqual(mock_execute_workflow.call_count, 2)

    @patch("products.tasks.backend.automation_service.execute_task_processing_workflow_for_automation")
    def test_run_task_automation_reuses_task_and_creates_new_runs(self, mock_execute_workflow):
        automation = self.create_automation()

        with self.captureOnCommitCallbacks(execute=True):
            first_task, first_run = run_task_automation(str(automation.id))
        with self.captureOnCommitCallbacks(execute=True):
            second_task, second_run = run_task_automation(str(automation.id))

        automation.refresh_from_db()
        self.assertEqual(first_task.id, second_task.id)
        self.assertEqual(automation.task_id, first_task.id)
        self.assertNotEqual(first_run.id, second_run.id)
        self.assertEqual(Task.objects.filter(origin_product=Task.OriginProduct.AUTOMATION).count(), 1)
        self.assertEqual(TaskRun.objects.filter(task=first_task).count(), 2)
        self.assertEqual(mock_execute_workflow.call_count, 2)
