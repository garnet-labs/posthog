"""Tests for posthog/temporal/anomalies/model_storage.py"""

from __future__ import annotations

import pickle

from unittest.mock import patch

from parameterized import parameterized

from posthog.temporal.anomalies.model_storage import (
    S3_PREFIX,
    delete_model,
    delete_old_versions,
    load_model,
    model_key,
    save_model,
)
from posthog.temporal.anomalies.trainable_ensemble import FittedEnsemble, FittedModel


def _make_fitted_ensemble() -> FittedEnsemble:
    return FittedEnsemble(
        sub_models=[FittedModel(detector_type="zscore", model_bytes=pickle.dumps({"mean": 1.0, "std": 0.5}))],
        operator="or",
        training_samples=10,
    )


class TestModelKey:
    @parameterized.expand(
        [
            ("basic", 1, 2, 3, "anomaly-models/1/2/v3.pkl"),
            ("large_ids", 9999, 88888, 100, "anomaly-models/9999/88888/v100.pkl"),
            ("version_zero", 1, 1, 0, "anomaly-models/1/1/v0.pkl"),
        ]
    )
    def test_model_key_generates_correct_path(self, _name, team_id, insight_id, version, expected):
        assert model_key(team_id, insight_id, version) == expected

    def test_model_key_starts_with_s3_prefix(self):
        key = model_key(1, 2, 3)
        assert key.startswith(S3_PREFIX + "/")

    def test_model_key_contains_pkl_extension(self):
        key = model_key(1, 2, 3)
        assert key.endswith(".pkl")

    def test_model_key_encodes_version_with_v_prefix(self):
        key = model_key(10, 20, 7)
        assert "/v7.pkl" in key


class TestSaveModel:
    def test_save_model_calls_object_storage_write(self):
        ensemble = _make_fitted_ensemble()
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            save_model(team_id=1, insight_id=2, version=3, fitted=ensemble)

        mock_storage.write.assert_called_once()
        call_args = mock_storage.write.call_args
        assert call_args[0][0] == "anomaly-models/1/2/v3.pkl"
        assert isinstance(call_args[0][1], bytes)

    def test_save_model_returns_correct_key(self):
        ensemble = _make_fitted_ensemble()
        with patch("posthog.temporal.anomalies.model_storage.object_storage"):
            result = save_model(team_id=5, insight_id=10, version=1, fitted=ensemble)

        assert result == "anomaly-models/5/10/v1.pkl"

    def test_save_model_writes_serialized_bytes(self):
        ensemble = _make_fitted_ensemble()
        expected_bytes = ensemble.serialize()

        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            save_model(team_id=1, insight_id=2, version=3, fitted=ensemble)

        written_data = mock_storage.write.call_args[0][1]
        assert written_data == expected_bytes


class TestLoadModel:
    def test_load_model_returns_fitted_ensemble_when_data_exists(self):
        ensemble = _make_fitted_ensemble()
        serialized = ensemble.serialize()

        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.read_bytes.return_value = serialized
            result = load_model("anomaly-models/1/2/v3.pkl")

        assert result is not None
        assert isinstance(result, FittedEnsemble)
        assert result.operator == ensemble.operator
        assert result.training_samples == ensemble.training_samples

    def test_load_model_returns_none_when_key_is_missing(self):
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.read_bytes.return_value = None
            result = load_model("anomaly-models/does/not/exist.pkl")

        assert result is None

    def test_load_model_calls_read_bytes_with_missing_ok(self):
        key = "anomaly-models/1/2/v3.pkl"
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.read_bytes.return_value = None
            load_model(key)

        mock_storage.read_bytes.assert_called_once_with(key, missing_ok=True)

    def test_load_model_roundtrip_preserves_sub_models(self):
        original = _make_fitted_ensemble()
        serialized = original.serialize()

        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.read_bytes.return_value = serialized
            loaded = load_model("anomaly-models/1/2/v3.pkl")

        assert loaded is not None
        assert len(loaded.sub_models) == len(original.sub_models)
        assert loaded.sub_models[0].detector_type == original.sub_models[0].detector_type

    def test_save_then_load_roundtrip(self):
        original = _make_fitted_ensemble()
        stored: dict[str, bytes] = {}

        def fake_write(key, data):
            stored[key] = data

        def fake_read_bytes(key, *, missing_ok=False):
            return stored.get(key)

        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.write.side_effect = fake_write
            save_model(team_id=7, insight_id=8, version=2, fitted=original)

        key = model_key(7, 8, 2)
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.read_bytes.side_effect = fake_read_bytes
            loaded = load_model(key)

        assert loaded is not None
        assert isinstance(loaded, FittedEnsemble)
        assert loaded.training_samples == original.training_samples
        assert loaded.operator == original.operator


class TestDeleteModel:
    def test_delete_model_calls_object_storage_delete(self):
        key = "anomaly-models/1/2/v3.pkl"
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            delete_model(key)

        mock_storage.delete.assert_called_once_with(key)

    def test_delete_model_does_not_raise_when_storage_raises(self):
        key = "anomaly-models/1/2/v3.pkl"
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.delete.side_effect = RuntimeError("S3 unavailable")
            # should not raise
            delete_model(key)


class TestDeleteOldVersions:
    def test_delete_old_versions_removes_keys_below_keep_version(self):
        keys = [
            "anomaly-models/1/2/v1.pkl",
            "anomaly-models/1/2/v2.pkl",
            "anomaly-models/1/2/v3.pkl",
        ]
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.list_objects.return_value = keys
            mock_storage.delete.return_value = None
            count = delete_old_versions(team_id=1, insight_id=2, keep_version=3)

        assert count == 2
        deleted_keys = [call[0][0] for call in mock_storage.delete.call_args_list]
        assert "anomaly-models/1/2/v1.pkl" in deleted_keys
        assert "anomaly-models/1/2/v2.pkl" in deleted_keys
        assert "anomaly-models/1/2/v3.pkl" not in deleted_keys

    def test_delete_old_versions_returns_zero_when_no_old_versions(self):
        keys = ["anomaly-models/1/2/v5.pkl"]
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.list_objects.return_value = keys
            count = delete_old_versions(team_id=1, insight_id=2, keep_version=5)

        assert count == 0

    def test_delete_old_versions_returns_zero_when_list_objects_returns_none(self):
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.list_objects.return_value = None
            count = delete_old_versions(team_id=1, insight_id=2, keep_version=1)

        assert count == 0

    def test_delete_old_versions_skips_keys_with_unparseable_filename(self):
        keys = [
            "anomaly-models/1/2/v1.pkl",
            "anomaly-models/1/2/corrupt-file.pkl",
        ]
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.list_objects.return_value = keys
            mock_storage.delete.return_value = None
            count = delete_old_versions(team_id=1, insight_id=2, keep_version=10)

        assert count == 1

    def test_delete_old_versions_uses_correct_prefix(self):
        with patch("posthog.temporal.anomalies.model_storage.object_storage") as mock_storage:
            mock_storage.list_objects.return_value = []
            delete_old_versions(team_id=42, insight_id=99, keep_version=1)

        mock_storage.list_objects.assert_called_once_with("anomaly-models/42/99/")
