from datetime import datetime
from typing import Any

from django.db.models import Count, Max, Q, QuerySet

from posthog.models import Team, User
from posthog.models.comment.comment import Comment
from posthog.sync import database_sync_to_async

from ee.hogai.context.org_intelligence.prompts import (
    DISCUSSIONS_CONTEXT_TEMPLATE,
    DISCUSSIONS_NO_RESULTS,
    DISCUSSIONS_PAGINATION_END,
    DISCUSSIONS_PAGINATION_MORE,
)


class DiscussionsContext:
    def __init__(self, team: Team, user: User):
        self._team = team
        self._user = user

    async def fetch_and_format(
        self,
        *,
        scope: str | None = None,
        item_id: str | None = None,
        date_range: tuple[str, str] | None = None,
        search_text: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        entries, total = await self._fetch_entries(
            scope=scope,
            item_id=item_id,
            date_range=date_range,
            search_text=search_text,
            limit=limit,
            offset=offset,
        )
        return self._format_entries(entries, total_count=total, limit=limit, offset=offset, scope_filter=scope)

    @database_sync_to_async
    def _fetch_entries(
        self,
        *,
        scope: str | None = None,
        item_id: str | None = None,
        date_range: tuple[str, str] | None = None,
        search_text: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        queryset: QuerySet[Comment] = (
            Comment.objects.filter(team=self._team, deleted=False, source_comment__isnull=True)
            .select_related("created_by")
            .annotate(
                reply_count=Count("comment", filter=Q(comment__deleted=False)),
                last_reply_at=Max("comment__created_at", filter=Q(comment__deleted=False)),
            )
            .order_by("-created_at")
        )

        if scope:
            queryset = queryset.filter(scope=scope)

        if item_id:
            queryset = queryset.filter(item_id=item_id)

        if date_range:
            after_str, before_str = date_range
            try:
                queryset = queryset.filter(created_at__gte=datetime.fromisoformat(after_str))
            except ValueError:
                pass
            try:
                queryset = queryset.filter(created_at__lte=datetime.fromisoformat(before_str))
            except ValueError:
                pass

        if search_text:
            queryset = queryset.filter(content__icontains=search_text)

        limit = min(max(limit, 1), 50)
        total_count = queryset.count()
        entries = list(queryset[offset : offset + limit])

        result: list[dict[str, Any]] = []
        for comment in entries:
            mentions = self._extract_mentions(comment.rich_content)
            result.append(
                {
                    "timestamp": comment.created_at.isoformat(),
                    "scope": comment.scope,
                    "item_id": comment.item_id,
                    "item_name": self._extract_item_name(comment),
                    "content_preview": (comment.content or "")[:200],
                    "reply_count": comment.reply_count,
                    "last_activity": (comment.last_reply_at or comment.created_at).isoformat(),
                    "created_by": (
                        comment.created_by.first_name or comment.created_by.email if comment.created_by else "Unknown"
                    ),
                    "mentions": mentions,
                }
            )
        return result, total_count

    def _format_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        total_count: int,
        limit: int,
        offset: int,
        scope_filter: str | None = None,
    ) -> str:
        if not entries:
            return DISCUSSIONS_NO_RESULTS

        formatted: list[str] = []
        for entry in entries:
            mentions_str = ""
            if entry["mentions"]:
                mentions_str = f" | mentions: {', '.join(entry['mentions'])}"
            formatted.append(
                f'- **{entry["timestamp"]}** | {entry["scope"]} | "{entry["item_name"]}" | '
                f"{entry['reply_count']} replies | last activity: {entry['last_activity']}{mentions_str}"
            )

        filter_desc = f" for scope={scope_filter}" if scope_filter else ""
        has_more = total_count > offset + limit
        pagination_hint = (
            DISCUSSIONS_PAGINATION_MORE.format(next_offset=offset + limit) if has_more else DISCUSSIONS_PAGINATION_END
        )

        return DISCUSSIONS_CONTEXT_TEMPLATE.format(
            count=len(entries),
            total_count=total_count,
            offset_start=offset + 1,
            offset_end=offset + len(entries),
            scope_filter=filter_desc,
            entries="\n".join(formatted),
            pagination_hint=pagination_hint,
        )

    def _extract_item_name(self, comment: Comment) -> str:
        if comment.item_context and isinstance(comment.item_context, dict):
            name = comment.item_context.get("name")
            if name:
                return str(name)[:200]
        return f"{comment.scope} #{comment.item_id}"

    def _extract_mentions(self, rich_content: dict | None) -> list[str]:
        if not rich_content or not isinstance(rich_content, dict):
            return []
        mentions: list[str] = []
        self._walk_mentions(rich_content, mentions)
        return mentions

    def _walk_mentions(self, node: dict, mentions: list[str]) -> None:
        if node.get("type") == "mention":
            label = node.get("attrs", {}).get("label", "")
            if label:
                mentions.append(label)
        for child in node.get("content", []):
            if isinstance(child, dict):
                self._walk_mentions(child, mentions)
