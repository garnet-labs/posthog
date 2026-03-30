"""Train/score split for the anomalies system.

Wraps existing detector implementations WITHOUT modifying BaseDetector.
The alert system continues using detect() as-is.

For PyOD detectors (KNN, PCA): captures the fitted sklearn model after fit().
For statistical detectors (ZScore): captures computed window stats.

Fitted state is pickle-serializable for S3 persistence.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
from scipy.special import erf

from posthog.tasks.alerts.detectors.base import DetectionResult
from posthog.tasks.alerts.detectors.preprocessing import preprocess_data


@dataclass
class FittedModel:
    """Individual fitted detector state."""

    detector_type: str
    model_bytes: bytes  # pickled PyOD model or statistical params dict
    threshold: float = 0.95
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FittedEnsemble:
    """Serializable container for all fitted sub-detector models."""

    sub_models: list[FittedModel]
    operator: str = "or"
    trained_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    training_samples: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def serialize(self) -> bytes:
        return pickle.dumps(self)

    @staticmethod
    def deserialize(data: bytes) -> FittedEnsemble:
        return pickle.loads(data)  # noqa: S301


# -- PyOD detector types that produce fitted sklearn models --
PYOD_DETECTOR_TYPES = {"knn", "pca", "copod", "ecod", "hbos", "isolation_forest", "lof", "ocsvm"}

# -- Statistical detector types where we capture computed params --
STATISTICAL_DETECTOR_TYPES = {"zscore", "mad", "iqr"}


class TrainableEnsemble:
    """Wraps existing detectors with a train/score split."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.operator = config.get("operator", "or")
        self.sub_configs: list[dict[str, Any]] = config.get("detectors", [])

    def train(self, data: np.ndarray) -> FittedEnsemble:
        """Fit all sub-detectors on training data. Returns serializable fitted state."""
        sub_models: list[FittedModel] = []

        for sub_config in self.sub_configs:
            detector_type = sub_config.get("type", "zscore")
            preprocessing_config = sub_config.get("preprocessing", {})
            threshold = sub_config.get("threshold", 0.95)

            processed = preprocess_data(data.copy(), preprocessing_config)
            if processed.ndim == 1:
                values = processed
            else:
                values = processed[:, 0]

            if detector_type in PYOD_DETECTOR_TYPES:
                fitted = self._train_pyod(detector_type, sub_config, values)
            elif detector_type in STATISTICAL_DETECTOR_TYPES:
                fitted = self._train_statistical(detector_type, sub_config, values)
            else:
                continue

            fitted.threshold = threshold
            sub_models.append(fitted)

        return FittedEnsemble(
            sub_models=sub_models,
            operator=self.operator,
            trained_at=datetime.now(UTC),
            training_samples=len(data),
            config=self.config,
        )

    def score(self, data: np.ndarray, fitted: FittedEnsemble) -> DetectionResult:
        """Score data against pre-fitted models.

        Args:
            data: Recent data points. The last point is scored. Enough context
                  should be provided for preprocessing (e.g. diffs_n=1 needs >=2 points).
            fitted: Previously trained FittedEnsemble.
        """
        results: list[DetectionResult] = []

        for sub_model in fitted.sub_models:
            sub_config = self._find_sub_config(sub_model.detector_type)
            preprocessing_config = sub_config.get("preprocessing", {})

            processed = preprocess_data(data.copy(), preprocessing_config)
            if processed.ndim == 1:
                values = processed
            else:
                values = processed[:, 0]

            if sub_model.detector_type in PYOD_DETECTOR_TYPES:
                result = self._score_pyod(sub_model, values)
            elif sub_model.detector_type in STATISTICAL_DETECTOR_TYPES:
                result = self._score_statistical(sub_model, values)
            else:
                continue

            results.append(result)

        return self._combine_results(results)

    # -- PyOD train/score --

    def _train_pyod(self, detector_type: str, config: dict[str, Any], values: np.ndarray) -> FittedModel:
        from posthog.tasks.alerts.detectors import get_detector

        detector = get_detector(config)
        pyod_model = detector._build_model(n_samples=len(values))  # type: ignore[attr-defined]

        train_data = values.reshape(-1, 1) if values.ndim == 1 else values
        pyod_model.fit(train_data)

        return FittedModel(
            detector_type=detector_type,
            model_bytes=pickle.dumps(pyod_model),
            metadata={"n_samples": len(values)},
        )

    def _score_pyod(self, fitted: FittedModel, values: np.ndarray) -> DetectionResult:
        model = pickle.loads(fitted.model_bytes)  # noqa: S301
        point = values[-1:].reshape(1, -1) if values.ndim == 1 else values[-1:]

        if not np.all(np.isfinite(point)):
            return DetectionResult(is_anomaly=False)

        try:
            prob = float(model.predict_proba(point)[0, 1])
        except (ValueError, np.linalg.LinAlgError):
            return DetectionResult(is_anomaly=False)

        return DetectionResult(
            is_anomaly=prob > fitted.threshold,
            score=prob,
            triggered_indices=[len(values) - 1] if prob > fitted.threshold else [],
            all_scores=[prob],
        )

    # -- Statistical train/score --

    def _train_statistical(self, detector_type: str, config: dict[str, Any], values: np.ndarray) -> FittedModel:
        window = config.get("window", 30)

        if len(values) < window + 1:
            window = max(len(values) - 1, 2)

        window_data = values[-(window + 1) : -1]

        if detector_type == "zscore":
            mean = float(np.mean(window_data))
            std = float(np.std(window_data))
            if std > 0:
                window_zscores = np.abs((window_data - mean) / std).tolist()
            else:
                window_zscores = [0.0] * len(window_data)
            params = {"mean": mean, "std": std, "window_zscores": window_zscores, "window": window}

        elif detector_type == "mad":
            median = float(np.median(window_data))
            mad_val = float(np.median(np.abs(window_data - median)))
            if mad_val > 0:
                window_scores = (np.abs(window_data - median) / (mad_val * 1.4826)).tolist()
            else:
                window_scores = [0.0] * len(window_data)
            params = {"median": median, "mad": mad_val, "window_scores": window_scores, "window": window}

        elif detector_type == "iqr":
            q1 = float(np.percentile(window_data, 25))
            q3 = float(np.percentile(window_data, 75))
            iqr = q3 - q1
            if iqr > 0:
                window_scores = []
                for v in window_data:
                    if v < q1:
                        window_scores.append(float((q1 - v) / iqr))
                    elif v > q3:
                        window_scores.append(float((v - q3) / iqr))
                    else:
                        window_scores.append(0.0)
            else:
                window_scores = [0.0] * len(window_data)
            params = {"q1": q1, "q3": q3, "iqr": iqr, "window_scores": window_scores, "window": window}
        else:
            params = {}

        return FittedModel(
            detector_type=detector_type,
            model_bytes=pickle.dumps(params),
            metadata={"n_samples": len(values), "window": window},
        )

    def _score_statistical(self, fitted: FittedModel, values: np.ndarray) -> DetectionResult:
        params: dict[str, Any] = pickle.loads(fitted.model_bytes)  # noqa: S301
        current_value = float(values[-1])

        if fitted.detector_type == "zscore":
            mean = params["mean"]
            std = params["std"]
            if std == 0:
                is_anomaly = abs(current_value - mean) > 0
                return DetectionResult(is_anomaly=is_anomaly, score=1.0 if is_anomaly else 0.0)

            z_score = abs((current_value - mean) / std)
            window_zscores = np.array(params["window_zscores"])
            prob = _zscore_to_probability(z_score, window_zscores)

        elif fitted.detector_type == "mad":
            median = params["median"]
            mad_val = params["mad"]
            if mad_val == 0:
                is_anomaly = abs(current_value - median) > 0
                return DetectionResult(is_anomaly=is_anomaly, score=1.0 if is_anomaly else 0.0)

            score_raw = abs(current_value - median) / (mad_val * 1.4826)
            window_scores = np.array(params["window_scores"])
            prob = _unify_score(score_raw, window_scores)

        elif fitted.detector_type == "iqr":
            q1, q3, iqr = params["q1"], params["q3"], params["iqr"]
            if iqr == 0:
                is_anomaly = current_value < q1 or current_value > q3
                return DetectionResult(is_anomaly=is_anomaly, score=1.0 if is_anomaly else 0.0)

            if current_value < q1:
                score_raw = (q1 - current_value) / iqr
            elif current_value > q3:
                score_raw = (current_value - q3) / iqr
            else:
                score_raw = 0.0
            window_scores = np.array(params["window_scores"])
            prob = _unify_score(score_raw, window_scores)
        else:
            return DetectionResult(is_anomaly=False)

        return DetectionResult(
            is_anomaly=prob > fitted.threshold,
            score=prob,
            triggered_indices=[len(values) - 1] if prob > fitted.threshold else [],
            all_scores=[prob],
        )

    # -- Helpers --

    def _find_sub_config(self, detector_type: str) -> dict[str, Any]:
        for cfg in self.sub_configs:
            if cfg.get("type") == detector_type:
                return cfg
        return {"type": detector_type}

    def _combine_results(self, results: list[DetectionResult]) -> DetectionResult:
        if not results:
            return DetectionResult(is_anomaly=False)

        if self.operator == "and":
            is_anomaly = all(r.is_anomaly for r in results)
            score = min((r.score for r in results if r.score is not None), default=None)
        else:  # or
            is_anomaly = any(r.is_anomaly for r in results)
            score = max((r.score for r in results if r.score is not None), default=None)

        triggered = []
        if is_anomaly:
            all_triggered = [set(r.triggered_indices) for r in results if r.triggered_indices]
            if all_triggered:
                if self.operator == "and":
                    triggered = sorted(set.intersection(*all_triggered))
                else:
                    triggered = sorted(set.union(*all_triggered))

        return DetectionResult(
            is_anomaly=is_anomaly,
            score=score,
            triggered_indices=triggered,
            all_scores=[score] if score is not None else [],
            metadata={
                "operator": self.operator,
                "sub_results": [
                    {"type": r.metadata.get("type", "unknown") if r.metadata else "unknown", "score": r.score}
                    for r in results
                ],
            },
        )


def _zscore_to_probability(z_score: float, window_zscores: np.ndarray) -> float:
    """Normalize z-score using pyod's 'unify' approach."""
    mean_z = float(window_zscores.mean())
    std_z = float(window_zscores.std())
    if std_z == 0:
        return 1.0 if z_score > mean_z else 0.0
    standardized = (z_score - mean_z) / std_z
    return float(np.clip(erf(standardized / np.sqrt(2)), 0.0, 1.0))


def _unify_score(raw_score: float, window_scores: np.ndarray) -> float:
    """Normalize a raw score against training window distribution using erf."""
    if len(window_scores) == 0:
        return 0.0
    mean_s = float(window_scores.mean())
    std_s = float(window_scores.std())
    if std_s == 0:
        return 1.0 if raw_score > mean_s else 0.0
    standardized = (raw_score - mean_s) / std_s
    return float(np.clip(erf(standardized / np.sqrt(2)), 0.0, 1.0))
