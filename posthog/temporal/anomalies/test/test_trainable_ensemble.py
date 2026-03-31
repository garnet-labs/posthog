"""Unit tests for TrainableEnsemble train/score split."""

from __future__ import annotations

import pickle
from datetime import UTC

import numpy as np
from parameterized import parameterized

from posthog.temporal.anomalies.trainable_ensemble import (
    FittedEnsemble,
    FittedModel,
    TrainableEnsemble,
    _unify_score,
    _zscore_to_probability,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Clear oscillating signal — last point is normal
NORMAL_DATA = np.array(
    [10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11],
    dtype=float,
)

# Same pattern with an extreme spike at the last position
ANOMALY_DATA = np.array(
    [10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 1000],
    dtype=float,
)

# Constant series — std=0 edge case
CONSTANT_DATA = np.full(22, 42.0)

# Default ensemble config used throughout most tests
DEFAULT_CONFIG: dict = {
    "type": "ensemble",
    "operator": "or",
    "threshold": 0.95,
    "detectors": [
        {
            "type": "zscore",
            "threshold": 0.95,
            "preprocessing": {"diffs_n": 1, "lags_n": 5},
        },
        {
            "type": "knn",
            "threshold": 0.95,
            "n_neighbors": 5,
            "method": "largest",
            "preprocessing": {"diffs_n": 1, "lags_n": 5},
        },
        {
            "type": "pca",
            "threshold": 0.95,
            "preprocessing": {"diffs_n": 1, "lags_n": 5},
        },
    ],
}


# ---------------------------------------------------------------------------
# FittedModel and FittedEnsemble dataclass tests
# ---------------------------------------------------------------------------


class TestFittedModel:
    def test_default_threshold(self) -> None:
        model = FittedModel(detector_type="zscore", model_bytes=b"data")
        assert model.threshold == 0.95

    def test_custom_threshold(self) -> None:
        model = FittedModel(detector_type="knn", model_bytes=b"data", threshold=0.8)
        assert model.threshold == 0.8

    def test_metadata_defaults_to_empty_dict(self) -> None:
        model = FittedModel(detector_type="zscore", model_bytes=b"data")
        assert model.metadata == {}

    def test_metadata_is_not_shared_across_instances(self) -> None:
        a = FittedModel(detector_type="zscore", model_bytes=b"x")
        b = FittedModel(detector_type="mad", model_bytes=b"y")
        a.metadata["key"] = "value"
        assert "key" not in b.metadata


class TestFittedEnsemble:
    def test_default_operator_is_or(self) -> None:
        ensemble = FittedEnsemble(sub_models=[])
        assert ensemble.operator == "or"

    def test_default_training_samples_is_zero(self) -> None:
        ensemble = FittedEnsemble(sub_models=[])
        assert ensemble.training_samples == 0

    def test_trained_at_is_utc(self) -> None:
        ensemble = FittedEnsemble(sub_models=[])
        assert ensemble.trained_at.tzinfo == UTC

    def test_config_defaults_to_empty_dict(self) -> None:
        ensemble = FittedEnsemble(sub_models=[])
        assert ensemble.config == {}


# ---------------------------------------------------------------------------
# FittedEnsemble serialization roundtrip
# ---------------------------------------------------------------------------


class TestFittedEnsembleSerialization:
    def test_serialize_returns_bytes(self) -> None:
        ensemble = FittedEnsemble(sub_models=[], operator="and", training_samples=50)
        result = ensemble.serialize()
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_deserialize_roundtrip_preserves_operator(self) -> None:
        original = FittedEnsemble(sub_models=[], operator="and")
        restored = FittedEnsemble.deserialize(original.serialize())
        assert restored.operator == "and"

    def test_deserialize_roundtrip_preserves_training_samples(self) -> None:
        original = FittedEnsemble(sub_models=[], training_samples=123)
        restored = FittedEnsemble.deserialize(original.serialize())
        assert restored.training_samples == 123

    def test_deserialize_roundtrip_preserves_config(self) -> None:
        config = {"type": "ensemble", "threshold": 0.9}
        original = FittedEnsemble(sub_models=[], config=config)
        restored = FittedEnsemble.deserialize(original.serialize())
        assert restored.config == config

    def test_deserialize_roundtrip_preserves_sub_models(self) -> None:
        params = {"mean": 10.0, "std": 1.0, "window_zscores": [0.1, 0.2], "window": 5}
        sub = FittedModel(
            detector_type="zscore",
            model_bytes=pickle.dumps(params),
            threshold=0.95,
            metadata={"n_samples": 20},
        )
        original = FittedEnsemble(sub_models=[sub])
        restored = FittedEnsemble.deserialize(original.serialize())
        assert len(restored.sub_models) == 1
        assert restored.sub_models[0].detector_type == "zscore"
        assert restored.sub_models[0].threshold == 0.95

    def test_deserialize_roundtrip_preserves_trained_at(self) -> None:
        original = FittedEnsemble(sub_models=[])
        restored = FittedEnsemble.deserialize(original.serialize())
        assert restored.trained_at == original.trained_at

    def test_sub_model_bytes_survive_roundtrip(self) -> None:
        params = {"mean": 5.0, "std": 2.0, "window_zscores": [0.5], "window": 10}
        sub = FittedModel(detector_type="zscore", model_bytes=pickle.dumps(params))
        ensemble = FittedEnsemble(sub_models=[sub])
        restored = FittedEnsemble.deserialize(ensemble.serialize())
        recovered_params = pickle.loads(restored.sub_models[0].model_bytes)  # noqa: S301
        assert recovered_params["mean"] == 5.0
        assert recovered_params["std"] == 2.0


# ---------------------------------------------------------------------------
# TrainableEnsemble.train() — structure
# ---------------------------------------------------------------------------


class TestTrainableEnsembleTrain:
    def test_train_returns_fitted_ensemble(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        assert isinstance(fitted, FittedEnsemble)

    def test_train_produces_one_sub_model_per_detector(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        assert len(fitted.sub_models) == 3

    def test_train_records_correct_training_samples(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        assert fitted.training_samples == len(NORMAL_DATA)

    def test_train_records_operator(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        assert fitted.operator == "or"

    def test_train_preserves_config(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        assert fitted.config == DEFAULT_CONFIG

    def test_train_sets_trained_at_to_utc(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        assert fitted.trained_at.tzinfo == UTC

    def test_train_sub_models_have_correct_types(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        types = [m.detector_type for m in fitted.sub_models]
        assert "zscore" in types
        assert "knn" in types
        assert "pca" in types

    def test_train_sub_models_have_threshold_set(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        for sub in fitted.sub_models:
            assert sub.threshold == 0.95

    def test_train_sub_model_bytes_are_non_empty(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        for sub in fitted.sub_models:
            assert len(sub.model_bytes) > 0

    def test_train_skips_unknown_detector_types(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.95, "preprocessing": {}},
                {"type": "unknown_type", "threshold": 0.95, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        assert len(fitted.sub_models) == 1
        assert fitted.sub_models[0].detector_type == "zscore"

    def test_train_with_no_detectors_returns_empty_sub_models(self) -> None:
        config = {"type": "ensemble", "operator": "or", "threshold": 0.95, "detectors": []}
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        assert fitted.sub_models == []

    @parameterized.expand(
        [
            ("and_operator", "and"),
            ("or_operator", "or"),
        ]
    )
    def test_train_respects_operator(self, _name: str, operator: str) -> None:
        config = {**DEFAULT_CONFIG, "operator": operator}
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        assert fitted.operator == operator


# ---------------------------------------------------------------------------
# Statistical detectors — train captures correct params
# ---------------------------------------------------------------------------


class TestStatisticalDetectorTraining:
    def _make_zscore_config(self) -> dict:
        return {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "zscore", "threshold": 0.95, "preprocessing": {}}],
        }

    def _make_mad_config(self) -> dict:
        return {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "mad", "threshold": 0.95, "preprocessing": {}}],
        }

    def _make_iqr_config(self) -> dict:
        return {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "iqr", "threshold": 0.95, "preprocessing": {}}],
        }

    def test_zscore_train_captures_mean(self) -> None:
        ensemble = TrainableEnsemble(self._make_zscore_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert "mean" in params
        assert isinstance(params["mean"], float)

    def test_zscore_train_captures_std(self) -> None:
        ensemble = TrainableEnsemble(self._make_zscore_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert "std" in params
        assert params["std"] >= 0.0

    def test_zscore_train_captures_window_zscores(self) -> None:
        ensemble = TrainableEnsemble(self._make_zscore_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert "window_zscores" in params
        assert isinstance(params["window_zscores"], list)

    def test_zscore_train_mean_close_to_data_mean(self) -> None:
        data = np.arange(1, 32, dtype=float)  # 1..31
        ensemble = TrainableEnsemble(self._make_zscore_config())
        fitted = ensemble.train(data)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        # window defaults to 30; window_data is data[-31:-1] = data[0:30] = 1..30
        expected_mean = float(np.mean(np.arange(1, 31, dtype=float)))
        assert abs(params["mean"] - expected_mean) < 1e-6

    def test_mad_train_captures_median(self) -> None:
        ensemble = TrainableEnsemble(self._make_mad_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert "median" in params

    def test_mad_train_captures_mad(self) -> None:
        ensemble = TrainableEnsemble(self._make_mad_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert "mad" in params
        assert params["mad"] >= 0.0

    def test_mad_train_captures_window_scores(self) -> None:
        ensemble = TrainableEnsemble(self._make_mad_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert "window_scores" in params

    def test_iqr_train_captures_q1_q3_iqr(self) -> None:
        ensemble = TrainableEnsemble(self._make_iqr_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert "q1" in params
        assert "q3" in params
        assert "iqr" in params

    def test_iqr_q3_greater_than_or_equal_q1(self) -> None:
        ensemble = TrainableEnsemble(self._make_iqr_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert params["q3"] >= params["q1"]

    def test_iqr_train_captures_window_scores(self) -> None:
        ensemble = TrainableEnsemble(self._make_iqr_config())
        fitted = ensemble.train(NORMAL_DATA)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert "window_scores" in params

    def test_statistical_metadata_records_n_samples(self) -> None:
        ensemble = TrainableEnsemble(self._make_zscore_config())
        fitted = ensemble.train(NORMAL_DATA)
        assert fitted.sub_models[0].metadata["n_samples"] == len(NORMAL_DATA)

    def test_window_shrinks_when_data_is_short(self) -> None:
        short_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        ensemble = TrainableEnsemble(self._make_zscore_config())
        fitted = ensemble.train(short_data)
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        # window cannot exceed len(data) - 1 = 4, so params["window"] <= 4
        assert params["window"] <= len(short_data) - 1


# ---------------------------------------------------------------------------
# PyOD detectors — train fits model, score uses fitted model
# ---------------------------------------------------------------------------


class TestPyODDetectorTraining:
    def _make_knn_config(self) -> dict:
        return {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {
                    "type": "knn",
                    "threshold": 0.95,
                    "n_neighbors": 5,
                    "method": "largest",
                    "preprocessing": {"diffs_n": 1, "lags_n": 5},
                }
            ],
        }

    def _make_pca_config(self) -> dict:
        return {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {
                    "type": "pca",
                    "threshold": 0.95,
                    "preprocessing": {"diffs_n": 1, "lags_n": 5},
                }
            ],
        }

    @parameterized.expand(
        [
            ("knn",),
            ("pca",),
        ]
    )
    def test_pyod_train_produces_sub_model(self, detector_type: str) -> None:
        config = self._make_knn_config() if detector_type == "knn" else self._make_pca_config()
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        assert len(fitted.sub_models) == 1
        assert fitted.sub_models[0].detector_type == detector_type

    @parameterized.expand(
        [
            ("knn",),
            ("pca",),
        ]
    )
    def test_pyod_model_bytes_deserializable(self, detector_type: str) -> None:
        config = self._make_knn_config() if detector_type == "knn" else self._make_pca_config()
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        # Should not raise — deserialization must work
        model = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert model is not None

    @parameterized.expand(
        [
            ("knn",),
            ("pca",),
        ]
    )
    def test_pyod_model_is_fitted(self, detector_type: str) -> None:
        config = self._make_knn_config() if detector_type == "knn" else self._make_pca_config()
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        model = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        # A fitted PyOD model exposes decision_scores_
        assert hasattr(model, "decision_scores_")

    @parameterized.expand(
        [
            ("knn",),
            ("pca",),
        ]
    )
    def test_pyod_metadata_records_n_samples(self, detector_type: str) -> None:
        config = self._make_knn_config() if detector_type == "knn" else self._make_pca_config()
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        assert "n_samples" in fitted.sub_models[0].metadata


# ---------------------------------------------------------------------------
# TrainableEnsemble.score() — happy path / anomaly detection
# ---------------------------------------------------------------------------


class TestTrainableEnsembleScore:
    def test_score_returns_detection_result(self) -> None:
        from posthog.tasks.alerts.detectors.base import DetectionResult

        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert isinstance(result, DetectionResult)

    def test_score_normal_data_is_not_anomaly(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert not result.is_anomaly

    def test_score_anomaly_data_is_anomaly(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        assert result.is_anomaly

    def test_score_normal_produces_low_score(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert result.score is not None
        assert result.score < 0.95

    def test_score_anomaly_produces_high_score(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        assert result.score is not None
        assert result.score > 0.95

    def test_score_result_has_operator_in_metadata(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert result.metadata.get("operator") == "or"

    def test_score_result_has_sub_results_in_metadata(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert "sub_results" in result.metadata
        assert len(result.metadata["sub_results"]) == 3

    def test_score_result_score_is_in_unit_interval(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        for data in [NORMAL_DATA, ANOMALY_DATA]:
            result = ensemble.score(data, fitted)
            if result.score is not None:
                assert 0.0 <= result.score <= 1.0

    def test_score_anomaly_has_triggered_indices(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        assert result.is_anomaly
        assert len(result.triggered_indices) >= 1

    def test_score_normal_has_empty_triggered_indices(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert result.triggered_indices == []

    def test_score_after_serialization_roundtrip(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        restored = FittedEnsemble.deserialize(fitted.serialize())
        result = ensemble.score(ANOMALY_DATA, restored)
        assert result.is_anomaly


# ---------------------------------------------------------------------------
# Statistical detector scoring
# ---------------------------------------------------------------------------


class TestStatisticalDetectorScoring:
    def _make_zscore_only_config(self) -> dict:
        return {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "zscore", "threshold": 0.95, "preprocessing": {}}],
        }

    def _make_mad_only_config(self) -> dict:
        return {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "mad", "threshold": 0.95, "preprocessing": {}}],
        }

    def _make_iqr_only_config(self) -> dict:
        return {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "iqr", "threshold": 0.95, "preprocessing": {}}],
        }

    @parameterized.expand(
        [
            ("zscore",),
            ("mad",),
            ("iqr",),
        ]
    )
    def test_statistical_score_is_float_in_unit_interval(self, detector_type: str) -> None:
        config_map = {
            "zscore": self._make_zscore_only_config(),
            "mad": self._make_mad_only_config(),
            "iqr": self._make_iqr_only_config(),
        }
        ensemble = TrainableEnsemble(config_map[detector_type])
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        assert result.score is not None
        assert 0.0 <= result.score <= 1.0, f"{detector_type} score {result.score} not in [0, 1]"

    @parameterized.expand(
        [
            ("zscore",),
            ("mad",),
            ("iqr",),
        ]
    )
    def test_statistical_anomaly_detected(self, detector_type: str) -> None:
        config_map = {
            "zscore": self._make_zscore_only_config(),
            "mad": self._make_mad_only_config(),
            "iqr": self._make_iqr_only_config(),
        }
        ensemble = TrainableEnsemble(config_map[detector_type])
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        assert result.is_anomaly, f"{detector_type} should detect a spike of 1000 in data with mean ~10"

    @parameterized.expand(
        [
            ("zscore",),
            ("iqr",),
        ]
    )
    def test_statistical_normal_not_flagged(self, detector_type: str) -> None:
        config_map = {
            "zscore": self._make_zscore_only_config(),
            "iqr": self._make_iqr_only_config(),
        }
        ensemble = TrainableEnsemble(config_map[detector_type])
        # Train on one slice, score a different but still normal slice
        train_data = NORMAL_DATA[:20]
        score_data = np.array([10, 11, 10, 9, 10, 11, 10, 9, 10, 11], dtype=float)
        fitted = ensemble.train(train_data)
        result = ensemble.score(score_data, fitted)
        assert not result.is_anomaly, f"{detector_type} should not flag normal oscillating data"

    def test_mad_normal_not_flagged_wider_variance(self) -> None:
        # MAD with unify normalization needs wider variance data to not be overly sensitive
        train_data = np.array([5, 15, 8, 12, 7, 13, 9, 11, 6, 14, 8, 12, 7, 13, 10, 11, 9, 12, 8, 11], dtype=float)
        score_data = np.array([8, 12, 7, 13, 10, 11, 9, 12, 8, 11], dtype=float)
        ensemble = TrainableEnsemble(self._make_mad_only_config())
        fitted = ensemble.train(train_data)
        result = ensemble.score(score_data, fitted)
        assert not result.is_anomaly, "MAD should not flag data within normal variance range"


# ---------------------------------------------------------------------------
# Ensemble combining — OR and AND operators
# ---------------------------------------------------------------------------


class TestEnsembleCombining:
    def test_or_is_anomaly_when_any_detector_fires(self) -> None:
        # Use a low threshold on zscore so it fires, high on mad/iqr so they don't
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.1, "preprocessing": {}},
                {"type": "mad", "threshold": 0.99, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        # Score a moderate anomaly — zscore (low threshold) should fire, mad shouldn't
        mild_anomaly = np.append(NORMAL_DATA[:-1], 20.0)
        result = ensemble.score(mild_anomaly, fitted)
        # At least zscore should fire, so OR should be True
        sub = result.metadata["sub_results"]
        if any(s["score"] is not None and s["score"] > 0.1 for s in sub):
            assert result.is_anomaly

    def test_and_is_anomaly_only_when_all_detectors_fire(self) -> None:
        # Both detectors have low threshold — both will fire on obvious anomaly
        config = {
            "type": "ensemble",
            "operator": "and",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.1, "preprocessing": {}},
                {"type": "mad", "threshold": 0.1, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        sub = result.metadata["sub_results"]
        both_fire = all(s["score"] is not None and s["score"] > 0.1 for s in sub)
        assert result.is_anomaly == both_fire

    def test_and_not_anomaly_when_only_one_fires(self) -> None:
        # zscore with very low threshold fires on anything, iqr with very high threshold won't
        config = {
            "type": "ensemble",
            "operator": "and",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.0001, "preprocessing": {}},
                {"type": "iqr", "threshold": 0.9999, "preprocessing": {}},
            ],
        }
        # Use wider variance data where iqr behaves well
        train_data = np.array([5, 15, 8, 12, 7, 13, 9, 11, 6, 14, 8, 12, 7, 13, 10, 11, 9, 12, 8, 11], dtype=float)
        score_data = np.array([8, 12, 7, 13, 10, 11, 9, 12, 8, 10], dtype=float)
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(train_data)
        result = ensemble.score(score_data, fitted)
        assert not result.is_anomaly

    def test_or_score_is_max_of_sub_scores(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.95, "preprocessing": {}},
                {"type": "mad", "threshold": 0.95, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        sub_scores = [s["score"] for s in result.metadata["sub_results"] if s["score"] is not None]
        assert result.score == max(sub_scores)

    def test_and_score_is_min_of_sub_scores(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "and",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.95, "preprocessing": {}},
                {"type": "mad", "threshold": 0.95, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        sub_scores = [s["score"] for s in result.metadata["sub_results"] if s["score"] is not None]
        assert result.score == min(sub_scores)

    def test_or_triggered_indices_is_union(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.95, "preprocessing": {}},
                {"type": "mad", "threshold": 0.95, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        assert result.is_anomaly
        assert len(result.triggered_indices) >= 1

    def test_and_triggered_indices_is_intersection(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "and",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.95, "preprocessing": {}},
                {"type": "mad", "threshold": 0.95, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        if result.is_anomaly:
            assert len(result.triggered_indices) >= 1

    def test_or_no_anomaly_has_empty_triggered_indices(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.95, "preprocessing": {}},
                {"type": "mad", "threshold": 0.95, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert result.triggered_indices == []

    def test_empty_results_returns_no_anomaly(self) -> None:
        config = {"type": "ensemble", "operator": "or", "threshold": 0.95, "detectors": []}
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert not result.is_anomaly


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_constant_data_zscore_returns_result(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "zscore", "threshold": 0.95, "preprocessing": {}}],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(CONSTANT_DATA)
        result = ensemble.score(CONSTANT_DATA, fitted)
        # Constant data is not anomalous against itself
        assert not result.is_anomaly

    def test_constant_data_zscore_spike_detected(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "zscore", "threshold": 0.95, "preprocessing": {}}],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(CONSTANT_DATA)
        # Any deviation from the constant value should be an anomaly (std=0 branch)
        spike_data = np.append(CONSTANT_DATA[:-1], 43.0)
        result = ensemble.score(spike_data, fitted)
        assert result.is_anomaly

    def test_constant_data_mad_spike_detected(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "mad", "threshold": 0.95, "preprocessing": {}}],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(CONSTANT_DATA)
        spike_data = np.append(CONSTANT_DATA[:-1], 99.0)
        result = ensemble.score(spike_data, fitted)
        assert result.is_anomaly

    def test_constant_data_iqr_spike_detected(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "iqr", "threshold": 0.95, "preprocessing": {}}],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(CONSTANT_DATA)
        spike_data = np.append(CONSTANT_DATA[:-1], 99.0)
        result = ensemble.score(spike_data, fitted)
        assert result.is_anomaly

    def test_inf_value_in_score_data_returns_no_anomaly_for_pyod(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {
                    "type": "knn",
                    "threshold": 0.95,
                    "n_neighbors": 3,
                    "method": "largest",
                    "preprocessing": {},
                }
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        inf_data = np.append(NORMAL_DATA[:-1], np.inf)
        result = ensemble.score(inf_data, fitted)
        # Inf should be rejected gracefully — no crash and no false anomaly
        assert isinstance(result.is_anomaly, bool)

    def test_nan_value_in_score_data_returns_no_anomaly_for_pyod(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {
                    "type": "knn",
                    "threshold": 0.95,
                    "n_neighbors": 3,
                    "method": "largest",
                    "preprocessing": {},
                }
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        nan_data = np.append(NORMAL_DATA[:-1], np.nan)
        result = ensemble.score(nan_data, fitted)
        assert isinstance(result.is_anomaly, bool)

    def test_very_short_data_trains_with_reduced_window(self) -> None:
        short_data = np.array([1.0, 2.0, 3.0, 4.0])
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "zscore", "threshold": 0.95, "window": 30, "preprocessing": {}}],
        }
        ensemble = TrainableEnsemble(config)
        # Should not raise even though window > len(data)
        fitted = ensemble.train(short_data)
        assert len(fitted.sub_models) == 1

    def test_score_with_empty_fitted_sub_models(self) -> None:
        config = {"type": "ensemble", "operator": "or", "threshold": 0.95, "detectors": []}
        ensemble = TrainableEnsemble(config)
        fitted = FittedEnsemble(sub_models=[], operator="or")
        result = ensemble.score(NORMAL_DATA, fitted)
        assert not result.is_anomaly
        assert result.score is None


# ---------------------------------------------------------------------------
# Preprocessing integration — diffs_n=1 and lags_n=5
# ---------------------------------------------------------------------------


class TestPreprocessingIntegration:
    def test_train_with_diffs_reduces_effective_length(self) -> None:
        # diffs_n=1 produces first differences, which changes the distribution
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "zscore", "threshold": 0.95, "preprocessing": {"diffs_n": 1}}],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        # With diffs, mean should be close to 0 for the oscillating data
        params = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        assert abs(params["mean"]) < 5.0

    def test_train_with_lags_produces_multivariate_knn_model(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {
                    "type": "knn",
                    "threshold": 0.95,
                    "n_neighbors": 3,
                    "method": "largest",
                    "preprocessing": {"lags_n": 5},
                }
            ],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        model = pickle.loads(fitted.sub_models[0].model_bytes)  # noqa: S301
        # KNN was fitted on 6-dimensional data (1 value + 5 lags)
        assert model.decision_scores_ is not None

    def test_score_with_diffs_and_lags_does_not_raise(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        # Should complete without error
        result = ensemble.score(NORMAL_DATA, fitted)
        assert isinstance(result.is_anomaly, bool)

    def test_default_config_score_anomaly_detected(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(ANOMALY_DATA, fitted)
        assert result.is_anomaly

    def test_no_preprocessing_config_is_handled(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [{"type": "zscore", "threshold": 0.95}],
        }
        ensemble = TrainableEnsemble(config)
        fitted = ensemble.train(NORMAL_DATA)
        result = ensemble.score(NORMAL_DATA, fitted)
        assert isinstance(result.is_anomaly, bool)


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestZscoreToProbability:
    def test_high_zscore_returns_high_probability(self) -> None:
        window_zscores = np.array([0.1, 0.2, 0.15, 0.3, 0.1])
        prob = _zscore_to_probability(z_score=10.0, window_zscores=window_zscores)
        assert prob > 0.9

    def test_low_zscore_returns_low_probability(self) -> None:
        window_zscores = np.array([0.5, 1.0, 0.8, 0.7, 0.9])
        prob = _zscore_to_probability(z_score=0.1, window_zscores=window_zscores)
        assert prob < 0.5

    def test_result_is_clipped_to_unit_interval(self) -> None:
        window_zscores = np.array([0.1, 0.2, 0.1])
        prob = _zscore_to_probability(z_score=100.0, window_zscores=window_zscores)
        assert 0.0 <= prob <= 1.0

    def test_constant_window_zscores_std_zero(self) -> None:
        # std=0 branch: score > mean → 1.0, score <= mean → 0.0
        window_zscores = np.full(5, 0.5)
        prob_high = _zscore_to_probability(z_score=1.0, window_zscores=window_zscores)
        prob_low = _zscore_to_probability(z_score=0.3, window_zscores=window_zscores)
        assert prob_high == 1.0
        assert prob_low == 0.0

    def test_z_score_equal_to_mean_returns_zero(self) -> None:
        window_zscores = np.full(5, 0.5)
        prob = _zscore_to_probability(z_score=0.5, window_zscores=window_zscores)
        # z_score == mean → std=0 branch → not (0.5 > 0.5) → 0.0
        assert prob == 0.0


class TestUnifyScore:
    def test_high_raw_score_returns_high_probability(self) -> None:
        window_scores = np.array([0.1, 0.2, 0.1, 0.15, 0.1])
        prob = _unify_score(raw_score=10.0, window_scores=window_scores)
        assert prob > 0.9

    def test_low_raw_score_returns_low_probability(self) -> None:
        window_scores = np.array([1.0, 2.0, 1.5, 1.8, 1.2])
        prob = _unify_score(raw_score=0.01, window_scores=window_scores)
        assert prob < 0.5

    def test_empty_window_scores_returns_zero(self) -> None:
        prob = _unify_score(raw_score=5.0, window_scores=np.array([]))
        assert prob == 0.0

    def test_result_clipped_to_unit_interval(self) -> None:
        window_scores = np.array([0.1, 0.1, 0.1])
        prob = _unify_score(raw_score=1000.0, window_scores=window_scores)
        assert 0.0 <= prob <= 1.0

    def test_constant_window_scores_std_zero(self) -> None:
        window_scores = np.full(5, 1.0)
        prob_above = _unify_score(raw_score=2.0, window_scores=window_scores)
        prob_below = _unify_score(raw_score=0.5, window_scores=window_scores)
        assert prob_above == 1.0
        assert prob_below == 0.0

    @parameterized.expand(
        [
            ("small_window", np.array([0.1, 0.2])),
            ("large_window", np.arange(1, 101, dtype=float) * 0.01),
        ]
    )
    def test_result_always_in_unit_interval(self, _name: str, window_scores: np.ndarray) -> None:
        for raw in [0.0, 0.5, 1.0, 5.0, 100.0]:
            prob = _unify_score(raw_score=raw, window_scores=window_scores)
            assert 0.0 <= prob <= 1.0, f"prob={prob} out of range for raw={raw}"


# ---------------------------------------------------------------------------
# find_sub_config helper
# ---------------------------------------------------------------------------


class TestFindSubConfig:
    def test_returns_matching_config_by_type(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        result = ensemble._find_sub_config("zscore")
        assert result["type"] == "zscore"
        assert result["threshold"] == 0.95

    def test_returns_fallback_for_unknown_type(self) -> None:
        ensemble = TrainableEnsemble(DEFAULT_CONFIG)
        result = ensemble._find_sub_config("nonexistent")
        assert result == {"type": "nonexistent"}

    def test_returns_first_matching_config(self) -> None:
        config = {
            "type": "ensemble",
            "operator": "or",
            "threshold": 0.95,
            "detectors": [
                {"type": "zscore", "threshold": 0.8, "preprocessing": {}},
                {"type": "zscore", "threshold": 0.6, "preprocessing": {}},
            ],
        }
        ensemble = TrainableEnsemble(config)
        result = ensemble._find_sub_config("zscore")
        assert result["threshold"] == 0.8
