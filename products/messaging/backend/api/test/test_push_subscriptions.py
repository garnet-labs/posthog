import json

from posthog.test.base import BaseTest

from django.test import Client

from rest_framework import status

from posthog.models.integration import Integration
from posthog.models.team.team import Team

from products.workflows.backend.models.push_subscription import PushSubscription


class TestPushSubscriptionsAPI(BaseTest):
    def setUp(self):
        super().setUp()
        self.client = Client()

        self.firebase_integration = Integration.objects.create(
            team=self.team,
            kind="firebase",
            integration_id="my-firebase-project",
            config={"project_id": "my-firebase-project"},
            sensitive_config={},
        )
        self.apns_integration = Integration.objects.create(
            team=self.team,
            kind="apns",
            integration_id="TEAM123.com.example.app",
            config={"bundle_id": "com.example.app", "team_id": "TEAM123", "key_id": "KEY123"},
            sensitive_config={},
        )

    def _post(self, data: dict, api_key: str | None = None):
        payload = {**data, "api_key": api_key or self.team.api_token}
        return self.client.post(
            "/api/push_subscriptions/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_register_android_token(self):
        response = self._post(
            {
                "distinct_id": "user-1",
                "token": "fcm-device-token-abc",
                "platform": "android",
                "app_id": "my-firebase-project",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["distinct_id"] == "user-1"
        assert data["platform"] == "android"
        assert data["is_active"] is True

        sub = PushSubscription.objects.get(id=data["id"])
        assert sub.integration_id == self.firebase_integration.id

    def test_register_ios_token(self):
        response = self._post(
            {
                "distinct_id": "user-1",
                "token": "apns-device-token-abc",
                "platform": "ios",
                "app_id": "com.example.app",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["distinct_id"] == "user-1"
        assert data["platform"] == "ios"
        assert data["is_active"] is True

        sub = PushSubscription.objects.get(id=data["id"])
        assert sub.integration_id == self.apns_integration.id

    def test_upsert_existing_token(self):
        self._post(
            {
                "distinct_id": "user-1",
                "token": "device-token-abc",
                "platform": "android",
                "app_id": "my-firebase-project",
            }
        )

        response = self._post(
            {
                "distinct_id": "user-1",
                "token": "device-token-abc",
                "platform": "android",
                "app_id": "my-firebase-project",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert PushSubscription.objects.count() == 1

    def test_missing_api_key_returns_401(self):
        response = self.client.post(
            "/api/push_subscriptions/",
            data=json.dumps({"distinct_id": "user-1", "token": "t", "platform": "android", "app_id": "proj"}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token_returns_401(self):
        response = self._post(
            {"distinct_id": "user-1", "token": "t", "platform": "android", "app_id": "proj"},
            api_key="phc_invalid_token",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_required_fields(self):
        response = self._post({"distinct_id": "user-1"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "token" in response.json()["detail"]
        assert "platform" in response.json()["detail"]
        assert "app_id" in response.json()["detail"]

    def test_invalid_platform(self):
        response = self._post(
            {
                "distinct_id": "user-1",
                "token": "device-token",
                "platform": "windows_phone",
                "app_id": "proj",
            }
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid platform" in response.json()["detail"]

    def test_integration_not_found(self):
        response = self._post(
            {
                "distinct_id": "user-1",
                "token": "device-token",
                "platform": "android",
                "app_id": "nonexistent-project",
            }
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "integration" in response.json()["detail"].lower()

    def test_team_isolation(self):
        other_team = Team.objects.create(organization=self.organization, name="Other Team")
        Integration.objects.create(
            team=other_team,
            kind="firebase",
            integration_id="other-project",
            config={"project_id": "other-project"},
            sensitive_config={},
        )

        response = self._post(
            {
                "distinct_id": "user-1",
                "token": "device-token",
                "platform": "android",
                "app_id": "other-project",
            }
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "integration" in response.json()["detail"].lower()

    def test_get_method_not_allowed(self):
        response = self.client.get(
            f"/api/push_subscriptions/?token={self.team.api_token}",
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_options_returns_200(self):
        response = self.client.options("/api/push_subscriptions/")

        assert response.status_code == status.HTTP_200_OK
