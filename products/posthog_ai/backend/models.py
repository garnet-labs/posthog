from typing import TYPE_CHECKING

from django.db import models

import tiktoken

from posthog.models.utils import CreatedMetaFields, UpdatedMetaFields, UUIDModel

if TYPE_CHECKING:
    from kafka.producer.kafka import FutureRecordMetadata

EMBEDDING_MODEL_TOKEN_LIMIT = 8192


class AgentMemory(UUIDModel):
    team = models.ForeignKey(
        "posthog.Team",
        on_delete=models.CASCADE,
        related_name="agent_memories",
    )
    user = models.ForeignKey(
        "posthog.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_memories",
    )
    contents = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["team", "id"]),
        ]

    def embed(self, model_name: str) -> "FutureRecordMetadata":
        enc = tiktoken.get_encoding("cl100k_base")
        token_count = len(enc.encode(self.contents))
        if token_count > EMBEDDING_MODEL_TOKEN_LIMIT:
            raise ValueError(
                f"Memory content exceeds {EMBEDDING_MODEL_TOKEN_LIMIT} token limit for embedding model (got {token_count} tokens)"
            )

        from posthog.api.embedding_worker import emit_embedding_request

        embedding_metadata = {**self.metadata}
        if self.user_id is not None:
            embedding_metadata["user_id"] = str(self.user_id)

        return emit_embedding_request(
            content=self.contents,
            team_id=self.team_id,
            product="posthog-ai",
            document_type="memory",
            rendering="plaintext",
            document_id=str(self.id),
            models=[model_name],
            timestamp=self.created_at,
            metadata=embedding_metadata,
        )


class ActionPredictionModel(UUIDModel, CreatedMetaFields, UpdatedMetaFields):
    team = models.ForeignKey(
        "posthog.Team",
        on_delete=models.CASCADE,
        related_name="action_prediction_models",
    )
    name = models.CharField(max_length=400, blank=True, default="")
    description = models.TextField(blank=True, default="")
    action = models.ForeignKey(
        "posthog.Action",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    event_name = models.CharField(max_length=400, null=True, blank=True)
    lookback_days = models.PositiveIntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["team", "id"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(action__isnull=False, event_name__isnull=True)
                    | models.Q(action__isnull=True, event_name__isnull=False)
                ),
                name="action_or_event_name_exclusive",
            ),
        ]


class ActionPredictionModelRun(UUIDModel, CreatedMetaFields, UpdatedMetaFields):
    prediction_model = models.ForeignKey(
        ActionPredictionModel,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    team = models.ForeignKey(
        "posthog.Team",
        on_delete=models.CASCADE,
        related_name="action_prediction_model_runs",
    )
    is_winning = models.BooleanField(
        default=False,
        help_text="Whether this run produced a winning prediction model.",
    )
    model_url = models.URLField(
        max_length=2000,
        help_text="S3 URL to the serialized model artifact.",
    )
    metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Model evaluation metrics (e.g. accuracy, AUC, F1).",
    )
    feature_importance = models.JSONField(
        default=dict,
        blank=True,
        help_text="Feature importance scores from model training.",
    )
    artifact_scripts = models.JSONField(
        default=dict,
        blank=True,
        help_text="Python scripts used in this run. Keys: data, preprocess, train, predict.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["team", "id"]),
            models.Index(fields=["prediction_model", "-created_at"]),
        ]
