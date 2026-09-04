"""
Genuine SHAP explanation layer for the Razorpay Serving Model.
Explains the underlying XGBoost model's raw output (log-odds/margin space).
Does NOT perform calibration, thresholding, or any decision making.
Does NOT load test.csv.
Does NOT touch Model C.
"""
import json
import logging
import math
import os
import time
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd
import shap

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_CALIBRATED_ARTIFACT_PATH = "data/razorpay_serving_model_calibrated.joblib"
_CONTRACT_PATH = "data/razorpay_serving_feature_contract.json"


class ServingSHAPExplainer:
    """
    Genuine per-transaction SHAP explainer for the frozen Razorpay Serving Model.

    Architecture:
        features → XGBoost → SHAP → explanation   (read-only)
        features → XGBoost → calibration → policy → decision (unchanged)

    A SHAP failure NEVER modifies risk or decision.
    """

    def __init__(self, artifact_path: str = _CALIBRATED_ARTIFACT_PATH):
        if not os.path.exists(artifact_path):
            raise FileNotFoundError(f"Missing serving artifact: {artifact_path}")

        artifact = joblib.load(artifact_path)
        pipeline = artifact["frozen_model_artifact"]
        self.preprocessor = pipeline.named_steps["preprocessor"]   # ColumnTransformer
        self.xgb_model = pipeline.named_steps["classifier"]          # XGBClassifier
        self.features = artifact["metadata"]["features"]             # 15 original names

        # Transformed feature names (after OHE / scaling)
        self.transformed_names: List[str] = list(
            self.preprocessor.get_feature_names_out()
        )

        # Map every transformed name → original source feature
        self._name_map: Dict[str, str] = {}
        for t_name in self.transformed_names:
            if t_name.startswith("num__"):
                self._name_map[t_name] = t_name[5:]   # strip "num__"
            elif t_name.startswith("cat__"):
                # "cat__<feature>_<category>" — find longest-matching original feature
                inner = t_name[5:]   # strip "cat__"
                matched = None
                for orig in self.features:
                    if inner.startswith(orig + "_") or inner == orig:
                        if matched is None or len(orig) > len(matched):
                            matched = orig
                self._name_map[t_name] = matched if matched else inner
            else:
                self._name_map[t_name] = t_name

        # shap.TreeExplainer on the raw XGBoost model
        # output_type defaults to "raw" (log-odds margin) for binary XGBoost
        self.explainer = shap.TreeExplainer(self.xgb_model)

    # ─────────────────────────────────────────────────────────────────────────

    def _make_unavailable(self, reason: str) -> Dict[str, Any]:
        return {
            "status": "UNAVAILABLE",
            "model_track": "RAZORPAY_SERVING_MODEL",
            "reason": reason,
        }

    # ─────────────────────────────────────────────────────────────────────────

    def explain(
        self,
        X: pd.DataFrame,
        top_positive_k: int = 5,
        top_negative_k: int = 3,
    ) -> Dict[str, Any]:
        """
        Explain a single transaction.

        X must contain exactly the 15 contract features.
        No target label (isFraud) must be present.
        Does NOT modify calibrated risk or decision.
        """
        try:
            # Guard: reject target / rejected columns
            for banned in ("isFraud", "TransactionID", "TransactionDT"):
                if banned in X.columns:
                    return self._make_unavailable(
                        f"Rejected column present: {banned}"
                    )

            # Guard: exactly 1 row
            if len(X) != 1:
                return self._make_unavailable(
                    "Explainer supports single-transaction input only"
                )

            # Guard: all 15 features present
            missing = [f for f in self.features if f not in X.columns]
            if missing:
                return self._make_unavailable(f"Missing features: {missing}")

            X_in = X[self.features].copy()

            # Preprocess with FROZEN transformer (no fitting)
            try:
                X_trans = self.preprocessor.transform(X_in)
            except Exception as e:
                return self._make_unavailable(f"Preprocessing error: {e}")

            # Compute SHAP values (raw margin / log-odds space)
            shap_expl = self.explainer(X_trans)
            raw_shap: np.ndarray = shap_expl.values[0]       # shape: (n_transformed_features,)
            base_value: float = float(shap_expl.base_values[0])
            model_output: float = float(base_value + raw_shap.sum())

            # Aggregate per original source feature
            agg: Dict[str, float] = {f: 0.0 for f in self.features}
            for i, t_name in enumerate(self.transformed_names):
                orig = self._name_map.get(t_name, t_name)
                if orig in agg:
                    agg[orig] += float(raw_shap[i])

            # Build explanation items
            items = []
            row = X_in.iloc[0]
            for feat in self.features:
                sv = agg[feat]
                if abs(sv) < 1e-9:
                    continue
                raw_val = row[feat]
                if isinstance(raw_val, float) and math.isnan(raw_val):
                    raw_val = "MISSING"
                elif isinstance(raw_val, (np.integer,)):
                    raw_val = int(raw_val)
                elif isinstance(raw_val, (np.floating,)):
                    raw_val = float(raw_val)
                items.append(
                    {
                        "feature": feat,
                        "value": raw_val,
                        "shap_value": round(sv, 6),
                        "direction": (
                            "INCREASES_MODEL_SCORE" if sv > 0 else "DECREASES_MODEL_SCORE"
                        ),
                    }
                )

            # Sort by |shap_value| descending
            items.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
            positives = [e for e in items if e["direction"] == "INCREASES_MODEL_SCORE"]
            negatives = [e for e in items if e["direction"] == "DECREASES_MODEL_SCORE"]

            return {
                "status": "AVAILABLE",
                "model_track": "RAZORPAY_SERVING_MODEL",
                "explained_output": "UNCALIBRATED_XGBOOST_MARGIN",
                "base_value": round(base_value, 6),
                "model_output": round(model_output, 6),
                "top_positive": positives[:top_positive_k],
                "top_negative": negatives[:top_negative_k],
            }

        except Exception as e:
            logger.error(f"SHAP explanation failed: {e}")
            return self._make_unavailable(f"Internal SHAP error: {e}")

    # ─────────────────────────────────────────────────────────────────────────

    def check_additivity(self, X: pd.DataFrame, tol: float = 1e-4) -> Dict[str, Any]:
        """
        Verify SHAP additivity: base_value + Σ(shap_values) ≈ model_output.
        Uses raw SHAP values before per-feature aggregation to be precise.
        """
        if len(X) != 1 or any(f not in X.columns for f in self.features):
            return {"passed": False, "reason": "Invalid input"}

        X_trans = self.preprocessor.transform(X[self.features])
        shap_expl = self.explainer(X_trans)
        raw_shap = shap_expl.values[0]
        base_val = float(shap_expl.base_values[0])
        shap_sum = float(base_val + raw_shap.sum())

        # XGBoost raw output for verification
        xgb_raw = float(np.float64(self.xgb_model.predict(X_trans, output_margin=True)[0]))
        delta = abs(shap_sum - xgb_raw)

        return {
            "passed": bool(delta < tol),
            "base_value": float(base_val),
            "shap_sum": float(round(float(raw_shap.sum()), 6)),
            "reconstructed": float(round(shap_sum, 6)),
            "xgb_raw_margin": float(round(xgb_raw, 6)),
            "delta": float(round(delta, 8)),
            "tolerance": float(tol),
        }

    # ─────────────────────────────────────────────────────────────────────────

    def benchmark_latency(self, X: pd.DataFrame, n_runs: int = 25) -> Dict[str, float]:
        """
        Measure per-transaction explanation latency (ms).
        Warmup excluded from measurements.
        """
        for _ in range(5):
            self.explain(X)   # warmup

        times = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            self.explain(X)
            times.append((time.perf_counter() - t0) * 1000)

        return {
            "n_runs": n_runs,
            "median_ms": round(float(np.median(times)), 2),
            "p95_ms": round(float(np.percentile(times, 95)), 2),
            "min_ms": round(float(np.min(times)), 2),
            "max_ms": round(float(np.max(times)), 2),
        }


# ── Deterministic fixture ──────────────────────────────────────────────────────

def make_fixture() -> pd.DataFrame:
    """Create a deterministic synthetic transaction fixture (not from test.csv)."""
    return pd.DataFrame([{
        "amount": 150.0,
        "log_amount": math.log1p(150.0),
        "hour_of_day": 14,
        "day_of_week": 3,
        "email_domain": "gmail.com",
        "email_domain_missing": 0,
        "card_network": "visa",
        "card_type": "credit",
        "previous_transaction_count": 5,
        "is_new_customer": 0,
        "avg_customer_amount": 100.0,
        "amount_deviation": 50.0,
        "amount_ratio": 1.5,
        "txns_last_1h": 1,
        "txns_last_24h": 3,
    }])


if __name__ == "__main__":
    explainer = ServingSHAPExplainer()
    fixture = make_fixture()

    result = explainer.explain(fixture)
    print(json.dumps(result, indent=2))

    additivity = explainer.check_additivity(fixture)
    print("\nAdditivity check:", json.dumps(additivity, indent=2))

    latency = explainer.benchmark_latency(fixture, n_runs=25)
    print(f"\nLatency: median {latency['median_ms']:.2f}ms  p95 {latency['p95_ms']:.2f}ms")
