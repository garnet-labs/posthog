from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from temporalio import activity

from posthog.temporal.common.utils import asyncify

from products.tasks.backend.services.sandbox import Sandbox
from products.tasks.backend.temporal.observability import log_activity_execution


@dataclass
class CheckHogbotServerAliveInput:
    sandbox_id: str


@activity.defn(name="hogbot_check_server_alive")
@asyncify
def check_hogbot_server_alive(input: CheckHogbotServerAliveInput) -> bool:
    """Hit the sandbox server's health endpoint. Returns True if alive, False if down."""
    with log_activity_execution(
        "check_hogbot_server_alive",
        sandbox_id=input.sandbox_id,
    ):
        sandbox = Sandbox.get_by_id(input.sandbox_id)

        if not sandbox.is_running():
            return False

        provider = getattr(settings, "SANDBOX_PROVIDER", None)
        port = 47821 if provider == "docker" else 8080

        try:
            result = sandbox.execute(
                f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/health",
                timeout_seconds=10,
            )
            return result.exit_code == 0 and result.stdout.strip() == "200"
        except Exception:
            return False
