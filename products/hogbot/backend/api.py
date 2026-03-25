"""
Hogbot API viewsets.

Serves admin agent logs, sandbox filesystem access, and message ingestion.
All data currently comes from stub/mock responses — the sandbox and S3
integration will be wired in by the Temporal workflow work.
"""

import json
from typing import Any

from django.http import HttpResponse

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.permissions import APIScopePermission

# ---------------------------------------------------------------------------
# Stub data — will be replaced by S3 reads / sandbox filesystem access
# ---------------------------------------------------------------------------

STUB_ADMIN_LOGS = "\n".join(
    [
        json.dumps(
            {
                "type": "notification",
                "timestamp": "2026-03-25T10:00:00Z",
                "notification": {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {
                                "type": "text",
                                "text": "Hello! I'm Hogbot, your AI research assistant. I can help you investigate your product data, run analyses, and proactively surface insights. What would you like me to look into?",
                            },
                        }
                    },
                },
            }
        ),
        json.dumps(
            {
                "type": "notification",
                "timestamp": "2026-03-25T10:01:00Z",
                "notification": {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {
                                "type": "text",
                                "text": "Can you analyze our funnel conversion rates for the last 30 days?",
                            },
                        }
                    },
                },
            }
        ),
        json.dumps(
            {
                "type": "notification",
                "timestamp": "2026-03-25T10:01:05Z",
                "notification": {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call",
                            "toolCallId": "tc-1",
                            "title": "posthog_query_funnel",
                            "status": "completed",
                            "rawInput": {"date_from": "-30d", "events": ["$pageview", "$signup"]},
                            "rawOutput": {"conversion_rate": 0.42},
                            "_meta": {"claudeCode": {"toolName": "posthog_query_funnel"}},
                        }
                    },
                },
            }
        ),
        json.dumps(
            {
                "type": "notification",
                "timestamp": "2026-03-25T10:01:10Z",
                "notification": {
                    "jsonrpc": "2.0",
                    "method": "_posthog/console",
                    "params": {"level": "info", "message": "Funnel query completed. Analyzing conversion rates."},
                },
            }
        ),
        json.dumps(
            {
                "type": "notification",
                "timestamp": "2026-03-25T10:01:30Z",
                "notification": {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {
                                "type": "text",
                                "text": "I've analyzed your funnel conversion rates.\n\nYour signup-to-activation funnel has a **42% conversion rate** over the last 30 days, which is up 3% from the previous period.\n\nKey findings:\n- Step 1 → Step 2 (Sign up → Onboarding): 78% conversion\n- Step 2 → Step 3 (Onboarding → First event): 54% conversion\n- The biggest drop-off is between onboarding completion and sending the first event",
                            },
                        }
                    },
                },
            }
        ),
    ]
)

STUB_SANDBOX_FILES = [
    {
        "path": "/research/mobile-retention-drop.md",
        "filename": "mobile-retention-drop.md",
        "size": 1240,
        "modified_at": "2026-03-25T10:30:00Z",
    },
    {
        "path": "/research/funnel-conversion-analysis.md",
        "filename": "funnel-conversion-analysis.md",
        "size": 890,
        "modified_at": "2026-03-25T10:01:30Z",
    },
    {
        "path": "/research/weekly-insights-summary.md",
        "filename": "weekly-insights-summary.md",
        "size": 720,
        "modified_at": "2026-03-24T08:00:00Z",
    },
]

STUB_FILE_CONTENTS: dict[str, str] = {
    "/research/mobile-retention-drop.md": "# Mobile retention drop investigation\n\n## Summary\n\n7-day retention for mobile users dropped from 32% to 19% in the week of March 17-23, 2026.\n\n## Root cause analysis\n\n### Timeline\n- **March 16**: Mobile SDK v2.4.1 released\n- **March 17**: Retention begins declining\n- **March 19**: First user reports of \"blank screen after onboarding\"\n\n### Key findings\n\n1. **SDK update correlation**: The drop coincides exactly with the v2.4.1 SDK release\n2. **Affected flow**: The onboarding completion event fires, but the subsequent `app_home_viewed` event is missing for 61% of mobile users\n3. **Platform breakdown**: iOS affected (23% → 11% retention), Android less impacted (38% → 29%)\n\n## Recommendations\n\n- Roll back mobile SDK to v2.4.0 or hotfix the onboarding navigation bug\n- Add monitoring alert for onboarding completion → home view drop-off rate\n- Consider a re-engagement campaign for affected users",
    "/research/funnel-conversion-analysis.md": "# Funnel conversion rate analysis - March 2026\n\n## Overview\n\nAnalysis of the primary signup-to-activation funnel for the 30-day period ending March 25, 2026.\n\n## Metrics\n\n| Step | Conversion | Change vs. prior period |\n|------|-----------|------------------------|\n| Sign up → Onboarding | 78% | +2% |\n| Onboarding → First event | 54% | -1% |\n| First event → Retained (7d) | 42% | +3% |\n\n## Observations\n\n- Overall funnel health is improving, driven by better sign-up-to-onboarding conversion\n- The onboarding → first event step remains the weakest link\n- Users who complete onboarding within 5 minutes have 2.3x higher retention",
    "/research/weekly-insights-summary.md": "# Weekly insights summary\n\n## Week of March 17-23, 2026\n\n### Highlights\n\n- **Active users**: 12,450 (+5% WoW)\n- **New signups**: 1,230 (+8% WoW)\n- **Feature adoption**: Dashboard sharing feature used by 34% of teams (up from 28%)\n\n### Anomalies detected\n\n1. Mobile retention drop (see dedicated research document)\n2. Unusual spike in API errors on March 20 (resolved — was a dependency timeout)\n3. Feature flag evaluation latency increased 15ms on average\n\n### Recommendations\n\n- Prioritize mobile SDK fix\n- Review API dependency timeout settings\n- Investigate feature flag evaluation performance",
}

# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(help_text="Message text to send to the admin agent.")


class SandboxFileSerializer(serializers.Serializer):
    path = serializers.CharField(help_text="Full path on the sandbox filesystem.")
    filename = serializers.CharField(help_text="Basename of the file.")
    size = serializers.IntegerField(help_text="File size in bytes.")
    modified_at = serializers.DateTimeField(help_text="Last modification time.")


class SandboxFileListSerializer(serializers.Serializer):
    results = SandboxFileSerializer(many=True)


# ---------------------------------------------------------------------------
# ViewSets
# ---------------------------------------------------------------------------


@extend_schema(tags=["hogbot"])
class HogbotViewSet(TeamAndOrgViewSetMixin, viewsets.GenericViewSet):
    """
    Hogbot agent endpoints — admin agent logs, messages, and sandbox file access.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, APIScopePermission]
    scope_object = "INTERNAL"

    # ── Admin agent logs (GET /api/projects/:team_id/hogbot/admin/logs/) ──

    @extend_schema(
        responses={200: OpenApiResponse(description="JSONL log content for the admin agent")},
        summary="Get admin agent logs",
        description="Returns JSONL formatted log entries for the admin agent. Polled by the frontend every 2 seconds.",
    )
    @action(detail=False, methods=["get"], url_path="admin/logs")
    def admin_logs(self, request: Request, **kwargs: Any) -> HttpResponse:
        # TODO: Replace stub with S3 read when sandbox is wired up
        # from posthog.storage import object_storage
        # team_id = self.team_id
        # log_content = object_storage.read(f"hogbot/{team_id}/admin.jsonl", missing_ok=True) or ""
        log_content = STUB_ADMIN_LOGS

        response = HttpResponse(log_content, content_type="application/jsonl")
        response["Cache-Control"] = "no-cache"
        return response

    # ── Send message (POST /api/projects/:team_id/hogbot/admin/messages/) ──

    @extend_schema(
        request=SendMessageSerializer,
        responses={202: OpenApiResponse(description="Message accepted")},
        summary="Send message to admin agent",
        description="Sends a user message to the admin agent. The agent response will appear in subsequent log polls.",
    )
    @action(detail=False, methods=["post"], url_path="admin/messages")
    def admin_messages(self, request: Request, **kwargs: Any) -> Response:
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # TODO: Forward message to the sandbox admin agent
        # content = serializer.validated_data["content"]
        # sandbox.send_message(team_id=self.team_id, content=content)

        return Response(status=status.HTTP_202_ACCEPTED)

    # ── List sandbox files (GET /api/projects/:team_id/hogbot/files/) ──

    @extend_schema(
        responses={200: SandboxFileListSerializer},
        summary="List sandbox files",
        description="Lists files on the sandbox filesystem. Accepts an optional `glob` query parameter.",
    )
    @action(detail=False, methods=["get"], url_path="files")
    def files_list(self, request: Request, **kwargs: Any) -> Response:
        # TODO: Replace stub with sandbox filesystem listing
        # glob_pattern = request.query_params.get("glob", "*")
        # files = sandbox.list_files(team_id=self.team_id, glob=glob_pattern)
        files = STUB_SANDBOX_FILES

        return Response({"results": files})

    # ── Read sandbox file (GET /api/projects/:team_id/hogbot/files/read/) ──

    @extend_schema(
        responses={
            200: OpenApiResponse(description="File content as plain text"),
            400: OpenApiResponse(description="Missing path parameter"),
            404: OpenApiResponse(description="File not found"),
        },
        summary="Read sandbox file",
        description="Reads a single file from the sandbox filesystem. Requires a `path` query parameter.",
    )
    @action(detail=False, methods=["get"], url_path="files/read")
    def files_read(self, request: Request, **kwargs: Any) -> HttpResponse:
        file_path = request.query_params.get("path")
        if not file_path:
            return HttpResponse("Missing `path` query parameter", status=400, content_type="text/plain")

        # TODO: Replace stub with sandbox filesystem read
        # content = sandbox.read_file(team_id=self.team_id, path=file_path)
        content = STUB_FILE_CONTENTS.get(file_path)

        if content is None:
            return HttpResponse("File not found", status=404, content_type="text/plain")

        return HttpResponse(content, content_type="text/plain; charset=utf-8")
