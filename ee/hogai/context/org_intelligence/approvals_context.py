from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from posthog.approvals.models import ChangeRequest
from posthog.constants import AvailableFeature
from posthog.models import Team, User
from posthog.sync import database_sync_to_async

from ee.hogai.context.org_intelligence.prompts import (
    APPROVALS_CONTEXT_TEMPLATE,
    APPROVALS_NO_RESULTS,
    APPROVALS_PAGINATION_END,
    APPROVALS_PAGINATION_MORE,
)

STALE_THRESHOLD_HOURS = 48


class ApprovalsContext:
    def __init__(self, team: Team, user: User):
        self._team = team
        self._user = user

    async def fetch_and_format(
        self,
        *,
        state: str | None = None,
        resource_type: str | None = None,
        date_range: tuple[str, str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        if not self._team.organization.is_feature_available(AvailableFeature.APPROVALS):
            return APPROVALS_NO_RESULTS

        if state is None:
            state = "pending"

        entries, total = await self._fetch_entries(
            state=state,
            resource_type=resource_type,
            date_range=date_range,
            limit=limit,
            offset=offset,
        )
        return self._format_entries(entries, total_count=total, limit=limit, offset=offset, state_filter=state)

    @database_sync_to_async
    def _fetch_entries(
        self,
        *,
        state: str | None = None,
        resource_type: str | None = None,
        date_range: tuple[str, str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ChangeRequest], int]:
        queryset: QuerySet[ChangeRequest] = (
            ChangeRequest.objects.filter(team=self._team)
            .select_related("created_by")
            .prefetch_related("approvals", "approvals__created_by")
            .order_by("-created_at")
        )

        if state and state != "all":
            queryset = queryset.filter(state=state)

        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

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

        limit = min(max(limit, 1), 50)
        total_count = queryset.count()
        entries = list(queryset[offset : offset + limit])
        return entries, total_count

    def _format_entries(
        self,
        entries: list[ChangeRequest],
        *,
        total_count: int,
        limit: int,
        offset: int,
        state_filter: str | None = None,
    ) -> str:
        if not entries:
            return APPROVALS_NO_RESULTS

        formatted_entries: list[str] = []
        for entry in entries:
            formatted_entries.append(self._format_single_entry(entry))

        filter_desc = f" for state={state_filter}" if state_filter and state_filter != "all" else ""
        has_more = total_count > offset + limit
        pagination_hint = (
            APPROVALS_PAGINATION_MORE.format(next_offset=offset + limit) if has_more else APPROVALS_PAGINATION_END
        )

        return APPROVALS_CONTEXT_TEMPLATE.format(
            count=len(entries),
            total_count=total_count,
            offset_start=offset + 1,
            offset_end=offset + len(entries),
            state_filter=filter_desc,
            entries="\n".join(formatted_entries),
            pagination_hint=pagination_hint,
        )

    def _format_single_entry(self, entry: ChangeRequest) -> str:
        timestamp = entry.created_at.isoformat()
        intent_summary = self._extract_intent_summary(entry)
        user_attr = self._format_user_attribution(entry)
        vote_status = self._format_vote_status(entry)
        staleness = self._format_staleness(entry)

        return (
            f"- **{timestamp}** | {entry.resource_type} | {entry.state} | "
            f'"{intent_summary}"{user_attr}{vote_status}{staleness}'
        )

    def _extract_intent_summary(self, entry: ChangeRequest) -> str:
        if entry.intent_display and isinstance(entry.intent_display, dict):
            summary = entry.intent_display.get("summary")
            if summary:
                return str(summary)[:200]
        return f"{entry.action_key} on {entry.resource_type}"

    def _format_user_attribution(self, entry: ChangeRequest) -> str:
        if entry.created_by:
            name = entry.created_by.first_name or entry.created_by.email
            return f" | by {name}"
        return ""

    def _format_vote_status(self, entry: ChangeRequest) -> str:
        approvals = list(entry.approvals.all())
        if not approvals:
            return " | no votes yet"
        approved = sum(1 for a in approvals if a.decision == "approved")
        rejected = sum(1 for a in approvals if a.decision == "rejected")
        parts: list[str] = []
        if approved:
            parts.append(f"{approved} approved")
        if rejected:
            parts.append(f"{rejected} rejected")
        return f" | votes: {', '.join(parts)}"

    def _format_staleness(self, entry: ChangeRequest) -> str:
        if entry.state != "pending":
            return ""
        age = timezone.now() - entry.created_at
        if age > timedelta(hours=STALE_THRESHOLD_HOURS):
            hours = int(age.total_seconds() // 3600)
            if hours >= 48:
                days = hours // 24
                return f" | stale ({days} days pending)"
            return f" | stale ({hours}h pending)"
        return ""
