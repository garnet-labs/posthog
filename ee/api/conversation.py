import os
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse, StreamingHttpResponse

import httpx
import pydantic
import structlog
from asgiref.sync import async_to_sync as asgi_async_to_sync
from drf_spectacular.utils import OpenApiResponse, extend_schema
from elevenlabs import ElevenLabs
from elevenlabs.types.voice_settings import VoiceSettings
from loginas.utils import is_impersonated_session
from prometheus_client import Histogram
from rest_framework import exceptions, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import Throttled
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from posthog.schema import AgentMode, AssistantMessage, HumanMessage, MaxBillingContext

from posthog.api.mixins import ValidatedRequest, validated_request
from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.exceptions import Conflict, QuotaLimitExceeded
from posthog.exceptions_capture import capture_exception
from posthog.models.user import User
from posthog.rate_limit import (
    AIBurstRateThrottle,
    AIResearchBurstRateThrottle,
    AIResearchSustainedRateThrottle,
    AISustainedRateThrottle,
    is_team_exempt_from_ai_rate_limit,
)
from posthog.temporal.ai.chat_agent import (
    CHAT_AGENT_STREAM_MAX_LENGTH,
    CHAT_AGENT_WORKFLOW_TIMEOUT,
    ChatAgentWorkflow,
    ChatAgentWorkflowInputs,
)
from posthog.temporal.ai.research_agent import (
    RESEARCH_AGENT_STREAM_MAX_LENGTH,
    RESEARCH_AGENT_WORKFLOW_TIMEOUT,
    ResearchAgentWorkflow,
    ResearchAgentWorkflowInputs,
)

from ee.billing.quota_limiting import QuotaLimitingCaches, QuotaResource, is_team_limited
from ee.hogai.api.serializers import ConversationSerializer
from ee.hogai.chat_agent import AssistantGraph
from ee.hogai.core.executor import AgentExecutor
from ee.hogai.queue import ConversationQueueMessage, ConversationQueueStore, QueueFullError, build_queue_message
from ee.hogai.sandbox.executor import handle_sandbox_message
from ee.hogai.stream.redis_stream import get_conversation_stream_key
from ee.hogai.utils.aio import async_to_sync
from ee.hogai.utils.sse import AssistantSSESerializer
from ee.hogai.utils.tts_text import prepare_text_for_elevenlabs_tts
from ee.hogai.utils.types import PartialAssistantState
from ee.hogai.utils.voice_speculative_ack import generate_speculative_ack
from ee.hogai.utils.voice_tool_narration import generate_tool_call_narration_sentence
from ee.hogai.utils.voice_wait_fill_tts import generate_wait_fill_tts_lines
from ee.models.assistant import Conversation

logger = structlog.get_logger(__name__)
elevenlabs_client = ElevenLabs()

RESEARCH_RATE_LIMIT_MESSAGE = (
    "You've reached the usage limit for Research mode, which is currently in beta "
    "with limited capacity. Please try again {retry_after}, or switch to a regular "
    "conversation for continued access."
)

STREAM_ITERATION_LATENCY_HISTOGRAM = Histogram(
    "posthog_ai_stream_iteration_latency_seconds",
    "Time between iterations in the async stream loop",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")],
)


class MessageMinimalSerializer(serializers.Serializer):
    """Serializer for appending a message to an existing conversation without triggering AI processing."""

    content = serializers.CharField(required=True, max_length=10000)


class MessageSerializer(MessageMinimalSerializer):
    content = serializers.CharField(
        required=True,
        allow_null=True,  # Null content means we're resuming streaming or continuing previous generation
        max_length=40000,  # Roughly 10k tokens
    )
    conversation = serializers.UUIDField(
        required=True
    )  # this either retrieves an existing conversation or creates a new one
    contextual_tools = serializers.DictField(required=False, child=serializers.JSONField())
    ui_context = serializers.JSONField(required=False)
    billing_context = serializers.JSONField(required=False)
    trace_id = serializers.UUIDField(required=True)
    session_id = serializers.CharField(required=False)
    agent_mode = serializers.ChoiceField(required=False, choices=[mode.value for mode in AgentMode])
    is_sandbox = serializers.BooleanField(required=False, default=False)
    resume_payload = serializers.JSONField(required=False, allow_null=True)

    def validate(self, attrs):
        data = attrs
        if data["content"] is not None:
            try:
                message = HumanMessage.model_validate(
                    {
                        "content": data["content"],
                        "ui_context": data.get("ui_context"),
                        "trace_id": str(data["trace_id"]) if data.get("trace_id") else None,
                    }
                )
            except pydantic.ValidationError:
                if settings.DEBUG:
                    raise
                raise serializers.ValidationError("Invalid message content.")
            data["message"] = message
        else:
            # NOTE: If content is empty, it means we're resuming streaming or continuing generation with only the contextual_tools potentially different
            # Because we intentionally don't add a HumanMessage, we are NOT updating ui_context here
            data["message"] = None
        billing_context = data.get("billing_context")
        if billing_context:
            try:
                billing_context = MaxBillingContext.model_validate(billing_context)
                data["billing_context"] = billing_context
            except pydantic.ValidationError as e:
                capture_exception(e)
                # billing data relies on a lot of legacy code, this might break and we don't want to block the conversation
                data["billing_context"] = None
        if agent_mode := data.get("agent_mode"):
            try:
                data["agent_mode"] = AgentMode(agent_mode)
            except ValueError:
                raise serializers.ValidationError("Invalid agent mode.")
        return data


class QueueMessageSerializer(serializers.Serializer):
    content = serializers.CharField(required=True, allow_blank=False, max_length=40000)
    contextual_tools = serializers.DictField(required=False, child=serializers.JSONField())
    ui_context = serializers.JSONField(required=False)
    billing_context = serializers.JSONField(required=False)
    agent_mode = serializers.ChoiceField(required=False, choices=[mode.value for mode in AgentMode])

    def validate(self, attrs):
        data = attrs
        try:
            HumanMessage.model_validate(
                {
                    "content": data["content"],
                    "ui_context": data.get("ui_context"),
                }
            )
        except pydantic.ValidationError:
            raise serializers.ValidationError("Invalid message content.")

        billing_context = data.get("billing_context")
        if billing_context:
            try:
                parsed_context = MaxBillingContext.model_validate(billing_context)
                data["billing_context"] = parsed_context.model_dump()
            except pydantic.ValidationError as e:
                capture_exception(e)
                data["billing_context"] = None

        if agent_mode := data.get("agent_mode"):
            try:
                data["agent_mode"] = AgentMode(agent_mode).value
            except ValueError:
                raise serializers.ValidationError("Invalid agent mode.")

        return data


class QueueMessageUpdateSerializer(serializers.Serializer):
    content = serializers.CharField(required=True, allow_blank=False, max_length=40000)


class ToolCallNarrationRequestSerializer(serializers.Serializer):
    tool_names = serializers.ListField(
        child=serializers.CharField(max_length=128),
        min_length=1,
        max_length=32,
        help_text="Tool identifiers being invoked (snake_case names)",
    )
    assistant_content = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=8000,
        help_text="Assistant message text before the tool call, if any",
    )
    tool_args_by_name = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text="Map of tool name to arguments object (truncated server-side)",
    )
    ui_payload = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text="Contextual ui_payload for contextual tools, if any",
    )
    recent_narrations = serializers.ListField(
        child=serializers.CharField(max_length=500),
        required=False,
        max_length=12,
        help_text="Recent spoken narration lines to avoid repeating phrasing",
    )


class ToolCallNarrationResponseSerializer(serializers.Serializer):
    sentence = serializers.CharField(help_text="Single spoken line for text-to-speech")


class WaitFillTtsRequestSerializer(serializers.Serializer):
    tweets = serializers.ListField(
        child=serializers.CharField(max_length=2000),
        min_length=1,
        max_length=5,
        help_text="Tweet bodies (verbatim) to wrap with spoken transitions for wait-fill TTS",
    )


class WaitFillTtsResponseSerializer(serializers.Serializer):
    lines = serializers.ListField(
        child=serializers.CharField(max_length=2000),
        help_text="Full spoken line per tweet, in the same order as tweets",
    )


class SpeculativeAckRequestSerializer(serializers.Serializer):
    prompt = serializers.CharField(
        max_length=2000,
        help_text="The user's message to generate a contextual acknowledgment for",
    )


class SpeculativeAckResponseSerializer(serializers.Serializer):
    text = serializers.CharField(help_text="Short contextual acknowledgment for TTS")


@extend_schema(tags=["max"])
class ConversationViewSet(TeamAndOrgViewSetMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):
    scope_object = "conversation"
    scope_object_write_actions = [
        "create",
        "update",
        "partial_update",
        "patch",
        "destroy",
        "stt_token",
        "transcribe",
        "tts",
        "tool_call_narration",
        "wait_fill_tts",
        "append_message",
    ]
    scope_object_read_actions = ["list", "retrieve", "queue"]
    serializer_class = ConversationSerializer
    queryset = Conversation.objects.all()
    lookup_url_kwarg = "conversation"

    def _queue_conversation_id(self) -> str:
        if not self.lookup_url_kwarg:
            raise exceptions.ValidationError("Conversation not provided")
        conversation_id = self.kwargs.get(self.lookup_url_kwarg)
        if not conversation_id:
            raise exceptions.ValidationError("Conversation not provided")
        return str(conversation_id)

    def _ensure_queue_access(self, request: Request, conversation_id: str) -> Response | None:
        try:
            # nosemgrep: idor-lookup-without-team (instance scoped to team via get_queryset)
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversation not found"}, status=status.HTTP_404_NOT_FOUND)
        if conversation.user != request.user or conversation.team != self.team:
            return Response({"error": "Cannot access other users' conversations"}, status=status.HTTP_403_FORBIDDEN)
        return None

    def _queue_response(self, queue_store: ConversationQueueStore, queue: list[ConversationQueueMessage]) -> Response:
        return Response({"messages": queue, "max_queue_messages": queue_store.max_messages})

    def safely_get_queryset(self, queryset):
        # Only single retrieval of a specific conversation is allowed for other users' conversations (if ID known)
        if self.action != "retrieve":
            queryset = queryset.filter(user=self.request.user)
        # For listing or single retrieval, conversations must be from the assistant and have a title
        if self.action in ("list", "retrieve"):
            queryset = queryset.filter(
                title__isnull=False,
                type__in=[Conversation.Type.DEEP_RESEARCH, Conversation.Type.ASSISTANT, Conversation.Type.SLACK],
            )
            # Hide internal conversations from customers, but show them to support agents during impersonation
            if not is_impersonated_session(self.request):
                queryset = queryset.filter(is_internal=False)
            queryset = queryset.order_by("-updated_at")
        return queryset

    def get_throttles(self):
        # For create action, throttling is handled in check_throttles() for conditional logic
        if self.action == "create":
            return []
        return super().get_throttles()

    def _is_research_request(self, request: Request) -> bool:
        """Check if the request is for a research conversation."""
        # Check if it's a new conversation with research mode
        agent_mode = request.data.get("agent_mode")
        if agent_mode == AgentMode.RESEARCH or agent_mode == AgentMode.RESEARCH.value:
            return True

        # Check if it's an existing deep research conversation
        conversation_id = request.data.get("conversation")
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, team=self.team)
                if conversation.type == Conversation.Type.DEEP_RESEARCH:
                    return True
            except (Conversation.DoesNotExist, ValidationError):
                # DoesNotExist or ValidationError (invalid UUID) - not a research conversation
                pass

        return False

    def check_throttles(self, request: Request):
        # Only apply custom throttling for create action
        if self.action != "create":
            return super().check_throttles(request)

        # Skip throttling in local development
        if settings.DEBUG:
            return

        # Determine which throttles to apply based on request type
        is_research = self._is_research_request(request)

        if is_research:
            if is_team_exempt_from_ai_rate_limit(self.team_id):
                return
            throttles = [AIResearchBurstRateThrottle(), AIResearchSustainedRateThrottle()]
        else:
            # Skip throttling for paying customers
            if self.organization.customer_id:
                return
            throttles = [AIBurstRateThrottle(), AISustainedRateThrottle()]

        for throttle in throttles:
            if not throttle.allow_request(request, self):
                wait = throttle.wait()
                if wait is not None:
                    if wait < 60:
                        retry_after = f"in {int(wait)} seconds"
                    elif wait < 3600:
                        retry_after = f"in {int(wait / 60)} minutes"
                    else:
                        retry_after = "later today"
                else:
                    retry_after = "later"

                if is_research:
                    detail = RESEARCH_RATE_LIMIT_MESSAGE.format(retry_after=retry_after)
                else:
                    detail = f"You've reached PostHog AI's usage limit for the moment. Please try again {retry_after}."

                raise Throttled(wait=wait, detail=detail)

    def get_serializer_class(self):
        if self.action == "create":
            return MessageSerializer
        if self.action == "append_message":
            return MessageMinimalSerializer
        return super().get_serializer_class()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["team"] = self.team
        context["user"] = cast(User, self.request.user)
        return context

    def create(self, request: Request, *args, **kwargs):
        """
        Unified endpoint that handles both conversation creation and streaming.

        - If message is provided: Start new conversation processing
        - If no message: Stream from existing conversation
        """

        if is_team_limited(self.team.api_token, QuotaResource.AI_CREDITS, QuotaLimitingCaches.QUOTA_LIMITER_CACHE_KEY):
            raise QuotaLimitExceeded(
                "Your organization reached its AI credit usage limit. Increase the limits in Billing settings, or ask an org admin to do so."
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation_id = serializer.validated_data["conversation"]

        has_message = serializer.validated_data.get("content") is not None
        is_research = serializer.validated_data.get("agent_mode") == AgentMode.RESEARCH

        is_new_conversation = False
        # Safely set the lookup kwarg for potential error handling
        if self.lookup_url_kwarg:
            self.kwargs[self.lookup_url_kwarg] = conversation_id
        try:
            # nosemgrep: idor-lookup-without-team, idor-taint-user-input-to-model-get (user+team check immediately after)
            conversation = Conversation.objects.get(id=conversation_id)
            if conversation.user != request.user or conversation.team != self.team:
                return Response(
                    {"error": "Cannot access other users' conversations"}, status=status.HTTP_400_BAD_REQUEST
                )
        except Conversation.DoesNotExist:
            # Conversation doesn't exist, create it if we have a message
            if not has_message:
                return Response(
                    {"error": "Cannot stream from non-existent conversation"}, status=status.HTTP_400_BAD_REQUEST
                )
            # Use frontend-provided conversation ID
            # Mark conversation as internal if created during an impersonated session (support agents)
            is_impersonated = is_impersonated_session(request)
            conversation_type = Conversation.Type.DEEP_RESEARCH if is_research else Conversation.Type.ASSISTANT
            conversation = Conversation.objects.create(
                user=cast(User, request.user),
                team=self.team,
                id=conversation_id,
                type=conversation_type,
                is_internal=is_impersonated,
            )
            is_new_conversation = True

        is_idle = conversation.status == Conversation.Status.IDLE
        has_message = serializer.validated_data.get("message") is not None
        has_resume_payload = serializer.validated_data.get("resume_payload") is not None
        is_sandbox = (
            serializer.validated_data.get("is_sandbox", False)
            or serializer.validated_data.get("agent_mode") == AgentMode.SANDBOX
        )

        if conversation.type == Conversation.Type.DEEP_RESEARCH:
            if not is_new_conversation and is_idle and has_message and not has_resume_payload:
                conversation.type = Conversation.Type.ASSISTANT
                conversation.save(update_fields=["type", "updated_at"])
                is_research = False
            else:
                is_research = True

        if has_message and not is_idle and not is_sandbox:
            raise Conflict("Cannot resume streaming with a new message")
        # If the frontend is trying to resume streaming for a finished conversation, return a conflict error
        if not has_message and conversation.status == Conversation.Status.IDLE and not has_resume_payload:
            raise exceptions.ValidationError("Cannot continue streaming from an idle conversation")

        is_impersonated = is_impersonated_session(request)

        if is_sandbox and has_message:
            return handle_sandbox_message(
                conversation=conversation,
                conversation_id=str(conversation_id),
                content=serializer.validated_data["content"],
                user=cast(User, request.user),
                team=self.team,
                is_new_conversation=is_new_conversation,
            )

        workflow_inputs: ChatAgentWorkflowInputs | ResearchAgentWorkflowInputs
        workflow_class: type[ChatAgentWorkflow] | type[ResearchAgentWorkflow]
        if is_research:
            workflow_inputs = ResearchAgentWorkflowInputs(
                team_id=self.team_id,
                user_id=cast(User, request.user).pk,  # Use pk instead of id for User model
                conversation_id=conversation.id,
                stream_key=get_conversation_stream_key(conversation.id),
                message=serializer.validated_data["message"].model_dump() if has_message else None,
                is_new_conversation=is_new_conversation,
                trace_id=serializer.validated_data["trace_id"],
                session_id=request.headers.get("X-POSTHOG-SESSION-ID"),  # Relies on posthog-js __add_tracing_headers
                billing_context=serializer.validated_data.get("billing_context"),
                is_agent_billable=False,
                is_impersonated=is_impersonated,
                resume_payload=serializer.validated_data.get("resume_payload"),
            )
            workflow_class = ResearchAgentWorkflow
            timeout = RESEARCH_AGENT_WORKFLOW_TIMEOUT
            max_length = RESEARCH_AGENT_STREAM_MAX_LENGTH
        else:
            is_agent_billable = not is_impersonated
            workflow_inputs = ChatAgentWorkflowInputs(
                team_id=self.team_id,
                user_id=cast(User, request.user).pk,  # Use pk instead of id for User model
                conversation_id=conversation.id,
                stream_key=get_conversation_stream_key(conversation.id),
                message=serializer.validated_data["message"].model_dump() if has_message else None,
                contextual_tools=serializer.validated_data.get("contextual_tools"),
                is_new_conversation=is_new_conversation,
                trace_id=serializer.validated_data["trace_id"],
                session_id=request.headers.get("X-POSTHOG-SESSION-ID"),  # Relies on posthog-js __add_tracing_headers
                billing_context=serializer.validated_data.get("billing_context"),
                agent_mode=serializer.validated_data.get("agent_mode"),
                use_checkpointer=True,
                is_agent_billable=is_agent_billable,
                is_impersonated=is_impersonated,
                resume_payload=serializer.validated_data.get("resume_payload"),
            )
            workflow_class = ChatAgentWorkflow
            timeout = CHAT_AGENT_WORKFLOW_TIMEOUT
            max_length = CHAT_AGENT_STREAM_MAX_LENGTH

        async def async_stream(
            workflow_inputs: ChatAgentWorkflowInputs | ResearchAgentWorkflowInputs,
        ) -> AsyncGenerator[bytes, None]:
            serializer = AssistantSSESerializer()
            stream_manager = AgentExecutor(conversation, timeout=timeout, max_length=max_length)
            last_iteration_time = time.time()
            async for chunk in stream_manager.astream(workflow_class, workflow_inputs):
                chunk_received_time = time.time()
                STREAM_ITERATION_LATENCY_HISTOGRAM.observe(chunk_received_time - last_iteration_time)
                last_iteration_time = chunk_received_time

                event = await serializer.dumps(chunk)
                yield event.encode("utf-8")

        return StreamingHttpResponse(
            (
                async_stream(workflow_inputs)
                if settings.SERVER_GATEWAY_INTERFACE == "ASGI"
                else async_to_sync(lambda: async_stream(workflow_inputs))
            ),
            content_type="text/event-stream",
        )

    @action(detail=True, methods=["GET", "POST"], url_path="queue")
    def queue(self, request: Request, *args, **kwargs):
        conversation_id = self._queue_conversation_id()
        error_response = self._ensure_queue_access(request, conversation_id)
        if error_response:
            return error_response

        queue_store = ConversationQueueStore(conversation_id)

        if request.method == "GET":
            return self._queue_response(queue_store, queue_store.list())

        serializer = QueueMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = build_queue_message(
            content=serializer.validated_data["content"],
            contextual_tools=serializer.validated_data.get("contextual_tools"),
            ui_context=serializer.validated_data.get("ui_context"),
            billing_context=serializer.validated_data.get("billing_context"),
            agent_mode=serializer.validated_data.get("agent_mode"),
            session_id=request.headers.get("X-POSTHOG-SESSION-ID"),
        )

        try:
            queue = queue_store.enqueue(message)
        except QueueFullError:
            return Response(
                {
                    "error": "queue_full",
                    "detail": "Only two messages can be queued at a time.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        return self._queue_response(queue_store, queue)

    @action(detail=True, methods=["PATCH", "DELETE"], url_path=r"queue/(?P<queue_id>[^/.]+)")
    def queue_item(self, request: Request, queue_id: str, *args, **kwargs):
        conversation_id = self._queue_conversation_id()
        error_response = self._ensure_queue_access(request, conversation_id)
        if error_response:
            return error_response

        queue_store = ConversationQueueStore(conversation_id)
        queue = queue_store.list()
        queue_index = next((index for index, item in enumerate(queue) if item.get("id") == queue_id), None)

        if queue_index is None:
            return Response({"detail": "Queue message not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "PATCH":
            serializer = QueueMessageUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            queue = queue_store.update(queue_id, serializer.validated_data["content"])
        else:
            queue = queue_store.delete(queue_id)

        return self._queue_response(queue_store, queue)

    @action(detail=True, methods=["POST"], url_path="queue/clear")
    def clear_queue(self, request: Request, *args, **kwargs):
        conversation_id = self._queue_conversation_id()
        error_response = self._ensure_queue_access(request, conversation_id)
        if error_response:
            return error_response
        queue_store = ConversationQueueStore(conversation_id)
        return self._queue_response(queue_store, queue_store.clear())

    @action(detail=True, methods=["PATCH"])
    def cancel(self, request: Request, *args, **kwargs):
        conversation = self.get_object()

        # IDLE is intentionally not short-circuited: during the handoff between the main
        # workflow completing and a queued workflow starting, the status is briefly IDLE
        # even though a queued Temporal workflow may be running.
        if conversation.status == Conversation.Status.CANCELING:
            return Response(status=status.HTTP_204_NO_CONTENT)

        async def cancel_workflow():
            agent_executor = AgentExecutor(conversation)
            await agent_executor.cancel_workflow()

        try:
            asgi_async_to_sync(cancel_workflow)()
        except Exception as e:
            logger.exception("Failed to cancel conversation", conversation_id=conversation.id, error=str(e))
            return Response({"error": "Failed to cancel conversation"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["POST"], url_path="append_message")
    def append_message(self, request: Request, *args, **kwargs):
        """
        Appends a message to an existing conversation without triggering AI processing.
        This is used for client-side generated messages that need to be persisted
        (e.g., support ticket confirmation messages).
        """
        conversation = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content = serializer.validated_data["content"]
        message = AssistantMessage(content=content, id=str(uuid.uuid4()))

        async def append_to_state():
            user = cast(User, request.user)
            graph = AssistantGraph(self.team, user).compile_full_graph()
            # Empty checkpoint_ns targets the root graph (not subgraphs)
            config = {"configurable": {"thread_id": str(conversation.id), "checkpoint_ns": ""}}
            await graph.aupdate_state(
                config,
                PartialAssistantState(messages=[message]),
            )

        try:
            asgi_async_to_sync(append_to_state)()
        except Exception as e:
            logger.exception("Failed to append message to conversation", conversation_id=conversation.id, error=str(e))
            return Response({"error": "Failed to append message"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response({"id": message.id}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["POST"])
    def stt_token(self, request: Request, *args, **kwargs):
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return Response({"error": "ElevenLabs API key not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            resp = httpx.post(
                "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe",
                headers={"xi-api-key": api_key},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("ElevenLabs token generation failed")
            return Response({"error": "Token generation failed"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"token": resp.json()["token"]})

    @action(detail=False, methods=["POST"], parser_classes=[MultiPartParser])
    def transcribe(self, request: Request, *args, **kwargs):
        audio = request.FILES.get("audio")
        if not audio:
            return Response({"error": "No audio file provided"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            transcript = elevenlabs_client.speech_to_text.convert(
                model_id="scribe_v2_realtime",
                file=audio,
                tag_audio_events=False,
            )
        except Exception:
            logger.exception("ElevenLabs STT failed")
            return Response({"error": "Transcription failed"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"text": transcript.text})

    @validated_request(
        request_serializer=ToolCallNarrationRequestSerializer,
        responses={200: OpenApiResponse(response=ToolCallNarrationResponseSerializer)},
        summary="Generate voice narration for tool calls",
        tags=["max"],
    )
    @action(detail=False, methods=["POST"])
    def tool_call_narration(self, request: Request, *args, **kwargs):
        """One short LLM line for voice mode when tools run (natural wording + brief why)."""
        vreq = cast(ValidatedRequest, request)
        data = vreq.validated_data
        user = cast(User, request.user)
        tool_args = data.get("tool_args_by_name")
        if tool_args is not None and not isinstance(tool_args, dict):
            return Response({"error": "tool_args_by_name must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        ui_pl = data.get("ui_payload")
        if ui_pl is not None and not isinstance(ui_pl, dict):
            return Response({"error": "ui_payload must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            sentence = generate_tool_call_narration_sentence(
                user=user,
                team=self.team,
                tool_names=list(data["tool_names"]),
                assistant_content=data.get("assistant_content"),
                tool_args_by_name=cast(dict[str, Any], tool_args) if tool_args else None,
                ui_payload=cast(dict[str, Any], ui_pl) if ui_pl else None,
                recent_narrations=list(data.get("recent_narrations") or []),
            )
        except Exception:
            logger.exception("tool_call_narration LLM failed")
            return Response({"error": "Narration generation failed"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"sentence": sentence})

    @validated_request(
        request_serializer=WaitFillTtsRequestSerializer,
        responses={200: OpenApiResponse(response=WaitFillTtsResponseSerializer)},
        summary="Generate wait-fill TTS lines (transitions around interstitial tweets)",
        tags=["max"],
    )
    @action(detail=False, methods=["POST"])
    def wait_fill_tts(self, request: Request, *args, **kwargs):
        """Short LLM lines for voice mode while tools run (natural transitions + verbatim tweet text)."""
        vreq = cast(ValidatedRequest, request)
        data = vreq.validated_data
        user = cast(User, request.user)
        tweets = [str(t).strip() for t in data["tweets"] if str(t).strip()]
        if not tweets:
            return Response({"error": "No tweets provided"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lines = generate_wait_fill_tts_lines(user=user, team=self.team, tweets=tweets)
        except Exception:
            logger.exception("wait_fill_tts LLM failed")
            return Response({"error": "Wait-fill line generation failed"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"lines": lines})

    @validated_request(
        request_serializer=SpeculativeAckRequestSerializer,
        responses={200: OpenApiResponse(response=SpeculativeAckResponseSerializer)},
        summary="Generate a fast contextual acknowledgment for voice mode",
        tags=["max"],
    )
    @action(detail=False, methods=["POST"])
    def speculative_ack(self, request: Request, *args, **kwargs):
        """Fast Haiku call to produce a contextual 'I understood you' line before the main agent responds."""
        vreq = cast(ValidatedRequest, request)
        data = vreq.validated_data
        user = cast(User, request.user)
        try:
            text = generate_speculative_ack(user=user, team=self.team, prompt=data["prompt"])
        except Exception:
            logger.exception("speculative_ack LLM failed")
            return Response({"error": "Acknowledgment generation failed"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"text": text})

    @action(detail=False, methods=["POST"])
    def tts(self, request: Request, *args, **kwargs):
        raw = request.data.get("text") or ""
        text = prepare_text_for_elevenlabs_tts(str(raw))[:5000]
        if not text:
            return Response({"error": "No text provided"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            audio = elevenlabs_client.text_to_speech.convert(
                voice_id="SNQH49XmxHOJ7Xc0YHNb",
                model_id="eleven_flash_v2_5",
                text=text,
                voice_settings=VoiceSettings(
                    stability=0.5,
                    similarity_boost=0.75,
                    style=0.0,
                    use_speaker_boost=True,
                    speed=1.0,
                ),
                # ElevenLabs built-in normalizer (numbers, dates, etc.) — complements our abbreviation expansion
                apply_text_normalization="on",
                # PCM s16le mono @ 44.1kHz — streamed to the client as raw bytes (see voiceLogic TTS_PCM_SAMPLE_RATE)
                # Requires a plan that includes 44.1kHz PCM; otherwise use e.g. pcm_24000 and match the frontend constant
                output_format="pcm_44100",
                optimize_streaming_latency=3,
            )
        except Exception:
            logger.exception("ElevenLabs TTS failed")
            return Response({"error": "Text-to-speech failed"}, status=status.HTTP_502_BAD_GATEWAY)
        # Raw s16le mono @ 44.1kHz (ElevenLabs pcm_44100) — client decodes with fixed layout
        response = HttpResponse(content_type="application/octet-stream")
        for chunk in audio:
            if chunk:
                response.write(chunk)
        return response
