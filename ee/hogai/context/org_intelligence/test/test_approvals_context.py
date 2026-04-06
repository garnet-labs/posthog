from datetime import timedelta

from freezegun import freeze_time
from posthog.test.base import BaseTest
from unittest.mock import patch

from django.utils import timezone

from posthog.approvals.models import Approval, ApprovalPolicy, ChangeRequest
from posthog.constants import AvailableFeature

from ee.hogai.context.org_intelligence.approvals_context import ApprovalsContext
from ee.hogai.context.org_intelligence.prompts import APPROVALS_NO_RESULTS


class ApprovalsContextTestBase(BaseTest):
    def _mock_feature(self):
        return patch.object(
            type(self.organization),
            "is_feature_available",
            side_effect=lambda feature, **kwargs: feature == AvailableFeature.APPROVALS,
        )

    async def _create_policy(self, **kwargs):
        defaults = {
            "organization": self.organization,
            "team": self.team,
            "action_key": "feature_flag:update",
            "approver_config": {"users": []},
            "enabled": True,
        }
        defaults.update(kwargs)
        return await ApprovalPolicy.objects.acreate(**defaults)

    async def _create_change_request(self, **kwargs):
        action_key = kwargs.get("action_key", "feature_flag:update")
        await self._create_policy(action_key=action_key)
        defaults = {
            "team": self.team,
            "organization": self.organization,
            "action_key": action_key,
            "action_version": 1,
            "resource_type": "FeatureFlag",
            "intent": {"key": "new-checkout", "rollout_percentage": 50},
            "intent_display": {"summary": "Roll out new-checkout to 50%"},
            "policy_snapshot": {},
            "state": "pending",
            "expires_at": timezone.now() + timedelta(days=14),
            "created_by": self.user,
        }
        defaults.update(kwargs)
        return await ChangeRequest.objects.acreate(**defaults)


@freeze_time("2025-06-15T12:00:00Z")
class TestApprovalsContext(ApprovalsContextTestBase):
    def _create_context(self) -> ApprovalsContext:
        return ApprovalsContext(team=self.team, user=self.user)

    async def test_fetch_and_format_returns_pending_by_default(self):
        await self._create_change_request(state="pending")
        await self._create_change_request(state="approved", action_key="feature_flag:update:2")

        with self._mock_feature():
            result = await self._create_context().fetch_and_format()

        assert "pending" in result.lower()
        assert result.count("- **") == 1

    async def test_fetch_and_format_filters_by_state(self):
        await self._create_change_request(state="pending")
        await self._create_change_request(state="approved", action_key="feature_flag:update:2")

        with self._mock_feature():
            result = await self._create_context().fetch_and_format(state="approved")

        assert "approved" in result.lower()

    async def test_fetch_and_format_state_all(self):
        await self._create_change_request(state="pending")
        await self._create_change_request(state="approved", action_key="feature_flag:update:2")

        with self._mock_feature():
            result = await self._create_context().fetch_and_format(state="all")

        assert result.count("- **") == 2

    async def test_fetch_and_format_empty(self):
        with self._mock_feature():
            result = await self._create_context().fetch_and_format()

        assert result == APPROVALS_NO_RESULTS

    async def test_fetch_and_format_includes_vote_status(self):
        cr = await self._create_change_request(state="pending")
        await Approval.objects.acreate(
            change_request=cr,
            decision="approved",
            reason="Looks good",
            created_by=self.user,
        )

        with self._mock_feature():
            result = await self._create_context().fetch_and_format()

        assert "1 approved" in result.lower()

    async def test_fetch_and_format_shows_staleness(self):
        cr = await self._create_change_request(state="pending")
        await ChangeRequest.objects.filter(id=cr.id).aupdate(
            created_at=timezone.now() - timedelta(hours=50),
        )

        with self._mock_feature():
            result = await self._create_context().fetch_and_format()

        assert "stale" in result.lower()

    async def test_fetch_and_format_no_staleness_for_recent(self):
        await self._create_change_request(state="pending")

        with self._mock_feature():
            result = await self._create_context().fetch_and_format()

        assert "stale" not in result.lower()

    async def test_fetch_and_format_respects_team_scope(self):
        await self._create_change_request(state="pending")

        other_team = await self.organization.teams.acreate(name="Other team")
        await ChangeRequest.objects.acreate(
            team=other_team,
            organization=self.organization,
            action_key="feature_flag:update",
            action_version=1,
            resource_type="FeatureFlag",
            intent={},
            intent_display={"summary": "Other team request"},
            policy_snapshot={},
            state="pending",
            expires_at=timezone.now() + timedelta(days=14),
            created_by=self.user,
        )

        with self._mock_feature():
            result = await self._create_context().fetch_and_format()

        assert "other team request" not in result.lower()

    async def test_fetch_and_format_pagination(self):
        for i in range(5):
            await self._create_change_request(
                state="pending",
                action_key=f"feature_flag:update:{i}",
            )

        with self._mock_feature():
            result = await self._create_context().fetch_and_format(limit=2)

        assert "more results" in result.lower()
        assert "offset=2" in result.lower()

    async def test_fetch_and_format_shows_intent_summary(self):
        await self._create_change_request(
            state="pending",
            intent_display={"summary": "Roll out new-checkout to 50%"},
        )

        with self._mock_feature():
            result = await self._create_context().fetch_and_format()

        assert "roll out new-checkout to 50%" in result.lower()

    async def test_fetch_and_format_returns_empty_when_feature_unavailable(self):
        await self._create_change_request(state="pending")

        with patch.object(
            type(self.organization),
            "is_feature_available",
            return_value=False,
        ):
            result = await self._create_context().fetch_and_format()

        assert result == APPROVALS_NO_RESULTS
