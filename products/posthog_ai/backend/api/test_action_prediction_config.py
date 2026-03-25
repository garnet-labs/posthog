from posthog.test.base import APIBaseTest

from rest_framework import status

from posthog.models import Team
from posthog.models.action import Action


class TestActionPredictionConfigAPI(APIBaseTest):
    def setUp(self):
        super().setUp()
        self.action = Action.objects.create(team=self.team, name="Test Action")

    def _url(self, pk=None):
        base = f"/api/environments/{self.team.id}/action_prediction_configs"
        if pk:
            return f"{base}/{pk}/"
        return f"{base}/"

    def test_create_with_action(self):
        response = self.client.post(
            self._url(),
            {"name": "Churn predictor", "action": self.action.id, "lookback_days": 30},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["action"], self.action.id)
        self.assertIsNone(data["event_name"])
        self.assertEqual(data["lookback_days"], 30)
        self.assertEqual(data["name"], "Churn predictor")
        self.assertEqual(data["created_by"]["id"], self.user.id)

    def test_create_with_event_name(self):
        response = self.client.post(
            self._url(),
            {"event_name": "$pageview", "lookback_days": 7},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIsNone(data["action"])
        self.assertEqual(data["event_name"], "$pageview")
        self.assertEqual(data["lookback_days"], 7)

    def test_create_rejects_both_action_and_event_name(self):
        response = self.client.post(
            self._url(),
            {"action": self.action.id, "event_name": "$pageview", "lookback_days": 30},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_neither_action_nor_event_name(self):
        response = self.client.post(
            self._url(),
            {"lookback_days": 30},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_lookback_days_zero(self):
        response = self.client.post(
            self._url(),
            {"event_name": "$pageview", "lookback_days": 0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_negative_lookback_days(self):
        response = self.client.post(
            self._url(),
            {"event_name": "$pageview", "lookback_days": -5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_nonexistent_action(self):
        response = self.client.post(
            self._url(),
            {"action": 999999, "lookback_days": 30},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list(self):
        self.client.post(self._url(), {"event_name": "$pageview", "lookback_days": 7}, format="json")
        self.client.post(self._url(), {"action": self.action.id, "lookback_days": 14}, format="json")

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 2)

    def test_list_scoped_to_team(self):
        self.client.post(self._url(), {"event_name": "$pageview", "lookback_days": 7}, format="json")

        other_team = Team.objects.create(organization=self.organization, name="Other Team")
        response = self.client.get(f"/api/environments/{other_team.id}/action_prediction_configs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 0)

    def test_retrieve(self):
        create_response = self.client.post(
            self._url(),
            {"name": "My config", "event_name": "$pageview", "lookback_days": 7},
            format="json",
        )
        pk = create_response.json()["id"]

        response = self.client.get(self._url(pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["name"], "My config")

    def test_partial_update(self):
        create_response = self.client.post(
            self._url(),
            {"event_name": "$pageview", "lookback_days": 7},
            format="json",
        )
        pk = create_response.json()["id"]

        response = self.client.patch(self._url(pk), {"lookback_days": 14}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["lookback_days"], 14)

    def test_partial_update_switch_event_to_action(self):
        create_response = self.client.post(
            self._url(),
            {"event_name": "$pageview", "lookback_days": 7},
            format="json",
        )
        pk = create_response.json()["id"]

        response = self.client.patch(
            self._url(pk),
            {"action": self.action.id, "event_name": None},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["action"], self.action.id)
        self.assertIsNone(data["event_name"])

    def test_delete(self):
        create_response = self.client.post(
            self._url(),
            {"event_name": "$pageview", "lookback_days": 7},
            format="json",
        )
        pk = create_response.json()["id"]

        response = self.client.delete(self._url(pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(self._url(pk))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
