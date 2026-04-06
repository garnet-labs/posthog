from typing import Any

from posthog.models import Team, User
from posthog.models.organization import OrganizationMembership
from posthog.sync import database_sync_to_async

from ee.hogai.context.org_intelligence.prompts import (
    MEMBERSHIP_LEVEL_NAMES,
    ORG_MEMBERS_CONTEXT_TEMPLATE,
    ORG_MEMBERS_NO_RESULTS,
)


class OrgMembersContext:
    def __init__(self, team: Team, user: User):
        self._team = team
        self._user = user

    async def fetch_and_format(
        self,
        *,
        include_roles: bool = False,
        include_activity_summary: bool = False,
    ) -> str:
        entries = await self._fetch_entries(include_roles=include_roles)
        return self._format_entries(entries)

    @database_sync_to_async
    def _fetch_entries(self, *, include_roles: bool = False) -> list[dict[str, Any]]:
        memberships = (
            OrganizationMembership.objects.filter(organization=self._team.organization)
            .select_related("user")
            .order_by("-level", "user__first_name", "user__email")
        )

        role_map: dict[int, list[str]] = {}
        if include_roles:
            from ee.models.rbac.role import RoleMembership

            role_memberships = RoleMembership.objects.filter(role__organization=self._team.organization).select_related(
                "role", "user"
            )
            for rm in role_memberships:
                role_map.setdefault(rm.user_id, []).append(rm.role.name)

        entries: list[dict[str, Any]] = []
        for membership in memberships:
            user = membership.user
            level_name = MEMBERSHIP_LEVEL_NAMES.get(membership.level, "member")
            roles = role_map.get(user.id, []) if include_roles else []
            entries.append(
                {
                    "name": user.first_name or user.email.split("@")[0],
                    "email": user.email,
                    "level": level_name,
                    "roles": roles,
                    "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
                    "last_active": user.last_login.isoformat() if user.last_login else None,
                }
            )
        return entries

    def _format_entries(self, entries: list[dict[str, Any]]) -> str:
        if not entries:
            return ORG_MEMBERS_NO_RESULTS

        formatted: list[str] = []
        for entry in entries:
            roles_str = f" | roles: {', '.join(entry['roles'])}" if entry["roles"] else ""
            last_active_str = f" | last active: {entry['last_active']}" if entry["last_active"] else ""
            formatted.append(f"- {entry['name']} ({entry['email']}) | {entry['level']}{roles_str}{last_active_str}")

        return ORG_MEMBERS_CONTEXT_TEMPLATE.format(
            count=len(entries),
            entries="\n".join(formatted),
        )
