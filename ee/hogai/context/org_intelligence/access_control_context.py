from typing import Any

from django.db.models import QuerySet

from posthog.constants import AvailableFeature
from posthog.models import Team, User
from posthog.sync import database_sync_to_async

from ee.hogai.context.org_intelligence.prompts import ACCESS_CONTROL_CONTEXT_TEMPLATE, ACCESS_CONTROL_NO_CUSTOM
from ee.models.rbac.access_control import AccessControl
from ee.models.rbac.role import Role, RoleMembership


class AccessControlContext:
    def __init__(self, team: Team, user: User):
        self._team = team
        self._user = user

    async def fetch_and_format(
        self,
        *,
        resource: str | None = None,
        include_members: bool = False,
        include_roles: bool = False,
    ) -> str:
        if not self._team.organization.is_feature_available(AvailableFeature.ACCESS_CONTROL):
            return ACCESS_CONTROL_NO_CUSTOM

        if include_roles and not self._team.organization.is_feature_available(AvailableFeature.ROLE_BASED_ACCESS):
            include_roles = False

        data = await self._fetch_data(
            resource=resource,
            include_members=include_members,
            include_roles=include_roles,
        )
        return self._format_data(data)

    @database_sync_to_async
    def _fetch_data(
        self,
        *,
        resource: str | None = None,
        include_members: bool = False,
        include_roles: bool = False,
    ) -> dict[str, Any]:
        queryset: QuerySet[AccessControl] = AccessControl.objects.filter(team=self._team)

        if resource:
            queryset = queryset.filter(resource=resource)

        defaults = list(
            queryset.filter(resource_id__isnull=True, organization_member__isnull=True, role__isnull=True).values(
                "resource", "access_level"
            )
        )

        restricted = list(
            queryset.exclude(resource_id__isnull=True, organization_member__isnull=True, role__isnull=True)
            .select_related("organization_member__user", "role")
            .values("resource", "resource_id", "access_level", "role__name", "organization_member__user__email")
        )

        roles_data: list[dict[str, Any]] = []
        if include_roles:
            roles = Role.objects.filter(organization=self._team.organization)
            for role in roles:
                members = list(
                    RoleMembership.objects.filter(role=role)
                    .select_related("user")
                    .values_list("user__email", flat=True)
                )
                roles_data.append({"name": role.name, "member_count": len(members), "members": list(members)})

        return {
            "defaults": defaults,
            "restricted": restricted,
            "roles": roles_data,
        }

    def _format_data(self, data: dict[str, Any]) -> str:
        defaults = data["defaults"]
        restricted = data["restricted"]
        roles = data["roles"]

        if not defaults and not restricted and not roles:
            return ACCESS_CONTROL_NO_CUSTOM

        if defaults:
            defaults_str = "\n".join(f"- {d['resource']}: {d['access_level']}" for d in defaults)
        else:
            defaults_str = "No custom defaults — using organization-level defaults."

        if restricted:
            restricted_lines: list[str] = []
            for r in restricted:
                target = ""
                if r.get("role__name"):
                    target = f" (role: {r['role__name']})"
                elif r.get("organization_member__user__email"):
                    target = f" (member: {r['organization_member__user__email']})"
                resource_id = f" #{r['resource_id']}" if r.get("resource_id") else ""
                restricted_lines.append(f"- {r['resource']}{resource_id}: {r['access_level']}{target}")
            restricted_str = "\n".join(restricted_lines)
        else:
            restricted_str = "No resource-specific overrides."

        roles_section = ""
        if roles:
            roles_lines = ["\n## Roles"]
            for role in roles:
                members_preview = ", ".join(role["members"][:5])
                if role["member_count"] > 5:
                    members_preview += f" (+{role['member_count'] - 5} more)"
                roles_lines.append(f"- {role['name']} ({role['member_count']} members): {members_preview}")
            roles_section = "\n".join(roles_lines)

        return ACCESS_CONTROL_CONTEXT_TEMPLATE.format(
            team_name=self._team.name,
            defaults=defaults_str,
            restricted_resources=restricted_str,
            roles_section=roles_section,
            members_section="",
        )
