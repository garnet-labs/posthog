from django.core.cache import cache
from django.utils import timezone

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from posthog.api.shared import UserBasicSerializer
from posthog.models.integration import Integration
from posthog.storage import object_storage

from .models import SandboxEnvironment, Task, TaskRepository, TaskRun
from .services.title_generator import generate_task_title

PRESIGNED_URL_CACHE_TTL = 55 * 60  # 55 minutes (less than 1 hour URL expiry)


class TaskRepositorySerializer(serializers.Serializer):
    repository = serializers.CharField(
        max_length=400,
        help_text="Repository in org/repo format (e.g. posthog/posthog-js)",
    )
    github_integration = serializers.PrimaryKeyRelatedField(
        queryset=Integration.objects.filter(kind="github"),
        required=False,
        allow_null=True,
        default=None,
        help_text="GitHub integration ID",
    )

    def validate_repository(self, value):
        if not value:
            return value
        parts = value.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise serializers.ValidationError("Repository must be in the format organization/repository")
        return value.lower()

    def validate_github_integration(self, value):
        team = self.context.get("team")
        if value and team and value.team_id != team.id:
            raise serializers.ValidationError("Integration must belong to the same team")
        return value


class TaskSerializer(serializers.ModelSerializer):
    # Deprecated: kept for backward compatibility, returns the first repository
    repository = serializers.SerializerMethodField(
        help_text="First repository (deprecated, use repositories instead)",
    )
    github_integration = serializers.SerializerMethodField(
        help_text="First repository's GitHub integration (deprecated, use repositories instead)",
    )

    repositories = TaskRepositorySerializer(
        many=True,
        required=False,
        source="task_repositories",
        help_text="Repositories associated with this task",
    )

    latest_run = serializers.SerializerMethodField()
    created_by = UserBasicSerializer(read_only=True)

    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    origin_product = serializers.ChoiceField(choices=Task.OriginProduct.choices, required=False)

    class Meta:
        model = Task
        fields = [
            "id",
            "task_number",
            "slug",
            "title",
            "title_manually_set",
            "description",
            "origin_product",
            "repository",
            "github_integration",
            "repositories",
            "json_schema",
            "internal",
            "latest_run",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = [
            "id",
            "task_number",
            "slug",
            "repository",
            "github_integration",
            "created_at",
            "updated_at",
            "created_by",
            "latest_run",
        ]

    def get_repository(self, obj) -> str | None:
        repos = self._get_task_repositories(obj)
        return repos[0].repository if repos else obj.repository

    def get_github_integration(self, obj) -> int | None:
        repos = self._get_task_repositories(obj)
        if repos:
            return repos[0].github_integration_id
        return obj.github_integration_id

    def _get_task_repositories(self, obj) -> list:
        """Return task_repositories, using prefetch cache when available."""
        if hasattr(obj, "_prefetched_objects_cache") and "task_repositories" in obj._prefetched_objects_cache:
            return list(obj._prefetched_objects_cache["task_repositories"])
        return list(obj.task_repositories.all())

    @extend_schema_field(serializers.DictField(allow_null=True, help_text="Latest run details for this task"))
    def get_latest_run(self, obj):
        latest_run = obj.latest_run
        if latest_run:
            return TaskRunDetailSerializer(latest_run, context=self.context).data
        return None

    def to_internal_value(self, data):
        # Handle legacy create: if `repository` string is sent without `repositories` array,
        # convert it into the new format so the rest of the pipeline is uniform.
        if isinstance(data, dict) and "repository" in data and "repositories" not in data:
            repo_str = data.pop("repository")
            gh_int = data.pop("github_integration", None)
            if repo_str:
                entry: dict = {"repository": repo_str}
                if gh_int is not None:
                    entry["github_integration"] = gh_int
                data["repositories"] = [entry]

        return super().to_internal_value(data)

    def create(self, validated_data):
        repositories_data = validated_data.pop("task_repositories", [])

        validated_data["team"] = self.context["team"]

        if "request" in self.context and hasattr(self.context["request"], "user"):
            validated_data["created_by"] = self.context["request"].user

        title = validated_data.get("title", "").strip()
        if not title and validated_data.get("description"):
            validated_data["title"] = generate_task_title(validated_data["description"])
            validated_data.setdefault("title_manually_set", False)
        elif title:
            validated_data.setdefault("title_manually_set", True)

        task = super().create(validated_data)

        # If no repositories were provided, try to set a default GitHub integration
        if not repositories_data:
            default_integration = Integration.objects.filter(team=self.context["team"], kind="github").first()
            if default_integration:
                task.github_integration = default_integration
                task.save(update_fields=["github_integration"])
        else:
            self._sync_repositories(task, repositories_data)

        return task

    def update(self, instance, validated_data):
        repositories_data = validated_data.pop("task_repositories", None)

        if "title" in validated_data and "title_manually_set" not in validated_data:
            validated_data["title_manually_set"] = True

        instance = super().update(instance, validated_data)

        if repositories_data is not None:
            self._sync_repositories(instance, repositories_data)

        return instance

    def _sync_repositories(self, task: Task, repositories_data: list[dict]) -> None:
        """Replace all TaskRepository rows for a task and sync the legacy fields."""
        task.task_repositories.all().delete()

        default_integration = None
        for repo_data in repositories_data:
            gh_int = repo_data.get("github_integration")
            if gh_int is None and default_integration is None:
                default_integration = Integration.objects.filter(team=task.team, kind="github").first()
            TaskRepository.objects.create(
                task=task,
                repository=repo_data["repository"],
                github_integration=gh_int or default_integration,
            )

        # Sync legacy fields from the first repository
        first = task.task_repositories.first()
        if first:
            task.repository = first.repository
            task.github_integration = first.github_integration
        else:
            task.repository = None
            task.github_integration = None
        task.save(update_fields=["repository", "github_integration"])


class AgentDefinitionSerializer(serializers.Serializer):
    """Serializer for agent definitions"""

    id = serializers.CharField()
    name = serializers.CharField()
    agent_type = serializers.CharField()
    description = serializers.CharField()
    config = serializers.DictField(default=dict)
    is_active = serializers.BooleanField(default=True)


class TaskRunUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["not_started", "queued", "in_progress", "completed", "failed", "cancelled"],
        required=False,
        help_text="Current execution status",
    )
    branch = serializers.CharField(
        required=False, allow_null=True, help_text="Git branch name to associate with the task"
    )
    stage = serializers.CharField(
        required=False, allow_null=True, help_text="Current stage of the run (e.g. research, plan, build)"
    )
    output = serializers.JSONField(required=False, allow_null=True, help_text="Output from the run")
    state = serializers.JSONField(required=False, help_text="State of the run")
    error_message = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, help_text="Error message if execution failed"
    )


class TaskRunArtifactResponseSerializer(serializers.Serializer):
    name = serializers.CharField(help_text="Artifact file name")
    type = serializers.CharField(help_text="Artifact classification (plan, context, etc.)")
    size = serializers.IntegerField(required=False, help_text="Artifact size in bytes")
    content_type = serializers.CharField(required=False, allow_blank=True, help_text="Optional MIME type")
    storage_path = serializers.CharField(help_text="S3 object key for the artifact")
    uploaded_at = serializers.CharField(help_text="Timestamp when the artifact was uploaded")


class TaskRunDetailSerializer(serializers.ModelSerializer):
    log_url = serializers.SerializerMethodField(help_text="Presigned S3 URL for log access (valid for 1 hour).")
    artifacts = TaskRunArtifactResponseSerializer(many=True, read_only=True)

    class Meta:
        model = TaskRun
        fields = [
            "id",
            "task",
            "stage",
            "branch",
            "status",
            "environment",
            "log_url",
            "error_message",
            "output",
            "state",
            "artifacts",
            "created_at",
            "updated_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "task",
            "log_url",
            "created_at",
            "updated_at",
            "completed_at",
        ]

    @extend_schema_field(
        serializers.URLField(allow_null=True, help_text="Presigned S3 URL for log access (valid for 1 hour).")
    )
    def get_log_url(self, obj: TaskRun) -> str | None:
        """Return presigned S3 URL for log access, cached to avoid regeneration."""
        cache_key = f"task_run_log_url:{obj.id}"

        cached_url = cache.get(cache_key)
        if cached_url:
            return cached_url

        presigned_url = object_storage.get_presigned_url(obj.log_url, expiration=3600)

        if presigned_url:
            cache.set(cache_key, presigned_url, timeout=PRESIGNED_URL_CACHE_TTL)

        return presigned_url

    def validate_task(self, value):
        team = self.context.get("team")
        if team and value.team_id != team.id:
            raise serializers.ValidationError("Task must belong to the same team")
        return value

    def create(self, validated_data):
        validated_data["team"] = self.context["team"]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Never allow task reassignment through updates
        validated_data.pop("task", None)

        status = validated_data.get("status")
        if status in [TaskRun.Status.COMPLETED, TaskRun.Status.FAILED] and not validated_data.get("completed_at"):
            validated_data["completed_at"] = timezone.now()
        return super().update(instance, validated_data)


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField(help_text="Error message")


class AgentListResponseSerializer(serializers.Serializer):
    results = AgentDefinitionSerializer(many=True, help_text="Array of available agent definitions")


class TaskRunAppendLogRequestSerializer(serializers.Serializer):
    entries = serializers.ListField(
        child=serializers.DictField(),
        help_text="Array of log entry dictionaries to append",
    )

    def validate_entries(self, value):
        """Validate that entries is a non-empty list of dicts"""
        if not value:
            raise serializers.ValidationError("At least one log entry is required")
        return value


class TaskRunRelayMessageResponseSerializer(serializers.Serializer):
    status = serializers.CharField(help_text="Relay status: 'accepted' or 'skipped'")
    relay_id = serializers.CharField(required=False, help_text="Relay workflow ID when accepted")


class TaskRunRelayMessageRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=10000)


class TaskRunArtifactUploadSerializer(serializers.Serializer):
    ARTIFACT_TYPE_CHOICES = ["plan", "context", "reference", "output", "artifact", "tree_snapshot"]

    name = serializers.CharField(max_length=255, help_text="File name to associate with the artifact")
    type = serializers.ChoiceField(choices=ARTIFACT_TYPE_CHOICES, help_text="Classification for the artifact")
    content = serializers.CharField(help_text="Raw file contents (UTF-8 string or base64 data)")
    content_type = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Optional MIME type for the artifact",
    )


class TaskRunArtifactsUploadRequestSerializer(serializers.Serializer):
    artifacts = TaskRunArtifactUploadSerializer(many=True, help_text="Array of artifacts to upload")

    def validate_artifacts(self, value):
        if not value:
            raise serializers.ValidationError("At least one artifact is required")
        return value


class TaskRunArtifactsUploadResponseSerializer(serializers.Serializer):
    artifacts = TaskRunArtifactResponseSerializer(many=True, help_text="Updated list of artifacts on the run")


class TaskRunArtifactPresignRequestSerializer(serializers.Serializer):
    storage_path = serializers.CharField(
        max_length=500,
        help_text="S3 storage path returned in the artifact manifest",
    )


class TaskRunArtifactPresignResponseSerializer(serializers.Serializer):
    url = serializers.URLField(help_text="Presigned URL for downloading the artifact")
    expires_in = serializers.IntegerField(help_text="URL expiry in seconds")


class TaskListQuerySerializer(serializers.Serializer):
    """Query parameters for listing tasks"""

    origin_product = serializers.CharField(required=False, help_text="Filter by origin product")
    stage = serializers.CharField(required=False, help_text="Filter by task run stage")
    organization = serializers.CharField(required=False, help_text="Filter by repository organization")
    repository = serializers.CharField(
        required=False, help_text="Filter by repository name (can include org/repo format)"
    )
    created_by = serializers.IntegerField(required=False, help_text="Filter by creator user ID")
    internal = serializers.BooleanField(
        required=False, help_text="Filter by internal flag. Defaults to excluding internal tasks when not specified."
    )


class RepositoryReadinessQuerySerializer(serializers.Serializer):
    repository = serializers.CharField(required=True, help_text="Repository in org/repo format")
    window_days = serializers.IntegerField(required=False, default=7, min_value=1, max_value=30)
    refresh = serializers.BooleanField(required=False, default=False)

    def validate_repository(self, value: str) -> str:
        normalized = value.strip().lower()
        parts = normalized.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise serializers.ValidationError("Repository must be in the format organization/repository")
        return normalized


class CapabilityStateSerializer(serializers.Serializer):
    state = serializers.ChoiceField(
        choices=["needs_setup", "detected", "waiting_for_data", "ready", "not_applicable", "unknown"],
        help_text="Current state of the capability",
    )
    estimated = serializers.BooleanField(help_text="Whether the state is estimated from static analysis")
    reason = serializers.CharField(help_text="Human-readable explanation")
    evidence = serializers.DictField(required=False, default=dict, help_text="Supporting evidence")


class ScanEvidenceSerializer(serializers.Serializer):
    filesScanned = serializers.IntegerField(help_text="Number of files scanned")
    detectedFilesCount = serializers.IntegerField(help_text="Total candidate files detected")
    eventNameCount = serializers.IntegerField(help_text="Number of distinct event names found")
    foundPosthogInit = serializers.BooleanField(help_text="Whether posthog.init() was found in scanned files")
    foundPosthogCapture = serializers.BooleanField(help_text="Whether posthog.capture() was found in scanned files")
    foundErrorSignal = serializers.BooleanField(help_text="Whether error tracking signals were found in scanned files")


class RepositoryReadinessResponseSerializer(serializers.Serializer):
    repository = serializers.CharField(help_text="Normalized repository identifier")
    classification = serializers.CharField(help_text="Repository classification")
    excluded = serializers.BooleanField(help_text="Whether the repository is excluded from readiness checks")
    coreSuggestions = CapabilityStateSerializer(help_text="Tracking capability state")
    replayInsights = CapabilityStateSerializer(help_text="Computer vision capability state")
    errorInsights = CapabilityStateSerializer(help_text="Error tracking capability state")
    overall = serializers.CharField(help_text="Overall readiness state")
    evidenceTaskCount = serializers.IntegerField(help_text="Count of replay-derived evidence tasks")
    windowDays = serializers.IntegerField(help_text="Lookback window in days")
    generatedAt = serializers.CharField(help_text="ISO timestamp when the response was generated")
    cacheAgeSeconds = serializers.IntegerField(help_text="Age of cached response in seconds")
    scan = ScanEvidenceSerializer(required=False, help_text="Scan evidence details")


class ConnectionTokenResponseSerializer(serializers.Serializer):
    """Response containing a JWT token for direct sandbox connection"""

    token = serializers.CharField(help_text="JWT token for authenticating with the sandbox")


class TaskRunCreateRequestSerializer(serializers.Serializer):
    """Request body for creating a new task run"""

    mode = serializers.ChoiceField(
        choices=["interactive", "background"],
        required=False,
        default="background",
        help_text="Execution mode: 'interactive' for user-connected runs, 'background' for autonomous runs",
    )
    branch = serializers.CharField(
        required=False,
        allow_null=True,
        default=None,
        max_length=255,
        help_text="Git branch to checkout in the sandbox",
    )
    resume_from_run_id = serializers.UUIDField(
        required=False,
        default=None,
        help_text="ID of a previous run to resume from. Must belong to the same task.",
    )
    pending_user_message = serializers.CharField(
        required=False,
        default=None,
        allow_blank=False,
        help_text="Follow-up user message to include in the resumed run's prompt.",
    )
    sandbox_environment_id = serializers.UUIDField(
        required=False,
        default=None,
        help_text="Optional sandbox environment to apply for this cloud run.",
    )


class TaskRunCommandRequestSerializer(serializers.Serializer):
    """JSON-RPC request to send a command to the agent server in the sandbox."""

    ALLOWED_METHODS = [
        "user_message",
        "cancel",
        "close",
    ]

    jsonrpc = serializers.ChoiceField(
        choices=["2.0"],
        help_text="JSON-RPC version, must be '2.0'",
    )
    method = serializers.ChoiceField(
        choices=ALLOWED_METHODS,
        help_text="Command method to execute on the agent server",
    )
    params = serializers.DictField(
        required=False,
        default=dict,
        help_text="Parameters for the command",
    )
    id = serializers.JSONField(
        required=False,
        default=None,
        help_text="Optional JSON-RPC request ID (string or number)",
    )

    def validate_id(self, value):
        if value is not None and not isinstance(value, (str, int, float)):
            raise serializers.ValidationError("id must be a string or number")
        return value

    def validate(self, attrs):
        method = attrs["method"]
        params = attrs.get("params", {})
        if method == "user_message":
            content = params.get("content")
            if not content or not isinstance(content, str) or not content.strip():
                raise serializers.ValidationError({"params": "content is required and must be a non-empty string"})
        return attrs


class TaskRunCommandResponseSerializer(serializers.Serializer):
    """Response from the agent server command endpoint."""

    jsonrpc = serializers.CharField(help_text="JSON-RPC version")
    id = serializers.JSONField(required=False, default=None, help_text="Request ID echoed back (string or number)")
    result = serializers.DictField(required=False, help_text="Command result on success")
    error = serializers.DictField(required=False, help_text="Error details on failure")


class CodeInviteRedeemRequestSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)


class TaskRunSessionLogsQuerySerializer(serializers.Serializer):
    """Query parameters for filtering task run log events"""

    after = serializers.DateTimeField(
        required=False,
        help_text="Only return events after this ISO8601 timestamp",
    )
    event_types = serializers.CharField(
        required=False,
        help_text="Comma-separated list of event types to include",
    )
    exclude_types = serializers.CharField(
        required=False,
        help_text="Comma-separated list of event types to exclude",
    )
    limit = serializers.IntegerField(
        required=False,
        default=1000,
        min_value=1,
        max_value=5000,
        help_text="Maximum number of entries to return (default 1000, max 5000)",
    )


class SandboxEnvironmentSerializer(serializers.ModelSerializer):
    created_by = UserBasicSerializer(read_only=True)
    effective_domains = serializers.SerializerMethodField(
        help_text="Computed domain allowlist based on network_access_level and allowed_domains"
    )
    environment_variables = serializers.JSONField(
        write_only=True,
        required=False,
        default=dict,
        help_text="Encrypted environment variables (write-only, never returned in responses)",
    )
    has_environment_variables = serializers.SerializerMethodField(
        help_text="Whether this environment has any environment variables set"
    )

    class Meta:
        model = SandboxEnvironment
        fields = [
            "id",
            "name",
            "network_access_level",
            "allowed_domains",
            "include_default_domains",
            "repositories",
            "environment_variables",
            "has_environment_variables",
            "private",
            "effective_domains",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_at",
            "updated_at",
            "effective_domains",
            "has_environment_variables",
        ]

    def get_effective_domains(self, obj: SandboxEnvironment) -> list[str]:
        return obj.get_effective_domains()

    def get_has_environment_variables(self, obj: SandboxEnvironment) -> bool:
        return bool(obj.environment_variables)

    def validate_environment_variables(self, value):
        if value:
            for key in value:
                if not SandboxEnvironment.is_valid_env_var_key(key):
                    raise serializers.ValidationError(
                        f"Invalid environment variable key: {key!r}. Must match [A-Za-z_][A-Za-z0-9_]*"
                    )
        return value

    def create(self, validated_data):
        validated_data["team"] = self.context["team"]
        if "request" in self.context and hasattr(self.context["request"], "user"):
            validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class SandboxEnvironmentListSerializer(serializers.ModelSerializer):
    created_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = SandboxEnvironment
        fields = [
            "id",
            "name",
            "network_access_level",
            "allowed_domains",
            "repositories",
            "private",
            "created_by",
            "created_at",
            "updated_at",
        ]
