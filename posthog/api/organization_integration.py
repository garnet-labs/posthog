from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.api.shared import UserBasicSerializer
from posthog.models.organization_integration import OrganizationIntegration


class OrganizationIntegrationSerializer(serializers.ModelSerializer):
    """Serializer for organization-level integrations."""

    created_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = OrganizationIntegration
        fields = [
            "id",
            "kind",
            "integration_id",
            "config",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = fields


class OrganizationIntegrationViewSet(
    TeamAndOrgViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for organization-level integrations.

    Provides read-only access to integrations that are scoped to the entire organization
    (vs. project-level integrations). Examples include Vercel, AWS Marketplace, etc.

    This is read-only. Creation is handled by the integration installation flows
    (e.g., Vercel marketplace installation). Deletion requires contacting support
    due to billing implications.
    """

    scope_object = "organization_integration"
    queryset = OrganizationIntegration.objects.select_related("created_by").all()
    serializer_class = OrganizationIntegrationSerializer

    @action(detail=True, methods=["patch"], url_path="environment-mapping")
    def environment_mapping(self, request: Request, **kwargs) -> Response:
        integration = self.get_object()

        if integration.config.get("type") != "connectable":
            return Response(
                {"detail": "Environment mapping is only supported for connectable integrations."}, status=400
            )

        env_mapping = request.data
        if not isinstance(env_mapping, dict) or "production" not in env_mapping:
            return Response({"detail": "A mapping with at least 'production' is required."}, status=400)

        from posthog.models.team import Team

        org = integration.organization
        unique_team_ids: set[int] = set()
        for env_name, team_id in env_mapping.items():
            if not isinstance(env_name, str) or not env_name.strip():
                return Response({"detail": f"Invalid environment name: {env_name!r}"}, status=400)
            if not isinstance(team_id, int):
                return Response({"detail": f"Invalid project ID for {env_name}: expected integer."}, status=400)
            unique_team_ids.add(team_id)

        for tid in unique_team_ids:
            if not Team.objects.filter(pk=tid, organization=org).exists():
                return Response({"detail": f"Project {tid} does not belong to this organization."}, status=400)

        from posthog.models.integration import Integration as TeamIntegration

        from ee.vercel.client import VercelAPIClient

        teams_by_id: dict[int, Team] = {}
        resources: dict[int, TeamIntegration] = {}
        for tid in unique_team_ids:
            teams_by_id[tid] = Team.objects.get(pk=tid, organization=org)
            resources[tid], _ = TeamIntegration.objects.get_or_create(
                team=teams_by_id[tid],
                kind=TeamIntegration.IntegrationKind.VERCEL,
                integration_id=str(tid),
                defaults={"config": {"type": "connectable"}},
            )

        integration.config["environment_mapping"] = env_mapping
        integration.save(update_fields=["config"])

        production_id = env_mapping["production"]
        production_team = teams_by_id[production_id]
        production_resource = resources[production_id]

        access_token = integration.sensitive_config.get("credentials", {}).get(
            "access_token"
        ) or integration.config.get("credentials", {}).get("access_token")
        if access_token and integration.integration_id:
            from ee.api.vercel.vercel_connect import VercelConnectLinkViewSet

            secrets = VercelConnectLinkViewSet._build_env_secrets(teams_by_id, env_mapping)
            client = VercelAPIClient(bearer_token=access_token)
            client.import_resource(
                integration_config_id=integration.integration_id,
                resource_id=str(production_resource.pk),
                product_id="posthog",
                name=production_team.name,
                secrets=secrets,
            )

        return Response(OrganizationIntegrationSerializer(integration).data)
