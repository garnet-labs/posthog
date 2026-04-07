from posthog.test.base import APIBaseTest

from rest_framework import status

from products.notebooks.backend.models import Notebook


class TestNotebookCollabAPI(APIBaseTest):
    def _create_notebook(self, content=None):
        data = {}
        if content:
            data["content"] = content
        response = self.client.post(f"/api/projects/{self.team.id}/notebooks/", data=data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        return response.json()

    def test_collab_join(self):
        notebook = self._create_notebook(
            {"type": "doc", "content": [{"type": "heading", "content": [{"type": "text", "text": "Test"}]}]}
        )
        response = self.client.post(f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/join/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "client_id" in data
        assert "version" in data
        assert "doc" in data
        assert data["version"] == notebook["version"]

    def test_collab_submit_steps_accepted(self):
        notebook = self._create_notebook(
            {"type": "doc", "content": [{"type": "heading", "content": [{"type": "text", "text": "Test"}]}]}
        )
        # Join first
        join_response = self.client.post(f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/join/")
        join_data = join_response.json()

        # Submit steps
        response = self.client.post(
            f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/steps/",
            data={
                "client_id": join_data["client_id"],
                "version": join_data["version"],
                "steps": [{"stepType": "replace", "from": 0, "to": 0}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["accepted"] is True
        assert data["version"] == join_data["version"] + 1

    def test_collab_submit_steps_rejected_stale_version(self):
        notebook = self._create_notebook(
            {"type": "doc", "content": [{"type": "heading", "content": [{"type": "text", "text": "Test"}]}]}
        )
        # Two clients join
        join1 = self.client.post(f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/join/").json()
        join2 = self.client.post(f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/join/").json()

        # First client submits
        self.client.post(
            f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/steps/",
            data={
                "client_id": join1["client_id"],
                "version": join1["version"],
                "steps": [{"stepType": "replace", "from": 0, "to": 0}],
            },
            format="json",
        )

        # Second client submits with stale version
        response = self.client.post(
            f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/steps/",
            data={
                "client_id": join2["client_id"],
                "version": join2["version"],
                "steps": [{"stepType": "replace", "from": 1, "to": 1}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["accepted"] is False
        assert "steps" in data
        assert len(data["steps"]) == 1

    def test_collab_get_steps(self):
        notebook = self._create_notebook(
            {"type": "doc", "content": [{"type": "heading", "content": [{"type": "text", "text": "Test"}]}]}
        )
        join = self.client.post(f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/join/").json()

        # Submit some steps
        self.client.post(
            f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/steps/",
            data={
                "client_id": join["client_id"],
                "version": join["version"],
                "steps": [
                    {"stepType": "replace", "from": 0, "to": 0},
                    {"stepType": "replace", "from": 1, "to": 1},
                ],
            },
            format="json",
        )

        # Get steps since the original version
        response = self.client.get(
            f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/steps/?since={join['version']}"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["version"] == join["version"] + 2
        assert len(data["steps"]) == 2

    def test_collab_save(self):
        notebook = self._create_notebook(
            {"type": "doc", "content": [{"type": "heading", "content": [{"type": "text", "text": "Test"}]}]}
        )
        join = self.client.post(f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/join/").json()

        new_content = {
            "type": "doc",
            "content": [{"type": "heading", "content": [{"type": "text", "text": "Updated"}]}],
        }
        response = self.client.post(
            f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/save/",
            data={
                "content": new_content,
                "version": join["version"] + 1,
                "text_content": "Updated",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["saved"] is True

        # Verify the content was persisted
        nb = Notebook.objects.get(short_id=notebook["short_id"])
        assert nb.content == new_content
        assert nb.text_content == "Updated"

    def test_collab_save_rejects_stale_version(self):
        notebook = self._create_notebook(
            {"type": "doc", "content": [{"type": "heading", "content": [{"type": "text", "text": "Test"}]}]}
        )
        self.client.post(f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/join/")

        # Advance the version via the regular update
        self.client.patch(
            f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/",
            data={
                "content": {
                    "type": "doc",
                    "content": [{"type": "heading", "content": [{"type": "text", "text": "v2"}]}],
                },
                "version": notebook["version"],
            },
            format="json",
        )

        # Try to save with old version
        response = self.client.post(
            f"/api/projects/{self.team.id}/notebooks/{notebook['short_id']}/collab/save/",
            data={
                "content": {
                    "type": "doc",
                    "content": [{"type": "heading", "content": [{"type": "text", "text": "stale"}]}],
                },
                "version": 0,
                "text_content": "stale",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["saved"] is False
