from posthog.test.base import BaseTest

from ee.hogai.context.org_intelligence.metalytics_context import MetalyticsContext
from ee.hogai.context.org_intelligence.prompts import METALYTICS_NO_RESULTS


class TestMetalyticsContext(BaseTest):
    def _create_context(self) -> MetalyticsContext:
        return MetalyticsContext(team=self.team, user=self.user)

    async def test_fetch_and_format_empty(self):
        result = await self._create_context().fetch_and_format()

        assert result == METALYTICS_NO_RESULTS

    async def test_fetch_and_format_with_scope_filter(self):
        result = await self._create_context().fetch_and_format(scope="Dashboard")

        assert result == METALYTICS_NO_RESULTS

    async def test_format_entries_formats_correctly(self):
        ctx = self._create_context()
        entries = [
            {"resource_type": "Dashboard", "resource_id": "42", "view_count": 100, "unique_viewers": 8},
            {"resource_type": "Insight", "resource_id": "7", "view_count": 50, "unique_viewers": 3},
        ]

        result = ctx._format_entries(entries, total_count=2, limit=20, offset=0, scope_filter=None)

        assert "Dashboard #42" in result
        assert "100 views" in result
        assert "8 unique viewers" in result
        assert "Insight #7" in result
        assert "all matching results" in result.lower()

    async def test_format_entries_with_pagination(self):
        ctx = self._create_context()
        entries = [
            {"resource_type": "Dashboard", "resource_id": "1", "view_count": 10, "unique_viewers": 2},
        ]

        result = ctx._format_entries(entries, total_count=5, limit=1, offset=0, scope_filter="Dashboard")

        assert "more results" in result.lower()
        assert "offset=1" in result.lower()
        assert "for Dashboard" in result
