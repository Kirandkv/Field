import pytest
from fieldforge_anomaly import DeviceAnomalyDetector


def test_fit_requires_minimum_history():
    detector = DeviceAnomalyDetector()
    with pytest.raises(ValueError, match="at least 10"):
        detector.fit("dev-1", [1.0, 2.0, 3.0])


def test_score_without_fit_raises():
    detector = DeviceAnomalyDetector()
    with pytest.raises(ValueError, match="no fitted anomaly model"):
        detector.score("dev-1", 5.0)


def test_normal_reading_scores_as_not_anomalous():
    detector = DeviceAnomalyDetector()
    baseline = [10.0, 9.5, 10.2, 9.8, 10.1, 9.9, 10.3, 9.7, 10.0, 9.6, 10.4, 9.9]
    detector.fit("dev-1", baseline)
    result = detector.score("dev-1", 10.0)
    assert result.is_anomaly is False
    assert result.training_samples == len(baseline)


def test_extreme_reading_scores_as_anomalous():
    detector = DeviceAnomalyDetector()
    baseline = [10.0, 9.5, 10.2, 9.8, 10.1, 9.9, 10.3, 9.7, 10.0, 9.6, 10.4, 9.9]
    detector.fit("dev-1", baseline)
    result = detector.score("dev-1", 5000.0)
    assert result.is_anomaly is True


def test_models_are_independent_per_device():
    detector = DeviceAnomalyDetector()
    detector.fit("dev-1", [10.0] * 12)
    with pytest.raises(ValueError):
        detector.score("dev-2", 10.0)
