from django.conf import settings
from django.utils import timezone

import dagster
import structlog
import posthoganalytics

from posthog.dags.common import JobOwners
from posthog.email import EmailMessage, is_email_available
from posthog.models import Team
from posthog.models.organization import Organization, OrganizationMembership
from posthog.tasks.email import NotificationSetting, should_send_notification
from posthog.user_permissions import UserPermissions

from products.web_analytics.backend.weekly_digest import auto_select_project_for_user, build_team_digest

logger = structlog.get_logger(__name__)


@dagster.op(out=dagster.DynamicOut(str))
def get_orgs_for_digest_op(context: dagster.OpExecutionContext):
    """Discover orgs where the digest flag is enabled, yield one DynamicOutput per org."""
    org_ids = [str(oid) for oid in Organization.objects.values_list("id", flat=True)]

    targeted_org_ids = [
        org_id
        for org_id in org_ids
        if posthoganalytics.feature_enabled(
            "web-analytics-weekly-digest",
            distinct_id=f"digest-worker-{org_id}",
            groups={"organization": org_id},
            only_evaluate_locally=False,
            send_feature_flag_events=False,
        )
    ]

    context.log.info(f"Found {len(targeted_org_ids)}/{len(org_ids)} orgs with digest flag enabled, fanning out")

    for org_id in targeted_org_ids:
        yield dagster.DynamicOutput(
            org_id,
            mapping_key=org_id.replace("-", "_"),
        )


@dagster.op
def build_and_send_digest_for_org_op(context: dagster.OpExecutionContext, org_id: str) -> None:
    """Process a single org: compute digests per team, send email per member."""
    if not is_email_available(with_absolute_urls=True):
        return

    try:
        org = Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        context.log.warning(f"Organization {org_id} not found for WA weekly digest")
        return

    memberships = list(OrganizationMembership.objects.prefetch_related("user").filter(organization_id=org.id))
    targeted_memberships = [
        m
        for m in memberships
        if posthoganalytics.feature_enabled(
            "web-analytics-weekly-digest",
            distinct_id=str(m.user.distinct_id),
            groups={"organization": str(org.id)},
            only_evaluate_locally=False,
            send_feature_flag_events=False,
        )
    ]
    if not targeted_memberships:
        return

    all_org_teams = list(Team.objects.filter(organization_id=org.id))
    if not all_org_teams:
        return

    team_digest_data: dict[int, dict] = {}
    for team in all_org_teams:
        team_digest_data[team.id] = build_team_digest(team)

    date_suffix = timezone.now().strftime("%Y-%W")
    sent_count = 0

    for membership in targeted_memberships:
        user = membership.user

        if not should_send_notification(user, NotificationSetting.WEB_ANALYTICS_WEEKLY_DIGEST.value):
            continue

        if auto_select_project_for_user(user, org.id, team_digest_data):
            user.refresh_from_db(fields=["partial_notification_settings"])

        user_team_sections = []
        disabled_team_names = []
        user_perms = UserPermissions(user)
        for team_id, data in team_digest_data.items():
            team = data["team"]
            if user_perms.team(team).effective_membership_level_for_parent_membership(org, membership) is None:
                continue

            if should_send_notification(user, NotificationSetting.WEB_ANALYTICS_WEEKLY_DIGEST.value, team_id):
                user_team_sections.append(data)
            else:
                disabled_team_names.append(team.name)

        if not user_team_sections:
            continue

        user_team_sections.sort(key=lambda d: d.get("visitors", {}).get("current", 0), reverse=True)

        campaign_key = f"web_analytics_weekly_digest_{org_id}_{user.uuid}_{date_suffix}"
        message = EmailMessage(
            campaign_key=campaign_key,
            subject=f"Web analytics weekly digest for {org.name}",
            template_name="web_analytics_weekly_digest",
            template_context={
                "organization": org,
                "project_sections": user_team_sections,
                "disabled_project_names": disabled_team_names,
                "settings_url": f"{settings.SITE_URL}/settings/user-notifications?highlight=wa-weekly-digest",
            },
        )
        message.add_user_recipient(user)
        message.send()
        sent_count += 1

    context.log.info(f"Sent WA weekly digest to {sent_count} members for org {org_id} ({len(team_digest_data)} teams)")
    context.add_output_metadata({"sent_count": sent_count, "team_count": len(team_digest_data)})


@dagster.job(
    description="Sends weekly web analytics digest emails",
    tags={"owner": JobOwners.TEAM_WEB_ANALYTICS.value},
)
def web_analytics_weekly_digest_job():
    org_ids = get_orgs_for_digest_op()
    org_ids.map(build_and_send_digest_for_org_op)


@dagster.schedule(
    cron_schedule="0 9 * * 1",
    job=web_analytics_weekly_digest_job,
    execution_timezone="UTC",
    tags={"owner": JobOwners.TEAM_WEB_ANALYTICS.value},
)
def web_analytics_weekly_digest_schedule(context: dagster.ScheduleEvaluationContext):
    return dagster.RunRequest()


class SendTestDigestConfig(dagster.Config):
    team_id: int
    email: str
    force: bool = False


@dagster.op
def send_test_digest_op(context: dagster.OpExecutionContext, config: SendTestDigestConfig) -> None:
    """Send a single digest email for a specific team, bypassing the feature flag."""
    if not is_email_available(with_absolute_urls=True):
        context.log.error("Email is not available — check EMAIL_HOST in instance settings")
        return

    team = Team.objects.select_related("organization").filter(id=config.team_id).first()
    if not team:
        context.log.error(f"Team {config.team_id} not found")
        return

    digest = build_team_digest(team)

    date_suffix = timezone.now().strftime("%Y-%W")
    campaign_key = f"wa_digest_test_{team.pk}_{date_suffix}"
    if config.force:
        campaign_key = f"{campaign_key}_{timezone.now().isoformat()}"
    message = EmailMessage(
        campaign_key=campaign_key,
        subject=f"[Test] Web analytics weekly digest for {team.organization.name}",
        template_name="web_analytics_weekly_digest",
        template_context={
            "organization": team.organization,
            "project_sections": [digest],
            "disabled_project_names": [],
            "settings_url": f"{settings.SITE_URL}/settings/user-notifications?highlight=wa-weekly-digest",
        },
    )
    message.add_recipient(email=config.email, name="Test")
    message.send()
    context.log.info(f"Sent test digest for team {team.name} ({team.pk}) to {config.email}")


@dagster.job(
    description="Send a test web analytics digest email for a single team (bypasses feature flag)",
    tags={"owner": JobOwners.TEAM_WEB_ANALYTICS.value},
)
def web_analytics_weekly_digest_test_job():
    send_test_digest_op()
