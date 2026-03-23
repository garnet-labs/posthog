from django.test import override_settings

from posthog.models.oauth import OAuthAccessToken
from posthog.models.team.team import Team

from ee.api.agentic_provisioning.test.base import HMAC_SECRET, StripeProvisioningTestBase


@override_settings(STRIPE_APP_SECRET_KEY=HMAC_SECRET)
class TestProvisioningUpdateService(StripeProvisioningTestBase):
    def test_update_service_returns_complete(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}/update_service",
            data={"service_id": "analytics"},
            token=token,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "complete"
        assert data["id"] == str(self.team.id)
        assert data["service_id"] == "analytics"
        assert "api_key" in data["complete"]["access_configuration"]
        assert "host" in data["complete"]["access_configuration"]

    def test_update_service_with_payment_credentials(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}/update_service",
            data={
                "service_id": "pay_as_you_go",
                "payment_credentials": {
                    "type": "stripe_payment_token",
                    "stripe_payment_token": "spt_test_123",
                },
            },
            token=token,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "complete"
        assert data["service_id"] == "pay_as_you_go"

    def test_update_service_without_payment_credentials(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}/update_service",
            data={"service_id": "analytics"},
            token=token,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "complete"

    def test_update_service_missing_bearer_returns_401(self):
        res = self._post_signed(
            f"/api/agentic/provisioning/resources/{self.team.id}/update_service",
            data={"service_id": "analytics"},
        )
        assert res.status_code == 401

    def test_update_service_wrong_team_returns_403(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/resources/99999/update_service",
            data={"service_id": "analytics"},
            token=token,
        )
        assert res.status_code == 403

    def test_update_service_deleted_team_returns_404(self):
        token = self._get_bearer_token()
        team_id = self.team.id
        access_token = OAuthAccessToken.objects.get(token=token)
        access_token.scoped_teams = [team_id]
        access_token.save(update_fields=["scoped_teams"])
        Team.objects.filter(id=team_id).delete()
        res = self._post_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{team_id}/update_service",
            data={"service_id": "analytics"},
            token=token,
        )
        assert res.status_code == 404

    def test_update_service_invalid_id_returns_400(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/resources/not-a-number/update_service",
            data={"service_id": "analytics"},
            token=token,
        )
        assert res.status_code == 400

    def test_update_service_unknown_service_returns_400(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}/update_service",
            data={"service_id": "nonexistent_service"},
            token=token,
        )
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "unknown_service"

    def test_update_service_defaults_service_id_to_analytics(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}/update_service",
            data={},
            token=token,
        )
        assert res.status_code == 200
        assert res.json()["service_id"] == "analytics"

    def test_update_service_persists_service_id(self):
        token = self._get_bearer_token()
        self._post_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}/update_service",
            data={"service_id": "pay_as_you_go"},
            token=token,
        )
        res = self._get_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}",
            token=token,
        )
        assert res.json()["service_id"] == "pay_as_you_go"
