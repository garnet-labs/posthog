from freezegun import freeze_time
from posthog.test.base import BaseTest

from posthog.models.comment.comment import Comment

from ee.hogai.context.org_intelligence.discussions_context import DiscussionsContext
from ee.hogai.context.org_intelligence.prompts import DISCUSSIONS_NO_RESULTS


class DiscussionsContextTestBase(BaseTest):
    async def _create_comment(self, **kwargs):
        defaults = {
            "team": self.team,
            "content": "Test comment",
            "scope": "Dashboard",
            "item_id": "1",
            "created_by": self.user,
        }
        defaults.update(kwargs)
        return await Comment.objects.acreate(**defaults)


@freeze_time("2025-06-15T12:00:00Z")
class TestDiscussionsContext(DiscussionsContextTestBase):
    def _create_context(self) -> DiscussionsContext:
        return DiscussionsContext(team=self.team, user=self.user)

    async def test_fetch_and_format_returns_threads(self):
        parent = await self._create_comment(content="Parent thread")
        await self._create_comment(content="Reply 1", source_comment=parent)
        await self._create_comment(content="Reply 2", source_comment=parent)

        result = await self._create_context().fetch_and_format(scope="Dashboard")

        assert "dashboard" in result.lower()
        assert "2 repl" in result.lower()

    async def test_fetch_and_format_filters_by_scope(self):
        await self._create_comment(scope="Dashboard", item_id="1")
        await self._create_comment(scope="FeatureFlag", item_id="2")

        result = await self._create_context().fetch_and_format(scope="Dashboard")

        assert result.count("- **") == 1
        assert "dashboard" in result.lower()

    async def test_fetch_and_format_empty(self):
        result = await self._create_context().fetch_and_format(scope="Dashboard")

        assert result == DISCUSSIONS_NO_RESULTS

    async def test_fetch_and_format_excludes_deleted(self):
        await self._create_comment(content="Active", deleted=False)
        await self._create_comment(content="Deleted", deleted=True)

        result = await self._create_context().fetch_and_format(scope="Dashboard")

        assert result.count("- **") == 1

    async def test_fetch_and_format_respects_team_scope(self):
        await self._create_comment(content="My team comment")
        other_team = await self.organization.teams.acreate(name="Other")
        await Comment.objects.acreate(
            team=other_team, content="Other team", scope="Dashboard", item_id="1", created_by=self.user
        )

        result = await self._create_context().fetch_and_format(scope="Dashboard")

        assert "other team" not in result.lower()
        assert result.count("- **") == 1

    async def test_fetch_and_format_extracts_mentions(self):
        await self._create_comment(
            content="Hey @alice check this",
            rich_content={"type": "doc", "content": [{"type": "mention", "attrs": {"label": "alice@example.com"}}]},
        )

        result = await self._create_context().fetch_and_format(scope="Dashboard")

        assert "alice@example.com" in result

    async def test_fetch_and_format_extracts_item_name_from_context(self):
        await self._create_comment(
            item_context={"name": "Growth KPIs"},
        )

        result = await self._create_context().fetch_and_format(scope="Dashboard")

        assert "growth kpis" in result.lower()

    async def test_fetch_and_format_pagination(self):
        for i in range(5):
            await self._create_comment(item_id=str(i))

        result = await self._create_context().fetch_and_format(scope="Dashboard", limit=2)

        assert "more results" in result.lower()
        assert "offset=2" in result.lower()

    async def test_fetch_and_format_search_text(self):
        await self._create_comment(content="Found this bug in checkout")
        await self._create_comment(content="Everything is fine", item_id="2")

        result = await self._create_context().fetch_and_format(scope="Dashboard", search_text="bug")

        assert result.count("- **") == 1
