from freezegun import freeze_time
from posthog.test.base import BaseTest

from ee.hogai.context.org_intelligence.org_members_context import OrgMembersContext
from ee.models.rbac.role import Role, RoleMembership


@freeze_time("2025-06-15T12:00:00Z")
class TestOrgMembersContext(BaseTest):
    def _create_context(self) -> OrgMembersContext:
        return OrgMembersContext(team=self.team, user=self.user)

    async def test_fetch_and_format_lists_members(self):
        result = await self._create_context().fetch_and_format()

        assert self.user.email in result

    async def test_fetch_and_format_shows_membership_level(self):
        result = await self._create_context().fetch_and_format()

        assert "member" in result.lower()

    async def test_fetch_and_format_includes_roles(self):
        role = await Role.objects.acreate(
            name="Analysts",
            organization=self.organization,
            created_by=self.user,
        )
        await RoleMembership.objects.acreate(role=role, user=self.user)

        result = await self._create_context().fetch_and_format(include_roles=True)

        assert "analysts" in result.lower()

    async def test_fetch_and_format_excludes_roles_by_default(self):
        role = await Role.objects.acreate(
            name="Analysts",
            organization=self.organization,
            created_by=self.user,
        )
        await RoleMembership.objects.acreate(role=role, user=self.user)

        result = await self._create_context().fetch_and_format()

        assert "analysts" not in result.lower()

    async def test_fetch_and_format_shows_member_count(self):
        result = await self._create_context().fetch_and_format()

        assert "1 total" in result.lower()
