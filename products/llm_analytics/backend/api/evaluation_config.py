from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.monitoring import monitor
from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.event_usage import report_user_action
from posthog.permissions import AccessControlPermission

from ..models.evaluation_config import EvaluationConfig
from ..models.evaluations import Evaluation
from ..models.model_configuration import LLMModelConfiguration
from ..models.provider_keys import LLMProviderKey
from .metrics import llma_track_latency
from .provider_keys import LLMProviderKeySerializer


class EvaluationConfigSerializer(serializers.ModelSerializer):
    trial_evals_remaining = serializers.IntegerField(read_only=True)
    active_provider_key = LLMProviderKeySerializer(read_only=True)
    trial_providers = serializers.SerializerMethodField(
        help_text="Providers whose evaluations are consuming trial quota (no BYOK key available)."
    )

    class Meta:
        model = EvaluationConfig
        fields = [
            "trial_eval_limit",
            "trial_evals_used",
            "trial_evals_remaining",
            "active_provider_key",
            "trial_providers",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "trial_evals_used",
            "trial_evals_remaining",
            "active_provider_key",
            "trial_providers",
            "created_at",
            "updated_at",
        ]

    def get_trial_providers(self, obj: EvaluationConfig) -> list[str]:
        """Return providers whose evaluations would consume trial quota.

        A provider is on trial when it has active evaluations without a pinned
        BYOK key and the team has no healthy BYOK key for that provider.
        """
        # Providers used by active evals without a pinned BYOK key
        unpinned_providers = set(
            LLMModelConfiguration.objects.filter(
                team_id=obj.team_id,
                provider_key__isnull=True,
                evaluations__deleted=False,
            )
            .values_list("provider", flat=True)
            .distinct()
        )

        # Legacy evaluations (no model_configuration) default to OpenAI
        has_legacy_evals = Evaluation.objects.filter(
            team_id=obj.team_id,
            model_configuration__isnull=True,
            deleted=False,
        ).exists()
        if has_legacy_evals:
            unpinned_providers.add("openai")

        if not unpinned_providers:
            return []

        # Providers with a healthy BYOK key
        covered_providers = set(
            LLMProviderKey.objects.filter(
                team_id=obj.team_id,
                state=LLMProviderKey.State.OK,
                provider__in=unpinned_providers,
            )
            .values_list("provider", flat=True)
            .distinct()
        )

        return sorted(unpinned_providers - covered_providers)


class EvaluationConfigViewSet(TeamAndOrgViewSetMixin, viewsets.ViewSet):
    """Team-level evaluation configuration"""

    scope_object = "llm_provider_key"
    permission_classes = [IsAuthenticated, AccessControlPermission]

    @llma_track_latency("llma_evaluation_config_list")
    @monitor(feature=None, endpoint="llma_evaluation_config_list", method="GET")
    def list(self, request: Request, **kwargs) -> Response:
        """Get the evaluation config for this team"""
        config, _ = EvaluationConfig.objects.get_or_create(team_id=self.team_id)
        serializer = EvaluationConfigSerializer(config)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    @llma_track_latency("llma_evaluation_config_set_active_key")
    @monitor(feature=None, endpoint="llma_evaluation_config_set_active_key", method="POST")
    def set_active_key(self, request: Request, **kwargs) -> Response:
        """Set the active provider key for evaluations"""
        key_id = request.data.get("key_id")

        if not key_id:
            return Response(
                {"detail": "key_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            key = LLMProviderKey.objects.get(id=key_id, team_id=self.team_id)
        except LLMProviderKey.DoesNotExist:
            return Response(
                {"detail": "Key not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if key.state != LLMProviderKey.State.OK:
            return Response(
                {"detail": f"Cannot activate key with state '{key.state}'. Please validate the key first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config, _ = EvaluationConfig.objects.get_or_create(team_id=self.team_id)
        old_key = config.active_provider_key
        config.active_provider_key = key
        config.save(update_fields=["active_provider_key", "updated_at"])

        report_user_action(
            request.user,
            "llma evaluation config active key set",
            {
                "key_id": str(key.id),
                "old_key_id": str(old_key.id) if old_key else None,
            },
            team=self.team,
            request=self.request,
        )

        serializer = EvaluationConfigSerializer(config)
        return Response(serializer.data)
