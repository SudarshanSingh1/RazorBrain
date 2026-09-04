"""
Loader for the calibrated Razorpay Serving Model artifact.
Provides deterministic inference: raw XGBoost score → calibrated probability.
Never performs silent retraining or silent calibration on load.
"""
import json
import os

import joblib
import numpy as np
import pandas as pd

_CALIBRATED_ARTIFACT_PATH = "data/razorpay_serving_model_calibrated.joblib"
_CONTRACT_PATH = "data/razorpay_serving_feature_contract.json"
_UNCALIBRATED_ARTIFACT_PATH = "data/razorpay_serving_model_uncalibrated.joblib"

# Must never accidentally load Model C.
_FORBIDDEN_PATHS = {
    "data/model_c_calibrated.joblib",
    "data/model_c_engineered_raw_safe.joblib",
}


def _load_contract() -> list:
    if not os.path.exists(_CONTRACT_PATH):
        raise FileNotFoundError(f"Feature contract missing: {_CONTRACT_PATH}")
    with open(_CONTRACT_PATH) as f:
        c = json.load(f)
    return [feat["name"] for feat in c["features"]]


class ServingModelLoader:
    """
    Deterministic loader for the calibrated Razorpay Serving Model.
    Validates feature contract on load; raises clearly on any mismatch.
    """

    def __init__(self, artifact_path: str = _CALIBRATED_ARTIFACT_PATH):
        if artifact_path in _FORBIDDEN_PATHS:
            raise ValueError(
                f"Attempted to load a Model C artifact via ServingModelLoader: {artifact_path}"
            )
        if not os.path.exists(artifact_path):
            raise FileNotFoundError(
                f"Calibrated serving model artifact not found: {artifact_path}. "
                "Run model/calibrate_serving_model.py first."
            )

        artifact = joblib.load(artifact_path)

        required_keys = {"frozen_model_artifact", "calibrator", "calibrator_type", "metadata"}
        missing = required_keys - set(artifact.keys())
        if missing:
            raise ValueError(f"Malformed artifact — missing keys: {missing}")

        contract_features = _load_contract()
        artifact_features = artifact["metadata"].get("features", [])
        if artifact_features != contract_features:
            raise ValueError(
                f"Feature contract mismatch.\n"
                f"  Artifact:  {artifact_features}\n"
                f"  Contract:  {contract_features}"
            )

        self._pipeline = artifact["frozen_model_artifact"]
        self._calibrator = artifact["calibrator"]
        self._calibrator_type = artifact["calibrator_type"]
        self._features = artifact_features
        self.metadata = artifact["metadata"]

    @property
    def features(self) -> list:
        return list(self._features)

    def predict_calibrated_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Return calibrated risk estimates for each row in X.
        X must contain exactly the 15 contract features.
        Labels (isFraud) must NOT be included.
        """
        missing = [f for f in self._features if f not in X.columns]
        if missing:
            raise ValueError(f"Input DataFrame missing features: {missing}")

        raw_scores = self._pipeline.predict_proba(X[self._features])[:, 1]

        if self._calibrator_type == "platt":
            return self._calibrator.predict_proba(raw_scores.reshape(-1, 1))[:, 1]
        elif self._calibrator_type == "isotonic":
            return np.clip(self._calibrator.predict(raw_scores), 1e-7, 1 - 1e-7)
        else:
            raise ValueError(f"Unknown calibrator type: {self._calibrator_type}")
