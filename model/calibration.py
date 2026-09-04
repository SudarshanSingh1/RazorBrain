"""
Calibration evaluation for RazorBrain fraud models.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss

logger = logging.getLogger(__name__)

def fit_calibration(
    model_artifact: dict[str, Any], 
    X_calib: pd.DataFrame, 
    y_calib: pd.Series, 
    method: str = "none"
) -> dict[str, Any]:
    if method == "none":
        return {
            "calibrator": None,
            "method": method,
            "feature_names": model_artifact["feature_names"],
            "base_model_artifact": model_artifact
        }
    if method != "isotonic":
        raise ValueError("Only 'isotonic' or 'none' is currently supported in this direct implementation.")

        
    base_model = model_artifact["model"]
    scaler = model_artifact.get("scaler")
    
    # Get raw predictions from the base model
    X_calib_proc = scaler.transform(X_calib) if scaler else X_calib
    y_prob_raw = base_model.predict_proba(X_calib_proc)[:, 1]
    
    calibrator = IsotonicRegression(out_of_bounds='clip')
    calibrator.fit(y_prob_raw, y_calib)
    
    return {
        "calibrator": calibrator,
        "method": method,
        "feature_names": model_artifact["feature_names"],
        "base_model_artifact": model_artifact
    }


def predict_calibrated_proba(calibration_artifact: dict[str, Any], X: pd.DataFrame) -> np.ndarray:
    if list(X.columns) != calibration_artifact["feature_names"]:
        raise ValueError("Feature columns do not match the expected training order.")
        
    calibrator = calibration_artifact["calibrator"]
    base_model_artifact = calibration_artifact["base_model_artifact"]
    
    from model.baseline import predict_proba as get_raw_proba
    y_prob_raw = get_raw_proba(base_model_artifact, X)
    
    if calibrator is None:
        return y_prob_raw
    
    return calibrator.predict(y_prob_raw)


def evaluate_calibration(
    y_true: pd.Series, 
    y_prob_raw: np.ndarray, 
    y_prob_calib: np.ndarray | None = None,
    n_bins: int = 10
) -> dict[str, Any]:
    """
    Evaluate calibration metrics including Brier score, Log Loss, and Expected Calibration Error (ECE).
    Returns metrics for raw and (if provided) calibrated probabilities.
    """
    metrics = {}
    
    # Raw metrics
    metrics["raw_brier"] = float(brier_score_loss(y_true, y_prob_raw))
    metrics["raw_log_loss"] = float(log_loss(y_true, y_prob_raw))
    metrics["raw_ece"], metrics["raw_curve"] = _compute_ece_and_curve(y_true, y_prob_raw, n_bins)
    
    # Calibrated metrics
    if y_prob_calib is not None:
        metrics["calib_brier"] = float(brier_score_loss(y_true, y_prob_calib))
        metrics["calib_log_loss"] = float(log_loss(y_true, y_prob_calib))
        metrics["calib_ece"], metrics["calib_curve"] = _compute_ece_and_curve(y_true, y_prob_calib, n_bins)
        
    return metrics


def _compute_ece_and_curve(y_true: pd.Series, y_prob: np.ndarray, n_bins: int) -> tuple[float, list[dict]]:
    """
    Compute Expected Calibration Error (ECE) and the empirical calibration curve bins.
    Uses uniform binning [0, 1].
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    binned = np.digitize(y_prob, bins) - 1
    
    ece = 0.0
    total_samples = len(y_true)
    curve = []
    
    for i in range(n_bins):
        bin_idx = (binned == i) | ((y_prob == 1.0) & (i == n_bins - 1))
        bin_true = y_true[bin_idx]
        bin_prob = y_prob[bin_idx]
        
        count = len(bin_true)
        if count > 0:
            fraction_pos = float(bin_true.mean())
            mean_prob = float(bin_prob.mean())
            weight = count / total_samples
            ece += weight * abs(fraction_pos - mean_prob)
            
            curve.append({
                "bin": i,
                "mean_pred_prob": mean_prob,
                "fraction_positives": fraction_pos,
                "sample_count": count
            })
        else:
            curve.append({
                "bin": i,
                "mean_pred_prob": None,
                "fraction_positives": None,
                "sample_count": 0
            })
            
    return float(ece), curve
