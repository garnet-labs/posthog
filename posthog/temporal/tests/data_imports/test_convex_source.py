import pytest
from unittest.mock import MagicMock, patch

from posthog.temporal.data_imports.sources.convex.convex import (
    InvalidWindowError,
    convex_source,
    document_deltas,
    list_snapshot,
)

DEPLOY_URL = "https://test-deployment.convex.cloud"
DEPLOY_KEY = "prod:test-key"


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"{status_code} Client Error")
    return resp


class TestListSnapshot:
    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_single_page(self, mock_get):
        mock_get.return_value = _mock_response(
            {"values": [{"_id": "1", "_ts": 100}], "snapshot": 12345, "cursor": "abc", "hasMore": False}
        )

        gen = list_snapshot(DEPLOY_URL, DEPLOY_KEY, "events")
        batches = []
        try:
            while True:
                batches.append(next(gen))
        except StopIteration as e:
            cursor = e.value

        assert len(batches) == 1
        assert batches[0] == [{"_id": "1", "_ts": 100}]
        assert cursor == 12345

    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_multi_page(self, mock_get):
        mock_get.side_effect = [
            _mock_response(
                {"values": [{"_id": "1", "_ts": 100}], "snapshot": 12345, "cursor": "page2", "hasMore": True}
            ),
            _mock_response(
                {"values": [{"_id": "2", "_ts": 200}], "snapshot": 12345, "cursor": "page3", "hasMore": False}
            ),
        ]

        gen = list_snapshot(DEPLOY_URL, DEPLOY_KEY, "events")
        batches = []
        try:
            while True:
                batches.append(next(gen))
        except StopIteration as e:
            cursor = e.value

        assert len(batches) == 2
        assert cursor == 12345

    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_empty_table_returns_snapshot_cursor(self, mock_get):
        mock_get.return_value = _mock_response({"values": [], "snapshot": 99999, "cursor": None, "hasMore": False})

        gen = list_snapshot(DEPLOY_URL, DEPLOY_KEY, "empty_table")
        batches = []
        try:
            while True:
                batches.append(next(gen))
        except StopIteration as e:
            cursor = e.value

        assert len(batches) == 0
        assert cursor == 99999


class TestDocumentDeltas:
    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_returns_new_cursor(self, mock_get):
        mock_get.return_value = _mock_response({"values": [{"_id": "1", "_ts": 200}], "cursor": 300, "hasMore": False})

        gen = document_deltas(DEPLOY_URL, DEPLOY_KEY, "events", cursor=100)
        batches = []
        try:
            while True:
                batches.append(next(gen))
        except StopIteration as e:
            new_cursor = e.value

        assert len(batches) == 1
        assert new_cursor == 300

    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_no_changes_still_returns_cursor(self, mock_get):
        mock_get.return_value = _mock_response({"values": [], "cursor": 500, "hasMore": False})

        gen = document_deltas(DEPLOY_URL, DEPLOY_KEY, "events", cursor=100)
        batches = []
        try:
            while True:
                batches.append(next(gen))
        except StopIteration as e:
            new_cursor = e.value

        assert len(batches) == 0
        assert new_cursor == 500

    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_invalid_window_raises(self, mock_get):
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {
            "code": "InvalidWindowToReadDocuments",
            "message": "Cursor too old",
        }
        mock_get.return_value = resp

        gen = document_deltas(DEPLOY_URL, DEPLOY_KEY, "events", cursor=100)
        with pytest.raises(InvalidWindowError, match="retention window"):
            next(gen)


class TestConvexSource:
    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_incremental_sync_captures_cursor_on_response(self, mock_get):
        mock_get.return_value = _mock_response({"values": [{"_id": "1", "_ts": 200}], "cursor": 300, "hasMore": False})

        response = convex_source(
            deploy_url=DEPLOY_URL,
            deploy_key=DEPLOY_KEY,
            table_name="events",
            team_id=1,
            job_id="job-1",
            should_use_incremental_field=True,
            db_incremental_field_last_value=100,
        )

        assert response.override_incremental_field_last_value is None

        batches = list(response.items())  # type: ignore[arg-type]

        assert len(batches) == 1
        assert response.override_incremental_field_last_value == 300

    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_incremental_sync_no_records_still_captures_cursor(self, mock_get):
        mock_get.return_value = _mock_response({"values": [], "cursor": 500, "hasMore": False})

        response = convex_source(
            deploy_url=DEPLOY_URL,
            deploy_key=DEPLOY_KEY,
            table_name="quiet_table",
            team_id=1,
            job_id="job-1",
            should_use_incremental_field=True,
            db_incremental_field_last_value=100,
        )

        list(response.items())  # type: ignore[arg-type]

        assert response.override_incremental_field_last_value == 500

    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_initial_sync_captures_snapshot_cursor(self, mock_get):
        mock_get.return_value = _mock_response(
            {"values": [{"_id": "1", "_ts": 100}], "snapshot": 12345, "cursor": "abc", "hasMore": False}
        )

        response = convex_source(
            deploy_url=DEPLOY_URL,
            deploy_key=DEPLOY_KEY,
            table_name="events",
            team_id=1,
            job_id="job-1",
            should_use_incremental_field=False,
            db_incremental_field_last_value=None,
        )

        list(response.items())  # type: ignore[arg-type]

        assert response.override_incremental_field_last_value == 12345

    @patch("posthog.temporal.data_imports.sources.convex.convex.requests.get")
    def test_initial_sync_empty_table_captures_snapshot_cursor(self, mock_get):
        mock_get.return_value = _mock_response({"values": [], "snapshot": 99999, "cursor": None, "hasMore": False})

        response = convex_source(
            deploy_url=DEPLOY_URL,
            deploy_key=DEPLOY_KEY,
            table_name="empty_table",
            team_id=1,
            job_id="job-1",
            should_use_incremental_field=False,
            db_incremental_field_last_value=None,
        )

        list(response.items())  # type: ignore[arg-type]

        assert response.override_incremental_field_last_value == 99999
