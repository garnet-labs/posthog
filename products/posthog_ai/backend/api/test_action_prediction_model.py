from posthog.test.base import APIBaseTest

from rest_framework import status

from posthog.models import Team
from posthog.models.action import Action

from products.posthog_ai.backend.models import ActionPredictionConfig


class TestActionPredictionModelAPI(APIBaseTest):
    def setUp(self):
        super().setUp()
        self.action = Action.objects.create(team=self.team, name="Test Action")
        self.config = ActionPredictionConfig.objects.create(
            team=self.team,
            action=self.action,
            lookback_days=30,
            name="Churn predictor",
            created_by=self.user,
        )

    def _url(self, pk=None):
        base = f"/api/environments/{self.team.id}/action_prediction_models"
        if pk:
            return f"{base}/{pk}/"
        return f"{base}/"

    def _create_model(self, **overrides):
        defaults = {
            "config": str(self.config.id),
            "is_winning": False,
            "model_url": "https://s3.amazonaws.com/bucket/model.pkl",
            "metrics": {"accuracy": 0.95, "auc": 0.87},
            "feature_importance": {"feature_a": 0.8, "feature_b": 0.2},
            "artifact_script": "import sklearn\n# training script",
        }
        defaults.update(overrides)
        return self.client.post(self._url(), defaults, format="json")

    def test_create(self):
        response = self._create_model()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertFalse(data["is_winning"])
        self.assertEqual(data["model_url"], "https://s3.amazonaws.com/bucket/model.pkl")
        self.assertEqual(data["metrics"]["accuracy"], 0.95)
        self.assertEqual(data["feature_importance"]["feature_a"], 0.8)
        self.assertEqual(data["artifact_script"], "import sklearn\n# training script")
        self.assertEqual(data["config"], str(self.config.id))
        self.assertEqual(data["created_by"]["id"], self.user.id)

    def test_list(self):
        self._create_model()
        self._create_model(is_winning=True, model_url="https://s3.amazonaws.com/bucket/model2.pkl")

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 2)

    def test_list_ordered_by_newest_first(self):
        resp1 = self._create_model(model_url="https://s3.amazonaws.com/bucket/first.pkl")
        resp2 = self._create_model(model_url="https://s3.amazonaws.com/bucket/second.pkl")

        response = self.client.get(self._url())
        results = response.json()["results"]
        self.assertEqual(results[0]["id"], resp2.json()["id"])
        self.assertEqual(results[1]["id"], resp1.json()["id"])

    def test_list_scoped_to_team(self):
        self._create_model()

        other_team = Team.objects.create(organization=self.organization, name="Other Team")
        response = self.client.get(f"/api/environments/{other_team.id}/action_prediction_models/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 0)

    def test_retrieve(self):
        create_response = self._create_model()
        pk = create_response.json()["id"]

        response = self.client.get(self._url(pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], pk)

    def test_partial_update(self):
        create_response = self._create_model()
        pk = create_response.json()["id"]

        response = self.client.patch(self._url(pk), {"is_winning": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["is_winning"])

    def test_partial_update_metrics(self):
        create_response = self._create_model()
        pk = create_response.json()["id"]

        new_metrics = {"accuracy": 0.99, "auc": 0.95, "f1": 0.92}
        response = self.client.patch(self._url(pk), {"metrics": new_metrics}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["metrics"], new_metrics)

    def test_delete_not_allowed(self):
        create_response = self._create_model()
        pk = create_response.json()["id"]

        response = self.client.delete(self._url(pk))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
