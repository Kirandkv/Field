"""Per-device Isolation Forest anomaly detection over a single-metric telemetry stream.

Real scikit-learn IsolationForest, fit per device on that device's own baseline
history — not a stub, not a hardcoded score. See ADR 0002 decision 5 for why model
fitting stays in-memory for this slice (no registry/versioning yet — that's an Ops
milestone concern).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest


@dataclass
class AnomalyResult:
    device_id: str
    value: float
    is_anomaly: bool
    anomaly_score: float  # scikit-learn decision_function output: lower = more anomalous
    training_samples: int


class DeviceAnomalyDetector:
    def __init__(self, contamination: float | str = "auto", random_state: int = 42) -> None:
        self._contamination = contamination
        self._random_state = random_state
        self._models: dict[str, IsolationForest] = {}
        self._sample_counts: dict[str, int] = {}

    def fit(self, device_id: str, historical_values: list[float]) -> None:
        if len(historical_values) < 10:
            raise ValueError(
                f"need at least 10 historical readings to fit an anomaly model for "
                f"{device_id!r}, got {len(historical_values)}"
            )
        model = IsolationForest(contamination=self._contamination, random_state=self._random_state)
        x = np.array(historical_values, dtype=float).reshape(-1, 1)
        model.fit(x)
        self._models[device_id] = model
        self._sample_counts[device_id] = len(historical_values)

    def score(self, device_id: str, value: float) -> AnomalyResult:
        model = self._models.get(device_id)
        if model is None:
            raise ValueError(f"no fitted anomaly model for device {device_id!r}; call fit() first")
        x = np.array([[value]], dtype=float)
        prediction = int(model.predict(x)[0])  # -1 = anomaly, 1 = normal
        score = float(model.decision_function(x)[0])
        return AnomalyResult(
            device_id=device_id,
            value=value,
            is_anomaly=prediction == -1,
            anomaly_score=score,
            training_samples=self._sample_counts[device_id],
        )
