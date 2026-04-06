from freezegun import freeze_time
from posthog.test.base import BaseTest
from unittest.mock import patch

from posthog.constants import AvailableFeature

from ee.hogai.context.org_intelligence.access_control_context import AccessControlContext
from ee.hogai.context.org_intelligence.prompts import ACCESS_CONTROL_NO_CUSTOM
from ee.models.rbac.access_control import AccessControl
from ee.models.rbac.role import Role, RoleMembership


class AccessControlContextTestBase(BaseTest):
    def _mock_features(self, access_control: bool = True, rbac: bool = True):
        def side_effect(feature, **kwargs):
            if feature == AvailableFeature.ACCESS_CONTROL:
                return access_control
            if feature == AvailableFeature.ROLE_BASED_ACCESS:
                return rbac
            return False

        return patch.object(
            type(self.organization),
            "is_feature_available",
            side_effect=side_effect,
        )


@freeze_time("2025-06-15T12:00:00Z")
class TestAccessControlContext(AccessControlContextTestBase):
    def _create_context(self) -> AccessControlContext:
        return AccessControlContext(team=self.team, user=self.user)

    async def test_fetch_and_format_no_custom_controls(self):
        with self._mock_features():
            result = await self._create_context().fetch_and_format()

        assert result == ACCESS_CONTROL_NO_CUSTOM

    async def test_fetch_and_format_shows_defaults(self):
        await AccessControl.objects.acreate(
            team=self.team,
            resource="dashboard",
            access_level="viewer",
        )

        with self._mock_features():
            result = await self._create_context().fetch_and_format()

        assert "dashboard" in result.lower()
        assert "viewer" in result.lower()

    async def test_fetch_and_format_shows_restricted_resources(self):
        await AccessControl.objects.acreate(
            team=self.team,
            resource="dashboard",
            resource_id="42",
            access_level="viewer",
        )

        with self._mock_features():
            result = await self._create_context().fetch_and_format()

        assert "42" in result
        assert "viewer" in result.lower()

    async def test_fetch_and_format_includes_roles(self):
        role = await Role.objects.acreate(
            name="Release Managers",
            organization=self.organization,
            created_by=self.user,
        )
        await RoleMembership.objects.acreate(role=role, user=self.user)

        with self._mock_features():
            result = await self._create_context().fetch_and_format(include_roles=True)

        assert "release managers" in result.lower()

    async def test_fetch_and_format_respects_team_scope(self):
        await AccessControl.objects.acreate(
            team=self.team,
            resource="dashboard",
            access_level="viewer",
        )
        other_team = await self.organization.teams.acreate(name="Other")
        await AccessControl.objects.acreate(
            team=other_team,
            resource="insight",
            access_level="none",
        )

        with self._mock_features():
            result = await self._create_context().fetch_and_format()

        assert "dashboard" in result.lower()
        assert "insight: none" not in result.lower()

    async def test_fetch_and_format_returns_empty_when_feature_unavailable(self):
        await AccessControl.objects.acreate(
            team=self.team,
            resource="dashboard",
            access_level="viewer",
        )

        with self._mock_features(access_control=False):
            result = await self._create_context().fetch_and_format()

        assert result == ACCESS_CONTROL_NO_CUSTOM

    async def test_fetch_and_format_skips_roles_when_rbac_unavailable(self):
        role = await Role.objects.acreate(
            name="Release Managers",
            organization=self.organization,
            created_by=self.user,
        )
        await RoleMembership.objects.acreate(role=role, user=self.user)
        await AccessControl.objects.acreate(
            team=self.team,
            resource="dashboard",
            access_level="viewer",
        )

        with self._mock_features(rbac=False):
            result = await self._create_context().fetch_and_format(include_roles=True)

        assert "release managers" not in result.lower()
        assert "dashboard" in result.lower()

    async def test_fetch_and_format_filters_by_resource(self):
        await AccessControl.objects.acreate(
            team=self.team,
            resource="dashboard",
            access_level="viewer",
        )
        await AccessControl.objects.acreate(
            team=self.team,
            resource="insight",
            access_level="editor",
        )

        with self._mock_features():
            result = await self._create_context().fetch_and_format(resource="dashboard")

        assert "dashboard" in result.lower()
        assert "insight" not in result.lower()
