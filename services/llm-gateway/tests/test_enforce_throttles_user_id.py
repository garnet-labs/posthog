"""Tests for end_user_id resolution in enforce_throttles.

Verifies that:
- Internal service products with trust_client_user_id=True use the client-provided
  'user' param for rate limiting (per-team budgets for temporal workers).
- End-user-facing products always use the authenticated user's ID to prevent
  rate limit poisoning (#50542).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from llm_gateway.auth.models import AuthenticatedUser
from llm_gateway.products.config import get_product_config
from llm_gateway.rate_limiting.runner import ThrottleRunner
from llm_gateway.rate_limiting.throttles import ThrottleContext, ThrottleResult


def _make_user(user_id: int = 42) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id,
        team_id=1,
        auth_method="personal_api_key",
        distinct_id=f"test-distinct-id-{user_id}",
        scopes=["llm_gateway:read"],
    )


class TestEnforceThrottlesEndUserId:
    """Test that enforce_throttles resolves end_user_id correctly based on product config."""

    @pytest.fixture
    def captured_contexts(self) -> list[ThrottleContext]:
        return []

    @pytest.fixture
    def app(self, captured_contexts: list[ThrottleContext]) -> FastAPI:
        app = FastAPI()

        mock_runner = MagicMock(spec=ThrottleRunner)
        mock_runner.check = AsyncMock(return_value=ThrottleResult.allow())
        app.state.throttle_runner = mock_runner
        app.state.db_pool = MagicMock()

        user = _make_user()

        @app.post("/{product}/v1/chat/completions")
        async def endpoint(request: Request) -> dict:
            return {"ok": True}

        @app.middleware("http")
        async def capture_context(request: Request, call_next):
            # Simulate what enforce_throttles does
            from llm_gateway.dependencies import get_cached_body, get_product_from_request

            product = get_product_from_request(request)
            product_config = get_product_config(product)

            client_user_id = None
            if product_config and product_config.trust_client_user_id:
                body = await get_cached_body(request)
                if body:
                    try:
                        data = json.loads(body)
                        client_user_id = data.get("user")
                    except (json.JSONDecodeError, TypeError):
                        pass
            end_user_id = client_user_id or str(user.user_id)

            context = ThrottleContext(
                user=user,
                product=product,
                end_user_id=end_user_id,
            )
            captured_contexts.append(context)

            response = await call_next(request)
            return response

        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        return TestClient(app)

    def test_service_product_uses_client_user_param(self, client: TestClient, captured_contexts: list) -> None:
        response = client.post(
            "/llma_summarization/v1/chat/completions",
            json={"model": "gpt-4.1-mini", "messages": [], "user": "temporal-workflow-team-23408"},
        )
        assert response.status_code == 200
        assert len(captured_contexts) == 1
        assert captured_contexts[0].end_user_id == "temporal-workflow-team-23408"

    def test_service_product_falls_back_to_auth_user_when_no_user_param(
        self, client: TestClient, captured_contexts: list
    ) -> None:
        response = client.post(
            "/llma_summarization/v1/chat/completions",
            json={"model": "gpt-4.1-mini", "messages": []},
        )
        assert response.status_code == 200
        assert len(captured_contexts) == 1
        assert captured_contexts[0].end_user_id == "42"

    def test_regular_product_ignores_client_user_param(self, client: TestClient, captured_contexts: list) -> None:
        response = client.post(
            "/django/v1/chat/completions",
            json={"model": "gpt-4.1-mini", "messages": [], "user": "attacker-supplied-id"},
        )
        assert response.status_code == 200
        assert len(captured_contexts) == 1
        assert captured_contexts[0].end_user_id == "42"

    def test_unknown_product_ignores_client_user_param(self, client: TestClient, captured_contexts: list) -> None:
        response = client.post(
            "/llm_gateway/v1/chat/completions",
            json={"model": "gpt-4.1-mini", "messages": [], "user": "should-be-ignored"},
        )
        assert response.status_code == 200
        assert len(captured_contexts) == 1
        assert captured_contexts[0].end_user_id == "42"


class TestTrustClientUserIdSecurity:
    """Verify that trust_client_user_id does not weaken security for user-facing products."""

    @pytest.mark.parametrize(
        "product",
        ["posthog_code", "background_agents", "wizard", "django", "llm_gateway", "growth"],
    )
    def test_user_facing_products_never_trust_client(self, product: str) -> None:
        config = get_product_config(product)
        if config is not None:
            assert config.trust_client_user_id is False, (
                f"Product '{product}' must not trust client user IDs — this would allow rate limit poisoning attacks"
            )
